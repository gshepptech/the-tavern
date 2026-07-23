#!/usr/bin/env python3
"""Enforce the repo's documentation rules.

Two rules, both easy to break by accident and invisible in review:

  1. No emoji or decorative Unicode in documentation. Headings, tables and
     prose stay plain text. This keeps the docs readable in every terminal,
     diff viewer and screen reader, and stops the READMEs drifting into
     decoration. GitHub alert callouts and mermaid are fine - they put no
     emoji character in the source.

  2. Relative links must resolve. A broken link in a README is the fastest way
     to lose a reader who is deciding whether to trust the project.

Glyphs that define runtime output are deliberately exempt: the state markers in
Sellsword's run table, the verdict marks in Smith's TRACE tables and the good/bad
example marks in Scout's authoring skill are part of what an agent prints, not
decoration. Those live outside README.md, which is why only READMEs and the
root docs are scanned for rule 1.

Exit 0 if clean, 1 otherwise. Run from the repo root.
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

# Emoji planes, dingbats, arrows and the emoji-presentation selector.
# (c), (r) and (tm) are allowed - they are legal marks in the licence footers.
BANNED_RANGES = [
    (0x1F000, 0x1FAFF),  # emoji
    (0x1F1E6, 0x1F1FF),  # regional indicators / flags
    (0x2600, 0x27BF),    # misc symbols and dingbats
    (0x2B00, 0x2BFF),    # arrows and stars
    (0x2190, 0x21FF),    # arrows
    (0xFE0F, 0xFE0F),    # variation selector-16
]

ROOT_DOCS = ["README.md", "CONTRIBUTING.md", "SECURITY.md", "CODE_OF_CONDUCT.md", "CHANGELOG.md"]


def is_banned(ch: str) -> bool:
    return any(lo <= ord(ch) <= hi for lo, hi in BANNED_RANGES)


def scanned_docs() -> list[Path]:
    docs = [ROOT / name for name in ROOT_DOCS]
    docs += sorted(ROOT.glob("plugins/*/README.md"))
    return [d for d in docs if d.exists()]


def check_emoji(docs: list[Path]) -> list[str]:
    problems = []
    for path in docs:
        in_fence = False
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            hits = [c for c in line if is_banned(c)]
            if hits:
                names = ", ".join(
                    f"{c!r} ({unicodedata.name(c, 'unnamed')})" for c in dict.fromkeys(hits)
                )
                rel = path.relative_to(ROOT)
                problems.append(f"{rel}:{lineno}: decorative Unicode - {names}")
    return problems


def check_links(docs: list[Path]) -> list[str]:
    problems = []
    for path in docs:
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"\[[^\]]*\]\((?!https?:|mailto:|#)([^)#]+)", text):
            target = (path.parent / match.group(1)).resolve()
            if not target.exists():
                rel = path.relative_to(ROOT)
                problems.append(f"{rel}: broken relative link -> {match.group(1)}")
    return problems


def main() -> int:
    docs = scanned_docs()
    problems = check_emoji(docs) + check_links(docs)

    if problems:
        print(f"doc check FAILED ({len(problems)} problem(s)):")
        for p in problems:
            print(f"  - {p}")
        return 1

    print(f"doc check passed - {len(docs)} documents, no decorative Unicode, all links resolve")
    return 0


if __name__ == "__main__":
    sys.exit(main())
