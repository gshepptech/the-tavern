from conftest import git, j, write

import land
from common import head, load_state, update_state, write_json

SUB = "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n"
BUGGY = "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return b - a\n"


def _split(run):
    root, name, rdir = run
    write_json(rdir / "plan.json", {"mode": "split", "contract_block": "def sub(a, b)", "slices": [
        {"id": "s1", "requirement_ids": ["GI-001", "FR-001"], "files": ["calc.py"], "anchors": [{"at": "calc.py:1", "fact": "f"}], "new_loc": 1000},
        {"id": "s2", "requirement_ids": ["GI-001", "FR-002"], "files": ["sub.py"], "anchors": [{"at": "calc.py:1", "fact": "f"}], "new_loc": 1000}],
        "seams": []})
    assert j(root, "plan", "--run", name)["passed"]
    return root, name, rdir


def test_commit_in_a_split_takes_only_owned_files(run):
    root, name, rdir = _split(run)
    write(root, "calc.py", SUB)
    write(root, "sub.py", "x = 1\n")
    write(root, "calc_extra_test.py", "")
    r = j(root, "commit", "--run", name, "--as", "s1", "-m", "add sub")
    assert r["ok"] and r["files"] == ["calc.py", "calc_extra_test.py"] and "sub.py" in r["left_uncommitted"]
    assert load_state(rdir)["commits"]["s1"] == [r["commit"]]
    refused = j(root, "commit", "--run", name, "--as", "s1", "-m", "x", "sub.py")
    assert not refused["ok"] and refused["refused"]["sub.py"] == "owned by s2"


def test_a_fixer_may_commit_files_no_slice_owns(run):
    root, name, rdir = _split(run)
    state = load_state(rdir)
    assert land.may_commit(state, "fix:s1", "README.md") == ""
    assert land.may_commit(state, "s1", "README.md") == "owned by no slice"
    assert land.may_commit(state, "fix:s1", "sub.py") == "owned by s2"
    assert land.may_commit(state, "all", "calc.py") == "unknown actor 'all'"
    assert land.may_commit(state, "s1", "tinker-archive/t1/x") != ""


def test_single_builder_owns_everything(run):
    root, name, rdir = run
    write(root, "anything/new.py", "x = 1\n")
    assert j(root, "commit", "--run", name, "--as", "all", "-m", "new")["ok"]


def test_verify_passes_clean_committed_work(run):
    root, name, rdir = run
    write(root, "calc.py", SUB)
    write(root, "tests/test_sub.py", "from calc import sub\nassert sub(5, 3) == 2\n")
    assert j(root, "commit", "--run", name, "--as", "all", "-m", "sub")["ok"]
    r = j(root, "verify", "--run", name, "--round", "1")
    assert r["failures"] == [] and r["head"] == head(root) and r["integration"] is None
    st = load_state(rdir)
    assert "verify:1" in st["steps_done"] and st["round_base"]["1"] == head(root)


def test_verify_finds_ids_new_failures_and_uncommitted_work(run):
    root, name, rdir = run
    write(root, "calc.py", SUB + "# implements FR-002\n")
    write(root, "tests/test_bad.py", "assert False\n")
    assert j(root, "commit", "--run", name, "--as", "all", "-m", "sub")["ok"]
    write(root, "calc.py", SUB)
    r = j(root, "verify", "--run", name, "--round", "1")
    kinds = {f["kind"]: f for f in r["failures"]}
    assert set(kinds) == {"uncommitted", "ids", "checks"}
    assert "calc.py:7 names requirement FR-002" in kinds["ids"]["title"]
    assert kinds["checks"]["names"] == ["tests/test_bad.py"] and "`make test` has new failures" in kinds["checks"]["title"]
    assert [f["id"] for f in r["failures"]] == ["V1-1", "V1-2", "V1-3"]


def test_verify_with_nothing_committed(run):
    root, name, _ = run
    r = j(root, "verify", "--run", name, "--round", "1")
    assert [f["title"] for f in r["failures"]] == ["nothing was committed since the base commit"]


