#!/usr/bin/env python3
"""Ranger guard-git — PreToolUse guard for /ranger:run (Ranger v0.1.0).

An unattended loop must not be able to publish. Prompt instructions are a
request; a hook is a guarantee. While a Ranger run is active this guard denies
any Bash command that would push to a remote, mutate remote config, open a pull
request, or — unless the matching flag was passed — create a branch or merge.

Enforced while a run is active:
  always denied        git push, git remote add/set-url/rename/remove,
                       gh pr create/merge, git clean -x (would delete ignored
                       files such as .env), git branch -D of a protected branch
  needs --branch       git checkout -b, git switch -c, git branch <new>,
                       git worktree add
  needs --merge-dev    git merge, git cherry-pick, git rebase <other-branch>

`git reset --hard` and `git revert` are deliberately ALLOWED — they are how the
loop honours revert-don't-pile-on when a change regresses.

Fast path: no (or empty) .ranger/active-run.json -> exit 0. This hook fires on
EVERY Bash call in EVERY session, so outside an active run it must be invisible.
It never restricts the user's own hand-run git commands.

Fail-open on its own errors: malformed input -> exit 0. A guard that crashes
must not brick the Bash tool.

PreToolUse protocol: to deny, print the decision JSON to stderr and exit 2.
Exit 0 with no output allows the call.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# Shell separators that begin a new command. Splitting on these means a commit
# message containing the words "git push" is not mistaken for a push.
SEGMENT_SPLIT = re.compile(r"(?:&&|\|\||[;|\n])")

# `FOO=bar sudo -E git ...` — strip the noise before the real command word.
LEADING_NOISE = re.compile(r"^(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+|sudo\s+|command\s+|env\s+)+")

PROTECTED_BRANCHES = {"main", "master", "dev", "develop", "development"}


def _allow() -> int:
    return 0


def _deny(reason: str) -> int:
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

    state = _load_json(run_dir / "state.json")
    if not state or state.get("status") != "active":
        return None

    state_session = state.get("session_id")
    if state_session and session_id and state_session != session_id:
        return None

    flags = state.get("flags")
    return flags if isinstance(flags, dict) else {}


def _segments(command: str) -> list[list[str]]:
    """Split a shell string into per-command token lists, best effort."""
    out = []
    for raw in SEGMENT_SPLIT.split(command):
        cleaned = LEADING_NOISE.sub("", raw.strip())
        if cleaned:
            out.append(cleaned.split())
    return out


def _verdict(tokens: list[str], flags: dict) -> str | None:
    """Return a denial reason for one command, or None to allow it."""
    prog = os.path.basename(tokens[0])
    args = tokens[1:]
    # Skip git's global options (-C <dir>, --git-dir=..., -c k=v) to find the
    # subcommand: `git -C foo push` must still read as a push.
    while args and (args[0].startswith("-") or args[0].startswith("--")):
        if args[0] in ("-C", "-c", "--git-dir", "--work-tree") and len(args) > 1:
            args = args[2:]
        else:
            args = args[1:]
    if not args:
        return None
    sub, rest = args[0], args[1:]

    if prog == "gh":
        if sub == "pr" and rest and rest[0] in ("create", "merge", "ready"):
            return (
                "Ranger works locally only — opening or merging a pull request "
                "is never permitted during a run."
            )
        if sub in ("release", "repo") and rest and rest[0] in ("create", "delete", "edit"):
            return "Ranger works locally only — remote repository mutation is blocked."
        return None

    if prog != "git":
        return None

    if sub == "push":
        return (
            "Ranger commits LOCALLY ONLY. `git push` is blocked for the whole "
            "run — there is no flag that enables it. Commit locally and let the "
            "user push when they have reviewed the work."
        )

    if sub == "remote" and rest and rest[0] in ("add", "set-url", "rename", "remove", "rm"):
        return "Ranger must not mutate remote configuration during a run."

    if sub == "clean" and any("x" in t for t in rest if t.startswith("-")):
        return (
            "`git clean -x` deletes git-ignored files (.env, local config). "
            "Blocked during an unattended run."
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
        if any(t in ("-b", "-B", "-c", "-C") for t in rest) and not flags.get("branch"):
            return (
                "Branch creation needs `--branch`. Without it Ranger commits to "
                "the current branch."
            )
        return None

    if sub == "worktree" and rest and rest[0] == "add" and not flags.get("branch"):
        return "Creating a worktree needs `--branch`."

    if sub in ("merge", "cherry-pick") and not flags.get("merge_dev"):
        return (
            f"`git {sub}` needs `--merge-dev`. Without it Ranger leaves "
            "integration to the user."
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
