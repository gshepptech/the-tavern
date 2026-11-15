#!/usr/bin/env python3
"""Ranger guard-git — PreToolUse guard for /ranger:run (Ranger v0.3.0).

An unattended loop must not be able to publish. A prompt instruction is a
request the model may reinterpret; this hook is enforced outside the model, so
it holds even under bypassed permissions. While a Ranger run is active it
denies any Bash command that would push to a remote, mutate remote config, send
work off the machine, or — unless the matching flag was passed — create a
branch or merge.

Enforced while a run is active:
  always denied        git push, git remote add/set-url/rename/remove/rm,
                       git config remote.*, git send-email, gh pr
                       create/merge/ready, gh release/repo create/delete/edit,
                       gh api with a write method or request fields, git
                       clean -x (would delete ignored files such as .env),
                       git branch -D/-d/--delete of a protected branch
  needs --branch       git checkout -b/-B, git switch -c/-C, git branch <new>,
                       git worktree add
  needs --merge-dev    git merge, git cherry-pick, git rebase <other-branch>

`git reset --hard` and `git revert` are deliberately ALLOWED — they are how the
loop honours revert-don't-pile-on when a change regresses.

THREAT MODEL — read this before trusting it further than it goes.
The adversary is an agent doing something unintended, not a human trying to
defeat the guard. Commands are inspected as text, so the guard is strong
against accidents and weak against deliberate obfuscation. It resolves shell
quoting, recurses into `sh -c` / `bash -c` / `eval` payloads, and strips
`sudo` / `env` / `VAR=` prefixes — the wrappers an agent plausibly reaches for.
It does NOT sandbox: a command that writes a script and runs it, or that
reaches the network by some route nobody enumerated, gets through. Treat this
as a strong guardrail, not a security boundary. The actual containment for
unattended runs is running them somewhere disposable.

Fast path: no (or empty) .ranger/active-run.json -> exit 0. This hook fires on
EVERY Bash call in EVERY session, so outside an active run it must be invisible.
It never restricts the user's own hand-run git commands.

Fail-open on its own errors: malformed input -> exit 0. A guard that crashes
must not brick the Bash tool. A line that will not lex still gets inspected by
the older regex split rather than being waved through.

PreToolUse protocol: to deny, print the decision JSON to stderr and exit 2.
Exit 0 with no output allows the call.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Shell separators that begin a new command. Splitting on these means a commit
# message containing the words "git push" is not mistaken for a push.
SEGMENT_SPLIT = re.compile(r"(?:&&|\|\||[;|\n])")

# `FOO=bar sudo -E git ...` — strip the noise before the real command word.
LEADING_NOISE = re.compile(r"^(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+|sudo\s+|command\s+|env\s+)+")

# Launchers that run another program. Without stripping these, `nohup git push`
# and `timeout 60 git push` read as commands named nohup and timeout.
LAUNCHERS = {
    "sudo", "command", "env", "nohup", "timeout", "time", "nice", "ionice",
    "stdbuf", "setsid", "doas", "xargs", "watch",
}

# git subcommands that move work off this machine. `push` is the obvious one;
# every other name here is an equally good way to publish.
GIT_PUBLISH_VERBS = {
    "push", "send-email", "request-pull", "bundle", "daemon", "svn", "p4",
    "format-patch",
}

# gh is an allowlist, not a denylist: it grows verbs faster than a guard can
# track, and almost all of them touch the network. Only unmistakable reads pass.
GH_SAFE = {
    ("pr", "list"), ("pr", "view"), ("pr", "diff"), ("pr", "checks"),
    ("issue", "list"), ("issue", "view"),
    ("repo", "view"), ("repo", "list"),
    ("run", "list"), ("run", "view"), ("run", "watch"),
    ("release", "list"), ("release", "view"),
    ("workflow", "list"), ("workflow", "view"),
    ("auth", "status"), ("browse", None), ("status", None),
}

PROTECTED_BRANCHES = {"main", "master", "dev", "develop", "development"}

# Shells whose `-c <payload>` argument is another command line. Without looking
# inside, `sh -c "git push"` sails straight past a guard that only inspects the
# outer command word.
WRAPPER_SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "fish"}

# `gh api` can write to a remote directly — creating refs, tags and releases —
# without ever naming a subcommand the guard would otherwise recognise.
GH_API_WRITE_METHODS = {"POST", "PATCH", "PUT", "DELETE"}


def _allow() -> int:
    return 0


def _deny(reason: str) -> int:
    # Always say how to clear the state. Someone hitting this without a run in
    # progress is looking at a stale marker, and a denial with no exit is the
    # difference between a guardrail and a trap.
    reason = (
        f"{reason}\n"
        "(If no Ranger run is in progress, this marker is stale: run "
        "/ranger:stop, or delete .ranger/active-run.json)"
    )
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                },
                "systemMessage": reason,
            }
        ),
        file=sys.stderr,
    )
    return 2


def _load_json(path: Path) -> dict | None:
    try:
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


STALE_AFTER_SECONDS = 6 * 60 * 60


def _pid_alive(pid) -> bool | None:
    """True/False if we can tell, None if we cannot."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return None
    if pid <= 0:
        return None
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by someone else
    except OSError:
        return None


