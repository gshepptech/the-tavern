"""What a bard finding must contain, checked in code, and how the report reads.

A finding nobody can reproduce is not a finding. Every one, in a slice file
or in the final report, needs the page it happened on, steps to reproduce,
what was expected and what happened, a severity from a fixed set, at least one
screenshot that exists in the run directory, and a suggested fix. The report
must also be ranked by severity, free of duplicate titles, traceable to the
slice findings it came from (none dropped), and honest about slices that did
not run.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

SEVERITIES = ("blocker", "major", "minor", "polish")
LENSES = ("task-completion", "copy", "feedback", "states", "accessibility", "responsive", "silent-failure")
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}
SLICE_STATUS = ("done", "blocked", "missing")


# ------------------------------------------------------------------ validation

def is_text(v: object) -> bool:
    return isinstance(v, str) and bool(v.strip())


def _evidence(paths: object, run_dir: Path, where: str) -> list[str]:
    if not isinstance(paths, list) or not paths:
        return [f"{where}: evidence must list at least one screenshot path"]
    errors = []
    for p in paths:
        if not is_text(p):
            errors.append(f"{where}: evidence entries must be paths")
            continue
        rel = Path(p)
        if rel.is_absolute() or ".." in rel.parts:
            errors.append(f"{where}: evidence {p!r} must be relative to the run directory")
        elif rel.suffix.lower() not in IMAGE_EXT:
            errors.append(f"{where}: evidence {p!r} is not an image ({', '.join(sorted(IMAGE_EXT))})")
        elif not (run_dir / rel).is_file():
            errors.append(f"{where}: evidence {p!r} does not exist in the run directory")
    return errors


def _finding(f: object, run_dir: Path, where: str, lens_key: str) -> list[str]:
    if not isinstance(f, dict):
        return [f"{where}: must be an object"]
    errors = []
    for key in ("title", "expected", "actual", "suggested_fix"):
        if not is_text(f.get(key)):
            errors.append(f"{where}: '{key}' is required")
    if f.get("severity") not in SEVERITIES:
        errors.append(f"{where}: severity {f.get('severity')!r} is not one of {', '.join(SEVERITIES)}")
    lenses = f.get(lens_key)
    lenses = [lenses] if isinstance(lenses, str) else lenses
    if not isinstance(lenses, list) or not lenses or any(x not in LENSES for x in lenses):
        errors.append(f"{where}: '{lens_key}' must be from {', '.join(LENSES)}, got {f.get(lens_key)!r}")
    steps = f.get("steps")
    if not isinstance(steps, list) or not steps or not all(is_text(s) for s in steps):
        errors.append(f"{where}: 'steps' must list the steps to reproduce, one string each")
    if not (isinstance(f.get("url"), str) and urlparse(f["url"]).scheme in ("http", "https")):
        errors.append(f"{where}: 'url' must be the http(s) page where it happens")
    if not isinstance(f.get("signals", []), list):
        errors.append(f"{where}: 'signals' must be a list of console or network lines")
    return errors + _evidence(f.get("evidence"), run_dir, where)


def validate_slice(data: object, run_dir: Path, slice_id: str) -> list[str]:
    if not isinstance(data, dict):
        return ["the slice file must be a JSON object"]
    errors = []
    if data.get("slice") != slice_id:
        errors.append(f"'slice' must be {slice_id!r}")
    tasks = data.get("tasks")
    if not isinstance(tasks, list) or not tasks and not is_text(data.get("blocked")):
        errors.append("'tasks' must list what the persona attempted, unless 'blocked' says why nothing could be")
    for n, t in enumerate(tasks or []):
        if not isinstance(t, dict) or not is_text(t.get("task")) or t.get("outcome") not in ("completed", "failed", "abandoned"):
            errors.append(f"tasks[{n}]: needs 'task' and an 'outcome' of completed, failed or abandoned")
    findings = data.get("findings")
    if not isinstance(findings, list):
        return errors + ["'findings' must be a list (empty when nothing was found)"]
    for n, f in enumerate(findings):
        errors += _finding(f, run_dir, f"findings[{n}]", "lens")
    return errors


def validate_report(data: object, run_dir: Path, plan: dict) -> list[str]:
    if not isinstance(data, dict):
        return ["the report must be a JSON object"]
    errors = []
    if not is_text(data.get("summary")):
        errors.append("'summary' is required")
    planned = {s["id"] for s in plan.get("slices", [])}
    personas = {p["key"] for p in plan.get("personas", [])}
    listed = data.get("slices")
    if not isinstance(listed, list):
        listed, errors = [], [*errors, "'slices' must list every planned slice"]
    for n, s in enumerate(listed):
        if not isinstance(s, dict) or s.get("status") not in SLICE_STATUS:
            errors.append(f"slices[{n}]: needs 'id' and a 'status' of {', '.join(SLICE_STATUS)}")
    covered = {s.get("id") for s in listed if isinstance(s, dict)}
    for sid in sorted(planned - covered):
        errors.append(f"slice {sid} is planned but missing from 'slices'; list it, with status blocked or missing if it did not run")
    raw = _slice_findings(run_dir, planned)
    findings = data.get("findings")
    if not isinstance(findings, list):
        return errors + ["'findings' must be a list"]
    ids, titles, last = set(), {}, -1
    for n, f in enumerate(findings):
        where = f.get("id", f"findings[{n}]") if isinstance(f, dict) else f"findings[{n}]"
        errors += _finding(f, run_dir, where, "lenses")
        if not isinstance(f, dict):
            continue
        if not re.fullmatch(r"UX-\d{3}", str(f.get("id"))):
            errors.append(f"{where}: id must look like UX-001")
        elif f["id"] in ids:
            errors.append(f"{where}: duplicate id")
        ids.add(f.get("id"))
        if f.get("rank") != n + 1:
            errors.append(f"{where}: rank must be {n + 1}; findings are listed in rank order")
        if f.get("severity") in SEVERITIES:
            sev = SEVERITIES.index(f["severity"])
            if sev < last:
                errors.append(f"{where}: a {f['severity']} finding is ranked below a less severe one")
            last = max(last, sev)
        title = str(f.get("title", "")).strip().lower()
        if title and title in titles:
            errors.append(f"{where}: same title as {titles[title]}; merge duplicates into one finding")
        titles.setdefault(title, where)
        who = f.get("personas")
        if not isinstance(who, list) or not who:
            errors.append(f"{where}: 'personas' must name who hit it")
        elif any(p not in personas for p in who):
            errors.append(f"{where}: 'personas' must use the run's persona keys ({', '.join(sorted(personas))})")
        src = f.get("sources")
        if not isinstance(src, list) or not src:
            errors.append(f"{where}: 'sources' must name the slice findings it came from, such as s03#1")
            continue
        for ref in src:
            if raw.get(ref):
                errors.append(f"{where}: source {ref!r} is already cited by another finding; merge them")
            elif ref in raw:
                raw[ref] = True
            else:
                errors.append(f"{where}: source {ref!r} is not a finding in any slice file")
    for ref, used in raw.items():
        if not used:
            errors.append(f"slice finding {ref} is in no report finding's 'sources'; merge it or list it, never drop it")
    return errors


def _slice_findings(run_dir: Path, planned: set[str]) -> dict[str, bool]:
    """Every finding in the run's slice files, as '<slice>#<n>', mapped to whether the report cites it yet."""
    refs: dict[str, bool] = {}
    for sid in sorted(planned):
        f = run_dir / "slices" / f"{sid}.json"
        try:
            found = json.loads(f.read_text(encoding="utf-8")).get("findings", [])
        except (OSError, ValueError, AttributeError):
            continue
        for n in range(1, len(found) + 1 if isinstance(found, list) else 1):
            refs[f"{sid}#{n}"] = False
    return refs


