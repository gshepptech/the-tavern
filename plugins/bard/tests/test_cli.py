"""init and plan: arguments, personas, areas, and the slice order under a cap."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import URL, j
from bard import PERSONAS, interleave, parse_personas


def test_init_uses_the_four_default_personas_and_ignores_its_own_directory(tmp_path):
    out = j(tmp_path, "init", URL)
    assert out["ok"]
    assert [p["key"] for p in out["personas"]] == ["first-time", "power-user", "keyboard-only", "mobile"]
    assert out["max_slices"] == 12 and out["read_only"] is False and out["areas"] == []
    d = Path(out["run_dir"])
    assert (d / "screenshots").is_dir() and (d / "slices").is_dir()
    assert (tmp_path / ".bard" / ".gitignore").read_text() == "*\n"
    assert json.loads((d / "run.json").read_text())["url"] == URL


@pytest.mark.parametrize("argv, message", [
    ([], "usage"),
    (["localhost:3000"], "usage"),
    (["ftp://example.com"], "usage"),
    ([URL, "--max-slices", "0"], "--max-slices must be between 1 and 40"),
    ([URL, "--personas", "wizard"], "unknown persona 'wizard'"),
    ([URL, "--personas", "Admin:"], "needs 'name: description'"),
])
def test_init_refusals(tmp_path, argv, message):
    out = j(tmp_path, "init", *argv)
    assert out["ok"] is False and message in out["stop"]


def test_custom_personas_and_flags(tmp_path):
    out = j(tmp_path, "init", URL, "--personas", "mobile,Clinic admin: books for three doctors,mobile",
            "--read-only", "--login", "demo@example.com / demo")
    assert [p["key"] for p in out["personas"]] == ["mobile", "clinic-admin"]
    assert out["personas"][1]["who"] == "books for three doctors"
    assert out["read_only"] is True and out["login"] == "demo@example.com / demo"


def test_builtin_personas_carry_a_viewport_and_constraints():
    for key, p in PERSONAS.items():
        assert p["viewport"].count("x") == 1, key
        assert p["who"] and p["jobs"] and p["constraints"], key
    assert parse_personas("mobile")[0]["viewport"] == "390x844"


def test_interleave_spreads_a_cap_over_every_persona_and_area():
    personas = parse_personas("first-time,power-user,keyboard-only")
    areas = [{"name": n, "url": f"{URL}/{n}"} for n in ("a", "b", "c", "d")]
    full = interleave(personas, areas, 40)
    assert len(full) == 12 and len({(s["persona"], s["area"]) for s in full}) == 12
    capped = interleave(personas, areas, 4)
    assert {s["persona"] for s in capped} == {"first-time", "power-user", "keyboard-only"}
    assert {s["area"] for s in capped[:3]} == {"a", "b", "c"}
    assert capped[0]["file"] == "slices/s01.json" and capped[0]["screenshot_prefix"] == "screenshots/s01-"


def test_plan_from_mapped_areas_resolves_paths_and_stays_on_host(tmp_path):
    d = j(tmp_path, "init", URL, "--personas", "mobile")["run_dir"]
    out = j(tmp_path, "plan", "--run", d, "--areas-json", json.dumps([{"name": "Search", "url": "/search"}]))
    assert out["slices"][0]["url"] == f"{URL}/search" and out["skipped"] == 0
    off = j(tmp_path, "plan", "--run", d, "--areas-json", json.dumps([{"name": "Docs", "url": "https://elsewhere.example/docs"}]))
    assert off["ok"] is False and "must stay on localhost:3000" in off["stop"]
    bad = j(tmp_path, "plan", "--run", d, "--areas-json", "[{\"name\": \"x\"}]")
    assert bad["ok"] is False and "list of" in bad["stop"]


def test_plan_without_areas_reviews_the_home_page_and_reports_what_the_cap_skipped(tmp_path):
    d = j(tmp_path, "init", URL, "--max-slices", "3")["run_dir"]
    out = j(tmp_path, "plan", "--run", d)
    assert [s["area"] for s in out["slices"]] == ["Home"] * 3 and out["skipped"] == 1


def test_an_unknown_run_is_a_stop(tmp_path):
    out = j(tmp_path, "validate", "--run", "nowhere", "--report")
    assert out["ok"] is False and "no bard run" in out["stop"]
