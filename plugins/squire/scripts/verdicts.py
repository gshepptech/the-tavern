"""Hold the verifier's output to its contract, and turn it into the fixer's gap list.

The verifier writes ``verify/verify-r<N>.json``:

    {
      "requirements": [
        {"id": "R-001", "verdict": "MET", "evidence": ["src/export.py:42"], "reason": "..."}
      ],
      "unrequested": [
        {"where": "src/export.py:80", "what": "adds a --format flag the spec does not ask for"}
      ]
    }

Code refuses the file unless every indexed requirement has exactly one
verdict, every MET verdict cites at least one ``path:line`` that exists in the
project, and every other verdict says why. A verdict squire cannot check is not
a verdict.
"""

from __future__ import annotations

import re
from pathlib import Path

VERDICTS = ("MET", "PARTIAL", "MISSING", "WRONG")
CITE = re.compile(r"^(?P<path>[^:\s][^:]*):(?P<start>\d+)(?:-(?P<end>\d+))?$")


def _check_cite(cite: object, root: Path, where: str) -> str | None:
    if not isinstance(cite, str):
        return f"{where}: evidence must be a 'path:line' string, got {cite!r}"
    m = CITE.match(cite.strip())
    if not m:
        return f"{where}: evidence {cite!r} is not 'path:line' or 'path:start-end'"
    rel = m.group("path")
    if Path(rel).is_absolute() or ".." in Path(rel).parts:
        return f"{where}: evidence {cite!r} must be a path relative to the project root"
    path = root / rel
    if not path.is_file():
        return f"{where}: evidence {cite!r} names a file that does not exist"
    last = int(m.group("end") or m.group("start"))
    lines = path.read_text(encoding="utf-8", errors="replace").count("\n") + 1
    if int(m.group("start")) < 1 or last > lines:
        return f"{where}: evidence {cite!r} points past the end of the file ({lines} lines)"
    return None


def validate(data: object, ids: list[str], root: Path) -> list[str]:
    """Every problem with a verifier file; an empty list means it can be used."""
    if not isinstance(data, dict):
        return ["the verifier file must be a JSON object"]
    errors: list[str] = []
    reqs = data.get("requirements")
    if not isinstance(reqs, list):
        return ["'requirements' must be a list with one entry per requirement"]

    counts: dict[str, int] = {}
    for n, r in enumerate(reqs):
        where = f"requirements[{n}]"
        if not isinstance(r, dict):
            errors.append(f"{where}: must be an object")
            continue
        rid = r.get("id")
        if rid not in ids:
            errors.append(f"{where}: {rid!r} is not a requirement in the spec index")
            continue
        counts[rid] = counts.get(rid, 0) + 1
        where = rid
        verdict = r.get("verdict")
        if verdict not in VERDICTS:
            errors.append(f"{where}: verdict {verdict!r} is not one of {', '.join(VERDICTS)}")
            continue
        evidence = r.get("evidence") or []
        if not isinstance(evidence, list):
            errors.append(f"{where}: evidence must be a list of 'path:line' strings")
            evidence = []
        if verdict == "MET" and not evidence:
            errors.append(f"{where}: MET needs at least one 'path:line' citation")
        if verdict != "MET" and not str(r.get("reason") or "").strip():
            errors.append(f"{where}: {verdict} needs a reason that says what is missing or wrong")
        for cite in evidence:
            problem = _check_cite(cite, root, where)
            if problem:
                errors.append(problem)

    for rid in ids:
        if counts.get(rid, 0) == 0:
            errors.append(f"{rid}: no verdict")
        elif counts[rid] > 1:
            errors.append(f"{rid}: {counts[rid]} verdicts; give exactly one")

    extra = data.get("unrequested", [])
    if not isinstance(extra, list):
        errors.append("'unrequested' must be a list")
    else:
        for n, u in enumerate(extra):
            if not isinstance(u, dict) or not str(u.get("what") or "").strip():
                errors.append(f"unrequested[{n}]: needs 'where' ('path:line') and 'what'")
                continue
            problem = _check_cite(u.get("where"), root, f"unrequested[{n}]")
            if problem:
                errors.append(problem)
    return errors


def gaps(data: dict, check: dict, baseline: dict[str, int], round_no: int) -> list[dict]:
    """The fixer's work list for a round: unmet requirements, drift, and new check failures."""
    out: list[dict] = []

    def add(kind: str, **fields: object) -> None:
        out.append({"id": f"G{round_no}-{len(out) + 1}", "kind": kind, **fields})

    for r in data.get("requirements", []):
        if r.get("verdict") != "MET":
            add("requirement", requirement=r["id"], verdict=r["verdict"], reason=r.get("reason", ""),
                evidence=r.get("evidence", []))
    for u in data.get("unrequested", []):
        add("unrequested", where=u["where"], what=u["what"])
    for leak in check.get("id_leaks", []):
        add("id-in-code", where=f"{leak['file']}:{leak['line']}", what=f"requirement ID {leak['id']} in production code",
            text=leak["text"])
    if check.get("uncommitted"):
        add("uncommitted", what="changes left uncommitted", files=check["uncommitted"])
    for c in check.get("commands", []):
        if c["exit"] != 0 and baseline.get(c["name"], 0) == 0:
            add("check", command=c["cmd"], exit=c["exit"], tail=c["tail"])
    return out