# ------------------------------------------------------------------ rendering

def render(data: dict, plan: dict) -> str:
    personas = {p["key"]: p["name"] for p in plan.get("personas", [])}
    findings = data["findings"]
    counts = {s: sum(1 for f in findings if f["severity"] == s) for s in SEVERITIES}
    md = [f"# UX review: {plan['url']}", "",
          f"Generated {plan.get('created', '')}. Personas: {', '.join(personas.values())}. "
          f"Slices run: {sum(1 for s in data['slices'] if s.get('status') == 'done')} of {len(plan['slices'])}.", "",
          "## Summary", "", data["summary"].strip(), "",
          "| Severity | Findings |", "|---|---|"]
    md += [f"| {s} | {counts[s]} |" for s in SEVERITIES]
    md += ["", "## Findings"]
    if not findings:
        md += ["", "No findings."]
    for f in findings:
        who = ", ".join(personas.get(p, p) for p in f["personas"])
        lenses = f["lenses"] if isinstance(f["lenses"], list) else [f["lenses"]]
        md += ["", f"### {f['rank']}. {f['id']} [{f['severity']}] {f['title']}", "",
               f"- Where: {f['url']}" + (f" ({', '.join(f['areas'])})" if f.get("areas") else ""),
               f"- Who hit it: {who}", f"- Lens: {', '.join(lenses)}", "",
               "**Steps to reproduce**", ""]
        md += [f"{n}. {s}" for n, s in enumerate(f["steps"], 1)]
        md += ["", f"**Expected:** {f['expected']}", "", f"**Actual:** {f['actual']}", ""]
        md += [f"![{f['id']} screenshot {n}]({p})" for n, p in enumerate(f["evidence"], 1)]
        if f.get("signals"):
            md += ["", "**Console and network:**", ""] + [f"- `{s}`" for s in f["signals"]]
        md += ["", f"**Suggested fix:** {f['suggested_fix']}"]
    md += ["", "## Coverage", "", "| Slice | Persona | Area | Status | Findings |", "|---|---|---|---|---|"]
    by_id = {s["id"]: s for s in data["slices"] if isinstance(s, dict)}
    for s in plan["slices"]:
        got = by_id.get(s["id"], {})
        status = got.get("status", "missing")
        if got.get("note"):
            status += f": {got['note']}"
        md.append(f"| {s['id']} | {personas.get(s['persona'], s['persona'])} | {s['area']} | {status} | {got.get('findings', 0)} |")
    return "\n".join(md) + "\n"
