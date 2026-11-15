"""validate-spec.py: the checks a spec must pass, the seal, and the phase report."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[1]
SCRIPT = PLUGIN / "scripts" / "validate-spec.py"
WRAPPER = PLUGIN / "scripts" / "sage"
TEMPLATE = (PLUGIN / "templates" / "spec.md").read_text(encoding="utf-8")

_spec = importlib.util.spec_from_file_location("validate_spec", SCRIPT)
vs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vs)


def rules(text: str) -> list[str]:
    return [e["rule"] for e in vs.check_text(text)["errors"]]


def write(tmp_path: Path, text: str, name: str = "spec.md") -> Path:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)


def test_the_shipped_template_passes():
    report = vs.check_text(TEMPLATE)
    assert report["ok"], report["errors"]
    assert report["counts"] == {"requirements": 3, "criteria": 8, "answers": 3, "facts": 3}
    assert [w["rule"] for w in report["warnings"]] == ["source-unused"]


@pytest.mark.parametrize(
    "old, new, rule",
    [
        ("Source: A-002, F-002\n", "", "requirement-source"),
        ("Source: A-003\n", "Source: A-009\n", "source-missing"),
        ("Acceptance:\n- A request with no session gets HTTP 401 and no CSV body.\n"
         "- A request from a non-admin session gets HTTP 403 and no CSV body.\n", "", "requirement-criteria"),
        ("- The response `Content-Type` is `text/csv; charset=utf-8`.",
         "- The export works correctly for every order.", "criterion-vague"),
        ("- The response `Content-Type` is `text/csv; charset=utf-8`.", "- It downloads.", "criterion-short"),
        ("### R-003: Columns", "### R-002: Columns", "duplicate-id"),
        ("### R-003: Columns", "### Columns", "requirement-id"),
        ("### R-003: Columns", "### R-003:", "requirement-title"),
        ("### A-003\n", "### A-002\n", "duplicate-id"),
        ("(`internal/server/routes.go:31`)", "(the routes file)", "fact-evidence"),
        ("- None\n", "- Should totals include tax?\n", "open-question"),
        ("- No export formats other than CSV.\n- No background jobs; the export is generated within the request.\n",
         "Nothing excluded.\n", "non-goals"),
        ("one row per order.", "one row per order (TODO: refunds).", "placeholder"),
        ("## Non-goals", "## Out of scope", "section"),
        ("status: draft", "status: final", "frontmatter"),
        ("status: draft", "status: sealed", "seal"),
    ],
)
def test_each_rule_fails_the_spec(old, new, rule):
    assert old in TEMPLATE, old
    assert rule in rules(TEMPLATE.replace(old, new, 1))


def test_a_spec_with_no_frontmatter_fails():
    assert "frontmatter" in rules(TEMPLATE.split("---\n", 2)[2])


def test_a_requirement_must_have_a_statement():
    text = TEMPLATE.replace(
        "The export MUST be reachable only through the existing admin middleware.\n\n", "", 1)
    assert "requirement-statement" in rules(text)


def test_ids_inside_code_fences_are_not_parsed():
    fenced = "\n```\n### R-001: inside a fence\n```\n"
    text = TEMPLATE.replace("## Non-goals", fenced + "\n## Non-goals", 1)
    assert vs.check_text(text)["ok"]


def test_hash_ignores_the_seal_line_only():
    sealed = vs.set_frontmatter(TEMPLATE, "sealed_by", "validate-spec.py sha256:" + "a" * 64)
    assert vs.spec_sha256(sealed) == vs.spec_sha256(TEMPLATE)
    assert vs.spec_sha256(TEMPLATE.replace("CSV", "TSV")) != vs.spec_sha256(TEMPLATE)


def test_seal_marks_the_spec_and_verify_passes(tmp_path):
    spec = write(tmp_path, TEMPLATE)
    r = run("seal", str(spec))
    assert r.returncode == 0, r.stderr
    text = spec.read_text(encoding="utf-8")
    assert vs.frontmatter(text)["status"] == "sealed"
    assert vs.seal_state(text) == "valid"
    assert run("verify-seal", str(spec)).returncode == 0
    assert vs.check_text(text)["ok"]


def test_sealing_twice_is_a_no_op(tmp_path):
    spec = write(tmp_path, TEMPLATE)
    assert vs.seal(spec, None)["ok"]
    first = spec.read_text(encoding="utf-8")
    r = vs.seal(spec, None)
    assert r["ok"] and "already sealed" in r["message"]
    assert spec.read_text(encoding="utf-8") == first


def test_a_failing_spec_is_never_sealed(tmp_path):
    bad = TEMPLATE.replace("Source: A-003\n", "")
    spec = write(tmp_path, bad)
    r = run("seal", str(spec))
    assert r.returncode == 1
    assert "requirement-source" in r.stderr
    assert spec.read_text(encoding="utf-8") == bad


def test_an_edit_after_sealing_breaks_the_seal(tmp_path):
    spec = write(tmp_path, TEMPLATE)
    assert vs.seal(spec, None)["ok"]
    spec.write_text(spec.read_text(encoding="utf-8").replace("exactly 3 data rows", "at least 3 data rows"))
    r = run("verify-seal", str(spec))
    assert r.returncode == 1 and "stale" in r.stderr
    assert "seal" in rules(spec.read_text(encoding="utf-8"))


def test_verify_refuses_an_unsealed_or_malformed_seal(tmp_path):
    assert vs.verify_seal(write(tmp_path, TEMPLATE))["message"].endswith("seal is absent")
    bad = vs.set_frontmatter(TEMPLATE.replace("status: draft", "status: sealed"), "sealed_by", "by hand")
    assert vs.verify_seal(write(tmp_path, bad, "b.md"))["message"].endswith("seal is malformed")


def test_seal_requires_a_passing_review_of_this_draft(tmp_path):
    spec = write(tmp_path, TEMPLATE)
    review = tmp_path / "review.json"
    draft_sha = vs.spec_sha256(TEMPLATE)

    review.write_text(json.dumps({"verdict": "block", "spec_sha256": draft_sha, "flags": []}))
    assert "not 'pass'" in vs.seal(spec, review)["message"]

    review.write_text(json.dumps({"verdict": "pass", "spec_sha256": "0" * 64, "flags": []}))
    assert "different draft" in vs.seal(spec, review)["message"]
    assert vs.frontmatter(spec.read_text())["status"] == "draft"

    review.write_text(json.dumps({"verdict": "pass", "spec_sha256": draft_sha, "flags": []}))
    assert vs.seal(spec, review)["ok"]


def test_the_seal_is_the_one_tinker_reads(tmp_path):
    """tinker checks Sage's seal itself before it builds; both sides must agree on the format."""
    tinker_seal = PLUGIN.parent / "tinker" / "scripts" / "seal.py"
    if not tinker_seal.is_file():
        pytest.skip("tinker is not beside sage")
    spec = write(tmp_path, TEMPLATE)
    assert vs.seal(spec, None)["ok"]
    r = subprocess.run([sys.executable, str(tinker_seal), "check", str(spec)], capture_output=True, text=True,
                       env={"TINKER_SAGE_VERIFIER": str(WRAPPER), "PATH": "/usr/bin:/bin"})
    assert r.returncode == 0 and r.stdout.startswith("SEAL_OK"), r.stdout + r.stderr


