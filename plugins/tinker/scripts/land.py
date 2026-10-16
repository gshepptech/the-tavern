"""Landing and verifying work, in code.

``preflight``     before anything is built: the integration check's needs (its
                  runner on PATH, a Docker daemon), a dry start of the check,
                  and the build at the base commit. Any that fails stops the
                  run with the command and its output.
``commit``        how builders and fixers commit. In a split build it stages
                  only the files the actor's slice owns and refuses the rest.
``integration``   runs the spec's end-to-end check and records its exit code
                  against HEAD, so "the suite passes" is a fact code holds.
``verify``        one round's code check: every change committed, no
                  requirement IDs in production code, ownership in a split
                  build, build, lint and the full unit test suite with no
                  failure the base did not have, the integration check, and
                  (after a fix round) that each behavioural fix's test fails
                  before the fix and passes after it.

``owner_of``, ``may_commit``, ``commit``, ``integration`` and the fix check are
cut down from tinker's land.py; tinker's frozen tests and its QA commits are gone.
"""

from __future__ import annotations

from pathlib import Path

import checks
from common import (ARCHIVE, ID_RE, git, git_retry, head, is_doc_file, is_test_file, load_state, mark,
                    read_json, tail, update_state, write_json)
from gates import _norm, overlaps


def _slices(state: dict) -> dict:
    return (state.get("plan") or {}).get("slices") or {}


def _entry_owns(entry: str, path: str) -> bool:
    return overlaps(entry, path) if entry.endswith("/") else _norm(entry) == _norm(path)


def owner_of(state: dict, path: str) -> str:
    """The slice that owns ``path``: a listed file or directory, else the slice
    whose listed file sits in the same directory when ``path`` is a test file
    (tests live with their unit). "" when none does."""
    slices = _slices(state)
    for sid, s in slices.items():
        if s.get("owns_all"):
            return sid
        if any(_entry_owns(e, path) for e in s.get("files") or []):
            return sid
    if is_test_file(path):
        d = str(Path(path).parent).lower()
        for sid, s in slices.items():
            if any(str(Path(e.rstrip("/")).parent).lower() == d for e in s.get("files") or [] if not e.endswith("/")):
                return sid
    return ""


def may_commit(state: dict, actor: str, path: str) -> str:
    """"" when ``actor`` may commit ``path``, else why not. A fixer may also
    commit a file no slice owns: a failure can sit outside every slice."""
    if path.startswith(f"{ARCHIVE}/"):
        return "the run directory is never committed"
    kind, _, sid = actor.partition(":")
    slice_id = sid if kind == "fix" else actor
    if slice_id not in _slices(state):
        return f"unknown actor {actor!r}"
    owner = owner_of(state, path)
    if owner == slice_id or (kind == "fix" and not owner):
        return ""
    return f"owned by {owner or 'no slice'}"


def _changed_paths(root: Path) -> list[str]:
    out = []
    entries = git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all").stdout.split("\0")
    i = 0
    while i < len(entries):
        e = entries[i]
        i += 1
        if len(e) < 4:
            continue
        if e[0] in "RC":
            i += 1  # the rename's source path follows
        out.append(e[3:])
    return [p for p in out if not p.startswith(f"{ARCHIVE}/")]


