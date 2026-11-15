#!/usr/bin/env python3
"""Check, seal and inspect a Sage spec. Stdlib only.

    validate-spec.py check SPEC                      lint the spec, print a JSON report
    validate-spec.py hash SPEC                       the spec's content hash
    validate-spec.py seal SPEC [--review REVIEW]     check, then mark the spec sealed
    validate-spec.py verify-seal SPEC                the seal is present, current and the spec still checks
    validate-spec.py status DIR                      which phase a spec directory is in

`check`, `seal` and `verify-seal` exit 0 on success and 1 on failure; usage
errors exit 2.

A spec is markdown with YAML-style frontmatter (`title`, `status`). It has a
`## Requirements` section of `### R-NNN: title` blocks, a `## Non-goals`
section, and two appendices that hold every source a requirement may cite:
`## Appendix: Interview Transcript` (`### A-NNN` answers) and
`## Appendix: Codebase Facts` (`### F-NNN` facts, each with file:line
evidence). A requirement block is a statement, a `Source:` line naming the
A- and F- entries behind it, and an `Acceptance:` list.

Sealing writes `status: sealed` and one frontmatter line,

    sealed_by: validate-spec.py sha256:<hex>

where <hex> is the sha256 of the file with every `sealed_by:` line removed
from the frontmatter. Any later edit breaks the seal.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
SEAL_LINE_RE = re.compile(r"^sealed_by:.*\n", re.MULTILINE)
SEAL_VALUE_RE = re.compile(r"^\s*validate-spec\.py\s+sha256:([0-9a-f]{64})\s*$")

SECTION_RE = re.compile(r"^##\s+(.+?)\s*$")
SUBHEAD_RE = re.compile(r"^###\s+(.+?)\s*$")
REQ_HEAD_RE = re.compile(r"^(R-\d{3})(?::\s*(.*))?$")
SOURCE_HEAD_RE = re.compile(r"^([AF]-\d{3})\b")
BULLET_RE = re.compile(r"^\s*[-*+]\s+(.*\S)\s*$")
SOURCE_LINE_RE = re.compile(r"^Source:\s*(.*)$", re.IGNORECASE)
ACCEPT_LINE_RE = re.compile(r"^Acceptance:\s*$", re.IGNORECASE)
CITE_RE = re.compile(r"\b[AF]-\d{3}\b")
EVIDENCE_RE = re.compile(r"[\w./-]+:\d+")
PLACEHOLDER_RE = re.compile(r"\b(TODO|TBD|FIXME|XXX)\b|\?\?\?")

# Words that let a criterion pass however the code behaves. A criterion has to
# name what is observed, so these are refused rather than warned about.
VAGUE_RE = re.compile(
    r"\b(properly|correctly|as expected|appropriate(ly)?|user[- ]friendly|intuitive(ly)?|"
    r"seamless(ly)?|robust(ly)?|graceful(ly)?|etc\.?|and so on|reasonabl[ey])\b",
    re.IGNORECASE,
)

REQUIRED_SECTIONS = ("Requirements", "Non-goals", "Appendix: Interview Transcript")
INTERVIEW = "Appendix: Interview Transcript"
FACTS = "Appendix: Codebase Facts"


def spec_sha256(text: str) -> str:
    m = FRONTMATTER_RE.match(text)
    if m:
        text = SEAL_LINE_RE.sub("", m.group(0)) + text[m.end():]
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def frontmatter(text: str) -> dict[str, str]:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip():
            out[key.strip()] = value.strip()
    return out


def sections(text: str) -> dict[str, list[tuple[int, str]]]:
    """Each `##` section's lines, numbered as in the file. The first of a repeated title wins."""
    m = FRONTMATTER_RE.match(text)
    offset = text[: m.end()].count("\n") if m else 0
    body = text[m.end():] if m else text
    out: dict[str, list[tuple[int, str]]] = {}
    current = None
    in_fence = False
    for n, line in enumerate(body.splitlines(), start=offset + 1):
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
            line = ""
        elif in_fence:
            line = ""  # fenced examples are not spec content
        head = SECTION_RE.match(line)
        if head:
            title = head.group(1)
            current = title if title not in out else None
            if current:
                out[current] = []
            continue
        if current:
            out[current].append((n, line))
    return out


