"""The validator refuses any finding a reader could not act on, and the report renders from what passes."""

from __future__ import annotations

import copy
import json

import pytest

from conftest import SLICE_1, finding, j, write_json
from report import render, validate_report, validate_slice


def plan_of(run) -> dict:
    return json.loads((run / "plan.json").read_text())


def test_both_slices_and_the_report_pass(run, report):
    assert validate_slice(SLICE_1, run, "s01") == []
    assert validate_report(report, run, plan_of(run)) == []


@pytest.mark.parametrize("over, message", [
    ({"steps": []}, "'steps' must list the steps to reproduce"),
    ({"steps": ["Open /cart", ""]}, "'steps' must list"),
    ({"severity": "critical"}, "severity 'critical' is not one of blocker, major, minor, polish"),
    ({"severity": None}, "severity None"),
    ({"evidence": []}, "evidence must list at least one screenshot"),
    ({"evidence": ["screenshots/missing.png"]}, "does not exist in the run directory"),
    ({"evidence": ["/tmp/s01-01.png"]}, "must be relative to the run directory"),
    ({"evidence": ["../outside.png"]}, "must be relative to the run directory"),
    ({"evidence": ["slices/s01.json"]}, "is not an image"),
    ({"lens": "vibes"}, "'lens' must be from"),
    ({"url": "/cart"}, "'url' must be the http(s) page"),
    ({"suggested_fix": " "}, "'suggested_fix' is required"),
    ({"expected": ""}, "'expected' is required"),
    ({"signals": "GET / -> 500"}, "'signals' must be a list"),
])
def test_a_slice_finding_missing_what_a_reader_needs_is_refused(run, over, message):
    data = copy.deepcopy(SLICE_1)
    data["findings"][0] = finding(**over)
    errors = validate_slice(data, run, "s01")
    assert any(message in e for e in errors), errors


def test_a_slice_must_say_what_was_tried_or_why_it_was_blocked(run):
    empty = {"slice": "s01", "tasks": [], "findings": [], "blocked": ""}
    assert any("'tasks' must list" in e for e in validate_slice(empty, run, "s01"))
    assert validate_slice({**empty, "blocked": "login required and no login notes given"}, run, "s01") == []
    bad_outcome = {**empty, "tasks": [{"task": "pay", "outcome": "meh"}]}
    assert any("an 'outcome' of completed" in e for e in validate_slice(bad_outcome, run, "s01"))
    assert any("'slice' must be 's01'" in e for e in validate_slice({**empty, "slice": "s09", "blocked": "x"}, run, "s01"))


@pytest.mark.parametrize("mutate, message", [
    (lambda r: r["findings"].reverse(), "ranked below a less severe one"),
    (lambda r: r["findings"][1].update(rank=7), "rank must be 2"),
    (lambda r: r["findings"][1].update(id="UX-001"), "duplicate id"),
    (lambda r: r["findings"][1].update(id="F-2"), "id must look like UX-001"),
    (lambda r: r["findings"][2].update(title=r["findings"][0]["title"]), "merge duplicates"),
    (lambda r: r["findings"][0].update(personas=[]), "'personas' must name who hit it"),
    (lambda r: r["findings"][0].update(personas=["robot"]), "the run's persona keys"),
    (lambda r: r["findings"][0].update(sources=[]), "'sources' must name"),
    (lambda r: r["findings"][0].update(sources=["s01#9"]), "is not a finding in any slice file"),
    (lambda r: r["findings"][2].update(sources=["s01#1"]), "already cited by another finding"),
    (lambda r: r["findings"].pop(), "slice finding s01#2 is in no report finding's 'sources'"),
    (lambda r: r["slices"].pop(), "slice s02 is planned but missing"),
    (lambda r: r["slices"][0].update(status="ok"), "a 'status' of done, blocked, missing"),
    (lambda r: r.update(summary=""), "'summary' is required"),
    (lambda r: r["findings"][0].update(lenses=[]), "'lenses' must be from"),
])
def test_a_report_that_is_unranked_duplicated_or_lossy_is_refused(run, report, mutate, message):
    mutate(report)
    errors = validate_report(report, run, plan_of(run))
    assert any(message in e for e in errors), errors


def test_render_puts_every_finding_in_rank_order_with_its_evidence(run, report):
    md = render(report, plan_of(run))
    assert md.index("UX-001") < md.index("UX-002") < md.index("UX-003")
    assert "### 1. UX-001 [blocker] Pay button is unreachable by keyboard" in md
    assert "1. Open /cart with one item\n2. Press Tab from the top" in md
    assert "![UX-001 screenshot 1](screenshots/s01-01.png)" in md
    assert "- `GET /api/search?q=x -> 500`" in md
    assert "**Suggested fix:** Make Pay a button element" in md
    assert "| blocker | 1 |" in md and "| polish | 0 |" in md
    assert "| s02 | Mobile user | Search | done | 1 |" in md


def test_render_command_refuses_an_invalid_report_and_writes_a_valid_one(run, report):
    root = run.parents[2]
    report["findings"][0]["steps"] = []
    write_json(run / "report.json", report)
    out = j(root, "render", "--run", str(run))
    assert out["ok"] is False and any("steps" in e for e in out["errors"])
    assert not (run / "report.md").exists()

    report["findings"][0]["steps"] = ["Open /cart", "Press Tab"]
    write_json(run / "report.json", report)
    out = j(root, "render", "--run", str(run))
    assert out["ok"] and out["counts"] == {"blocker": 1, "major": 1, "minor": 1, "polish": 0}
    assert out["top"][0] == {"id": "UX-001", "severity": "blocker", "title": "Pay button is unreachable by keyboard"}
    assert (run / "report.md").exists()


def test_validate_command_reports_a_missing_or_broken_file(run):
    root = run.parents[2]
    assert j(root, "validate", "--run", str(run), "--slice", "s01")["valid"]
    missing = j(root, "validate", "--run", str(run), "--report")
    assert missing["valid"] is False and "was not written" in missing["errors"][0]
    (run / "slices" / "s02.json").write_text("{not json", encoding="utf-8")
    broken = j(root, "validate", "--run", str(run), "--slice", "s02")
    assert broken["valid"] is False and "not valid JSON" in broken["errors"][0]
