"""Write a run's report: a verdict per requirement, what is still open, and how the rounds went."""

from __future__ import annotations

import json
import re
from pathlib import Path


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _rounds(run_dir: Path) -> list[int]:
    found = [int(m.group(1)) for p in (run_dir / "verify").glob("gaps-r*.json") if (m := re.match(r"gaps-r(\d+)\.json$", p.name))]
    return sorted(found)


def build(run_dir: Path) -> dict:
    """Render report.md and report.json for a run directory; return the summary."""
    state = _load(run_dir / "state.json")
    reqs = _load(run_dir / "index.json").get("requirements", [])
    rounds = _rounds(run_dir)
    last = rounds[-1] if rounds else 0
    verdicts = {r["id"]: r for r in _load(run_dir / "verify" / f"verify-r{last}.json").get("requirements", [])} if last else {}
    gaps = _load(run_dir / "verify" / f"gaps-r{last}.json").get("gaps", []) if last else []
    check = _load(run_dir / "verify" / f"check-r{last}.json") if last else {}
    history = [len(_load(run_dir / "verify" / f"gaps-r{n}.json").get("gaps", [])) for n in rounds]

    counts = {"MET": 0, "PARTIAL": 0, "MISSING": 0, "WRONG": 0, "NOT CHECKED": 0}
    rows = []
    for r in reqs:
        v = verdicts.get(r["id"])
        verdict = v["verdict"] if v else "NOT CHECKED"
        counts[verdict] = counts.get(verdict, 0) + 1
        detail = ", ".join(f"`{e}`" for e in v.get("evidence", [])) if v and verdict == "MET" else (v or {}).get("reason", "")
        rows.append((r["id"], r["title"], verdict, detail))

    other = [g for g in gaps if g["kind"] != "requirement"]
    clean = bool(rounds) and not gaps
    status = "done" if clean else "done_with_gaps"

    md = [f"# squire report: {state.get('run', run_dir.name)}", ""]
    md.append(f"- Spec: `{state.get('spec', '')}`")
    md.append(f"- Branch: `{state.get('branch', '')}`, base `{state.get('base', '')[:12]}`, head `{check.get('head', '')[:12]}`")
    md.append(f"- Result: **{'clean' if clean else 'open gaps remain'}** after {len(rounds)} verification round(s); "
              f"open gaps per round: {', '.join(map(str, history)) or 'none recorded'}")
    md.append(f"- Requirements: {counts['MET']} met, {counts['PARTIAL']} partial, {counts['MISSING']} missing, "
              f"{counts['WRONG']} wrong, {counts['NOT CHECKED']} not checked")
    md += ["", "## Requirements", "", "| ID | Requirement | Verdict | Evidence or reason |", "|---|---|---|---|"]
    for rid, title, verdict, detail in rows:
        md.append(f"| {rid} | {title.replace('|', '/')} | {verdict} | {str(detail).replace('|', '/')} |")

    if other:
        md += ["", "## Other open gaps", ""]
        for g in other:
            where = g.get("where") or g.get("command") or ", ".join(g.get("files", []))
            md.append(f"- **{g['kind']}** {where}: {g.get('what') or 'exit ' + str(g.get('exit'))}")

    commands = check.get("commands", [])
    if commands:
        md += ["", "## Checks at head", "", "| Command | Exit | At base |", "|---|---|---|"]
        base = state.get("baseline", {})
        for c in commands:
            md.append(f"| `{c['cmd']}` | {c['exit']} | {base.get(c['name'], 'not run')} |")
    pre = [c for c in commands if c["exit"] != 0 and state.get("baseline", {}).get(c["name"], 0) != 0]
    if pre:
        md += ["", "Failing at the base commit too, so not counted against this build: "
               + ", ".join(f"`{c['cmd']}`" for c in pre) + "."]

    text = "\n".join(md) + "\n"
    (run_dir / "report.md").write_text(text, encoding="utf-8")
    summary = {"status": status, "counts": counts, "rounds": len(rounds), "open": [g["id"] for g in gaps],
               "report": str(run_dir / "report.md")}
    (run_dir / "report.json").write_text(json.dumps({**summary, "requirements": rows, "gaps": gaps}, indent=2), encoding="utf-8")
    return summary