def blocks(lines: list[tuple[int, str]]) -> list[tuple[int, str, list[tuple[int, str]]]]:
    """Split a section into `###` blocks: (line number, heading text, body lines)."""
    out = []
    for n, line in lines:
        head = SUBHEAD_RE.match(line)
        if head:
            out.append((n, head.group(1), []))
        elif out:
            out[-1][2].append((n, line))
    return out


def parse_requirement(n: int, heading: str, body: list[tuple[int, str]], problems: list[dict]):
    m = REQ_HEAD_RE.match(heading)
    if not m:
        problems.append(err("requirement-id", n, f"'### {heading}' in Requirements is not 'R-NNN: title'"))
        return None
    rid, title = m.group(1), (m.group(2) or "").strip()
    statement, sources, criteria = [], None, []
    in_criteria = False
    for ln, line in body:
        src = SOURCE_LINE_RE.match(line.strip())
        if src:
            sources = CITE_RE.findall(src.group(1))
            in_criteria = False
            continue
        if ACCEPT_LINE_RE.match(line.strip()):
            in_criteria = True
            continue
        bullet = BULLET_RE.match(line)
        if in_criteria and bullet:
            criteria.append((ln, bullet.group(1)))
        elif line.strip() and not in_criteria and sources is None:
            statement.append(line.strip())
    if not title:
        problems.append(err("requirement-title", n, f"{rid} has no title"))
    if not statement:
        problems.append(err("requirement-statement", n, f"{rid} has no statement before Source:"))
    if not sources:
        problems.append(err("requirement-source", n, f"{rid} cites no source; add 'Source: A-NNN, F-NNN'"))
    if not criteria:
        problems.append(err("requirement-criteria", n, f"{rid} has no acceptance criteria under 'Acceptance:'"))
    for ln, crit in criteria:
        vague = VAGUE_RE.search(crit)
        if vague:
            problems.append(err("criterion-vague", ln,
                                f"{rid}: '{vague.group(0)}' cannot fail; name what is observed instead"))
        elif len(crit.split()) < 4:
            problems.append(err("criterion-short", ln, f"{rid}: '{crit}' is too short to check"))
    return {"id": rid, "line": n, "title": title, "sources": sources or [], "criteria": [c for _, c in criteria]}


def err(rule: str, line: int, message: str) -> dict:
    return {"rule": rule, "line": line, "message": message}