def test_wrapper_runs_the_script(tmp_path):
    spec = write(tmp_path, TEMPLATE)
    r = subprocess.run(["bash", str(WRAPPER), "check", str(spec)], capture_output=True, text=True)
    assert r.returncode == 0 and json.loads(r.stdout)["ok"]


@pytest.mark.parametrize(
    "files, phase",
    [
        ({}, "research"),
        ({"research.md": "### F-001\nx `a.py:1`\n"}, "interview"),
        ({"research.md": "", "interview.md": "### A-001\n", "spec.md": TEMPLATE}, "review"),
    ],
)
def test_status_reports_the_phase(tmp_path, files, phase):
    for name, text in files.items():
        write(tmp_path, text, name)
    assert vs.status(tmp_path)["phase"] == phase


def test_status_moves_from_review_to_seal_to_sealed(tmp_path):
    write(tmp_path, "### F-001\n### F-002\n", "research.md")
    write(tmp_path, "### A-001\n", "interview.md")
    spec = write(tmp_path, TEMPLATE)
    review = tmp_path / "review.json"
    review.write_text(json.dumps({"verdict": "pass", "spec_sha256": vs.spec_sha256(TEMPLATE)}))
    s = vs.status(tmp_path)
    assert (s["phase"], s["facts"], s["answers"], s["review_current"]) == ("seal", 2, 1, True)

    spec.write_text(TEMPLATE.replace("CSV", "csv"))
    assert vs.status(tmp_path)["phase"] == "review"

    spec.write_text(TEMPLATE)
    assert vs.seal(spec, review)["ok"]
    assert vs.status(tmp_path)["phase"] == "sealed"


def test_missing_spec_and_usage_errors():
    assert run("check", "/nonexistent/spec.md").returncode == 1
    assert run("bogus").returncode == 2
