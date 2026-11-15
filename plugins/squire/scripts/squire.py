#!/usr/bin/env python3
"""squire's code steps. Every command prints one JSON line.

    squire [--root DIR] args <spec> [--max-rounds N] [--timeout S] [--check CMD ...]
    squire [--root DIR] init --spec PATH --run NAME [--max-rounds N] [--timeout S] [--check CMD ...]
    squire [--root DIR] check --run NAME --round N
    squire [--root DIR] gaps --run NAME --round N
    squire [--root DIR] report --run NAME

The Workflow script has no filesystem, so an agent runs these and copies the
line back. Anything that can be decided in code is decided here.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import checks  # noqa: E402
import report  # noqa: E402
import spec_index  # noqa: E402
import verdicts  # noqa: E402

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
RUNS = "squire-runs"
MAX_ROUNDS = 5
SMALL_SPEC = 15


class Stop(Exception):
    """A refusal the user can act on, as opposed to a crash."""


def emit(obj: dict) -> None:
    print(json.dumps(obj, separators=(",", ":")))


def run_dir(root: Path, name: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,80}", name or ""):
        raise Stop(f"invalid run name {name!r}")
    return root / RUNS / name


def load_state(root: Path, name: str) -> tuple[Path, dict]:
    d = run_dir(root, name)
    if not (d / "state.json").exists():
        raise Stop(f"no run named {name!r} in {RUNS}/")
    return d, json.loads((d / "state.json").read_text(encoding="utf-8"))


def write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def head(root: Path) -> str:
    return checks.git(root, "rev-parse", "HEAD").strip()


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--max-rounds", type=int, default=3)
    p.add_argument("--timeout", type=int, default=300)
    p.add_argument("--check", action="append", default=[])


def _limits(a: argparse.Namespace) -> None:
    if not 0 <= a.max_rounds <= MAX_ROUNDS:
        raise Stop(f"--max-rounds must be between 0 and {MAX_ROUNDS}")
    if a.timeout < 10:
        raise Stop("--timeout must be at least 10 seconds")


def cmd_args(root: Path, a: argparse.Namespace) -> dict:
    if not a.spec:
        raise Stop("usage: /squire:build <spec> [--max-rounds N] [--timeout S] [--check CMD]")
    _limits(a)
    spec = (root / a.spec).resolve()
    if not spec.is_file():
        raise Stop(f"spec not found: {a.spec}")
    stem = re.sub(r"[^A-Za-z0-9]+", "-", spec.stem if spec.stem.lower() != "spec" else spec.parent.name).strip("-")[:40] or "spec"
    return {"ok": True, "args": {"plugin_root": str(PLUGIN_ROOT), "project_root": str(root), "spec": str(spec),
                                 "run": f"{stem}-{time.strftime('%Y%m%d-%H%M%S')}", "max_rounds": a.max_rounds,
                                 "timeout": a.timeout, "checks": a.check}}


def cmd_init(root: Path, a: argparse.Namespace) -> dict:
    _limits(a)
    try:
        checks.git(root, "rev-parse", "--show-toplevel")
    except RuntimeError:
        raise Stop(f"{root} is not a git repository")
    dirty = checks.git(root, "status", "--porcelain", "--untracked-files=no").strip()
    if dirty:
        raise Stop("the working tree has uncommitted changes to tracked files; commit or stash them first")
    spec = Path(a.spec)
    spec = spec if spec.is_absolute() else root / spec
    if not spec.is_file():
        raise Stop(f"spec not found: {a.spec}")
    idx = spec_index.index_file(spec)
    reqs = idx["requirements"]
    if not reqs:
        raise Stop("the spec defines no requirement IDs. squire builds structured specs only: give each requirement an ID "
                   "(R-001, FR-1) and acceptance criteria")
    warnings = list(idx["warnings"])
    if len(reqs) > SMALL_SPEC:
        warnings.append(f"the spec has {len(reqs)} requirements; squire is one builder in one lane and suits small specs. "
                        "A spec this size may be better split into parallel slices")
    d = run_dir(root, a.run)
    if d.exists():
        raise Stop(f"run {a.run} already exists")

    base = head(root)
    branch = f"squire/{a.run}"
    checks.git(root, "switch", "-q", "-c", branch)
    (root / RUNS).mkdir(exist_ok=True)
    (root / RUNS / ".gitignore").write_text("*\n", encoding="utf-8")
    d.mkdir()
    shutil.copyfile(spec, d / "spec.md")
    write_json(d / "index.json", idx)
    untracked = [line[3:].strip().strip('"') for line in
                 checks.git(root, "status", "--porcelain", "--untracked-files=all").splitlines() if line.startswith("??")]

    commands = [{"name": f"check{n + 1}", "cmd": c} for n, c in enumerate(a.check)] if a.check else checks.detect(root)
    if not commands:
        warnings.append("no build, lint or test command was found; pass --check to name one. Only the verifier's reading will judge the code")
    baseline = {r["name"]: r["exit"] for r in checks.run(commands, root, a.timeout)}
    for c in commands:
        if baseline[c["name"]] != 0:
            warnings.append(f"`{c['cmd']}` already fails at the base commit (exit {baseline[c['name']]}); "
                            "its failures are not counted against the build")
    state = {"run": a.run, "spec": str(spec.relative_to(root)) if spec.is_relative_to(root) else str(spec),
             "base": base, "branch": branch, "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
             "max_rounds": a.max_rounds, "timeout": a.timeout, "commands": commands, "baseline": baseline,
             "untracked_at_base": untracked, "warnings": warnings}
    write_json(d / "state.json", state)
    return {"ok": True, "run_dir": str(d), "base": base, "branch": branch, "ids": [r["id"] for r in reqs],
            "commands": [c["cmd"] for c in commands], "baseline": baseline, "warnings": warnings}


def cmd_check(root: Path, a: argparse.Namespace) -> dict:
    d, st = load_state(root, a.run)
    rel = f"{RUNS}/{a.run}"
    ids = [r["id"] for r in json.loads((d / "index.json").read_text(encoding="utf-8"))["requirements"]]
    results = checks.run(st["commands"], root, st["timeout"])
    out = {"round": a.round, "head": head(root), "commands": results,
           "id_leaks": checks.id_leaks(root, st["base"], ids, rel),
           "uncommitted": checks.uncommitted(root, st["untracked_at_base"], rel)}
    write_json(d / "verify" / f"check-r{a.round}.json", out)
    new_failures = [c["cmd"] for c in results if c["exit"] != 0 and st["baseline"].get(c["name"], 0) == 0]
    return {"ok": True, "round": a.round, "head": out["head"], "file": str(d / "verify" / f"check-r{a.round}.json"),
            "commands": [{"cmd": c["cmd"], "exit": c["exit"]} for c in results], "new_failures": new_failures,
            "id_leaks": len(out["id_leaks"]), "uncommitted": out["uncommitted"]}


def cmd_gaps(root: Path, a: argparse.Namespace) -> dict:
    d, st = load_state(root, a.run)
    vfile, cfile = d / "verify" / f"verify-r{a.round}.json", d / "verify" / f"check-r{a.round}.json"
    errors = []
    if not cfile.exists():
        errors.append(f"the checks were not run this round: run `squire check --run {a.run} --round {a.round}`")
    else:
        ran_at = json.loads(cfile.read_text(encoding="utf-8"))["head"]
        if ran_at != head(root):
            errors.append(f"the checks ran at {ran_at[:12]} but HEAD is now {head(root)[:12]}; run them again")
    if not vfile.exists():
        errors.append(f"no verifier file at {vfile}")
    else:
        try:
            data = json.loads(vfile.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            data, errors = None, [*errors, f"{vfile.name} is not valid JSON: {e}"]
        if data is not None:
            ids = [r["id"] for r in json.loads((d / "index.json").read_text(encoding="utf-8"))["requirements"]]
            errors += verdicts.validate(data, ids, root)
    if errors:
        return {"ok": True, "valid": False, "errors": errors}
    found = verdicts.gaps(data, json.loads(cfile.read_text(encoding="utf-8")), st["baseline"], a.round)
    write_json(d / "verify" / f"gaps-r{a.round}.json", {"round": a.round, "gaps": found})
    kinds: dict[str, int] = {}
    for g in found:
        kinds[g["kind"]] = kinds.get(g["kind"], 0) + 1
    return {"ok": True, "valid": True, "open": len(found), "by_kind": kinds,
            "file": str(d / "verify" / f"gaps-r{a.round}.json")}


def cmd_report(root: Path, a: argparse.Namespace) -> dict:
    d, _ = load_state(root, a.run)
    return {"ok": True, **report.build(d)}


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="squire")
    p.add_argument("--root", default=".")
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("args")
    s.add_argument("spec", nargs="?")
    _common(s)
    s = sub.add_parser("init")
    s.add_argument("--spec", required=True)
    s.add_argument("--run", required=True)
    _common(s)
    for name in ("check", "gaps"):
        s = sub.add_parser(name)
        s.add_argument("--run", required=True)
        s.add_argument("--round", type=int, required=True)
    s = sub.add_parser("report")
    s.add_argument("--run", required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    try:
        a = parser().parse_args(argv)
    except SystemExit as e:
        emit({"ok": False, "stop": "could not parse the arguments; see /squire:help"})
        return int(e.code or 1)
    root = Path(a.root).resolve()
    handler = {"args": cmd_args, "init": cmd_init, "check": cmd_check, "gaps": cmd_gaps, "report": cmd_report}[a.command]
    try:
        emit(handler(root, a))
        return 0
    except Stop as e:
        emit({"ok": False, "stop": str(e)})
        return 0
    except (RuntimeError, OSError, KeyError, json.JSONDecodeError) as e:
        emit({"ok": False, "error": f"{type(e).__name__}: {e}"})
        return 1


if __name__ == "__main__":
    sys.exit(main())
