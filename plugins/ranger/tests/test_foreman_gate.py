"""foreman-gate.py — the Stop hook that keeps an active run from ending early.

block == exit 0 with {"decision":"block", ...}; allow == exit 0, no output.
The gate must fail OPEN: any malformed input allows the stop, never traps.
"""

from __future__ import annotations

ACTIVE = {
    "mode": "interactive",
    "status": "active",
    "phase": "verify",
    "cycle": 3,
    "item": "polish the settings page",
    "stall_count": 0,
    "max_cycles": 0,
    "max_seconds": 0,
    "started_at": "2026-07-21T10:00:00Z",
    "session_id": "S1",
}


def _arm(gate, **overrides):
    gate.project.arm({**ACTIVE, **overrides})


def test_active_run_blocks_stop(gate):
    _arm(gate)
    blocked, reason = gate()
    assert blocked
    assert "ranger:run" in reason
    assert "VERIFY" in reason.upper()  # directive names the current phase


def test_headless_mode_allows_stop(gate):
    # headless: the external bash loop is the enforcement; each process must exit
    _arm(gate, mode="headless")
    assert gate() == (False, "")


def test_stopped_status_allows(gate):
    _arm(gate, status="stopped")
    assert gate() == (False, "")


def test_cycle_cap_reached_allows(gate):
    _arm(gate, cycle=5, max_cycles=5)
    assert gate() == (False, "")


def test_stall_directive_appears(gate):
    _arm(gate, phase="survey", stall_count=4)
    blocked, reason = gate()
    assert blocked
    assert "quarantine" in reason.lower()


def test_other_session_not_trapped(gate):
    _arm(gate)  # armed by S1
    assert gate(session_id="OTHER") == (False, "")


def test_no_marker_allows(gate):
    # project has .ranger/ but no active-run.json written
    assert gate() == (False, "")


def test_corrupt_state_fails_open(gate):
    gate.project.arm_raw(
        marker_text='{"run_id":"r1","run_dir":".ranger/runs/r1"}',
        state_text="not json {",
    )
    assert gate() == (False, "")


def test_empty_marker_allows(gate):
    gate.project.disarm()
    assert gate() == (False, "")