def commit(root: Path, rdir: Path, actor: str, message: str, paths: list[str]) -> dict:
    state = load_state(rdir)
    explicit = [p[2:] if p.startswith("./") else p for p in paths]
    targets = explicit or _changed_paths(root)
    refused = {p: why for p in targets if (why := may_commit(state, actor, p))}
    if explicit and refused:
        return {"ok": False, "error": "refused: you may not commit these files", "refused": refused}
    targets = [p for p in targets if p not in refused]
    if not targets:
        return {"ok": False, "error": "nothing of yours to commit", "left_uncommitted": refused}
    r = git_retry(root, "add", "-A", "--", *targets)
    if r.returncode != 0:
        return {"ok": False, "error": f"git add: {r.stderr.strip()}"}
    r = git_retry(root, "commit", "-q", "-m", message, "--only", "--", *targets)
    if r.returncode != 0:
        return {"ok": False, "error": f"git commit: {(r.stderr or r.stdout).strip()}"}
    sha = head(root)
    with update_state(rdir) as st:
        st.setdefault("commits", {}).setdefault(actor, []).append(sha)
    return {"ok": True, "commit": sha, "files": targets, "left_uncommitted": refused}


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------
def preflight(root: Path, rdir: Path, integ: dict | None, extra_needs: list[str] = ()) -> dict:
    """Run what the integration check needs, its dry start, and the base build.
    Records the check in state and marks ``preflight`` when everything passes."""
    state = load_state(rdir)
    ran = []
    if integ:
        for n in list(integ.get("needs") or []) + [{"what": "named by the finder", "command": c} for c in extra_needs if c]:
            r = checks.run_command(n["command"], Path(root) / (integ.get("cwd") or ""), timeout=300)
            ran.append({"what": n["what"], "cmd": n["command"], "exit": r["exit"], "tail": tail(r["tail"], 15)})
        if integ.get("dry_run"):
            r = checks.run_command(integ["dry_run"], Path(root) / (integ.get("cwd") or ""), timeout=900)
            ran.append({"what": "dry start of the integration check", "cmd": integ["dry_run"], "exit": r["exit"],
                        "tail": tail(r["tail"], 15)})
    for c in state.get("commands", {}).get("build", []):
        r = checks.run_at(root, rdir, state["base_commit"], c)
        ran.append({"what": "the build at the base commit", "cmd": c["cmd"], "exit": r["exit"], "tail": tail(r["tail"], 15)})
    failed = [x for x in ran if x["exit"] != 0]
    warnings = [] if integ else ["no integration or end-to-end check: verification runs build, lint and unit tests only"]
    if integ and not integ.get("exists", True):
        warnings.append(f"`{integ['command']}` does not exist yet; the builder writes it")
    with update_state(rdir) as st:
        st["integration"] = integ
        st["preflight"] = ran
        if not failed:
            st.setdefault("concerns", []).extend(warnings)
            mark(st, "preflight")
    if failed:
        stop = "The build cannot start here. " + " ".join(
            f"{x['what']}: `{x['cmd']}` exited {x['exit']}:\n{x['tail']}\n" for x in failed)
        stop += f"Fix this, then continue with /tinker:build --resume {state.get('run')}."
        return {"ok": False, "stop": stop, "ran": ran, "integration": integ}
    return {"ok": True, "stop": "", "ran": ran, "integration": integ, "warnings": warnings}


# ---------------------------------------------------------------------------
# Integration and verify
# ---------------------------------------------------------------------------
def integration(root: Path, rdir: Path) -> dict:
    integ = load_state(rdir).get("integration") or {}
    if not integ.get("command"):
        return {"ok": True, "ran": False, "why": "the spec names no integration check"}
    r = checks.run_command(integ["command"], Path(root) / (integ.get("cwd") or ""), int(integ.get("timeout_s") or 3600))
    rec = {"command": integ["command"], "cwd": integ.get("cwd") or "", "exit": r["exit"], "seconds": r["seconds"],
           "head": head(root), "tail": r["tail"], "failures": r["failures"]}
    write_json(Path(rdir) / "checks" / "integration-latest.json", rec)
    return {"ok": r["exit"] == 0, "ran": True, **{k: rec[k] for k in ("command", "exit", "seconds", "head", "failures")},
            "tail": tail(r["tail"], 40)}


def _commits(root: Path, base: str) -> list[str]:
    return git(root, "rev-list", "--reverse", f"{base}..HEAD").stdout.split()


def _files(root: Path, sha: str) -> list[str]:
    return [f for f in git(root, "show", "--name-only", "--format=", sha).stdout.splitlines() if f.strip()]


def ids_in_production(root: Path, base: str, ids: set) -> list[tuple[str, int, str]]:
    """Added lines of non-test, non-doc files that name a spec requirement ID."""
    out, cur, line = [], "", 0
    for ln in git(root, "diff", "-U0", f"{base}..HEAD").stdout.splitlines():
        if ln.startswith("+++ "):
            cur = ln[6:] if ln.startswith("+++ b/") else ""
        elif ln.startswith("@@"):
            try:
                line = int(ln.split("+")[1].split(",")[0].split(" ")[0])
            except (IndexError, ValueError):
                line = 0
        elif ln.startswith("+") and cur and not is_test_file(cur) and not is_doc_file(cur):
            hit = [m for m in ID_RE.findall(ln) if m in ids]
            if hit:
                out.append((cur, line, hit[0]))
            line += 1
    return out


