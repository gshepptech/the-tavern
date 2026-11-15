"""ledger.py: parsing a spec, checking a plan, and the evidence rule for done."""

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

import ledger  # noqa: E402

SPEC = """---
title: Calculator
status: draft
---

# Calculator

## Requirements

### R-001: Add

`add(a, b)` MUST return a + b.

Source: A-001

Acceptance:
- `add(2, 3)` returns 5.
- `add(-1, 1)` returns 0.

### R-002: Divide

`div(a, b)` MUST raise `ZeroDivisionError` when b is 0.

Acceptance:
- `div(1, 0)` raises ZeroDivisionError.

### R-003: CLI

The `calc` command MUST print the result of `calc add 2 3` as `5`.

Acceptance:
- `calc add 2 3` prints `5` and exits 0.

## Non-goals

- No floating-point formatting options.

## Appendix: Interview Transcript

### A-001

**Q:** Integers only? **A:** Yes.
"""


def call(root: Path, *args: str) -> tuple[int, dict]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = ledger.main(["--root", str(root), *args])
    return code, json.loads(buf.getvalue())


def ok(root: Path, *args: str) -> dict:
    code, out = call(root, *args)
    assert code == 0, out
    return out


def refused(root: Path, *args: str) -> str:
    code, out = call(root, *args)
    assert code == 1 and not out["ok"], out
    return out["refused"]


PLAN = {"slices": [
    {"id": "S1", "title": "core", "requirements": ["R-001", "R-002"], "files": ["calc/core.py", "tests/test_core.py"]},
    {"id": "S2", "title": "cli", "requirements": ["R-003"], "files": ["calc/cli/"], "depends_on": ["S1"]},
]}


@pytest.fixture
def root(tmp_path) -> Path:
    (tmp_path / "spec.md").write_text(SPEC)
    ok(tmp_path, "init", str(tmp_path / "spec.md"), "--name", "r1", "--max-rounds", "2")
    return tmp_path


@pytest.fixture
def planned(root) -> Path:
    (root / "plan.json").write_text(json.dumps(PLAN))
    ok(root, "plan", "--file", str(root / "plan.json"))
    return root


def plan_with(root: Path, plan: dict) -> str:
    (root / "plan.json").write_text(json.dumps(plan))
    return refused(root, "plan", "--file", str(root / "plan.json"))


def build_all(root: Path) -> None:
    for sid in ("S1", "S2"):
        ok(root, "slice", sid, "--status", "built")


def pass_(root: Path, rid: str) -> dict:
    return ok(root, "record", rid, "--verdict", "pass", "--command", "pytest -q tests", "--output", "3 passed",
              "--exit", "0", "--location", "calc/core.py:3")


# --- parsing -------------------------------------------------------------------


def test_parses_sage_style_requirements_and_criteria():
    reqs = {r["id"]: r for r in ledger.parse_requirements(SPEC)}
    assert list(reqs) == ["R-001", "R-002", "R-003"]
    assert reqs["R-001"]["criteria"] == ["`add(2, 3)` returns 5.", "`add(-1, 1)` returns 0."]
    assert reqs["R-001"]["text"].startswith("Add\n`add(a, b)` MUST")


@pytest.mark.parametrize(
    "spec, expected",
    [
        ("- **FR-1**: add numbers\n  - 2 + 3 is 5\n  - AC-1: 0 + 0 is 0\n- FR-2: subtract\n",
         {"FR-1": ["2 + 3 is 5", "AC-1: 0 + 0 is 0"], "FR-2": []}),
        ("| ID | Requirement |\n|---|---|\n| REQ-1 | logs in | \n| REQ-2 | logs out |\n",
         {"REQ-1": [], "REQ-2": []}),
        ("US-1: a user can sign in.\n\nUS-2. a user can sign out.\n", {"US-1": [], "US-2": []}),
        ("## FR-10 Export\n\n**Acceptance criteria:**\n\n1. a file is written\n\n## Notes\n\n- see FR-10\n",
         {"FR-10": ["a file is written"]}),
        ("```\n- R-9: inside a fence\n```\n- R-1: outside\n", {"R-1": []}),
    ],
)
def test_parses_other_spec_styles(spec, expected):
    assert {r["id"]: r["criteria"] for r in ledger.parse_requirements(spec)} == expected


def test_appendix_entries_are_not_requirements():
    ids = [r["id"] for r in ledger.parse_requirements(SPEC)]
    assert "A-001" not in ids


# --- init ----------------------------------------------------------------------


def test_init_freezes_the_spec_and_ignores_itself(root):
    d = root / ".smith" / "runs" / "r1"
    assert (d / "spec.md").read_text() == SPEC
    assert (root / ".smith" / ".gitignore").read_text() == "*\n"
    st = ok(root, "status")
    assert st["counts"]["pending"] == 3 and st["next"] == {"action": "plan"} and not st["sealed"]


