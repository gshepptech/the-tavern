"""Pytest fixtures for plugins/ranger tests.

Run in an isolated, ephemeral environment (the project is PEP 668-managed — do
NOT pip-install pytest globally):

    uvx pytest plugins/ranger/tests/

The hook is exercised as a subprocess, exactly as Claude Code invokes it:
a JSON event on stdin, behaviour expressed through exit code and stdout. This
tests the real contract, not an imported approximation.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _run(script: str, event: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
    )


@pytest.fixture
def project(tmp_path):
    """A tmp dir that can be armed with a Ranger run state.

    Returns a helper object with:
      .path                     the project dir
      .arm(state, run_id='r1')  write active-run.json + runs/<id>/state.json
      .disarm()                 write an empty {} marker
    """

    class _Project:
        def __init__(self, root: Path):
            self.path = root
            (root / ".ranger").mkdir(parents=True, exist_ok=True)

        def arm(self, state: dict, run_id: str = "r1"):
            run_dir = self.path / ".ranger" / "runs" / run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "state.json").write_text(json.dumps(state))
            (self.path / ".ranger" / "active-run.json").write_text(
                json.dumps({"run_id": run_id, "run_dir": f".ranger/runs/{run_id}"})
            )
            return self

        def arm_raw(self, marker_text: str, state_text: str | None = None, run_id: str = "r1"):
            if state_text is not None:
                run_dir = self.path / ".ranger" / "runs" / run_id
                run_dir.mkdir(parents=True, exist_ok=True)
                (run_dir / "state.json").write_text(state_text)
            (self.path / ".ranger" / "active-run.json").write_text(marker_text)
            return self

        def disarm(self):
            (self.path / ".ranger" / "active-run.json").write_text("{}")
            return self

    return _Project(tmp_path)


@pytest.fixture
def guard(project):
    """Return a function: cmd -> 'deny' | 'allow' for the git guard."""

    def _verdict(command: str, *, session_id: str = "S1"):
        cp = _run(
            "guard-git.py",
            {
                "cwd": str(project.path),
                "session_id": session_id,
                "tool_name": "Bash",
                "tool_input": {"command": command},
            },
        )
        return "deny" if cp.returncode == 2 else "allow"

    def _reason(command: str, *, session_id: str = "S1") -> str:
        """The text of a denial, so tests can assert the user is told what to do."""
        cp = _run(
            "guard-git.py",
            {
                "cwd": str(project.path),
                "session_id": session_id,
                "tool_name": "Bash",
                "tool_input": {"command": command},
            },
        )
        return cp.stderr

    _verdict.project = project
    _verdict.reason = _reason
    return _verdict