def _fixcheck(root: Path, rdir: Path, rnd: int, base: str) -> list[dict]:
    """Each fix the fixers of round ``rnd`` reported for a behavioural gap: its
    test must fail on the code before the round and pass now."""
    gaps = {g.get("id"): g for g in (read_json(Path(rdir) / "checks" / "spec-r1.json", {}) or {}).get("gaps") or []
            if isinstance(g, dict)}
    out = []
    for path in sorted((Path(rdir) / "fixes").glob(f"r{rnd}-*.json")):
        for fx in (read_json(path, {}) or {}).get("fixes") or []:
            item = str(fx.get("item", ""))
            gap = gaps.get(item)
            if not gap or gap.get("behavioural") is False or fx.get("outcome") != "fixed":
                continue
            tests = fx.get("test_files") or []
            bad = [t for t in tests if not is_test_file(t)]
            res = ({"ok": False, "why": f"not test files: {bad}"} if bad else
                   checks.fail_before_pass_after(root, base, tests, fx.get("test_command", ""), fx.get("cwd") or ""))
            out.append({"item": item, "ok": res["ok"], "why": res["why"], "test_command": fx.get("test_command", "")})
    return out


def verify(root: Path, rdir: Path, rnd: int) -> dict:
    root, rdir = Path(root), Path(rdir)
    state = load_state(rdir)
    sha = head(root)
    prior = read_json(rdir / "checks" / f"verify-r{rnd}.json")
    if prior and prior.get("head") == sha:
        return prior
    base = state["base_commit"]
    index = read_json(rdir / "spec-index.json", {}) or {}
    failures = []

    def fail(kind: str, title: str, detail: str = "", names=None, file: str = "", line: int = 0):
        failures.append({"id": f"V{rnd}-{len(failures) + 1}", "kind": kind, "title": title, "detail": detail,
                         "names": list(names or []), "file": file, "line": line})

    if rnd > 1:
        for fx in _fixcheck(root, rdir, rnd - 1, (state.get("round_base") or {}).get(str(rnd - 1), base)):
            if not fx["ok"]:
                fail("fixcheck", f"the fix for {fx['item']} is not pinned by a test that fails before it: {fx['why']}",
                     f"`{fx['test_command']}`")
    left = [p for p in _changed_paths(root) if p not in set(state.get("untracked_at_start") or [])]
    if left:
        fail("uncommitted", f"{len(left)} changed files were never committed", ", ".join(left[:20]))
    if not _commits(root, base):
        fail("uncommitted", "nothing was committed since the base commit")
    if (state.get("plan") or {}).get("mode") == "split":
        actors = {s: a for a, shas in (state.get("commits") or {}).items() for s in shas}
        for c in _commits(root, base):
            for f in _files(root, c):
                why = "not made with `tinker commit`" if c not in actors else may_commit(state, actors[c], f)
                if why:
                    fail("ownership", f"commit {c[:10]} changes {f}: {why}", file=f)
    for f, line, rid in ids_in_production(root, base, set(index.get("ids") or [])):
        fail("ids", f"{f}:{line} names requirement {rid} in production code; IDs belong in tests and docs", file=f, line=line)
    cmds = [c for k in ("build", "lint", "test") for c in state.get("commands", {}).get(k, [])]
    results = checks.new_failures(root, rdir, base, cmds)
    for r in results:
        if r["status"] == "new_failures":
            fail("checks", f"`{r['cmd']}` has new failures: {', '.join(r['new'][:12])}", tail(r["tail"], 40), r["new"])
    integ = state.get("integration") or {}
    irec = None
    if integ.get("command"):
        latest = read_json(rdir / "checks" / "integration-latest.json")
        irec = latest if latest and latest.get("head") == sha else integration(root, rdir)
        if irec.get("exit") != 0:
            fail("integration", f"the integration check `{integ['command']}` fails (exit {irec.get('exit')})",
                 tail(irec.get("tail", ""), 60), irec.get("failures"))
    out = {"ok": True, "round": rnd, "head": sha, "failures": failures,
           "checks": [{k: r[k] for k in ("cmd", "status", "new")} for r in results],
           "integration": {k: irec.get(k) for k in ("command", "exit", "seconds", "head")} if irec else None}
    write_json(rdir / "checks" / f"verify-r{rnd}.json", out)
    with update_state(rdir) as st:
        st.setdefault("round_base", {})[str(rnd)] = sha
        mark(st, f"verify:{rnd}", failures=len(failures))
    return out
