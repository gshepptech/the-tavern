"""questboard.py, the shared-workspace helper Sage uses to announce a sealed spec.

These are the semantics every vendored copy shares (see docs/questboard-contract.md):
an absent or damaged workspace reads as empty, a write never fails its caller,
and `resolve` only hands back a path that still exists.
"""

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
    return subprocess.run([sys.executable, str(QUESTBOARD), "--root", str(root), *args],
                          capture_output=True, text=True)


def write_spec_note(root: Path, path: str = "sage-specs/x/spec.md") -> subprocess.CompletedProcess:
    return questboard(root, "write", "--plugin", "sage", "--kind", "spec", "--title", "Spec sealed: x", "--path", path)


def test_reading_an_absent_workspace_is_empty_and_creates_nothing(tmp_path):
    r = questboard(tmp_path, "read")
    assert (r.returncode, json.loads(r.stdout)) == (0, [])
    assert not (tmp_path / ".questboard").exists()


def test_a_written_note_reads_back(tmp_path):
    assert write_spec_note(tmp_path).returncode == 0
    notes = json.loads(questboard(tmp_path, "read", "--kind", "spec").stdout)
    assert len(notes) == 1
    note = notes[0]
    assert (note["questboard"], note["kind"], note["plugin"], note["paths"]) == (1, "spec", "sage",
                                                                             ["sage-specs/x/spec.md"])
    assert (tmp_path / ".questboard" / "notes" / f"{note['id']}.json").is_file()


def test_malformed_notes_are_skipped_not_repaired(tmp_path):
    write_spec_note(tmp_path)
    notes = tmp_path / ".questboard" / "notes"
    (notes / "20990101T000000Z-x-0000.json").write_text("{not json")
    (notes / "20990101T000001Z-x-0001.json").write_text(json.dumps({"questboard": 1, "kind": "spec"}))
    assert len(json.loads(questboard(tmp_path, "read").stdout)) == 1
    assert (notes / "20990101T000000Z-x-0000.json").read_text() == "{not json"
    assert questboard(tmp_path, "validate").returncode == 1


def test_resolve_skips_a_spec_that_no_longer_exists(tmp_path):
    spec = tmp_path / "sage-specs" / "x" / "spec.md"
    spec.parent.mkdir(parents=True)
    spec.write_text("x")
    write_spec_note(tmp_path)
    assert questboard(tmp_path, "resolve").stdout.strip() == "sage-specs/x/spec.md"
    spec.unlink()
    r = questboard(tmp_path, "resolve")
    assert (r.returncode, r.stdout) == (0, "")


def test_a_failed_write_does_not_fail_the_caller(tmp_path):
    (tmp_path / ".questboard").write_text("a file where the directory should be")
    r = write_spec_note(tmp_path)
    assert r.returncode == 0 and "continuing" in r.stderr


def test_an_attempt_needs_an_outcome(tmp_path):
    r = questboard(tmp_path, "write", "--plugin", "sage", "--kind", "attempt", "--title", "t")
    assert r.returncode == 0 and "refusing" in r.stderr
    assert not (tmp_path / ".questboard" / "notes").exists()


def test_drews_declaration_is_valid():
    r = subprocess.run([sys.executable, str(QUESTBOARD), "validate", "--declarations", str(PLUGIN.parent)],
                       capture_output=True, text=True, cwd=PLUGIN)
    assert r.returncode == 0, r.stdout
    assert json.loads((PLUGIN / "questboard.json").read_text())["writes"] == ["spec"]


def test_vendored_copies_have_not_drifted():
    copies = sorted(REPO.glob("plugins/*/scripts/questboard.py"))
    if len(copies) < 2:
        pytest.skip("only one copy of questboard.py in this checkout")
    digests = {str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest() for p in copies}
    assert len(set(digests.values())) == 1, f"vendored copies have drifted: {digests}"
