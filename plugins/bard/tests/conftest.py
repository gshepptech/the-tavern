"""Shared fixtures: a planned bard run with two slice files, screenshots on disk,
and a report that passes validation, plus a helper that runs the CLI in-process."""

from __future__ import annotations

import copy
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "scripts"))

import bard  # noqa: E402

URL = "http://localhost:3000"


def j(root: Path, *args: str) -> dict:
    buf = io.StringIO()
    with redirect_stdout(buf):
        bard.main(["--root", str(root), *args])
    return json.loads(buf.getvalue().strip().splitlines()[-1])


def finding(**over) -> dict:
    f = {
        "title": "Pay button is unreachable by keyboard",
        "lens": "accessibility",
        "severity": "blocker",
        "url": f"{URL}/cart",
        "steps": ["Open /cart with one item", "Press Tab from the top", "Focus skips Pay"],
        "expected": "Pay receives focus",
        "actual": "Pay never receives focus",
        "evidence": ["screenshots/s01-01.png"],
        "signals": [],
        "suggested_fix": "Make Pay a button element",
    }
    f.update(over)
    return f


SLICE_1 = {"slice": "s01", "persona": "keyboard-only", "area": "Cart",
           "tasks": [{"task": "Pay for the cart", "outcome": "failed", "note": ""}],
           "findings": [finding(), finding(title="Coupon error says only 'Error'", lens="copy", severity="minor",
                                           evidence=["screenshots/s01-02.png"])],
           "blocked": ""}
SLICE_2 = {"slice": "s02", "persona": "mobile", "area": "Search",
           "tasks": [{"task": "Find a product", "outcome": "completed", "note": ""}],
           "findings": [finding(title="Search results request fails silently", lens="silent-failure", severity="major",
                                url=f"{URL}/search", evidence=["screenshots/s02-01.png"],
                                signals=["GET /api/search?q=x -> 500"])],
           "blocked": ""}

REPORT = {
    "summary": "Keyboard users cannot pay. Search fails quietly on errors.",
    "slices": [{"id": "s01", "status": "done", "findings": 2}, {"id": "s02", "status": "done", "findings": 1}],
    "findings": [
        {**finding(), "id": "UX-001", "rank": 1, "lenses": ["accessibility", "task-completion"],
         "personas": ["keyboard-only"], "areas": ["Cart"], "sources": ["s01#1"]},
        {**SLICE_2["findings"][0], "id": "UX-002", "rank": 2, "lenses": ["silent-failure"],
         "personas": ["mobile"], "areas": ["Search"], "sources": ["s02#1"]},
        {**SLICE_1["findings"][1], "id": "UX-003", "rank": 3, "lenses": ["copy"],
         "personas": ["keyboard-only"], "areas": ["Cart"], "sources": ["s01#2"]},
    ],
}
for f in REPORT["findings"]:
    f.pop("lens", None)


def write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


@pytest.fixture
def run(tmp_path) -> Path:
    """A run planned with two personas in two areas, capped at two slices, with both slice files written."""
    out = j(tmp_path, "init", URL, "--personas", "keyboard-only,mobile", "--areas", "Cart=/cart,Search=/search",
            "--max-slices", "2")
    assert out["ok"], out
    d = Path(out["run_dir"])
    plan = j(tmp_path, "plan", "--run", str(d))
    assert [(s["id"], s["persona"], s["area"]) for s in plan["slices"]] == [("s01", "keyboard-only", "Cart"), ("s02", "mobile", "Search")]
    for name in ("s01-01.png", "s01-02.png", "s02-01.png"):
        (d / "screenshots" / name).write_bytes(b"\x89PNG\r\n")
    write_json(d / "slices" / "s01.json", SLICE_1)
    write_json(d / "slices" / "s02.json", SLICE_2)
    return d


@pytest.fixture
def report() -> dict:
    return copy.deepcopy(REPORT)
