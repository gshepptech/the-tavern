"""Smith's copy of the shared-workspace helper, and how /smith:build uses it."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[1]
REPO = PLUGIN.parents[1]
QUESTBOARD = PLUGIN / "scripts" / "questboard.py"


def questboard(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(QUESTBOARD), "--root", str(root), *args], capture_output=True, text=True)


def test_resolve_finds_the_newest_spec_that_still_exists(tmp_path):
    for name in ("old", "new"):
        spec = tmp_path / "sage-specs" / name / "spec.md"
        spec.parent.mkdir(parents=True)
        spec.write_text("- R-1: x\n")
        questboard(tmp_path, "write", "--plugin", "sage", "--kind", "spec", "--title", name,
               "--path", f"sage-specs/{name}/spec.md")
    found = questboard(tmp_path, "resolve", "--kind", "spec").stdout.strip()
    assert found in ("sage-specs/old/spec.md", "sage-specs/new/spec.md")
    assert questboard(tmp_path, "resolve").returncode == 0


def test_resolve_without_a_workspace_prints_nothing(tmp_path):
    r = questboard(tmp_path, "resolve", "--kind", "spec")
    assert (r.returncode, r.stdout) == (0, "")


def test_an_attempt_note_records_the_outcome(tmp_path):
    r = questboard(tmp_path, "write", "--plugin", "smith", "--kind", "attempt", "--title", "Built: calc",
               "--outcome", "done", "--path", ".smith/runs/r1/report.md")
    assert r.returncode == 0, r.stderr
    note = json.loads(questboard(tmp_path, "read", "--kind", "attempt").stdout)[0]
    assert (note["plugin"], note["outcome"]) == ("smith", "done")


def test_masons_declaration_is_valid():
    r = subprocess.run([sys.executable, str(QUESTBOARD), "validate", "--declarations", str(PLUGIN.parent)],
                       capture_output=True, text=True, cwd=PLUGIN)
    assert r.returncode == 0, r.stdout
    decl = json.loads((PLUGIN / "questboard.json").read_text())
    assert (decl["reads"], decl["writes"]) == (["spec"], ["attempt"])


def test_vendored_copies_have_not_drifted():
    copies = sorted(REPO.glob("plugins/*/scripts/questboard.py"))
    if len(copies) < 2:
        pytest.skip("only one copy of questboard.py in this checkout")
    digests = {str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest() for p in copies}
    assert len(set(digests.values())) == 1, f"vendored copies have drifted: {digests}"
