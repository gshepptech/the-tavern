#!/usr/bin/env python3
"""bard's code steps. Every command prints one JSON line.

    bard [--root DIR] init <url> [--personas LIST] [--areas LIST] [--max-slices N] [--read-only] [--login TEXT]
    bard [--root DIR] plan --run DIR [--areas-json JSON]
    bard [--root DIR] validate --run DIR (--slice ID | --report)
    bard [--root DIR] render --run DIR

The persona drivers and the synthesizer are agents; what a finding must
contain, which slices exist and how the report reads are decided here.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

from report import SEVERITIES, is_text, render, validate_report, validate_slice  # noqa: E402

RUNS = ".bard/runs"
DEFAULT_PERSONAS = ("first-time", "power-user", "keyboard-only", "mobile")
MAX_SLICES = 40

PERSONAS = {
    "first-time": {
        "name": "First-time user",
        "who": "Has never seen the product and arrived from a link. Reads headings and buttons, not documentation.",
        "jobs": "Work out what the product is for, then complete its main task without help.",
        "viewport": "1280x800",
        "constraints": "Uses the mouse. Gives up on anything that needs prior knowledge of the product's terms.",
    },
    "power-user": {
        "name": "Power user",
        "who": "Uses the product daily and wants to get through repeated work quickly.",
        "jobs": "Do the main task several times in a row, use search, filters, bulk actions and shortcuts where offered.",
        "viewport": "1440x900",
        "constraints": "Notices extra clicks, lost state on back navigation, slow responses and settings that do not stick.",
    },
    "keyboard-only": {
        "name": "Keyboard-only user",
        "who": "Cannot use a pointing device.",
        "jobs": "Complete the main task with Tab, Shift+Tab, Enter, Space, Escape and arrow keys only.",
        "viewport": "1280x800",
        "constraints": "Never clicks. Needs a visible focus indicator, a sensible tab order, and dialogs that trap and return focus.",
    },
    "mobile": {
        "name": "Mobile user",
        "who": "On a phone, one-handed, on a small screen.",
        "jobs": "Complete the main task on a narrow viewport.",
        "viewport": "390x844",
        "constraints": "Needs tap targets of about 44px, no horizontal scrolling, and content not hidden behind fixed bars.",
    },
    "low-vision": {
        "name": "Low-vision user",
        "who": "Reads at 200% zoom and relies on contrast and text labels.",
        "jobs": "Read the main content and complete the main task with the page zoomed.",
        "viewport": "640x400",
        "constraints": "The viewport is half size to stand in for 200% zoom. Needs text that reflows, sufficient contrast, and meaning not carried by colour alone.",
    },
}


class Stop(Exception):
    """A refusal the user can act on."""


def emit(obj: dict) -> None:
    print(json.dumps(obj, separators=(",", ":")))


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "x"


def load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def run_path(root: Path, run: str) -> Path:
    d = Path(run)
    d = d if d.is_absolute() else root / d
    if not (d / "run.json").exists():
        raise Stop(f"no bard run at {run}")
    return d


# ------------------------------------------------------------------ personas and areas

def parse_personas(spec: str | None) -> list[dict]:
    """Built-in keys, or custom 'name: who they are and what they need' entries, comma separated."""
    entries = [e.strip() for e in (spec.split(",") if spec else DEFAULT_PERSONAS) if e.strip()]
    out, seen = [], set()
    for e in entries:
        if ":" in e:
            name, who = (x.strip() for x in e.split(":", 1))
            if not name or not who:
                raise Stop(f"custom persona {e!r} needs 'name: description'")
            p = {"key": slug(name), "name": name, "who": who, "jobs": "Complete the tasks this person comes to the product for.",
                 "viewport": "1280x800", "constraints": ""}
        elif e in PERSONAS:
            p = {"key": e, **PERSONAS[e]}
        else:
            raise Stop(f"unknown persona {e!r}; built-in personas are {', '.join(PERSONAS)}, or give 'name: description'")
        if p["key"] in seen:
            continue
        seen.add(p["key"])
        out.append(p)
    if not out:
        raise Stop("no personas given")
    return out


def parse_areas(spec: str | None, base: str) -> list[dict]:
    """'Name=/path' or '/path' entries, comma separated, resolved against the app URL."""
    out = []
    for e in (spec or "").split(","):
        e = e.strip()
        if not e:
            continue
        name, _, path = e.partition("=") if "=" in e else (e, "", e)
        out.append({"name": name.strip(), "url": urljoin(base, path.strip())})
    return out


def interleave(personas: list[dict], areas: list[dict], cap: int) -> list[dict]:
    """Every persona x area pair, ordered so a cap still spreads over all personas and all areas.

    Round r gives persona p the area (p + r) mod A, so the first round already
    covers min(P, A) different areas with every persona."""
    order = []
    for r in range(len(areas)):
        for p_i, p in enumerate(personas):
            order.append((p, areas[(p_i + r) % len(areas)]))
    slices = []
    for n, (p, a) in enumerate(order[:cap], 1):
        slices.append({"id": f"s{n:02d}", "persona": p["key"], "area": a["name"], "url": a["url"], "viewport": p["viewport"],
                       "file": f"slices/s{n:02d}.json", "screenshot_prefix": f"screenshots/s{n:02d}-"})
    return slices


# ------------------------------------------------------------------ commands

def cmd_init(root: Path, a: argparse.Namespace) -> dict:
    if not a.url or urlparse(a.url).scheme not in ("http", "https") or not urlparse(a.url).netloc:
        raise Stop("usage: /bard:run <http(s) url of the running app> [--personas LIST] [--areas LIST] [--max-slices N] [--read-only] [--login TEXT]")
    if not 1 <= a.max_slices <= MAX_SLICES:
        raise Stop(f"--max-slices must be between 1 and {MAX_SLICES}")
    personas = parse_personas(a.personas)
    areas = parse_areas(a.areas, a.url)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    d = root / RUNS / f"{stamp}-{slug(urlparse(a.url).netloc)}"
    if d.exists():
        raise Stop(f"{d} already exists; wait a second and run again")
    (d / "screenshots").mkdir(parents=True)
    (d / "slices").mkdir()
    (root / ".bard" / ".gitignore").write_text("*\n", encoding="utf-8")
    run = {"url": a.url, "created": time.strftime("%Y-%m-%d %H:%M"), "personas": personas, "areas": areas,
           "max_slices": a.max_slices, "read_only": a.read_only, "login": a.login or ""}
    write_json(d / "run.json", run)
    return {"ok": True, "run_dir": str(d), **run}


def cmd_plan(root: Path, a: argparse.Namespace) -> dict:
    d = run_path(root, a.run)
    run = load(d / "run.json")
    areas = run["areas"]
    if a.areas_json:
        try:
            given = json.loads(a.areas_json)
        except json.JSONDecodeError as e:
            raise Stop(f"--areas-json is not valid JSON: {e}")
        if not isinstance(given, list) or not all(isinstance(x, dict) and is_text(x.get("name")) and is_text(x.get("url")) for x in given):
            raise Stop("--areas-json must be a list of {\"name\", \"url\"} objects")
        areas = [{"name": x["name"].strip(), "url": urljoin(run["url"], x["url"].strip())} for x in given]
    if not areas:
        areas = [{"name": "Home", "url": run["url"]}]
    host = urlparse(run["url"]).netloc
    off = [x["url"] for x in areas if urlparse(x["url"]).netloc != host]
    if off:
        raise Stop(f"areas must stay on {host}: {', '.join(off)}")
    slices = interleave(run["personas"], areas, run["max_slices"])
    plan = {**run, "areas": areas, "slices": slices,
            "skipped": len(run["personas"]) * len(areas) - len(slices)}
    write_json(d / "plan.json", plan)
    return {"ok": True, "slices": slices, "skipped": plan["skipped"], "file": str(d / "plan.json")}


def cmd_validate(root: Path, a: argparse.Namespace) -> dict:
    d = run_path(root, a.run)
    if a.slice:
        f = d / "slices" / f"{a.slice}.json"
        kind, check = "slice", lambda data: validate_slice(data, d, a.slice)
    else:
        if not (d / "plan.json").exists():
            raise Stop("run `bard plan` first")
        f = d / "report.json"
        kind, check = "report", lambda data: validate_report(data, d, load(d / "plan.json"))
    if not f.exists():
        return {"ok": True, "valid": False, "kind": kind, "errors": [f"{f.name} was not written"]}
    try:
        data = load(f)
    except json.JSONDecodeError as e:
        return {"ok": True, "valid": False, "kind": kind, "errors": [f"{f.name} is not valid JSON: {e}"]}
    errors = check(data)
    found = len(data.get("findings", [])) if isinstance(data, dict) and isinstance(data.get("findings"), list) else 0
    return {"ok": True, "valid": not errors, "kind": kind, "errors": errors, "findings": found}


def cmd_render(root: Path, a: argparse.Namespace) -> dict:
    d = run_path(root, a.run)
    v = cmd_validate(root, argparse.Namespace(run=a.run, slice=None))
    if not v["valid"]:
        return {"ok": False, "stop": "the report does not pass validation", "errors": v["errors"]}
    data, plan = load(d / "report.json"), load(d / "plan.json")
    (d / "report.md").write_text(render(data, plan), encoding="utf-8")
    counts = {s: sum(1 for f in data["findings"] if f["severity"] == s) for s in SEVERITIES}
    top = [{"id": f["id"], "severity": f["severity"], "title": f["title"]} for f in data["findings"][:5]]
    return {"ok": True, "report": str(d / "report.md"), "counts": counts, "top": top}


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bard")
    p.add_argument("--root", default=".")
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("init")
    s.add_argument("url", nargs="?")
    s.add_argument("--personas")
    s.add_argument("--areas")
    s.add_argument("--max-slices", type=int, default=12)
    s.add_argument("--read-only", action="store_true")
    s.add_argument("--login")
    s = sub.add_parser("plan")
    s.add_argument("--run", required=True)
    s.add_argument("--areas-json")
    s = sub.add_parser("validate")
    s.add_argument("--run", required=True)
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--slice")
    g.add_argument("--report", action="store_true")
    s = sub.add_parser("render")
    s.add_argument("--run", required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    try:
        a = parser().parse_args(argv)
    except SystemExit as e:
        emit({"ok": False, "stop": "could not parse the arguments; see /bard:help"})
        return int(e.code or 1)
    root = Path(a.root).resolve()
    handler = {"init": cmd_init, "plan": cmd_plan, "validate": cmd_validate, "render": cmd_render}[a.command]
    try:
        emit(handler(root, a))
        return 0
    except Stop as e:
        emit({"ok": False, "stop": str(e)})
        return 0
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as e:
        emit({"ok": False, "error": f"{type(e).__name__}: {e}"})
        return 1


if __name__ == "__main__":
    sys.exit(main())
