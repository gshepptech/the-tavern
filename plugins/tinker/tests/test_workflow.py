"""The build workflow parses, keeps its declared shape, and routes in code.

workflow_harness.mjs wraps workflows/build.js the way the Workflow runtime
does, checks the wrapped file with ``node --check``, and drives it with
scripted agents and scripted ``tinker`` command results. This covers every
branch of the script: one builder or a planned split, a plan refused then
revised or never fixed, a preflight stop, the finder, verify -> fix ->
re-verify, the round cap, the agent cap, and resuming at each stage. The
tinker commands themselves are covered by the other test files.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[1]
SCRIPT = PLUGIN / "workflows" / "build.js"
HARNESS = Path(__file__).resolve().parent / "workflow_harness.mjs"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


def _run(scenario: str) -> dict:
    out = subprocess.run([NODE, str(HARNESS), str(SCRIPT), scenario], capture_output=True, text=True, timeout=60, check=True)
    d = json.loads(out.stdout)
    assert d["schemaProblems"] == []
    return d


@pytest.fixture(scope="module")
def single() -> dict:
    return _run("single")


@pytest.fixture(scope="module")
def split() -> dict:
    return _run("split")


def _cmds(d: dict) -> list[str]:
    return [c["cmd"] for c in d["commands"]]


def test_wrapped_script_passes_node_check(single):
    subprocess.run([NODE, "--check", single["syntaxFile"]], check=True, capture_output=True, text=True)


def test_meta_phases_match_every_phase_call():
    source = SCRIPT.read_text(encoding="utf-8")
    meta_block, body = source.split("\n}\n", 1)
    declared = re.findall(r"\{ title: '([^']+)'", meta_block)
    called = set(re.findall(r"\bphase\('([^']+)'\)", body))
    opts = set(re.findall(r"phase: '([^']+)'", body)) | set(re.findall(r"clerk\(`?[^,]+`?, '([^']+)'", body))
    assert len(declared) == len(set(declared))
    assert called == set(declared)
    assert opts <= set(declared), opts - set(declared)


def test_the_script_stays_small():
    assert len(SCRIPT.read_text(encoding="utf-8").splitlines()) <= 200


def test_single_builder_run_makes_five_agent_calls(single):
    assert single["result"]["status"] == "done"
    assert single["labels"] == ["clerk:init", "build:all", "clerk:verify:r1", "spec:r1", "clerk:report"]
    assert single["phases"] == ["Preflight", "Build", "Verify", "Report"]
    assert single["result"]["agent_calls"] == {"total": 5, "by": {"clerk": 3, "builder": 1, "spec-checker": 1}}
    assert _cmds(single)[0] == "[init-e0] init --spec 'docs/spec.md' --run 'r' --max-rounds 2 --max-agents 40"
    assert _cmds(single)[1] == "[verify-r1-e0] verify --run 'r' --round 1"


def test_code_is_told_the_running_agent_count(single):
    calls = [c["calls"] for c in single["commands"]]
    assert calls[0] is None  # no run state before init
    assert calls[1] == {"epoch": 0, "total": 3, "by": {"clerk": 2, "builder": 1}}
    assert calls[2]["total"] == 5 and "concerns" in calls[2]


def test_agents_get_the_right_type_model_and_effort(single, split):
    o = {**single["options"], **split["options"]}
    assert o["build:all"]["agentType"] == "tinker:builder" and o["build:all"]["model"] == "opus"
    assert o["spec:r1"]["agentType"] == "tinker:spec-checker" and o["spec:r1"]["effort"] == "max"
    assert o["plan"]["agentType"] == ""  # a general-purpose agent reading prompts/planner.md
    assert all(v["effort"] == "low" and v["agentType"] == "" for k, v in o.items() if k.startswith("clerk:"))


def test_single_builder_gets_the_whole_spec_and_the_integration_rule(single):
    p = single["prompts"]["build:all"]
    assert "Build the whole spec: /p/tinker-archive/r/spec.md is your brief, verbatim." in p
    assert "commit --run 'r' --as all -m" in p and "you own only" not in p
    assert "The spec names no integration check." in p
    d = _run("find-fix")
    assert "--job integ-all-e0 integration --run 'r'" in d["prompts"]["build:all"]


def test_split_plans_then_builds_waves_in_order(split):
    labels = split["labels"]
    assert labels[:2] == ["clerk:init", "plan"]
    assert labels.index("build:core") < labels.index("build:api") and "build:cli" in labels
    p = split["prompts"]["build:api"]
    assert "Your brief: /b/api.md" in p and "you own only: api/" in p and "--as api -m" in p
    assert "prompts/planner.md" in split["prompts"]["plan"] and "'/plugin/scripts/tinker' --root '/p' plan --run 'r'" in split["prompts"]["plan"]
    assert split["result"]["agent_calls"]["by"] == {"clerk": 3, "planner": 1, "builder": 3, "spec-checker": 1}


def test_plan_refused_then_revised_gets_its_errors():
    d = _run("plan-revised")
    assert d["labels"][:3] == ["clerk:init", "plan", "plan:rev1"]
    assert "- core: writes behaviour but owns no requirement (S2)" in d["prompts"]["plan:rev1"]
    assert d["result"]["status"] == "done"


def test_plan_that_never_passes_blocks_before_any_builder():
    d = _run("plan-stuck")
    assert d["result"]["status"] == "blocked" and "s1 and s2 both own api/" in d["result"]["message"]
    assert not any(x.startswith("build:") for x in d["labels"])


def test_preflight_stop_blocks_before_building():
    d = _run("preflight-stop")
    assert d["result"]["status"] == "blocked" and "Cannot connect to the Docker daemon" in d["result"]["message"]
    assert d["labels"] == ["clerk:init"]


def test_finder_names_the_check_when_detection_fails():
    d = _run("finder")
    assert d["labels"][:3] == ["clerk:init", "finder", "build:all"]
    assert d["options"]["finder"]["effort"] == "low"
    assert "--job preflight-e0 preflight --run 'r' --command" in d["prompts"]["finder"] and "--none" in d["prompts"]["finder"]
    assert "Integration check: `mage metrics`" in d["prompts"]["build:all"]
    blocked = _run("finder-blocked")
    assert blocked["result"]["status"] == "blocked" and "command -v mage" in blocked["result"]["message"]


def test_init_stop():
    d = _run("init-stop")
    assert d["result"]["status"] == "stopped" and d["labels"] == ["clerk:init"]


def test_verify_fix_reverify_batches_everything_into_one_fixer():
    d = _run("find-fix")
    labels = d["labels"]
    assert labels[2:] == ["clerk:verify:r1", "spec:r1", "fix:all:r1", "clerk:verify:r2", "spec:r2", "clerk:report"]
    fix = d["prompts"]["fix:all:r1"]
    assert "Fix every one of these: V1-1, G-001." in fix and "checks/verify-r1.json" in fix and "checks/spec-r1.json" in fix
    assert "--as fix:all" in fix and "fixes/r1-all.json" in fix and "--job integ-fix-all-r1-e0 integration" in fix
    assert d["options"]["fix:all:r1"]["agentType"] == "tinker:fixer" and d["options"]["fix:all:r1"]["model"] == "opus"
    assert "Re-check only these gaps after fix round 1: G-001." in d["prompts"]["spec:r2"]
    assert "Check every requirement" in d["prompts"]["spec:r1"]
    assert d["phases"] == ["Preflight", "Build", "Verify", "Fix", "Verify", "Report"]


def test_no_open_gaps_means_no_recheck():
    d = _run("failures-only")
    assert "spec:r2" not in d["labels"] and "clerk:verify:r2" in d["labels"]


def test_round_cap_stops_fixing_and_reports_what_remains():
    d = _run("round-cap")
    assert [x for x in d["labels"] if x.startswith("fix:")] == ["fix:all:r1", "fix:all:r2"]
    assert d["labels"][-3:] == ["clerk:verify:r3", "spec:r3", "clerk:report"]
    assert any("after 2 fix rounds these remain: V3-1, G-001" in c for c in d["result"]["concerns"])
    assert d["result"]["agent_calls"]["total"] == 11


def test_zero_rounds_reports_without_fixing():
    d = _run("no-rounds")
    assert not any(x.startswith("fix:") for x in d["labels"])
    assert any("after 0 fix rounds these remain: G-001" in c for c in d["result"]["concerns"])


def test_split_failures_and_gaps_go_to_the_owning_slice():
    d = _run("split-fix")
    p = d["prompts"]
    assert "against slice cli: V1-1, V1-3, G-002." in p["fix:cli:r1"]  # by file; unowned to the last slice; by requirement
    assert "against slice core: V1-2." in p["fix:core:r1"]  # by test name
    assert "against slice api: G-001." in p["fix:api:r1"]  # by file
    assert "Your slice's brief: /b/cli.md" in p["fix:cli:r1"]


def test_agent_cap_stops_before_the_next_agent_and_still_reports():
    d = _run("capped")
    assert d["result"]["status"] == "capped" and not any(x.startswith("fix:") for x in d["labels"])
    assert d["labels"][-1] == "clerk:report" and d["result"]["agent_calls"]["total"] == 5
    assert any("cap of 5 agent calls" in c for c in d["result"]["concerns"])


def test_resume_after_a_checked_round_goes_straight_to_the_fixer():
    d = _run("resume-fix")
    assert d["labels"] == ["clerk:resume", "fix:all:r1", "clerk:verify:r2", "spec:r2", "clerk:report"]
    assert "Fix every one of these: V1-1, G-001." in d["prompts"]["fix:all:r1"]
    assert d["commands"][0]["calls"] is None  # the epoch is unknown until resume answers
    assert d["commands"][1]["calls"]["epoch"] == 1


def test_resume_mid_build_builds_only_unbuilt_slices():
    d = _run("resume-build")
    assert [x for x in d["labels"] if x.startswith("build:")] == ["build:api", "build:cli"]
    assert "plan" not in d["labels"]


def test_resume_after_a_preflight_stop_reruns_preflight():
    d = _run("resume-preflight")
    assert d["labels"][:3] == ["clerk:resume", "clerk:preflight", "build:all"]
    assert _cmds(d)[1] == "[preflight-e1] preflight --run 'r'"