def check_text(text: str, ignore_seal: bool = False) -> dict:
    errors: list[dict] = []
    warnings: list[dict] = []
    fm = frontmatter(text)
    if not fm:
        errors.append(err("frontmatter", 1, "no frontmatter; the spec must open with ---, title and status"))
    for key in ("title", "status"):
        if fm and not fm.get(key):
            errors.append(err("frontmatter", 1, f"frontmatter has no '{key}'"))
    if fm.get("status") and fm["status"] not in ("draft", "sealed"):
        errors.append(err("frontmatter", 1, f"status '{fm['status']}' is not draft or sealed"))

    secs = sections(text)
    for name in REQUIRED_SECTIONS:
        if name not in secs:
            errors.append(err("section", 0, f"missing section '## {name}'"))

    # Sources: every A- and F- entry, and whether its body is usable.
    sources: dict[str, int] = {}
    for sec, prefix in ((INTERVIEW, "A"), (FACTS, "F")):
        for n, heading, body in blocks(secs.get(sec, [])):
            m = SOURCE_HEAD_RE.match(heading)
            if not m or not m.group(1).startswith(prefix):
                errors.append(err("source-id", n, f"'### {heading}' in '{sec}' is not '{prefix}-NNN'"))
                continue
            sid = m.group(1)
            if sid in sources:
                errors.append(err("duplicate-id", n, f"{sid} is defined twice (first at line {sources[sid]})"))
                continue
            sources[sid] = n
            content = " ".join(line.strip() for _, line in body if line.strip())
            if not content:
                errors.append(err("source-empty", n, f"{sid} has no content"))
            elif prefix == "F" and not EVIDENCE_RE.search(content):
                errors.append(err("fact-evidence", n, f"{sid} gives no file:line evidence"))

    # Requirements.
    reqs: list[dict] = []
    seen: dict[str, int] = {}
    for n, heading, body in blocks(secs.get("Requirements", [])):
        req = parse_requirement(n, heading, body, errors)
        if not req:
            continue
        if req["id"] in seen:
            errors.append(err("duplicate-id", n, f"{req['id']} is defined twice (first at line {seen[req['id']]})"))
            continue
        seen[req["id"]] = n
        for sid in req["sources"]:
            if sid not in sources:
                errors.append(err("source-missing", n, f"{req['id']} cites {sid}, which no appendix defines"))
        reqs.append(req)
    if "Requirements" in secs and not reqs:
        errors.append(err("requirements", 0, "the Requirements section defines no R-NNN requirement"))
    numbers = [int(r["id"][2:]) for r in reqs]
    if numbers != sorted(numbers):
        warnings.append(err("requirement-order", 0, "requirement IDs are not in ascending order"))

    if "Non-goals" in secs and not any(BULLET_RE.match(line) for _, line in secs["Non-goals"]):
        errors.append(err("non-goals", 0, "Non-goals lists nothing; name at least one thing this spec will not do"))

    for n, line in secs.get("Open questions", []):
        bullet = BULLET_RE.match(line)
        if bullet and bullet.group(1).strip().rstrip(".").lower() != "none":
            errors.append(err("open-question", n, f"unresolved open question: {bullet.group(1)}"))

    # Placeholders anywhere above the appendices: a spec with a TODO in it is not finished.
    for name, lines in secs.items():
        if name.startswith("Appendix"):
            continue
        for n, line in lines:
            if PLACEHOLDER_RE.search(line):
                errors.append(err("placeholder", n, f"placeholder text in '{name}': {line.strip()}"))

    cited = {sid for r in reqs for sid in r["sources"]}
    for sid in sorted(set(sources) - cited):
        warnings.append(err("source-unused", sources[sid], f"{sid} is not cited by any requirement"))

    if not ignore_seal:
        seal = seal_state(text)
        if fm.get("status") == "sealed" and seal != "valid":
            errors.append(err("seal", 1, f"status is sealed but the seal is {seal}"))
        if fm.get("status") != "sealed" and seal != "absent":
            errors.append(err("seal", 1, "a sealed_by line is present but status is not sealed"))

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "counts": {"requirements": len(reqs), "criteria": sum(len(r["criteria"]) for r in reqs),
                   "answers": sum(1 for s in sources if s.startswith("A")),
                   "facts": sum(1 for s in sources if s.startswith("F"))},
        "requirements": [{"id": r["id"], "title": r["title"], "sources": r["sources"],
                          "criteria": len(r["criteria"])} for r in reqs],
    }


def seal_state(text: str) -> str:
    """absent, malformed, stale or valid."""
    m = FRONTMATTER_RE.match(text)
    line = re.search(r"^sealed_by:(.*)$", m.group(1), re.MULTILINE) if m else None
    if not line:
        return "absent"
    value = SEAL_VALUE_RE.match(line.group(1))
    if not value:
        return "malformed"
    return "valid" if value.group(1) == spec_sha256(text) else "stale"


def set_frontmatter(text: str, key: str, value: str) -> str:
    m = FRONTMATTER_RE.match(text)
    if not m:
        raise ValueError("no frontmatter")
    lines = [ln for ln in m.group(1).splitlines() if not ln.startswith(f"{key}:")]
    lines.append(f"{key}: {value}")
    return text[: m.start(1)] + "\n".join(lines) + text[m.end(1):]