def _run_is_dead(pointer: dict, state: dict, state_path: Path) -> bool:
    """Has this 'active' run actually stopped without saying so?

    `status` only becomes non-active via /ranger:stop or the clean terminal
    path. A runner that is Ctrl-C'd, killed, or dies with the laptop leaves
    `active` on disk forever. That matters more than it sounds: a headless run
    deliberately skips session scoping, so a dead one goes on denying the
    USER's own pushes, branches and PRs in that repo indefinitely, in every
    later session, with no indication why.

    Two liveness signals. Any one saying "dead" disarms the guard.

    Deliberately NOT a wall-clock/`max_seconds` signal. The lead enforces the
    cap at the TOP of each cycle and only then flips `status: capped` — which
    the caller already honours via the `status != active` check. Between the
    deadline passing and that flip, the run is fully LIVE: the lead is building
    and implementer agents are running Bash. A clock-based disarm would open
    the guard for the whole of that over-cap cycle, allowing a `git push` in
    exactly the past-its-budget-but-still-running state the guard exists for.
    Genuine abandonment is caught by the PID and staleness signals instead.
    """
    # 1. The runner's PID, when ranger-run.sh recorded one. Deterministic, and
    #    fails safe: a dead PID later reused by another process reads as alive,
    #    so the guard stays armed rather than disarming wrongly.
    if _pid_alive(pointer.get("runner_pid")) is False:
        return True

    # 2. Staleness of last progress. The lead rewrites state.json at every
    #    phase transition, so an untouched file means nothing is driving it.
    #    A backstop for a run with no recorded PID (e.g. the in-session /loop
    #    form): generous enough that a slow phase is never mistaken for death.
    try:
        if time.time() - state_path.stat().st_mtime > STALE_AFTER_SECONDS:
            return True
    except OSError:
        pass

    return False


def _active_flags(project_dir: Path, session_id) -> dict | None:
    """Flags of the active run, or None when no run is armed for this session."""
    marker = project_dir / ".ranger" / "active-run.json"
    if not marker.is_file():
        return None

    pointer = _load_json(marker)
    run_dir_raw = pointer.get("run_dir") if pointer else None
    if not run_dir_raw:
        return None

    run_dir = Path(run_dir_raw)
    if not run_dir.is_absolute():
        run_dir = project_dir / run_dir

    state_path = run_dir / "state.json"
    state = _load_json(state_path)
    if not state or state.get("status") != "active":
        return None

    if _run_is_dead(pointer, state, state_path):
        return None

    # Session scoping keeps an interactive run from policing a human working in
    # the same repo from another window. It must NOT apply to a headless run:
    # the runner spawns a fresh `claude -p` per cycle, so every cycle carries a
    # new session id and the guard would disarm itself from cycle 2 onward —
    # in precisely the unattended mode the guarantee exists for.
    if state.get("mode") != "headless":
        state_session = state.get("session_id")
        if state_session and session_id and state_session != session_id:
            return None

    flags = state.get("flags")
    return flags if isinstance(flags, dict) else {}


