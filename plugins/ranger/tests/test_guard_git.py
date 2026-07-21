"""guard-git.py — the PreToolUse hook that keeps an unattended run local-only.

deny == exit code 2; allow == exit 0. The guard only acts while a run is armed
and active; outside that it must never touch the user's own git commands.
"""

from __future__ import annotations

import pytest

ACTIVE = {
    "status": "active",
    "session_id": "S1",
    "flags": {"branch": False, "merge_dev": False},
    "max_cycles": 0,
    "max_seconds": 0,
    "started_at": "2026-07-21T10:00:00Z",
}


def _arm(guard, **overrides):
    state = {**ACTIVE, **overrides}
    guard.project.arm(state)


# --- always denied, no flag enables them ---------------------------------

@pytest.mark.parametrize(
    "cmd",
    [
        "git push origin main",
        "git push --force",
        "git -C /repo push",
        "echo building && git push",
        "gh pr create --fill",
        "git remote set-url origin git@evil",
        "git clean -fdx",
    ],
)
def test_denied_by_default(guard, cmd):
    _arm(guard)
    assert guard(cmd) == "deny"


def test_push_denied_even_with_all_flags(guard):
    _arm(guard, flags={"branch": True, "merge_dev": True})
    assert guard("git push origin dev") == "deny"


# --- allowed: local work, and the revert path --------------------------------

@pytest.mark.parametrize(
    "cmd",
    [
        'git commit -m "docs: explain how git push works"',
        "git add -A",
        "git reset --hard HEAD",       # revert-don't-pile-on needs this
        "git revert abc123",           # and this
        "git clean -fd",               # non-ignored only
        "git log --oneline -5",
        "npm test",
    ],
)
def test_allowed_by_default(guard, cmd):
    _arm(guard)
    assert guard(cmd) == "allow"


# --- flag-gated: branch creation and integration -----------------------------

@pytest.mark.parametrize("cmd", ["git checkout -b feat", "git switch -c feat", "git branch feat"])
def test_branch_creation_needs_flag(guard, cmd):
    _arm(guard)
    assert guard(cmd) == "deny"
    _arm(guard, flags={"branch": True, "merge_dev": False})
    assert guard(cmd) == "allow"


@pytest.mark.parametrize("cmd", ["git merge dev", "git cherry-pick abc123"])
def test_merge_needs_flag(guard, cmd):
    _arm(guard)
    assert guard(cmd) == "deny"
    _arm(guard, flags={"branch": False, "merge_dev": True})
    assert guard(cmd) == "allow"


# --- scope: the guard is invisible unless a run is armed and active -----------

def test_inactive_run_allows_everything(guard):
    _arm(guard, status="stopped")
    assert guard("git push origin main") == "allow"


def test_disarmed_marker_allows_everything(guard):
    guard.project.disarm()
    assert guard("git push --force origin main") == "allow"


def test_other_session_not_restricted(guard):
    _arm(guard)  # armed by session S1
    assert guard("git push", session_id="OTHER") == "allow"
