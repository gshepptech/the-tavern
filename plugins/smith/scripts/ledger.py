#!/usr/bin/env python3
"""Smith's ledger: the state of one build, kept in a JSON file. Stdlib only.

The ledger is the only thing that decides whether a requirement is done. It
will not mark one done unless the verifier recorded, in the current round, a
passing check with the command it ran and the output it saw.

    ledger.py init SPEC [--run NAME] [--max-rounds N] [--max-parallel N]
    ledger.py plan --file PLAN_JSON
    ledger.py slice SLICE --status building|built|failed [--note TEXT]
    ledger.py owners FILE...
    ledger.py record REQ --verdict pass|fail --command CMD (--output TEXT | --output-file PATH)
                     [--exit N] [--location PATH:LINE]... [--reason TEXT]
    ledger.py done (REQ... | --all-passing)
    ledger.py round --touched FILE...
    ledger.py status
    ledger.py report

Every command takes `--root DIR` (default: the current directory) and every
command after `init` takes `--run NAME` (default: the newest run). Each prints
one JSON object. Exit 0 on success, 1 when the ledger refuses, 2 on usage.

State lives in <root>/.smith/runs/<run>/ledger.json, beside a frozen copy of
the spec.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ID = r"[A-Z][A-Z0-9]{0,7}-\d+(?:\.\d+)*"
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
SEAL_LINE_RE = re.compile(r"^sealed_by:.*\n", re.MULTILINE)
SEAL_VALUE_RE = re.compile(r"^sealed_by:\s*\S+\s+sha256:([0-9a-f]{64})\s*$", re.MULTILINE)
DEF_HEAD = re.compile(rf"^(#{{2,6}})\s+[*_`]*({ID})\b[*_`]*\s*:?\s*(.*)$")
DEF_ITEM = re.compile(rf"^(\s*)(?:[-*+]|\d+[.)])\s+[*_`\[]*({ID})\b[*_`\]]*\s*[:.)\-]?\s*(.*)$")
DEF_ROW = re.compile(rf"^\s*\|\s*[*_`]*({ID})\b[*_`]*\s*\|(.*)$")
DEF_LINE = re.compile(rf"^[*_`]*({ID})[*_`]*\s*[:.)]\s*(.*)$")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
BULLET_RE = re.compile(r"^(\s*)(?:[-*+]|\d+[.)])\s+(.*\S)\s*$")
ACCEPT_RE = re.compile(r"^\s*(?:#{1,6}\s+)?[*_]*acceptance(?:\s+criteria)?[*_]*\s*:?[*_]*\s*$", re.IGNORECASE)
APPENDIX_RE = re.compile(r"^#{1,2}\s+Appendix\b", re.IGNORECASE)
FENCE_RE = re.compile(r"^\s*(```|~~~)")

OUTPUT_LIMIT = 4000
REQ_STATUSES = ("pending", "passing", "failing", "done")


class Refused(Exception):
    """The ledger will not do what was asked; the message says why."""


# ---------------------------------------------------------------------------
# Spec parsing
# ---------------------------------------------------------------------------


def _spec_lines(text: str) -> list[str]:
    """Spec lines with frontmatter and fenced code blanked, cut at the first appendix."""
    m = FRONTMATTER_RE.match(text)
    skip = text[: m.end()].count("\n") if m else 0
    out, fence = [], False
    for i, line in enumerate(text.splitlines()):
        if i < skip:
            out.append("")
            continue
        if FENCE_RE.match(line):
            fence = not fence
            out.append("")
            continue
        if not fence and APPENDIX_RE.match(line):
            break
        out.append("" if fence else line)
    return out


def parse_requirements(text: str) -> list[dict]:
    """Every requirement the spec defines: {id, text, criteria}.

    An ID defines a requirement where it starts a heading, a list item, a table
    row or a line. Bullets under an `Acceptance` line inside a requirement, and
    bullets nested under a list-item requirement, are its criteria, even when
    they carry IDs of their own.
    """
    reqs: list[dict] = []
    current: dict | None = None
    kind, base_indent, head_level, in_accept = None, 0, 0, False

    for line in _spec_lines(text):
        head = HEADING_RE.match(line)
        bullet = BULLET_RE.match(line)

        if current is not None and kind == "item" and bullet and len(bullet.group(1)) > base_indent:
            current["criteria"].append(bullet.group(2))
            continue
        if current is not None and in_accept and bullet:
            current["criteria"].append(bullet.group(2))
            continue
        if current is not None and kind == "head" and ACCEPT_RE.match(line):
            in_accept = True
            continue

        m = DEF_HEAD.match(line)
        if m:
            current = {"id": m.group(2), "text": m.group(3).strip(), "criteria": []}
            kind, head_level, in_accept = "head", len(m.group(1)), False
            reqs.append(current)
            continue
        m = DEF_ITEM.match(line)
        if m:
            current = {"id": m.group(2), "text": m.group(3).strip(), "criteria": []}
            kind, base_indent, in_accept = "item", len(m.group(1)), False
            reqs.append(current)
            continue
        m = DEF_ROW.match(line)
        if m:
            cells = [c.strip() for c in m.group(2).strip().strip("|").split("|")]
            current = {"id": m.group(1), "text": " | ".join(c for c in cells if c), "criteria": []}
            kind, in_accept = "row", False
            reqs.append(current)
            continue
        m = DEF_LINE.match(line)
        if m:
            current = {"id": m.group(1), "text": m.group(2).strip(), "criteria": []}
            kind, in_accept = "line", False
            reqs.append(current)
            continue

        if head:
            if current is not None and kind == "head" and len(head.group(1)) > head_level:
                continue  # a subheading inside the requirement
            current, kind, in_accept = None, None, False
            continue
        if current is None:
            continue
        if kind == "head" and line.strip() and not bullet:
            current["text"] = (current["text"] + "\n" + line.strip()).strip()
        elif kind in ("item", "line") and not line.strip():
            current, kind = None, None
        elif kind == "item" and line.strip() and not bullet:
            current["text"] += " " + line.strip()

    for r in reqs:
        r["text"] = r["text"][:1500]
    return reqs


def spec_sha256(text: str) -> str:
    m = FRONTMATTER_RE.match(text)
    if m:
        text = SEAL_LINE_RE.sub("", m.group(0)) + text[m.end():]
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def seal_state(text: str) -> str:
    """absent, valid or broken. A spec without a seal is accepted; a broken one is not."""
    m = FRONTMATTER_RE.match(text)
    if not m or not re.search(r"^sealed_by:", m.group(1), re.MULTILINE):
        return "absent"
    value = SEAL_VALUE_RE.search(m.group(0))
    return "valid" if value and value.group(1) == spec_sha256(text) else "broken"


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def runs_dir(root: Path) -> Path:
    return root / ".smith" / "runs"


def run_dir(root: Path, run: str | None) -> Path:
    base = runs_dir(root)
    if run:
        d = base / run
        if not (d / "ledger.json").is_file():
            raise Refused(f"no run named {run} in {base}")
        return d
    runs = sorted(p.parent for p in base.glob("*/ledger.json")) if base.is_dir() else []
    if not runs:
        raise Refused(f"no smith run in {base}; start one with init")
    return max(runs, key=lambda p: json.loads((p / "ledger.json").read_text())["created"] + p.name)


def load(d: Path) -> dict:
    return json.loads((d / "ledger.json").read_text(encoding="utf-8"))


def save(d: Path, ledger: dict) -> None:
    ledger["updated"] = now()
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".ledger.")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(ledger, f, indent=2)
        f.write("\n")
    os.replace(tmp, d / "ledger.json")


def norm_path(p: str) -> str:
    p = p.strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    if not p or p.startswith("/") or ".." in p.split("/"):
        raise Refused(f"'{p}' is not a project-relative path")
    return p


def covers(owned: str, path: str) -> bool:
    """A path ending in / owns everything under it; anything else owns itself."""
    return path.startswith(owned) if owned.endswith("/") else path == owned


def git_head(root: Path) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_init(root: Path, spec: Path, run: str | None, max_rounds: int, max_parallel: int) -> dict:
    if not spec.is_file():
        raise Refused(f"{spec} does not exist")
    text = spec.read_text(encoding="utf-8")
    seal = seal_state(text)
    if seal == "broken":
        raise Refused(f"{spec} has a seal that does not match its content; re-seal it or remove the sealed_by line")
    reqs = parse_requirements(text)
    if not reqs:
        raise Refused(f"{spec} defines no requirement IDs (lines starting with an ID like R-001 or FR-1)")
    seen: set[str] = set()
    dupes = sorted({r["id"] for r in reqs if r["id"] in seen or seen.add(r["id"])})
    if dupes:
        raise Refused(f"{spec} defines these IDs more than once: {', '.join(dupes)}")

    name = run or f"{re.sub(r'[^a-z0-9]+', '-', spec.parent.name.lower()).strip('-') or 'run'}-" \
                  f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    d = runs_dir(root) / name
    if (d / "ledger.json").exists():
        raise Refused(f"run {name} already exists")
    d.mkdir(parents=True)
    (root / ".smith" / ".gitignore").write_text("*\n")
    (d / "spec.md").write_text(text, encoding="utf-8")
    (d / "notes").mkdir()

    ledger = {
        "run": name, "created": now(), "spec": str(spec), "spec_sha256": spec_sha256(text), "sealed": seal == "valid",
        "base_commit": git_head(root), "round": 0, "max_rounds": max_rounds, "max_parallel": max_parallel,
        "slices": [], "waves": [],
        "requirements": {r["id"]: {"text": r["text"], "criteria": r["criteria"], "slice": None,
                                   "status": "pending", "evidence": []} for r in reqs},
        "rounds": [],
    }
    save(d, ledger)
    no_criteria = [r["id"] for r in reqs if not r["criteria"]]
    return {"ok": True, "run": name, "run_dir": str(d), "requirements": len(reqs), "sealed": ledger["sealed"],
            "without_criteria": no_criteria}


def check_plan(ledger: dict, plan: dict) -> tuple[list[dict], list[list[str]]]:
    slices = plan.get("slices") if isinstance(plan, dict) else None
    if not isinstance(slices, list) or not slices:
        raise Refused("the plan has no slices")
    problems: list[str] = []
    ids: list[str] = []
    owner_of_req: dict[str, str] = {}
    owned: list[tuple[str, str]] = []
    clean: list[dict] = []
    for s in slices:
        sid = str(s.get("id", "")).strip()
        if not sid:
            problems.append("a slice has no id")
            continue
        if sid in ids:
            problems.append(f"slice {sid} appears twice")
            continue
        ids.append(sid)
        reqs = list(s.get("requirements") or [])
        if not reqs:
            problems.append(f"slice {sid} owns no requirement")
        for rid in reqs:
            if rid not in ledger["requirements"]:
                problems.append(f"slice {sid} names {rid}, which the spec does not define")
            elif rid in owner_of_req:
                problems.append(f"{rid} is in both {owner_of_req[rid]} and {sid}")
            else:
                owner_of_req[rid] = sid
        files = []
        for f in s.get("files") or []:
            try:
                files.append(norm_path(f))
            except Refused as exc:
                problems.append(f"slice {sid}: {exc}")
        if not files:
            problems.append(f"slice {sid} owns no files")
        for f in files:
            for other_sid, other in owned:
                if covers(other, f) or covers(f, other):
                    problems.append(f"{f} ({sid}) overlaps {other} ({other_sid})")
            owned.append((sid, f))
        clean.append({"id": sid, "title": str(s.get("title", sid)), "requirements": reqs, "files": files,
                      "depends_on": list(s.get("depends_on") or []), "brief": str(s.get("brief", "")),
                      "status": "pending", "note": ""})

    missing = sorted(set(ledger["requirements"]) - set(owner_of_req))
    if missing:
        problems.append(f"no slice owns {', '.join(missing)}")
    for s in clean:
        for dep in s["depends_on"]:
            if dep == s["id"] or dep not in ids:
                problems.append(f"slice {s['id']} depends on unknown slice {dep}")
    if problems:
        raise Refused("the plan is not buildable: " + "; ".join(problems))

    # Waves: every slice runs after the slices it depends on, at most max_parallel at once.
    done: set[str] = set()
    waves: list[list[str]] = []
    pending = [s["id"] for s in clean]
    deps = {s["id"]: set(s["depends_on"]) for s in clean}
    while pending:
        ready = [sid for sid in pending if deps[sid] <= done]
        if not ready:
            raise Refused(f"the plan's dependencies form a cycle among {', '.join(pending)}")
        for i in range(0, len(ready), ledger["max_parallel"]):
            waves.append(ready[i:i + ledger["max_parallel"]])
        done.update(ready)
        pending = [sid for sid in pending if sid not in done]
    return clean, waves


def cmd_plan(d: Path, plan_file: Path) -> dict:
    ledger = load(d)
    if any(s["status"] != "pending" for s in ledger["slices"]):
        raise Refused("building has started; the plan can no longer change")
    try:
        plan = json.loads(plan_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Refused(f"cannot read the plan {plan_file}: {exc}") from exc
    slices, waves = check_plan(ledger, plan)
    for s in slices:
        for rid in s["requirements"]:
            ledger["requirements"][rid]["slice"] = s["id"]
    ledger["slices"], ledger["waves"] = slices, waves
    save(d, ledger)
    return {"ok": True, "slices": len(slices), "waves": waves}


def slice_by_id(ledger: dict, sid: str) -> dict:
    for s in ledger["slices"]:
        if s["id"] == sid:
            return s
    raise Refused(f"no slice {sid} in the plan")


def cmd_slice(d: Path, sid: str, status: str, note: str) -> dict:
    ledger = load(d)
    s = slice_by_id(ledger, sid)
    if status in ("building", "built"):
        unbuilt = [dep for dep in s["depends_on"] if slice_by_id(ledger, dep)["status"] != "built"]
        if unbuilt:
            raise Refused(f"slice {sid} depends on {', '.join(unbuilt)}, which are not built")
    s["status"], s["note"] = status, note
    save(d, ledger)
    return {"ok": True, "slice": sid, "status": status}


def cmd_owners(d: Path, files: list[str]) -> dict:
    ledger = load(d)
    owned: dict[str, list[str]] = {}
    unowned: list[str] = []
    for f in files:
        p = norm_path(f)
        owner = next((s["id"] for s in ledger["slices"] if any(covers(o, p) for o in s["files"])), None)
        if owner:
            owned.setdefault(owner, []).append(p)
        else:
            unowned.append(p)
    return {"ok": True, "owned": owned, "unowned": unowned}


def requirement(ledger: dict, rid: str) -> dict:
    if rid not in ledger["requirements"]:
        raise Refused(f"{rid} is not a requirement in this spec")
    return ledger["requirements"][rid]


def cmd_record(d: Path, rid: str, verdict: str, command: str, output: str | None, output_file: Path | None,
               exit_code: int | None, locations: list[str], reason: str) -> dict:
    ledger = load(d)
    req = requirement(ledger, rid)
    if req["status"] == "done":
        raise Refused(f"{rid} is already done; a fix round reopens it if its files change")
    if output_file is not None:
        try:
            output = output_file.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise Refused(f"cannot read {output_file}: {exc}") from exc
    command, output = (command or "").strip(), (output or "").strip()
    if verdict == "pass" and (not command or not output):
        raise Refused(f"a pass for {rid} needs the command that was run and the output it printed")
    if verdict == "fail" and not (reason.strip() or output):
        raise Refused(f"a fail for {rid} needs a reason or the output that shows it")
    req["evidence"].append({"round": ledger["round"], "verdict": verdict, "command": command,
                            "output": output[-OUTPUT_LIMIT:], "exit": exit_code, "locations": locations,
                            "reason": reason.strip(), "at": now()})
    req["status"] = "passing" if verdict == "pass" else "failing"
    save(d, ledger)
    return {"ok": True, "requirement": rid, "status": req["status"], "round": ledger["round"]}


def done_problem(ledger: dict, rid: str) -> str | None:
    req = requirement(ledger, rid)
    if req["status"] == "done":
        return None
    if not req["evidence"]:
        return f"{rid} has no recorded evidence"
    last = req["evidence"][-1]
    if last["round"] != ledger["round"]:
        return f"{rid}'s latest evidence is from round {last['round']}; re-verify it in round {ledger['round']}"
    if last["verdict"] != "pass":
        return f"{rid}'s latest check failed"
    if not last["command"] or not last["output"]:
        return f"{rid}'s latest evidence has no command or no output"
    return None


def cmd_done(d: Path, rids: list[str], all_passing: bool) -> dict:
    ledger = load(d)
    if all_passing:
        rids = [rid for rid, r in ledger["requirements"].items() if r["status"] == "passing"]
    if not rids:
        raise Refused("no requirement named")
    problems = [p for p in (done_problem(ledger, rid) for rid in rids) if p]
    if problems:
        raise Refused("; ".join(problems))
    for rid in rids:
        ledger["requirements"][rid]["status"] = "done"
    save(d, ledger)
    return {"ok": True, "done": rids}


def cmd_round(d: Path, touched: list[str]) -> dict:
    ledger = load(d)
    if ledger["round"] >= ledger["max_rounds"]:
        raise Refused(f"the fix-round limit ({ledger['max_rounds']}) is reached; stop and report")
    paths = [norm_path(t) for t in touched]
    owners = cmd_owners(d, paths)
    hit = set(owners["owned"])
    reopened = []
    for rid, req in ledger["requirements"].items():
        if req["status"] == "failing":
            req["status"] = "pending"
            reopened.append(rid)
        elif req["status"] in ("passing", "done") and (owners["unowned"] or req["slice"] in hit):
            # A fix in a file this requirement depends on can break it again, so it is checked again.
            req["status"] = "pending"
            reopened.append(rid)
    ledger["round"] += 1
    ledger["rounds"].append({"round": ledger["round"], "touched": paths, "reopened": reopened, "at": now()})
    save(d, ledger)
    return {"ok": True, "round": ledger["round"], "reopened": reopened, "unowned": owners["unowned"]}


def next_action(ledger: dict) -> dict:
    reqs = ledger["requirements"]
    if not ledger["slices"]:
        return {"action": "plan"}
    by_id = {s["id"]: s for s in ledger["slices"]}
    failed = [s["id"] for s in ledger["slices"] if s["status"] == "failed"]
    if failed:
        return {"action": "blocked", "slices": failed}
    for i, wave in enumerate(ledger["waves"]):
        todo = [sid for sid in wave if by_id[sid]["status"] != "built"]
        if todo:
            return {"action": "build", "wave": i + 1, "slices": todo}
    pending = [rid for rid, r in reqs.items() if r["status"] == "pending"]
    if pending:
        return {"action": "verify", "requirements": pending}
    failing = [rid for rid, r in reqs.items() if r["status"] == "failing"]
    if failing:
        if ledger["round"] >= ledger["max_rounds"]:
            return {"action": "stop", "reason": f"fix-round limit {ledger['max_rounds']} reached",
                    "requirements": failing}
        return {"action": "fix", "requirements": failing}
    passing = [rid for rid, r in reqs.items() if r["status"] == "passing"]
    if passing:
        return {"action": "accept", "requirements": passing}
    return {"action": "finish"}


def cmd_status(d: Path) -> dict:
    ledger = load(d)
    counts = {s: 0 for s in REQ_STATUSES}
    for r in ledger["requirements"].values():
        counts[r["status"]] += 1
    return {"ok": True, "run": ledger["run"], "run_dir": str(d), "spec": ledger["spec"], "sealed": ledger["sealed"],
            "round": ledger["round"], "max_rounds": ledger["max_rounds"], "counts": counts,
            "slices": {s["id"]: s["status"] for s in ledger["slices"]}, "waves": ledger["waves"],
            "complete": counts["done"] == len(ledger["requirements"]), "next": next_action(ledger)}


def _cell(text: str) -> str:
    return " ".join(str(text).split()).replace("|", "\\|")


def cmd_report(d: Path) -> dict:
    ledger = load(d)
    st = cmd_status(d)
    lines = [f"# Smith report: {ledger['run']}", "",
             f"- Spec: `{ledger['spec']}` ({'sealed' if ledger['sealed'] else 'not sealed'})",
             f"- Base commit: `{ledger['base_commit'] or 'none'}`",
             f"- Fix rounds: {ledger['round']} of {ledger['max_rounds']}",
             f"- Requirements: {st['counts']['done']} done of {len(ledger['requirements'])}"
             + ("" if st["complete"] else f"; next step: {st['next']['action']}"), "",
             "## Requirements", "", "| ID | Status | Slice | Check | Exit | Where |", "|---|---|---|---|---|---|"]
    for rid, r in ledger["requirements"].items():
        ev = r["evidence"][-1] if r["evidence"] else {}
        lines.append(f"| {rid} | {r['status']} | {r['slice'] or ''} | `{_cell(ev.get('command', '')) or '-'}` | "
                     f"{'' if ev.get('exit') is None else ev['exit']} | {_cell(', '.join(ev.get('locations', [])))} |")
    open_reqs = [(rid, r) for rid, r in ledger["requirements"].items() if r["status"] != "done"]
    if open_reqs:
        lines += ["", "## Not done", ""]
        for rid, r in open_reqs:
            ev = r["evidence"][-1] if r["evidence"] else {}
            why = ev.get("reason") or (ev.get("output", "")[-300:] if ev else "never verified")
            lines.append(f"- **{rid}** ({r['status']}): {_cell(why)}")
    lines += ["", "## Slices", ""]
    for s in ledger["slices"]:
        lines.append(f"- **{s['id']}** {s['title']}: {s['status']}; {', '.join(s['requirements'])}; "
                     f"files {', '.join(s['files'])}")
    if ledger["rounds"]:
        lines += ["", "## Fix rounds", ""]
        for rnd in ledger["rounds"]:
            lines.append(f"- Round {rnd['round']}: touched {', '.join(rnd['touched']) or 'nothing'}; "
                         f"re-verified {', '.join(rnd['reopened']) or 'nothing'}")
    path = d / "report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"ok": True, "report": str(path), "complete": st["complete"], "counts": st["counts"]}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ledger.py", description="Smith's build ledger.")
    p.add_argument("--root", type=Path, default=Path.cwd())
    p.add_argument("--run", default=None, help="run name (default: the newest)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init")
    s.add_argument("spec", type=Path)
    s.add_argument("--name", dest="name", default=None, help="run name (default: derived from the spec)")
    s.add_argument("--max-rounds", type=int, default=3)
    s.add_argument("--max-parallel", type=int, default=4)

    sub.add_parser("plan").add_argument("--file", type=Path, required=True)

    s = sub.add_parser("slice")
    s.add_argument("slice")
    s.add_argument("--status", required=True, choices=("building", "built", "failed"))
    s.add_argument("--note", default="")

    sub.add_parser("owners").add_argument("files", nargs="+")

    s = sub.add_parser("record")
    s.add_argument("requirement")
    s.add_argument("--verdict", required=True, choices=("pass", "fail"))
    s.add_argument("--command", default="")
    out = s.add_mutually_exclusive_group()
    out.add_argument("--output", default=None)
    out.add_argument("--output-file", type=Path, default=None)
    s.add_argument("--exit", dest="exit_code", type=int, default=None)
    s.add_argument("--location", action="append", default=[])
    s.add_argument("--reason", default="")

    s = sub.add_parser("done")
    s.add_argument("requirements", nargs="*")
    s.add_argument("--all-passing", action="store_true")

    sub.add_parser("round").add_argument("--touched", nargs="*", default=[])
    sub.add_parser("status")
    sub.add_parser("report")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    try:
        if args.cmd == "init":
            if args.max_rounds < 0 or args.max_parallel < 1:
                raise Refused("--max-rounds must be 0 or more and --max-parallel 1 or more")
            result = cmd_init(root, args.spec, args.name or args.run, args.max_rounds, args.max_parallel)
        else:
            d = run_dir(root, args.run)
            if args.cmd == "plan":
                result = cmd_plan(d, args.file)
            elif args.cmd == "slice":
                result = cmd_slice(d, args.slice, args.status, args.note)
            elif args.cmd == "owners":
                result = cmd_owners(d, args.files)
            elif args.cmd == "record":
                result = cmd_record(d, args.requirement, args.verdict, args.command, args.output, args.output_file,
                                    args.exit_code, args.location, args.reason)
            elif args.cmd == "done":
                result = cmd_done(d, args.requirements, args.all_passing)
            elif args.cmd == "round":
                result = cmd_round(d, args.touched)
            elif args.cmd == "status":
                result = cmd_status(d)
            else:
                result = cmd_report(d)
    except Refused as exc:
        print(json.dumps({"ok": False, "refused": str(exc)}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