def test_init_refuses_a_spec_without_ids_or_with_duplicates(tmp_path):
    (tmp_path / "a.md").write_text("# Nothing\n\nJust prose.\n")
    assert "defines no requirement IDs" in refused(tmp_path, "init", str(tmp_path / "a.md"))
    (tmp_path / "b.md").write_text("- R-1: a\n- R-1: b\n")
    assert "more than once: R-1" in refused(tmp_path, "init", str(tmp_path / "b.md"))


def test_init_refuses_a_broken_seal_and_accepts_a_valid_one(tmp_path):
    body = SPEC.replace("status: draft\n", "status: sealed\n")
    digest = ledger.spec_sha256(body)
    good = body.replace("status: sealed\n", f"status: sealed\nsealed_by: validate-spec.py sha256:{digest}\n")
    (tmp_path / "good.md").write_text(good)
    assert ok(tmp_path, "init", str(tmp_path / "good.md"), "--name", "g")["sealed"]
    (tmp_path / "bad.md").write_text(good.replace("returns 5", "returns 6"))
    assert "does not match" in refused(tmp_path, "init", str(tmp_path / "bad.md"), "--name", "b")


def test_init_refuses_an_existing_run(root):
    assert "already exists" in refused(root, "init", str(root / "spec.md"), "--name", "r1")


# --- plan ----------------------------------------------------------------------


def test_plan_computes_waves_from_dependencies(planned):
    st = ok(planned, "status")
    assert st["waves"] == [["S1"], ["S2"]]
    assert st["next"] == {"action": "build", "wave": 1, "slices": ["S1"]}


def test_plan_splits_a_wide_wave_by_max_parallel(tmp_path):
    spec = "".join(f"- R-{i}: thing {i}\n" for i in range(1, 6))
    (tmp_path / "s.md").write_text(spec)
    ok(tmp_path, "init", str(tmp_path / "s.md"), "--name", "w", "--max-parallel", "2")
    plan = {"slices": [{"id": f"S{i}", "requirements": [f"R-{i}"], "files": [f"f{i}.py"]} for i in range(1, 6)]}
    (tmp_path / "p.json").write_text(json.dumps(plan))
    assert ok(tmp_path, "plan", "--file", str(tmp_path / "p.json"))["waves"] == [["S1", "S2"], ["S3", "S4"], ["S5"]]


@pytest.mark.parametrize(
    "change, message",
    [
        (lambda p: p["slices"][1].update(requirements=[]), "no slice owns R-003"),
        (lambda p: p["slices"][1]["requirements"].append("R-001"), "R-001 is in both S1 and S2"),
        (lambda p: p["slices"][1]["requirements"].append("R-099"), "R-099, which the spec does not define"),
        (lambda p: p["slices"][1].update(files=["calc/core.py"]), "overlaps calc/core.py (S1)"),
        (lambda p: p["slices"][0]["files"].append("calc/cli/main.py"), "calc/cli/ (S2) overlaps calc/cli/main.py (S1)"),
        (lambda p: p["slices"][1].update(files=["../outside.py"]), "not a project-relative path"),
        (lambda p: p["slices"][1].update(files=[]), "S2 owns no files"),
        (lambda p: p["slices"][1].update(depends_on=["S9"]), "unknown slice S9"),
        (lambda p: p["slices"][0].update(depends_on=["S2"]), "cycle"),
        (lambda p: p["slices"].append(dict(p["slices"][0])), "S1 appears twice"),
    ],
)
def test_plan_refuses_an_unbuildable_plan(root, change, message):
    plan = json.loads(json.dumps(PLAN))
    change(plan)
    assert message in plan_with(root, plan)


def test_plan_is_frozen_once_building_starts(planned):
    ok(planned, "slice", "S1", "--status", "building")
    assert "can no longer change" in plan_with(planned, PLAN)


def test_a_slice_cannot_start_before_its_dependencies(planned):
    assert "depends on S1" in refused(planned, "slice", "S2", "--status", "building")
    ok(planned, "slice", "S1", "--status", "built")
    ok(planned, "slice", "S2", "--status", "building")


def test_owners_maps_files_to_slices(planned):
    out = ok(planned, "owners", "calc/core.py", "./calc/cli/args.py", "README.md")
    assert out["owned"] == {"S1": ["calc/core.py"], "S2": ["calc/cli/args.py"]}
    assert out["unowned"] == ["README.md"]


# --- evidence and done ---------------------------------------------------------


def test_done_needs_recorded_evidence(planned):
    build_all(planned)
    assert "has no recorded evidence" in refused(planned, "done", "R-001")
    assert ok(planned, "status")["next"]["action"] == "verify"


