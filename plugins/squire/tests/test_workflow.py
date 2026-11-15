"""The build workflow parses, keeps its declared shape, and routes in code.

workflow_harness.mjs wraps workflows/build.js the way the Workflow runtime
does and drives it with scripted agents and scripted ``squire`` results. This
covers a clean first round, fix then clean, the round cap, --max-rounds 0, a
refused verifier file (once and twice), an init refusal and a builder crash.
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
def clean() -> dict:
    return _run("clean")


def test_wrapped_script_passes_node_check(clean):
    subprocess.run([NODE, "--check", clean["syntaxFile"]], check=True, capture_output=True, text=True)


def test_meta_phases_match_every_phase_used():
    source = SCRIPT.read_text(encoding="utf-8")
    meta_block, body = source.split("\n}\n", 1)
    declared = re.findall(r"\{ title: '([^']+)'", meta_block)
    called = set(re.findall(r"\bphase\('([^']+)'\)", body))
    used = set(re.findall(r"phase: '([^']+)'", body)) | set(re.findall(r"clerk\(`?[^,]+`?, '([^']+)'", body))
    assert called == set(declared)
    assert used <= set(declared), used - set(declared)


def test_a_clean_build_takes_five_agent_calls(clean):
    assert clean["result"]["status"] == "done"
    assert clean["labels"] == ["clerk:init", "build", "verify:r1", "clerk:gaps:r1", "clerk:report"]
    assert clean["phases"] == ["Index", "Build", "Verify", "Report"]
    assert clean["result"]["agent_calls"] == {"total": 5, "by": {"clerk": 3, "builder": 1, "verifier": 1}}
    assert clean["commands"][0] == "init --spec '/p/docs/spec.md' --run 'r' --max-rounds 3 --timeout 300"
    assert clean["result"]["concerns"] == ["R-002 has no acceptance criteria"]


def test_agents_get_their_types_and_models(clean):
    o = clean["options"]
    assert o["build"]["agentType"] == "squire:builder" and o["build"]["model"] == "opus"
    assert o["verify:r1"]["agentType"] == "squire:verifier"
    assert o["clerk:init"]["effort"] == "low"


def test_the_verifier_sees_the_spec_and_code_but_never_the_builders_notes(clean):
    p = clean["prompts"]["verify:r1"]
    assert "/p/squire-runs/r/spec.md" in p and "/p/squire-runs/r/index.json" in p
    assert "git diff base0000000000..HEAD" in p
    assert "check --run 'r' --round 1" in p
    assert "secret builder notes" not in p and "tests_added" not in p


def test_builder_and_fixer_are_told_to_stay_on_the_spec():
    d = _run("fix-then-clean")
    for label in ("build", "fix:r1"):
        assert "no requirement IDs in production code" in d["prompts"][label]
        assert "does not require" in d["prompts"][label]
    assert "/p/squire-runs/r/verify/gaps-r1.json" in d["prompts"]["fix:r1"]
    assert "and nothing else" in d["prompts"]["fix:r1"]


def test_fix_then_clean():
    d = _run("fix-then-clean")
    assert d["labels"] == ["clerk:init", "build", "verify:r1", "clerk:gaps:r1", "fix:r1",
                           "verify:r2", "clerk:gaps:r2", "clerk:report"]
    assert d["result"]["status"] == "done" and d["result"]["rounds"] == 2
    assert any("the fixer disputed G1-2" in c for c in d["result"]["concerns"])


def test_three_fix_rounds_then_the_report():
    d = _run("round-cap")
    assert [x for x in d["labels"] if x.startswith("fix:")] == ["fix:r1", "fix:r2", "fix:r3"]
    assert [x for x in d["labels"] if x.startswith("verify:")] == ["verify:r1", "verify:r2", "verify:r3", "verify:r4"]
    assert d["result"]["status"] == "done_with_gaps"
    assert any("gaps still open after 3 fix rounds: 1" in c for c in d["result"]["concerns"])


def test_max_rounds_zero_reports_without_fixing():
    d = _run("no-rounds")
    assert not any(x.startswith("fix:") for x in d["labels"])
    assert d["result"]["status"] == "done_with_gaps"


def test_a_refused_verifier_file_gets_one_retry_with_the_errors():
    d = _run("refused-then-accepted")
    assert d["labels"][2:6] == ["verify:r1", "clerk:gaps:r1", "verify:r1:retry", "clerk:gaps:r1:retry"]
    assert "R-002: no verdict" in d["prompts"]["verify:r1:retry"]
    assert d["result"]["status"] == "done"


def test_refused_twice_is_reported_as_unverified():
    d = _run("refused-twice")
    assert d["result"]["status"] == "unverified"
    assert not any(x.startswith("fix:") for x in d["labels"])
    assert d["labels"][-1] == "clerk:report"


def test_init_refusal_stops_before_any_builder():
    d = _run("init-stop")
    assert d["labels"] == ["clerk:init"]
    assert d["result"]["status"] == "stopped"
    assert "uncommitted changes" in d["result"]["message"]


def test_a_builder_crash_still_verifies_and_reports():
    d = _run("builder-dies")
    assert "verify:r1" in d["labels"] and d["labels"][-1] == "clerk:report"
    assert any("build failed: agent crashed" in c for c in d["result"]["concerns"])


def test_custom_checks_are_passed_to_init_quoted():
    d = _run("custom-checks")
    assert d["commands"][0].endswith("--check 'make test' --check 'go test -run '\\''X'\\'''")
