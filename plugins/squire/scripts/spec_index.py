"""Index a structured spec: every requirement ID, its text and its acceptance criteria.

squire only builds specs that already say what done means, so the index is the
contract every later step works from. A requirement is *defined* in one of
three places:

  heading     ``### R-001: Title``; the body runs to the next heading at the
              same or a shallower level, or the next requirement
  list item   ``- **FR-001**: text``; continuation lines and nested items
              belong to it
  table row   ``| FR-001 | text | criteria |``; the first cell is the ID

Anywhere else an ID is a reference (``see R-002``, ``Source: A-001``) and is
not indexed. Acceptance criteria are the list items after an ``Acceptance:``
line, or, for a list-item requirement, its nested items. Frontmatter, fenced
code and any section whose heading starts with ``Appendix`` are skipped.
"""

from __future__ import annotations

import re
from pathlib import Path

ID = r"[A-Z][A-Z0-9]{0,7}-\d+(?:\.\d+)*"
_WRAP = r"(?:\*\*|__|`)?"
HEAD_DEF = re.compile(rf"^(#{{2,6}})\s+{_WRAP}({ID}){_WRAP}\s*[:.)\-]?\s*(.*)$")
ITEM_DEF = re.compile(rf"^(\s*)(?:[-*+]|\d+[.)])\s+{_WRAP}({ID}){_WRAP}\s*[:.)\-]?\s*(.*)$")
ROW_DEF = re.compile(rf"^\s*\|\s*{_WRAP}({ID}){_WRAP}\s*\|(.*)$")
HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
ITEM = re.compile(r"^(\s*)(?:[-*+]|\d+[.)])\s+(.*)$")
ACCEPT = re.compile(r"^\s*(?:\*\*|__)?(?:acceptance(?:\s+criteria)?)(?:\*\*|__)?\s*:?\s*(?:\*\*|__)?\s*:?\s*$", re.I)
SOURCE = re.compile(r"^\s*(?:\*\*)?sources?(?:\*\*)?\s*:", re.I)
FENCE = re.compile(r"^\s*(```|~~~)")
FRONTMATTER = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.S)


def _visible(text: str) -> list[str]:
    """Spec lines with frontmatter, fenced code and appendices blanked, so line numbers still match the file."""
    lines = text.splitlines()
    m = FRONTMATTER.match(text)
    skip = text[: m.end()].count("\n") if m else 0
    out, fenced, appendix_level = [], False, 0
    for i, line in enumerate(lines):
        if i < skip:
            out.append("")
            continue
        if FENCE.match(line):
            fenced = not fenced
            out.append("")
            continue
        h = HEADING.match(line)
        if h and not fenced:
            level = len(h.group(1))
            if appendix_level and level <= appendix_level:
                appendix_level = 0
            if h.group(2).strip().lower().startswith("appendix"):
                appendix_level = level
        out.append("" if fenced or appendix_level else line)
    return out


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _criteria(lines: list[str]) -> tuple[list[str], list[str]]:
    """Split a requirement body into (text lines, acceptance criteria)."""
    text, crit, in_acc, item = [], [], False, None
    for line in lines:
        if ACCEPT.match(line):
            in_acc = True
            continue
        if SOURCE.match(line):
            continue
        it = ITEM.match(line)
        if in_acc:
            if it:
                item = [it.group(2)]
                crit.append(item)
            elif line.strip() and item is not None and line.startswith((" ", "\t")):
                item.append(line)
            elif line.strip():
                in_acc, item = False, None
                text.append(line)
            continue
        text.append(line)
    return text, [_clean(" ".join(c)) for c in crit]


def index(text: str) -> dict:
    """Return {"requirements": [...], "warnings": [...]} for a spec's text."""
    lines = _visible(text)
    reqs: list[dict] = []
    warnings: list[str] = []
    seen: dict[str, int] = {}

    def add(rid: str, title: str, body: list[str], line_no: int, nested_as_criteria: bool) -> None:
        if rid in seen:
            warnings.append(f"{rid} is defined twice (lines {seen[rid]} and {line_no}); the first definition is used")
            return
        seen[rid] = line_no
        body_text, crit = _criteria(body)
        if nested_as_criteria and not crit:
            body_text, crit = [], []
            for line in body:
                it = ITEM.match(line)
                (crit if it else body_text).append(it.group(2) if it else line)
            crit = [_clean(c) for c in crit]
        reqs.append({
            "id": rid,
            "title": _clean(title)[:120],
            "text": _clean(" ".join([title, *body_text])),
            "acceptance": [c for c in crit if c],
            "line": line_no,
        })

    i = 0
    while i < len(lines):
        line = lines[i]
        h = HEAD_DEF.match(line)
        if h:
            level = len(h.group(1))
            j = i + 1
            while j < len(lines):
                nh = HEADING.match(lines[j])
                if nh and len(nh.group(1)) <= level:
                    break
                if HEAD_DEF.match(lines[j]) or ITEM_DEF.match(lines[j]) or ROW_DEF.match(lines[j]):
                    break
                j += 1
            add(h.group(2), h.group(3), lines[i + 1 : j], i + 1, False)
            i = j
            continue
        it = ITEM_DEF.match(line)
        if it:
            indent = len(it.group(1).expandtabs())
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                if not nxt.strip():
                    # A blank line ends the item unless the next line is still indented under it.
                    k = j + 1
                    if k < len(lines) and lines[k].strip() and len(lines[k]) - len(lines[k].lstrip()) > indent:
                        j += 1
                        continue
                    break
                if HEADING.match(nxt) or ITEM_DEF.match(nxt):
                    break
                lead = len(nxt.expandtabs()) - len(nxt.expandtabs().lstrip())
                if ITEM.match(nxt) and lead <= indent:
                    break
                j += 1
            add(it.group(2), it.group(3), lines[i + 1 : j], i + 1, True)
            i = j
            continue
        row = ROW_DEF.match(line)
        if row:
            cells = [c.strip() for c in row.group(2).strip().rstrip("|").split("|")]
            title = cells[0] if cells else ""
            crit = [c for c in cells[1:] if c]
            if row.group(1) not in seen:
                seen[row.group(1)] = i + 1
                reqs.append({"id": row.group(1), "title": _clean(title)[:120], "text": _clean(title),
                             "acceptance": [_clean(c) for c in crit], "line": i + 1})
            else:
                warnings.append(f"{row.group(1)} is defined twice; the first definition is used")
        i += 1

    for r in reqs:
        if not r["acceptance"]:
            warnings.append(f"{r['id']} has no acceptance criteria; the verifier judges it against its text alone")
    return {"requirements": reqs, "warnings": warnings}


def index_file(path: Path) -> dict:
    return index(path.read_text(encoding="utf-8"))
