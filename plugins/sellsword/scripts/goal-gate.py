#!/usr/bin/env python3
"""Sellsword goal-gate — Stop-hook enforcement for /sellsword:goal (Sellsword v0.2.0).

While a Sellsword goal run is active, this Stop hook blocks Claude from ending the
turn until the goal is met (auditor AND fresh-eyes both return `pass`), a safety
cap is reached, or the run is no longer active (cancelled / blocked).

This is the ENFORCEMENT layer behind /sellsword:goal. commands/goal.md drives the
cooperative loop; this hook is the backstop that catches drift — a premature
"done", a mishandled agent return, an early stop.

Contract — written by commands/goal.md, read here:
  <project>/.sellsword/active-goal.json
      {"run_id": "...", "run_dir": ".sellsword/runs/<run_id>"}
      An empty object {} means "no active goal" (goal.md empties it on exit).
  <run_dir>/state.json   (goal-mode fields)
      mode                     "goal"
      status                   active | goal_met | capped | stuck |
                               blocked | cancelled
      condition                str   — the completion condition
      cycle                    int   — completed verify cycles
      max_cycles               int
      max_seconds              int
      started_at               ISO-8601 UTC
      last_auditor_verdict     pass | conditional-pass | fail | null
      last_fresh_eyes_verdict  pass | partial | fail | null

Fast path: no (or empty) .sellsword/active-goal.json -> exit 0. This hook fires on
EVERY Stop in EVERY session, so it must be a silent no-op unless a Sellsword goal
run is genuinely in progress.

Fail-open: any malformed/missing input -> exit 0 (allow stop). A Stop hook must
never trap the user because of its own bug.

Stop protocol: print {"decision":"block","reason":...} to block; exit 0 with no
output to allow.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# A goal loop runs inside a Claude session — there is no external runner to
# record a PID or trap on exit. So if that session is Ctrl-C'd or killed while
# the run is uncapped (max_seconds == 0), `status` stays `active` on disk with
# nothing to clear it, and this Stop hook goes on blocking EVERY later session
# in the repo from ending its turn — a far worse trap than a denied git command.
# state.json is rewritten every cycle (commands/goal.md PHASE 4), so its mtime
# is a heartbeat. The unit between writes is a whole builder+auditor+fresh-eyes
# cycle, which on a hard "thorough" problem can run for hours, so the window is
# deliberately wide: a cold heartbeat means the loop is abandoned, and a dead
# run must never police a live session. A false "dead" here only lets a loop
# end early (the user resumes) — milder than the guard's fail-open — so the
# margin is set generously rather than tight.
STALE_AFTER_SECONDS = 12 * 60 * 60


def _allow() -> int:
    """Allow the Stop — emit nothing, exit 0."""
    return 0


def _block(reason: str) -> int:
    print(json.dumps({"decision": "block", "reason": reason}))
    return 0


def _load_json(path: Path) -> dict | None:
    try:
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _as_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_ts(value) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return _allow()

    project_dir = Path(event.get("cwd") or os.getcwd())
    marker = project_dir / ".sellsword" / "active-goal.json"
    if not marker.is_file():
        return _allow()  # no active goal — silent no-op (the common case)

    pointer = _load_json(marker)
    run_dir_raw = pointer.get("run_dir") if pointer else None
    if not run_dir_raw:
        return _allow()  # empty / malformed marker — goal is not armed

    run_dir = Path(run_dir_raw)
    if not run_dir.is_absolute():
        run_dir = project_dir / run_dir

    state_path = run_dir / "state.json"
    state = _load_json(state_path)
    if not state or state.get("mode") != "goal":
        return _allow()

    # Only an `active` run is enforced. goal_met / capped / stuck / blocked /
    # cancelled all mean the orchestrator (or /sellsword:cancel) is done — let it stop.
    if state.get("status") != "active":
        return _allow()

    # An `active` run whose heartbeat has gone cold is a dead session, not a
    # live loop. Do not trap whatever session is now stopping. (goal.md rewrites
    # state.json every cycle, so a fresh mtime means the loop is genuinely
    # working; only a long silence trips this.)
    try:
        if time.time() - state_path.stat().st_mtime > STALE_AFTER_SECONDS:
            return _allow()
    except OSError:
        pass

    # --- safety caps: the gate stops enforcing once a cap is reached ----------
    cycle = _as_int(state.get("cycle"))
    max_cycles = _as_int(state.get("max_cycles"))
    max_seconds = _as_int(state.get("max_seconds"))

    if max_cycles > 0 and cycle >= max_cycles:
        return _allow()  # cycle cap — orchestrator debriefs as "capped"

    started = _parse_ts(state.get("started_at"))
    elapsed = None
    if started is not None:
        elapsed = (datetime.now(timezone.utc) - started).total_seconds()
        if max_seconds > 0 and elapsed >= max_seconds:
            return _allow()  # wall-clock cap — backstop against a spin loop

    # --- goal met? auditor AND fresh-eyes must BOTH be exactly `pass` ---------
    # auditor verdicts: pass | conditional-pass | fail
    # fresh-eyes verdicts: pass | partial | fail
    # Only a clean pass on both counts as met — conditional-pass / partial do not.
    auditor = str(state.get("last_auditor_verdict") or "").strip().lower()
    fresh = str(state.get("last_fresh_eyes_verdict") or "").strip().lower()
    if auditor == "pass" and fresh == "pass":
        return _allow()  # goal met — orchestrator debriefs as "goal_met"

    # --- not met, not capped, still active -> ENFORCE ------------------------
    elapsed_min = int(elapsed // 60) if elapsed is not None else "?"
    max_min = max_seconds // 60 if max_seconds > 0 else "?"
    reason = (
        "[sellsword:goal] Goal NOT met — the Sellsword goal loop is still active. "
        "Do NOT stop.\n"
        f"  Condition: {state.get('condition') or '(unspecified)'}\n"
        f"  Cycle: {cycle}/{max_cycles or '?'}    "
        f"Elapsed: {elapsed_min}m/{max_min}m\n"
        f"  Last auditor verdict: {auditor or 'none yet'}    "
        f"Last fresh-eyes verdict: {fresh or 'none yet'}\n"
        "Continue the Sellsword goal loop per commands/goal.md:\n"
        "  - If either verdict is fail / partial / conditional-pass, "
        "re-dispatch the builder with the auditor + fresh-eyes findings, then "
        "re-run dual verification.\n"
        "  - The goal is met ONLY when auditor AND fresh-eyes BOTH return "
        "'pass'.\n"
        "  - If the builder declared stuck, run multi-angle retry — do not "
        "stop.\n"
        "  - Update <run_dir>/state.json (cycle, last_auditor_verdict, "
        "last_fresh_eyes_verdict) after every cycle so this gate sees "
        "progress.\n"
        f"  - To end the run early: /sellsword:cancel {state.get('run_id') or '<run-id>'}"
    )
    return _block(reason)


if __name__ == "__main__":
    sys.exit(main())
