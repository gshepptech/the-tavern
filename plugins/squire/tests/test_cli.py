"""The CLI end to end on a real git repository: args, init, check, gaps, report."""

from __future__ import annotations

import json

from conftest import commit, git, j, write


def verifier_file(run_dir, rnd: int, data: dict) -> None:
    write(run_dir, f"verify/verify-r{rnd}.json", json.dumps(data))


def test_args_names_the_run_after_the_spec(repo):
    out = j(repo, "args", "spec.md", "--max-rounds", "2", "--check", "make test")
    assert out["ok"]
    a = out["args"]
    assert a["run"].startswith("proj-"), "a spec called spec.md is named after its directory"
    assert a["max_rounds"] == 2 and a["checks"] == ["make test"] and a["timeout"] == 300
    assert a["plugin_root"].endswith("squire")


def test_args_refuses_a_missing_spec_and_bad_limits(repo):
    assert "not found" in j(repo, "args", "nope.md")["stop"]
    assert "--max-rounds" in j(repo, "args", "spec.md", "--max-rounds", "9")["stop"]
    assert "usage" in j(repo, "args")["stop"]


def test_init_sets_up_branch_run_dir_and_baseline(run):
    root, name, d = run
    assert git(root, "branch", "--show-current") == f"squire/{name}"
    state = json.loads((d / "state.json").read_text())
    assert state["commands"] == [{"name": "test", "cmd": "make test"}]
    assert state["baseline"] == {"test": 0}
    assert [r["id"] for r in json.loads((d / "index.json").read_text())["requirements"]] == ["R-001", "R-002"]
    assert git(root, "status", "--porcelain") == "", "the run directory must ignore itself"


def test_init_refuses_a_dirty_tree_a_spec_without_ids_and_a_reused_run(repo):
    write(repo, "calc.py", "changed\n")
    assert "uncommitted changes" in j(repo, "init", "--spec", "spec.md", "--run", "a")["stop"]
    git(repo, "checkout", "--", "calc.py")
    write(repo, "loose.md", "# Ideas\n\n- make it faster\n")
    commit(repo, "loose", "loose.md")
    assert "no requirement IDs" in j(repo, "init", "--spec", "loose.md", "--run", "a")["stop"]
    assert j(repo, "init", "--spec", "spec.md", "--run", "a")["ok"]
    assert "already exists" in j(repo, "init", "--spec", "spec.md", "--run", "a")["stop"]


def test_init_warns_when_a_check_already_fails_at_base(repo):
    out = j(repo, "init", "--spec", "spec.md", "--run", "b", "--check", "false")
    assert out["baseline"] == {"check1": 1}
    assert any("already fails at the base commit" in w for w in out["warnings"])


def test_a_round_with_gaps_then_a_clean_round(run):
    root, name, d = run
    # Round 1: the builder added sub() with a requirement ID in its comment and an extra flag.
    write(root, "calc.py", CALC_WITH_LEAK)
    commit(root, "sub", "calc.py")
    chk = j(root, "check", "--run", name, "--round", "1")
    assert chk["id_leaks"] == 1 and chk["new_failures"] == []
    verifier_file(d, 1, {"requirements": [
        {"id": "R-001", "verdict": "MET", "evidence": ["calc.py:1-2"]},
        {"id": "R-002", "verdict": "PARTIAL", "evidence": ["calc.py:6"], "reason": "sub(5, 3) is untested"},
    ], "unrequested": [{"where": "calc.py:9", "what": "a verbose flag nobody asked for"}]})
    g = j(root, "gaps", "--run", name, "--round", "1")
    assert g["valid"] and g["open"] == 3
    assert g["by_kind"] == {"requirement": 1, "unrequested": 1, "id-in-code": 1}

    # Round 2: the fixer cleaned it up.
    write(root, "calc.py", "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n")
    write(root, "tests/test_sub.py", "from calc import sub\n\n\ndef test_sub():  # R-002\n    assert sub(5, 3) == 2\n")
    commit(root, "fix", "calc.py", "tests/test_sub.py")
    j(root, "check", "--run", name, "--round", "2")
    verifier_file(d, 2, {"requirements": [
        {"id": "R-001", "verdict": "MET", "evidence": ["calc.py:1-2"]},
        {"id": "R-002", "verdict": "MET", "evidence": ["calc.py:5-6", "tests/test_sub.py:4"]},
    ], "unrequested": []})
    assert j(root, "gaps", "--run", name, "--round", "2")["open"] == 0

    rep = j(root, "report", "--run", name)
    assert rep["status"] == "done" and rep["rounds"] == 2 and rep["counts"]["MET"] == 2
    text = (d / "report.md").read_text()
    assert "| R-002 | Subtract | MET | `calc.py:5-6`, `tests/test_sub.py:4` |" in text
    assert "open gaps per round: 3, 0" in text


def test_gaps_refuses_checks_from_another_commit_and_a_bad_file(run):
    root, name, d = run
    assert not j(root, "gaps", "--run", name, "--round", "1")["valid"]
    j(root, "check", "--run", name, "--round", "1")
    write(root, "calc.py", CALC_WITH_LEAK)
    commit(root, "later", "calc.py")
    verifier_file(d, 1, {"requirements": [{"id": "R-001", "verdict": "MET", "evidence": ["calc.py:1"]}]})
    g = j(root, "gaps", "--run", name, "--round", "1")
    assert not g["valid"]
    assert any("HEAD is now" in e for e in g["errors"])
    assert any("R-002: no verdict" in e for e in g["errors"])
    assert not (d / "verify" / "gaps-r1.json").exists()


def test_report_on_open_gaps(run):
    root, name, d = run
    j(root, "check", "--run", name, "--round", "1")
    verifier_file(d, 1, {"requirements": [
        {"id": "R-001", "verdict": "MET", "evidence": ["calc.py:1"]},
        {"id": "R-002", "verdict": "MISSING", "reason": "no sub()"},
    ]})
    j(root, "gaps", "--run", name, "--round", "1")
    rep = j(root, "report", "--run", name)
    assert rep["status"] == "done_with_gaps" and rep["open"] == ["G1-1"]
    assert "| R-002 | Subtract | MISSING | no sub() |" in (d / "report.md").read_text()


def test_unknown_run_is_a_stop(repo):
    assert "no run named" in j(repo, "check", "--run", "ghost", "--round", "1")["stop"]


CALC_WITH_LEAK = """def add(a, b):
    return a + b


# R-002
def sub(a, b):
    return a - b

VERBOSE = False
"""