def write_atomic(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def seal(path: Path, review: Path | None) -> dict:
    text = path.read_text(encoding="utf-8")
    if seal_state(text) == "valid" and frontmatter(text).get("status") == "sealed":
        return {"ok": True, "message": f"{path} is already sealed", "sha256": spec_sha256(text)}
    report = check_text(text, ignore_seal=True)
    if not report["ok"]:
        return {"ok": False, "message": f"{path} does not pass its checks; not sealed", "errors": report["errors"]}
    if review is not None:
        problem = review_problem(review, spec_sha256(text))
        if problem:
            return {"ok": False, "message": problem}
    text = set_frontmatter(text, "status", "sealed")
    digest = spec_sha256(text)
    text = set_frontmatter(text, "sealed_by", f"validate-spec.py sha256:{digest}")
    write_atomic(path, text)
    return {"ok": True, "message": f"{path} sealed", "sha256": digest, "counts": report["counts"]}


def review_problem(review: Path, draft_sha: str) -> str | None:
    try:
        data = json.loads(review.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return f"cannot read the review {review}: {exc}"
    if data.get("verdict") != "pass":
        return f"the review {review} says {data.get('verdict')!r}, not 'pass'"
    if data.get("spec_sha256") != draft_sha:
        return f"the review {review} is of a different draft; review the spec as it is now"
    return None


def verify_seal(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    state = seal_state(text)
    if state != "valid":
        return {"ok": False, "message": f"{path}: seal is {state}"}
    report = check_text(text)
    if not report["ok"]:
        return {"ok": False, "message": f"{path}: seal holds but the spec fails its checks",
                "errors": report["errors"]}
    return {"ok": True, "message": f"{path}: sealed, hash holds, checks pass", "counts": report["counts"]}


def status(directory: Path) -> dict:
    research = directory / "research.md"
    interview = directory / "interview.md"
    spec = directory / "spec.md"
    review = directory / "review.json"

    def count(path: Path, prefix: str) -> int:
        if not path.is_file():
            return 0
        return len(re.findall(rf"^###\s+{prefix}-\d{{3}}\b", path.read_text(encoding="utf-8"), re.MULTILINE))

    out = {"dir": str(directory), "facts": count(research, "F"), "answers": count(interview, "A"),
           "spec": spec.is_file(), "review": None, "review_current": False, "sealed": False}
    if spec.is_file():
        text = spec.read_text(encoding="utf-8")
        out["sealed"] = seal_state(text) == "valid" and frontmatter(text).get("status") == "sealed"
        if review.is_file():
            try:
                data = json.loads(review.read_text(encoding="utf-8"))
                out["review"] = data.get("verdict")
                out["review_current"] = data.get("spec_sha256") == spec_sha256(text)
            except (OSError, json.JSONDecodeError):
                out["review"] = "unreadable"
    if not research.is_file():
        out["phase"] = "research"
    elif not spec.is_file():
        out["phase"] = "interview"
    elif out["sealed"]:
        out["phase"] = "sealed"
    elif out["review"] == "pass" and out["review_current"]:
        out["phase"] = "seal"
    else:
        out["phase"] = "review"
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="validate-spec.py", description="Check, seal and inspect a Sage spec.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("check", "hash", "verify-seal"):
        sub.add_parser(name).add_argument("spec", type=Path)
    p = sub.add_parser("seal")
    p.add_argument("spec", type=Path)
    p.add_argument("--review", type=Path, default=None, help="review.json that must say pass for this draft")
    sub.add_parser("status").add_argument("dir", type=Path)
    args = parser.parse_args(argv)

    if args.cmd == "status":
        print(json.dumps(status(args.dir)))
        return 0
    if not args.spec.is_file():
        print(json.dumps({"ok": False, "message": f"{args.spec} does not exist"}))
        return 1
    if args.cmd == "hash":
        print(spec_sha256(args.spec.read_text(encoding="utf-8")))
        return 0
    if args.cmd == "check":
        result = check_text(args.spec.read_text(encoding="utf-8"))
    elif args.cmd == "seal":
        result = seal(args.spec, args.review)
    else:
        result = verify_seal(args.spec)
    print(json.dumps(result, indent=2))
    if not result["ok"]:
        for e in result.get("errors", []):
            print(f"{args.spec}:{e['line']}: [{e['rule']}] {e['message']}", file=sys.stderr)
        if "message" in result:
            print(result["message"], file=sys.stderr)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
