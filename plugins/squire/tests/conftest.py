"""Shared fixtures: a small git project with a Makefile test target, and a helper
that runs squire's CLI in-process and returns its JSON line."""

from __future__ import annotations

import io
import json
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "scripts"))

import squire  # noqa: E402

SPEC = """---
title: calculator
---

# Calculator

### R-001: Add

`add(a, b)` MUST return the sum of a and b.

Source: A-001

Acceptance:
- `add(2, 3)` returns 5.
- `add(-1, 1)` returns 0.

### R-002: Subtract

`sub(a, b)` MUST return a minus b.

Acceptance:
- `sub(5, 3)` returns 2.
"""

CALC = "def add(a, b):\n    return a + b\n"
TEST = "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"
MAKEFILE = "test:\n\tpython3 -c \"import calc; assert calc.add(2, 3) == 5\"\n"


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout.strip()


def write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def commit(root: Path, msg: str, *paths: str) -> None:
    git(root, "add", "--", *paths)
    git(root, "commit", "-q", "-m", msg)


@pytest.fixture
def repo(tmp_path) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    git(root, "config", "commit.gpgsign", "false")
    files = {"spec.md": SPEC, "calc.py": CALC, "tests/test_calc.py": TEST, "Makefile": MAKEFILE,
             ".gitignore": "__pycache__/\n"}
    for rel, text in files.items():
        write(root, rel, text)
    commit(root, "base", *files)
    return root


def j(root: Path, *args: str) -> dict:
    buf = io.StringIO()
    with redirect_stdout(buf):
        squire.main(["--root", str(root), *args])
    return json.loads(buf.getvalue().strip().splitlines()[-1])


@pytest.fixture
def run(repo):
    """An initialised run on the fixture project: (root, run name, run dir)."""
    r = j(repo, "init", "--spec", "spec.md", "--run", "t1")
    assert r["ok"], r
    return repo, "t1", Path(r["run_dir"])
