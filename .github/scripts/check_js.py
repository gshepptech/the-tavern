#!/usr/bin/env python3
"""Check that every tracked JavaScript file parses.

Plain scripts go straight to `node --check`. Workflow scripts
(plugins/*/workflows/*.js) cannot: the Workflow runtime executes the body
inside an async function, so a top-level `await` or `return` is legal there and
a syntax error to Node. Each one is wrapped the same way the runtime runs it,
with `export const meta` turned into a local, and the wrapper is checked
instead.

Exit 0 if every file parses, 1 otherwise. Run from the repo root.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

# The names the Workflow runtime puts in scope for a script.
RUNTIME_GLOBALS = "agent, parallel, pipeline, phase, log, args, budget, workflow"


def tracked_js() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "*.js"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout
    return [ROOT / line for line in out.splitlines() if line]


def is_workflow(path: Path) -> bool:
    return path.parent.name == "workflows" and path.read_text(encoding="utf-8").startswith(
        "export const meta"
    )


def wrap(source: str) -> str:
    body = source.replace("export const meta = ", "const meta = ", 1)
    return f"export default async function workflow({RUNTIME_GLOBALS}) {{\n{body}\n}}\n"


def node_check(path: Path) -> str | None:
    proc = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
    return None if proc.returncode == 0 else proc.stderr.strip()


def main() -> int:
    problems: list[str] = []
    files = tracked_js()
    with tempfile.TemporaryDirectory() as tmp:
        for path in files:
            rel = path.relative_to(ROOT)
            target = path
            if is_workflow(path):
                target = Path(tmp) / (str(rel).replace("/", "__") + ".mjs")
                target.write_text(wrap(path.read_text(encoding="utf-8")), encoding="utf-8")
            error = node_check(target)
            if error:
                problems.append(f"{rel}:\n{error}")

    if problems:
        print(f"JavaScript check FAILED ({len(problems)} file(s)):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"JavaScript check passed - {len(files)} files parse")
    return 0


if __name__ == "__main__":
    sys.exit(main())
