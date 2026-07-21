#!/usr/bin/env bash
# Ranger headless runner — one cycle per process, fresh context every time.
#
# The in-session loop (/ranger:run) keeps its lead thin so context grows slowly,
# but it still grows. This runner is the unbounded variant: each iteration is a
# brand-new `claude -p` process that reads the same .ranger/ state from disk,
# executes exactly one cycle, and exits. Nothing accumulates.
#
#   ./ranger-run.sh "make the dashboard genuinely good"
#   ./ranger-run.sh --resume            # continue the existing run
#
# Stop it with `/ranger:stop` from any session, by writing status != active into
# the run's state.json, or with Ctrl-C.

set -euo pipefail

MARKER=".ranger/active-run.json"
SLEEP_BETWEEN="${RANGER_SLEEP:-5}"
RESUME=0
BRIEF=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --resume) RESUME=1; shift ;;
    -h|--help)
      sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) BRIEF="${BRIEF:+$BRIEF }$1"; shift ;;
  esac
done

if [[ ! -d .git ]]; then
  echo "ranger: run this from the root of a git repository." >&2
  exit 1
fi

if ! command -v claude >/dev/null 2>&1; then
  echo "ranger: the 'claude' CLI is not on PATH." >&2
  exit 1
fi

if [[ $RESUME -eq 0 ]]; then
  if [[ -z "$BRIEF" ]]; then
    echo "ranger: give me a brief, or pass --resume to continue an existing run." >&2
    exit 1
  fi
  echo "ranger: starting a headless run…"
  claude -p "/ranger:run $BRIEF --headless" --permission-mode bypassPermissions
fi

if [[ ! -s "$MARKER" ]]; then
  echo "ranger: no active run found at $MARKER." >&2
  exit 1
fi

# The status lives in the run's state.json, which the marker points at. Read it
# with python3 rather than jq so the runner has no extra dependency.
run_status() {
  python3 - <<'PY' 2>/dev/null || echo "unknown"
import json, pathlib
marker = json.loads(pathlib.Path(".ranger/active-run.json").read_text() or "{}")
run_dir = marker.get("run_dir")
if not run_dir:
    print("stopped")
else:
    state = json.loads((pathlib.Path(run_dir) / "state.json").read_text())
    print(state.get("status", "unknown"))
PY
}

CYCLE_PROMPT='Run exactly ONE cycle of the active Ranger loop, then stop.
Read .ranger/active-run.json for the run directory, then that run directory'"'"'s
state.json, backlog.json and the tail of journal.md. Resume at the recorded
phase and carry the loop through to the next local commit (or to the item being
quarantined). Update state.json before you finish. Follow the Ranger
orchestration rules in the ranger plugin'"'"'s commands/run.md — you are the lead:
you spawn agents and manage state, you never read or edit code yourself. Do not
debrief; another cycle follows this one.'

echo "ranger: entering the loop. /ranger:stop to end it."
while :; do
  status="$(run_status)"
  if [[ "$status" != "active" ]]; then
    echo "ranger: run status is '$status' — exiting."
    break
  fi
  claude -p "$CYCLE_PROMPT" --permission-mode bypassPermissions || {
    echo "ranger: cycle exited non-zero; retrying after ${SLEEP_BETWEEN}s." >&2
  }
  sleep "$SLEEP_BETWEEN"
done