def test_verify_in_a_split_checks_ownership(run):
    root, name, rdir = _split(run)
    write(root, "sub.py", "x = 1\n")
    git(root, "add", "-A"); git(root, "commit", "-qm", "plain git")
    r = j(root, "verify", "--run", name, "--round", "1")
    assert any(f["kind"] == "ownership" and "not made with `tinker commit`" in f["title"] for f in r["failures"])


def test_verify_runs_the_integration_check_and_reuses_a_result_at_head(run):
    root, name, rdir = run
    with update_state(rdir) as st:
        st["integration"] = {"command": "python3 tests/run.py", "cwd": ""}
    write(root, "tests/test_bad.py", "assert False\n")
    assert j(root, "commit", "--run", name, "--as", "all", "-m", "bad")["ok"]
    rec = j(root, "integration", "--run", name)
    assert rec["ran"] and rec["exit"] == 1 and rec["failures"] == ["tests/test_bad.py"]
    with update_state(rdir) as st:  # a builder ran it already; verify must not run it again
        st["integration"]["command"] = "exit 0"
    write_json(rdir / "checks" / "integration-latest.json", {**rec, "command": "python3 tests/run.py", "tail": "FAILED"})
    r = j(root, "verify", "--run", name, "--round", "1")
    integ = [f for f in r["failures"] if f["kind"] == "integration"]
    assert integ and integ[0]["names"] == ["tests/test_bad.py"] and r["integration"]["exit"] == 1


def test_fixcheck_pins_behavioural_fixes_only(run):
    root, name, rdir = run
    write(root, "calc.py", BUGGY)
    assert j(root, "commit", "--run", name, "--as", "all", "-m", "sub")["ok"]
    j(root, "verify", "--run", name, "--round", "1")
    write_json(rdir / "checks" / "spec-r1.json", {"verdicts": [], "gaps": [
        {"id": "G-001", "requirement_ids": ["FR-002"], "behavioural": True},
        {"id": "G-002", "requirement_ids": ["FR-001"], "behavioural": True},
        {"id": "G-003", "requirement_ids": [], "behavioural": False}]})
    write(root, "calc.py", SUB)
    write(root, "tests/test_sub.py", "from calc import sub\nassert sub(5, 3) == 2\n")
    assert j(root, "commit", "--run", name, "--as", "fix:all", "-m", "fix sub")["ok"]
    write_json(rdir / "fixes" / "r1-all.json", {"fixes": [
        {"item": "G-001", "outcome": "fixed", "test_files": ["tests/test_sub.py"], "test_command": "PYTHONPATH=. python3 tests/test_sub.py"},
        {"item": "G-002", "outcome": "fixed", "test_files": ["tests/test_calc.py"], "test_command": "PYTHONPATH=. python3 tests/test_calc.py"},
        {"item": "G-003", "outcome": "fixed"},
        {"item": "V1-1", "outcome": "fixed"}]})
    r = j(root, "verify", "--run", name, "--round", "2")
    fx = [f for f in r["failures"] if f["kind"] == "fixcheck"]
    assert len(fx) == 1 and "G-002" in fx[0]["title"] and "passes before the fix" in fx[0]["title"]
    assert [f["id"] for f in r["failures"]] == ["V2-1"]


def test_a_fixer_may_commit_files_of_slices_no_fixer_works_on(run):
    root, name, rdir = _split(run)
    state = load_state(rdir)
    assert land.may_commit(state, "fix:s1", "sub.py", ("s2",)) == ""
    assert land.may_commit(state, "s1", "sub.py", ("s2",)) == "owned by s2"  # builders never
    write(root, "sub.py", "x = 1\n")
    r = j(root, "commit", "--run", name, "--as", "fix:s1", "--also", "s2", "-m", "fix across slices", "sub.py")
    assert r["ok"] and load_state(rdir)["commit_also"][r["commit"]] == ["s2"]
    v = j(root, "verify", "--run", name, "--round", "1")
    assert not any(f["kind"] == "ownership" for f in v["failures"])  # verify honours the allowance the commit had
