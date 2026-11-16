#!/usr/bin/env bash
# Ranger headless runner - one cycle per process, fresh context every time.
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
    *)
      # A glob like `.../ranger/*/scripts/ranger-run.sh "brief"` expands to
      # every installed version. The shell then runs the first and passes the
      # rest here, so the brief silently becomes "<path> <real brief>" and the
      # run starts under the wrong version. Catch it rather than obey it.
      case "$1" in
        */ranger-run.sh)
          echo "ranger: '$1' looks like another copy of this script, not a brief." >&2
          echo "        A glob matched several installed versions. Resolve one:" >&2
          echo "          RANGER=\$(ls -d ~/.claude/plugins/cache/the-tavern/ranger/*/scripts/ranger-run.sh | sort -V | tail -1)" >&2
          echo "          \"\$RANGER\" \"your brief\"" >&2
          exit 1
          ;;
      esac
      BRIEF="${BRIEF:+$BRIEF }$1"; shift ;;
  esac
done

# `.git` is a file, not a directory, in worktrees and submodules - ask git.
if ! git rev-parse --show-toplevel >/dev/null 2>&1; then
  echo "ranger: run this from inside a git repository." >&2
  exit 1
fi

if ! command -v claude >/dev/null 2>&1; then
  echo "ranger: the 'claude' CLI is not on PATH." >&2
  exit 1
fi

if [[ $RESUME -eq 1 ]]; then
  echo "ranger: re-arming the last stopped run…"
  claude -p "/ranger:resume --headless" --permission-mode bypassPermissions
else
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

# Record this runner's PID in the marker so the guard hook can tell a live run
# from an abandoned one. Without it, a run that is Ctrl-C'd or killed leaves
# status "active" on disk forever, and because headless runs deliberately skip
# session scoping, the guard goes on denying the USER's own pushes and branches
# in this repo in every later session.
python3 - "$MARKER" "$$" <<'PY' || true
import json, sys, pathlib
marker = pathlib.Path(sys.argv[1])
try:
    data = json.loads(marker.read_text() or "{}")
    if isinstance(data, dict):
        data["runner_pid"] = int(sys.argv[2])
        marker.write_text(json.dumps(data))
except (OSError, ValueError):
    pass
PY

# Disarm on the way out, however we leave. This covers Ctrl-C and the
# failure-backoff exit; it cannot cover SIGKILL, which is why the guard's own
# liveness check is the real fix and this is the cheap complement.
disarm() {
  printf '{}' > "$MARKER" 2>/dev/null || true
}
trap disarm EXIT INT TERM

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
quarantined, or to a dry cycle that rotates on). Dispatch the read-only pools —
scouts, planners, plan reviewers — as parallel batches in a single message, as
commands/run.md STEP 3 describes; build one item at a time. Update state.json
before you finish. Follow the Ranger orchestration rules in the ranger
plugin'"'"'s commands/run.md — you are the lead: you spawn agents and manage
state, you never read or edit code yourself. Do not debrief; another cycle
follows this one.'

echo "ranger: entering the loop. /ranger:stop to end it."

# A cycle that fails for a reason retrying cannot fix - expired auth, no
# network, a bad flag - would otherwise spin forever, and every spin is a fresh
# `claude -p`. Consecutive failures back off and then stop; any success resets
# the counter, so a single flaky cycle costs nothing.
MAX_CONSECUTIVE_FAILURES="${RANGER_MAX_FAILURES:-5}"
failures=0

while :; do
  status="$(run_status)"
  if [[ "$status" != "active" ]]; then
    echo "ranger: run status is '$status' — exiting."
    break
  fi

  if claude -p "$CYCLE_PROMPT" --permission-mode bypassPermissions; then
    failures=0
    sleep "$SLEEP_BETWEEN"
  else
    rc=$?
    failures=$((failures + 1))
    if (( failures >= MAX_CONSECUTIVE_FAILURES )); then
      echo "ranger: ${failures} cycles failed in a row (last exit ${rc}). Stopping" >&2
      echo "       rather than burning tokens on a fault that is not clearing." >&2
      echo "       Check your auth and network, then resume with:" >&2
      echo "         $0 --resume" >&2
      exit 1
    fi
    backoff=$(( SLEEP_BETWEEN * failures * failures ))
    echo "ranger: cycle exited ${rc} (${failures}/${MAX_CONSECUTIVE_FAILURES}); retrying in ${backoff}s." >&2
    sleep "$backoff"
  fi
done
