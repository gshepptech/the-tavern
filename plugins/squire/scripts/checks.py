"""The project's own checks, and the drift checks squire adds on top.

Detection looks at marker files in the project root. A Makefile wins over
language defaults because a project that has one usually wraps its real
commands in it. ``--check`` on the command line replaces detection entirely.

Drift is checked in code, not left to an agent's judgement:

  - a requirement ID on a line the build added to a production file
    (tests and docs may cite IDs; shipped code may not);
  - work left uncommitted: a modified tracked file, or a new untracked file
    that was not there at the base commit.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

TAIL = 60

TEST_DIRS = {"test", "tests", "__tests__", "spec", "specs", "testdata", "fixtures", "e2e"}
TEST_NAME = re.compile(
    r"(^test_.*\.py$|_test\.py$|_test\.go$|\.(test|spec)\.[cm]?[jt]sx?$|_spec\.rb$|Tests?\.(java|kt|cs|swift)$|^conftest\.py$)"
)
DOC_EXT = {".md", ".mdx", ".rst", ".txt", ".adoc"}


def git(root: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {proc.stderr.strip()}")
    return proc.stdout


def _make_targets(makefile: Path) -> set[str]:
    return set(re.findall(r"^([A-Za-z][\w-]*)\s*:(?!=)", makefile.read_text(encoding="utf-8", errors="replace"), re.M))


def detect(root: Path) -> list[dict]:
    """Return the build, lint and test commands for a project, in that order."""
    found: list[dict] = []
    mk = root / "Makefile"
    if mk.exists():
        targets = _make_targets(mk)
        for name in ("build", "lint", "test"):
            if name in targets:
                found.append({"name": name, "cmd": f"make {name}"})
        if found:
            return found

    pkg = root / "package.json"
    if pkg.exists():
        try:
            scripts = json.loads(pkg.read_text(encoding="utf-8")).get("scripts", {}) or {}
        except json.JSONDecodeError:
            scripts = {}
        runner = "pnpm" if (root / "pnpm-lock.yaml").exists() else "yarn" if (root / "yarn.lock").exists() else "npm"
        for name in ("build", "lint", "test"):
            if name in scripts:
                found.append({"name": name, "cmd": f"{runner} run {name}" if name != "test" or runner != "npm" else "npm test"})
        if found:
            return found

    if (root / "go.mod").exists():
        return [{"name": "build", "cmd": "go build ./..."}, {"name": "lint", "cmd": "go vet ./..."},
                {"name": "test", "cmd": "go test ./..."}]
    if (root / "Cargo.toml").exists():
        return [{"name": "build", "cmd": "cargo build"}, {"name": "test", "cmd": "cargo test"}]
    if any((root / f).exists() for f in ("pyproject.toml", "setup.cfg", "setup.py", "pytest.ini")) or (root / "tests").is_dir():
        return [{"name": "test", "cmd": "python3 -m pytest -q"}]
    return []


def run(commands: list[dict], root: Path, timeout: int) -> list[dict]:
    """Run each command from the project root; record its exit code and the tail of its output."""
    results = []
    for c in commands:
        start = time.monotonic()
        try:
            # The command is the project's own check (detected, or given with --check), written as a shell line.
            proc = subprocess.run(c["cmd"], shell=True, cwd=root, capture_output=True, text=True, timeout=timeout)
            code, output = proc.returncode, (proc.stdout + proc.stderr)
        except subprocess.TimeoutExpired as e:
            partial = e.stdout.decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
            code, output = 124, f"{partial}\ncole: timed out after {timeout}s"
        results.append({"name": c["name"], "cmd": c["cmd"], "exit": code,
                        "seconds": round(time.monotonic() - start, 1),
                        "tail": "\n".join(output.rstrip().splitlines()[-TAIL:])})
    return results


def is_exempt(path: str, run_dir_rel: str) -> bool:
    """True for files that may cite requirement IDs: tests, docs, and squire's own run directory."""
    p = Path(path)
    if run_dir_rel and (path == run_dir_rel or path.startswith(run_dir_rel.rstrip("/") + "/")):
        return True
    if p.suffix.lower() in DOC_EXT:
        return True
    if any(part.lower() in TEST_DIRS for part in p.parts[:-1]):
        return True
    return bool(TEST_NAME.search(p.name))


def added_lines(root: Path, base: str) -> list[tuple[str, int, str]]:
    """Every line added between base and HEAD, as (file, line number at HEAD, text)."""
    diff = git(root, "diff", "-U0", "--no-color", "--no-ext-diff", f"{base}..HEAD")
    out, file, line_no = [], None, 0
    for raw in diff.splitlines():
        if raw.startswith("+++ "):
            file = raw[6:] if raw.startswith("+++ b/") else None
        elif raw.startswith("@@"):
            m = re.search(r"\+(\d+)", raw)
            line_no = int(m.group(1)) if m else 0
        elif raw.startswith("+") and file:
            out.append((file, line_no, raw[1:]))
            line_no += 1
    return out


def id_leaks(root: Path, base: str, ids: list[str], run_dir_rel: str) -> list[dict]:
    """Requirement IDs on lines the build added to production files."""
    if not ids:
        return []
    pattern = re.compile(r"(?<![A-Za-z0-9-])(" + "|".join(re.escape(i) for i in sorted(ids, key=len, reverse=True)) + r")(?![\d.]*\d)")
    leaks = []
    for file, line_no, text in added_lines(root, base):
        if is_exempt(file, run_dir_rel):
            continue
        for m in pattern.finditer(text):
            leaks.append({"file": file, "line": line_no, "id": m.group(1), "text": text.strip()[:200]})
    return leaks


def uncommitted(root: Path, untracked_at_base: list[str], run_dir_rel: str) -> list[str]:
    """Tracked files with changes, and untracked files that did not exist at the base commit."""
    out = []
    for line in git(root, "status", "--porcelain", "--untracked-files=all").splitlines():
        path = line[3:].strip().strip('"')
        if run_dir_rel and path.startswith(run_dir_rel.rstrip("/") + "/"):
            continue
        if line.startswith("??") and path in untracked_at_base:
            continue
        out.append(path)
    return out