OPERATORS = {";", "&&", "||", "|", "&", "\n"}


def _split_commands(command: str) -> list[list[str]]:
    """Tokenize a shell line into per-command token lists, respecting quotes.

    Quote awareness matters in both directions. It stops a commit message that
    happens to contain "; git push" from reading as a real push, and it
    collapses the adjacent-quote trick (`git pu""sh` -> `git push`) that
    defeats a naive whitespace split.

    Falls back to the older regex split if the line will not lex — usually
    unbalanced quotes. A line we cannot parse must still be inspected, never
    silently allowed.
    """
    try:
        lex = shlex.shlex(command, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        tokens = list(lex)
    except ValueError:
        return [
            LEADING_NOISE.sub("", raw.strip()).split()
            for raw in SEGMENT_SPLIT.split(command)
            if LEADING_NOISE.sub("", raw.strip())
        ]

    out: list[list[str]] = []
    current: list[str] = []
    for tok in tokens:
        if tok in OPERATORS:
            if current:
                out.append(current)
                current = []
        else:
            current.append(tok)
    if current:
        out.append(current)
    return out


def _strip_noise(tokens: list[str]) -> list[str]:
    """Drop launcher and assignment prefixes to reach the real command word.

    `nohup git push`, `timeout 60 git push`, `env -i git push` and
    `xargs -I{} git push` all named a launcher as argv[0] and sailed through a
    guard that only looked at the first token. Options belonging to the
    launcher are skipped too, so `-i` in `env -i git push` does not become the
    command.
    """
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        base = os.path.basename(tok)
        if base in LAUNCHERS or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", tok):
            i += 1
            # Skip the launcher's own flags and their values.
            while i < len(tokens) and tokens[i].startswith("-"):
                if tokens[i] in ("-I", "-n", "-P", "-s", "-o") and i + 1 < len(tokens):
                    i += 2
                else:
                    i += 1
            # `timeout 60 git push` and `watch 2 git push` take a positional
            # duration before the command they run.
            if base in ("timeout", "watch") and i < len(tokens):
                if re.fullmatch(r"\d+(\.\d+)?[smhd]?", tokens[i]):
                    i += 1
            continue
        break
    return tokens[i:]


def _segments(command: str, _depth: int = 0) -> list[list[str]]:
    """Every command in a shell line, including ones hidden inside wrappers.

    Recurses into wrapper shells and `eval`: the guard is worthless if
    `sh -c "git push"` sails through while a bare `git push` is denied. Depth
    is bounded so pathological nesting cannot spin.
    """
    out: list[list[str]] = []
    for tokens in _split_commands(command):
        tokens = _strip_noise(tokens)
        if not tokens:
            continue
        out.append(tokens)

        if _depth >= 3:
            continue

        prog = os.path.basename(tokens[0])
        # `sh -c '<payload>'` — the payload is its own command line. The flag
        # can be bundled with others (`bash -lc`, `sh -cx`, `sh -xc`), so match
        # any short-flag token that contains a `c`, not the exact string `-c`.
        if prog in WRAPPER_SHELLS:
            for i, tok in enumerate(tokens[1:], start=1):
                is_c_flag = (
                    tok.startswith("-")
                    and not tok.startswith("--")
                    and "c" in tok[1:]
                )
                if is_c_flag and i + 1 < len(tokens):
                    out.extend(_segments(tokens[i + 1], _depth + 1))
                    break
        # `eval git push` — the remainder is a command line.
        elif prog == "eval" and len(tokens) > 1:
            out.extend(_segments(" ".join(tokens[1:]), _depth + 1))
    return out


def _verdict(tokens: list[str], flags: dict) -> str | None:
    """Return a denial reason for one command, or None to allow it."""
    prog = os.path.basename(tokens[0])

    # The guard's own arming file lives inside the tree it polices, so a
    # command that deletes it silently switches the guard off for the rest of
    # the run. run.md tells the loop to run `git clean -fd` on its reject path
    # and `.ranger/` is untracked by default, which makes this reachable by
    # accident rather than by intent.
    if any(".ranger" in tok for tok in tokens[1:]) and prog in (
        "rm", "rmdir", "mv", "shred", "truncate",
    ):
        return (
            "`.ranger/` holds the run state this guard reads. Removing or "
            "moving it would disarm the guard mid-run."
        )

    # `git-push` is a real, dispatchable form of `git push`.
    if prog.startswith("git-"):
        tokens = ["git", prog[4:], *tokens[1:]]
        prog = "git"

    args = tokens[1:]
    # Skip git's global options (-C <dir>, --git-dir=..., -c k=v) to find the
    # subcommand: `git -C foo push` must still read as a push.
    saw_alias_config = False
    # Global flags that take a following value, per program. Skipping their
    # value too is what keeps `gh --repo o/r pr view` from reading `o/r` as the
    # subcommand and wrongly denying a legitimate read.
    value_flags = {
        "git": {"-C", "-c", "--git-dir", "--work-tree"},
        "gh": {"-R", "--repo", "--hostname"},
    }.get(prog, set())
    while args and args[0].startswith("-"):
        if args[0] in value_flags and len(args) > 1:
            # `git -c alias.yolo=push yolo` defines an alias then invokes it,
            # so the subcommand the guard reads is a name it has never heard of.
            if args[0] == "-c" and args[1].startswith("alias."):
                saw_alias_config = True
            args = args[2:]
        else:
            args = args[1:]
    if not args:
        return None
    sub, rest = args[0], args[1:]

    if prog == "git" and saw_alias_config:
        return (
            "`git -c alias.<name>=...` defines an alias and runs it in one "
            "command, which hides the real subcommand from this guard."
        )

    if prog == "gh":
        # Allowlist, not denylist. gh grows verbs faster than any guard tracks
        # them, and nearly all of them talk to the network — `gh gist create`,
        # `gh release upload`, `gh secret set`, `gh workflow run` and
        # `gh auth token` would all walk past a short denylist.
        verb = rest[0] if rest and not rest[0].startswith("-") else None
        # `gh api` is judged by its HTTP method just below, not by the
        # allowlist: a plain GET is a legitimate read, a write is not.
        if sub != "api" and (sub, verb) not in GH_SAFE and (sub, None) not in GH_SAFE:
            if sub == "auth" and verb == "token":
                return "`gh auth token` would print a credential into the transcript."
            return (
                f"`gh {sub}{' ' + verb if verb else ''}` is not on the read-only "
                "allowlist. Ranger works locally only; only unmistakable reads "
                "are permitted during a run."
            )
        # `gh api -X POST /repos/o/r/git/refs` writes to the remote without ever
        # naming a subcommand the checks above would catch. Reads are fine.
        if sub == "api":
            for i, tok in enumerate(rest):
                if tok in ("-X", "--method") and i + 1 < len(rest):
                    if rest[i + 1].upper() in GH_API_WRITE_METHODS:
                        return (
                            "`gh api` with a write method mutates the remote. "
                            "Ranger works locally only."
                        )
                if tok.startswith("--method="):
                    if tok.split("=", 1)[1].upper() in GH_API_WRITE_METHODS:
                        return (
                            "`gh api` with a write method mutates the remote. "
                            "Ranger works locally only."
                        )
                if tok in ("-f", "-F", "--field", "--raw-field", "--input"):
                    # gh infers POST when fields are supplied.
                    return (
                        "`gh api` with request fields implies a write. "
                        "Ranger works locally only."
                    )
        return None

    if prog != "git":
        return None

    if sub in GIT_PUBLISH_VERBS:
        return (
            f"Ranger commits LOCALLY ONLY. `git {sub}` moves work off this "
            "machine and is blocked for the whole run — there is no flag that "
            "enables it. Commit locally and let the user publish once they "
            "have reviewed the work."
        )

    # `git archive --remote=` and `git fetch --upload-pack=` both reach a
    # remote and the latter executes an arbitrary command there.
    if sub in ("archive", "fetch", "ls-remote", "clone") and any(
        t.startswith(("--remote=", "--upload-pack=", "--exec=")) for t in rest
    ):
        return f"`git {sub}` with a remote/exec option reaches off this machine."

    # Rewriting a ref by hand sidesteps every branch and merge check below.
    if sub == "update-ref":
        return "`git update-ref` rewrites a ref directly, bypassing the branch guards."

    if sub == "submodule" and rest and rest[0] == "add":
        return "`git submodule add` introduces a new remote into the repository."

    if sub == "remote" and rest and rest[0] in ("add", "set-url", "rename", "remove", "rm"):
        return "Ranger must not mutate remote configuration during a run."

    # `git config remote.origin.pushurl <url>` repoints where a push would go.
    if sub == "config" and any(t.startswith("remote.") for t in rest):
        return "Ranger must not mutate remote configuration during a run."

    # send-email publishes work outside the repo just as effectively as a push.
    if sub == "send-email":
        return "Ranger works locally only — `git send-email` sends work off the machine."

    if sub == "clean":
        # -x and -X both delete git-ignored files; -X deletes ONLY those, which
        # is precisely the .env case the block exists for. The old check was
        # lowercase-only, so -X was allowed, and it substring-matched any flag,
        # so `--exclude=*.pyx` was denied for containing an "x".
        for tok in rest:
            if not tok.startswith("-"):
                continue
            if tok.startswith("--"):
                if tok in ("--force", "--dry-run", "--quiet", "--interactive"):
                    continue
                if tok.split("=", 1)[0] in ("--exclude",):
                    continue
            elif "x" not in tok and "X" not in tok:
                continue
            else:
                return (
                    "`git clean -x/-X` deletes git-ignored files (.env, local "
                    "config). Blocked during an unattended run."
                )

    if sub == "branch":
        if any(t in ("-D", "-d", "--delete") for t in rest):
            targets = [t for t in rest if not t.startswith("-")]
            if any(t in PROTECTED_BRANCHES for t in targets):
                return "Refusing to delete a protected branch during a run."
            return None
        creating = [t for t in rest if not t.startswith("-")]
        if creating and not flags.get("branch"):
            return (
                "Branch creation needs `--branch`. Without it Ranger commits to "
                "the current branch."
            )
        return None

    if sub in ("checkout", "switch"):
        creating = any(t in ("-b", "-B", "-c", "-C") for t in rest) or any(
            t.split("=", 1)[0] in ("--branch", "--create") for t in rest
        )
        if creating and not flags.get("branch"):
            return (
                "Branch creation needs `--branch`. Without it Ranger commits to "
                "the current branch."
            )
        return None

    if sub == "worktree" and rest and rest[0] == "add" and not flags.get("branch"):
        return "Creating a worktree needs `--branch`."

    if sub == "stash" and rest and rest[0] == "branch" and not flags.get("branch"):
        return "`git stash branch` creates a branch, which needs `--branch`."

    if sub in ("merge", "cherry-pick", "pull") and not flags.get("merge_dev"):
        return (
            f"`git {sub}` integrates other work and needs `--merge-dev`. "
            "Without it Ranger leaves integration to the user. (`git pull` is "
            "a fetch plus a merge.)"
        )

    if sub == "rebase" and rest and not flags.get("merge_dev"):
        # An interactive/autosquash rebase of your own commits is fine; pulling
        # another branch underneath you is integration.
        if not any(t.startswith("-") for t in rest[:1]):
            return "`git rebase <branch>` needs `--merge-dev`."

    return None


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return _allow()

    if event.get("tool_name") != "Bash":
        return _allow()

    command = (event.get("tool_input") or {}).get("command")
    if not isinstance(command, str) or not command.strip():
        return _allow()

    project_dir = Path(event.get("cwd") or os.getcwd())
    flags = _active_flags(project_dir, event.get("session_id"))
    if flags is None:
        return _allow()  # no active run — never restrict the user's own work

    for tokens in _segments(command):
        reason = _verdict(tokens, flags)
        if reason:
            return _deny(f"[ranger:guard] {reason}")

    return _allow()


if __name__ == "__main__":
    sys.exit(main())
