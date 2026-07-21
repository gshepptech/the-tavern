#!/usr/bin/env python3
"""Ranger foreman-gate — Stop-hook enforcement for /ranger:run (Ranger v0.1.0).

While a Ranger run is active this Stop hook refuses to let the turn end. Unlike
`sellsword:goal`, which stops when its goal is met, Ranger has **no goal** — the loop
is the product. There is always another item, and when the backlog empties the
scout generates more. The only clean exits are `/ranger:stop` and an explicit
opt-in cap.

This is the ENFORCEMENT layer. commands/run.md drives the cooperative loop; this
hook is the backstop that catches drift — a premature debrief, a mishandled
agent return, a "there's nothing left to do."

Contract — written by commands/run.md, read here:
  <project>/.ranger/active-run.json
      {"run_id": "...", "run_dir": ".ranger/runs/<run_id>"}
      An empty object {} means "no active run" (run.md empties it on exit).
  <run_dir>/state.json
      status        active | stopped | capped | halted
      phase         survey | select | plan | plan_review | build | review |
                    verify | commit
      cycle         int  — completed items
      item          str  — the item currently in flight, or null
      max_cycles    int  — 0 means unlimited (the default)
      max_seconds   int  — 0 means unlimited (the default)
      started_at    ISO-8601 UTC
      stall_count   int  — consecutive cycles that produced no commit
      session_id    str  — the session that armed the run

Fast path: no (or empty) .ranger/active-run.json -> exit 0. This hook fires on
EVERY Stop in EVERY session, so it must be a silent no-op unless a Ranger run is
genuinely in progress.

Fail-open: any malformed/missing input -> exit 0 (allow stop). A Stop hook must
never trap the user because of its own bug. The one thing worse than a loop that
stops early is a loop the user cannot escape.

Stop protocol: print {"decision":"block","reason":...} to block; exit 0 with no
output to allow.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# What the lead should do next, keyed by the phase recorded in state.json. The
# gate fires precisely when the lead tried to stop, so each directive names the
# resume point rather than restating the whole loop.
PHASE_DIRECTIVE = {
    "survey": (
        "You are mid-SURVEY. Spawn `ranger:scout` and write its ranked items "
        "into backlog.json. The scout does not return 'nothing to do' — if the "
        "maintenance dimensions are clean it advances the domain rotation "
        "pointer and sweeps the next domain (UI/UX, real-user flows, "
        "performance, a11y, security, feature gaps)."
    ),
    "select": (
        "You are mid-SELECT. Read backlog.json, take the highest-ranked "
        "`ready` item, mark it `in_flight`, and move to PLAN."
    ),
    "plan": (
        "You are mid-PLAN. Spawn `ranger:planner` for the in-flight item and "
        "write its plan to the item directory."
    ),
    "plan_review": (
        "You are mid-PLAN-REVIEW. Spawn `ranger:reviewer` in `plan` mode. A "
        "`revise` verdict returns to PLAN (max 2 revisions, then the item is "
        "split or quarantined). Do NOT implement an unapproved plan."
    ),
    "build": (
        "You are mid-BUILD. Spawn `ranger:implementer` with the approved plan."
    ),
    "review": (
        "You are mid-REVIEW. Spawn `ranger:reviewer` in `diff` mode against the "
        "working tree."
    ),
    "verify": (
        "You are mid-VERIFY. Spawn `ranger:assessor` — fresh eyes, no plan, no "
        "journal. For a UI item it must drive the running app in a browser as a "
        "real user before it may return `pass`."
    ),
    "commit": (
        "You are mid-COMMIT. Both reviewer and assessor passed: stage and "
        "commit LOCALLY, append to journal.md, mark the item `done`, increment "
        "`cycle`, reset `stall_count`, then start the next cycle at SURVEY."
    ),
}

DEFAULT_DIRECTIVE = (
    "Resume the loop at SURVEY: refill the backlog if it has no `ready` items, "
    "then select the top item."
)


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
    marker = project_dir / ".ranger" / "active-run.json"
    if not marker.is_file():
        return _allow()  # no active run — silent no-op (the common case)

    pointer = _load_json(marker)
    run_dir_raw = pointer.get("run_dir") if pointer else None
    if not run_dir_raw:
        return _allow()  # empty / malformed marker — the run is not armed

    run_dir = Path(run_dir_raw)
    if not run_dir.is_absolute():
        run_dir = project_dir / run_dir

    state = _load_json(run_dir / "state.json")
    if not state:
        return _allow()

    # Only an `active` run is enforced. stopped / capped / halted all mean the
    # lead (or /ranger:stop) is finished — let it go.
    if state.get("status") != "active":
        return _allow()

    # In headless mode the external `while` loop in scripts/ranger-run.sh is the
    # enforcement, and each `claude -p` process is one cycle. Blocking here would
    # stop that process from ever exiting and defeat the fresh-context design.
    if state.get("mode") == "headless":
        return _allow()

    # The marker is project-scoped but this hook fires in every session in the
    # project. A run belongs to the session that armed it; other sessions must
    # not be trapped by it.
    state_session = state.get("session_id")
    hook_session = event.get("session_id")
    if state_session and hook_session and state_session != hook_session:
        return _allow()

    # --- opt-in safety caps ------------------------------------------------
    # Both default to 0 (unlimited) because "never stops" is the point. When a
    # user does set one, reaching it releases the gate and the lead debriefs.
    cycle = _as_int(state.get("cycle"))
    max_cycles = _as_int(state.get("max_cycles"))
    max_seconds = _as_int(state.get("max_seconds"))

    if max_cycles > 0 and cycle >= max_cycles:
        return _allow()

    started = _parse_ts(state.get("started_at"))
    elapsed = None
    if started is not None:
        elapsed = (datetime.now(timezone.utc) - started).total_seconds()
        if max_seconds > 0 and elapsed >= max_seconds:
            return _allow()

    # --- still active, no cap hit -> ENFORCE --------------------------------
    phase = str(state.get("phase") or "").strip().lower()
    directive = PHASE_DIRECTIVE.get(phase, DEFAULT_DIRECTIVE)

    elapsed_min = int(elapsed // 60) if elapsed is not None else "?"
    cap_note = (
        f"{max_cycles}" if max_cycles > 0 else "unlimited"
    )
    item = state.get("item") or "(none selected)"
    stalls = _as_int(state.get("stall_count"))

    lines = [
        "[ranger:run] The run is still active. Do NOT stop.",
        f"  Cycle: {cycle}/{cap_note}    Elapsed: {elapsed_min}m    "
        f"Phase: {phase or 'unknown'}",
        f"  In flight: {item}",
        "",
        directive,
        "",
        "Standing rules:",
        "  - There is no 'nothing left to do'. An empty backlog is a SURVEY "
        "trigger, not an exit condition.",
        "  - Never summarise the run and hand back. The only exits are "
        "/ranger:stop and an explicit cap.",
        "  - Update state.json (phase, cycle, item, stall_count) as you go so "
        "this gate can see progress.",
    ]

    if stalls >= 3:
        lines += [
            "",
            f"  ⚠ stall_count={stalls} — three or more cycles with no commit. "
            "Stop retrying this item: quarantine it to the bottom of "
            "backlog.json with a blocker note, advance the domain rotation "
            "pointer, and pick different work. Do not keep grinding.",
        ]

    lines += ["", "  To end the run: /ranger:stop"]

    return _block("\n".join(lines))


if __name__ == "__main__":
    sys.exit(main())
