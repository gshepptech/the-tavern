from __future__ import annotations

import pytest

from conftest import write
from verdicts import gaps, validate

IDS = ["R-001", "R-002"]


@pytest.fixture
def root(tmp_path):
    write(tmp_path, "calc.py", "def add(a, b):\n    return a + b\n")
    write(tmp_path, "tests/test_calc.py", "def test_add():\n    assert True\n")
    return tmp_path


def good() -> dict:
    return {"requirements": [
        {"id": "R-001", "verdict": "MET", "evidence": ["calc.py:1-2", "tests/test_calc.py:1"], "reason": ""},
        {"id": "R-002", "verdict": "MISSING", "evidence": [], "reason": "no sub() anywhere in calc.py"},
    ], "unrequested": [{"where": "calc.py:2", "what": "logs every call"}]}


def test_a_complete_file_is_accepted(root):
    assert validate(good(), IDS, root) == []


@pytest.mark.parametrize("mutate, message", [
    (lambda d: d["requirements"].pop(), "R-002: no verdict"),
    (lambda d: d["requirements"].append(dict(d["requirements"][0])), "R-001: 2 verdicts"),
    (lambda d: d["requirements"][0].update(verdict="DONE"), "verdict 'DONE' is not one of"),
    (lambda d: d["requirements"][0].update(evidence=[]), "MET needs at least one"),
    (lambda d: d["requirements"][0].update(evidence=["calc.py"]), "is not 'path:line'"),
    (lambda d: d["requirements"][0].update(evidence=["calc.py:9"]), "points past the end"),
    (lambda d: d["requirements"][0].update(evidence=["nope.py:1"]), "does not exist"),
    (lambda d: d["requirements"][0].update(evidence=["/etc/hosts:1"]), "relative to the project root"),
    (lambda d: d["requirements"][1].update(reason=""), "MISSING needs a reason"),
    (lambda d: d["requirements"].append({"id": "R-404", "verdict": "MET"}), "'R-404' is not a requirement"),
    (lambda d: d["unrequested"].append({"where": "calc.py:1"}), "unrequested[1]: needs"),
    (lambda d: d.update(requirements={}), "'requirements' must be a list"),
])
def test_each_contract_break_is_named(root, mutate, message):
    data = good()
    mutate(data)
    errors = validate(data, IDS, root)
    assert any(message in e for e in errors), errors


def test_gaps_collect_every_kind_and_skip_failures_already_at_base():
    check = {
        "id_leaks": [{"file": "calc.py", "line": 4, "id": "R-002", "text": "# R-002"}],
        "uncommitted": ["new.py"],
        "commands": [
            {"name": "test", "cmd": "make test", "exit": 2, "tail": "FAILED"},
            {"name": "lint", "cmd": "make lint", "exit": 1, "tail": "old lint debt"},
            {"name": "build", "cmd": "make build", "exit": 0, "tail": ""},
        ],
    }
    out = gaps(good(), check, baseline={"test": 0, "lint": 1, "build": 0}, round_no=2)
    assert [(g["id"], g["kind"]) for g in out] == [
        ("G2-1", "requirement"), ("G2-2", "unrequested"), ("G2-3", "id-in-code"), ("G2-4", "uncommitted"), ("G2-5", "check")]
    assert out[0]["requirement"] == "R-002"
    assert out[4]["command"] == "make test"


def test_a_clean_round_has_no_gaps():
    data = {"requirements": [{"id": "R-001", "verdict": "MET", "evidence": ["calc.py:1"]}], "unrequested": []}
    assert gaps(data, {"commands": [{"name": "test", "cmd": "make test", "exit": 0, "tail": ""}]}, {"test": 0}, 1) == []