def test_a_pass_without_command_or_output_is_refused(planned):
    assert "needs the command" in refused(planned, "record", "R-001", "--verdict", "pass", "--output", "ok")
    assert "needs the command" in refused(planned, "record", "R-001", "--verdict", "pass", "--command", "pytest")
    assert "needs a reason" in refused(planned, "record", "R-001", "--verdict", "fail")


def test_done_refuses_a_failing_latest_check(planned):
    pass_(planned, "R-001")
    ok(planned, "record", "R-001", "--verdict", "fail", "--reason", "add(-1, 1) returned 2", "--command", "pytest")
    assert "latest check failed" in refused(planned, "done", "R-001")


def test_output_can_come_from_a_file_and_is_kept_short(planned):
    out = planned / "out.txt"
    out.write_text("x" * 10000 + "END")
    ok(planned, "record", "R-001", "--verdict", "pass", "--command", "pytest", "--output-file", str(out))
    ev = json.loads((planned / ".smith/runs/r1/ledger.json").read_text())["requirements"]["R-001"]["evidence"][-1]
    assert len(ev["output"]) == ledger.OUTPUT_LIMIT and ev["output"].endswith("END")


def test_full_cycle_to_finish(planned):
    build_all(planned)
    for rid in ("R-001", "R-002", "R-003"):
        pass_(planned, rid)
    assert ok(planned, "status")["next"]["action"] == "accept"
    assert ok(planned, "done", "--all-passing")["done"] == ["R-001", "R-002", "R-003"]
    st = ok(planned, "status")
    assert st["complete"] and st["next"] == {"action": "finish"}
    assert "already done" in refused(planned, "record", "R-001", "--verdict", "fail", "--reason", "x")


def test_a_fix_round_reopens_failing_and_touched_requirements(planned):
    build_all(planned)
    pass_(planned, "R-001")
    ok(planned, "record", "R-002", "--verdict", "fail", "--reason", "no ZeroDivisionError")
    pass_(planned, "R-003")
    ok(planned, "done", "R-003")
    assert ok(planned, "status")["next"] == {"action": "fix", "requirements": ["R-002"]}

    r = ok(planned, "round", "--touched", "calc/core.py")
    assert (r["round"], r["reopened"]) == (1, ["R-001", "R-002"])
    st = ok(planned, "status")
    assert st["counts"] == {"pending": 2, "passing": 0, "failing": 0, "done": 1}
    # Evidence from before the fix does not count in the new round.
    assert "re-verify" in refused(planned, "done", "R-001")


def test_an_unowned_touched_file_reopens_everything(planned):
    build_all(planned)
    for rid in ("R-001", "R-002", "R-003"):
        pass_(planned, rid)
    ok(planned, "done", "--all-passing")
    r = ok(planned, "round", "--touched", "setup.cfg")
    assert r["reopened"] == ["R-001", "R-002", "R-003"] and r["unowned"] == ["setup.cfg"]


def test_the_round_limit_stops_the_loop(planned):
    build_all(planned)
    ok(planned, "record", "R-001", "--verdict", "fail", "--reason", "wrong sum")
    ok(planned, "round")
    ok(planned, "record", "R-001", "--verdict", "fail", "--reason", "still wrong")
    ok(planned, "round")
    ok(planned, "record", "R-001", "--verdict", "fail", "--reason", "still wrong")
    assert "limit (2) is reached" in refused(planned, "round")
    assert ok(planned, "status")["next"]["action"] in ("verify", "stop")


def test_a_failed_slice_blocks_the_run(planned):
    ok(planned, "slice", "S1", "--status", "failed", "--note", "cannot import calc")
    assert ok(planned, "status")["next"] == {"action": "blocked", "slices": ["S1"]}


def test_report_lists_evidence_and_what_is_not_done(planned):
    build_all(planned)
    pass_(planned, "R-001")
    ok(planned, "done", "R-001")
    ok(planned, "record", "R-002", "--verdict", "fail", "--reason", "div(1, 0) returned inf")
    out = ok(planned, "report")
    text = Path(out["report"]).read_text()
    assert "| R-001 | done | S1 | `pytest -q tests` | 0 | calc/core.py:3 |" in text
    assert "**R-002** (failing): div(1, 0) returned inf" in text
    assert "**R-003** (pending): never verified" in text
    assert not out["complete"]


def test_the_newest_run_is_the_default(root):
    ok(root, "init", str(root / "spec.md"), "--name", "r2")
    assert ok(root, "status")["run"] == "r2"
    assert ok(root, "--run", "r1", "status")["run"] == "r1"
    assert "no run named nope" in refused(root, "--run", "nope", "status")


def test_wrapper_runs_the_ledger(tmp_path):
    (tmp_path / "spec.md").write_text(SPEC)
    r = subprocess.run(["bash", str(PLUGIN / "scripts" / "smith"), "--root", str(tmp_path), "init",
                        str(tmp_path / "spec.md")], capture_output=True, text=True)
    assert r.returncode == 0 and json.loads(r.stdout)["requirements"] == 3
