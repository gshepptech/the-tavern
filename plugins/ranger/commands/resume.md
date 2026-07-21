---
description: "Pick a stopped Ranger run back up where it left off — same backlog, same rotation, same flags"
argument-hint: "[run-id] [--unlimited] [--max-cycles=N] [--max-hours=N]"
allowed-tools: ["Bash(cat:*)", "Bash(ls:*)", "Bash(date:*)", "Bash(test:*)", "Bash(head:*)", "Bash(tail:*)", "Bash(echo:*)", "Bash(git:*)", "Bash(osascript:*)", "Read", "Write", "Edit", "Glob", "Grep", "Agent"]
---

# Ranger — resume

Pick up a previous run exactly where it stood down. The backlog, the domain rotation, the cycle count, and the run's flags are all on disk — resuming re-arms the hooks and continues the loop. This is what makes `/ranger:stop`'s promise ("picks up where this left off") true.

## Which run

Parse `$ARGUMENTS`: an optional `run-id`, plus the cap flags (`--unlimited`, `--max-cycles=`, `--max-hours=`), which override the resumed run's caps.

1. If `.ranger/active-run.json` is armed (non-empty, points at a run whose `state.json` is `status: active`), a run is **already going**. Say so — `/ranger:status` to see it, `/ranger:stop` to end it — and stop. Do not double-arm.
2. Else pick the run: the `run-id` if given, otherwise the most recently ended run under `.ranger/runs/*/` (highest `ended_at`) whose `status` is `stopped` or `capped`.
3. No resumable run found → tell the user to start one with `/ranger:run`, and stop.

## Preflight

Same as `/ranger:run`: confirm `~/.claude/.warden-strict-mode` reads exactly `off` (else stop and tell the user to run `/warden:strict-off`), and confirm the git tree is in a state you can commit against.

## Re-arm and continue

1. Read the chosen `<run_dir>/state.json`.
2. **Lift the cap that stopped it**, so it doesn't halt again on the first cycle:
   - If a cap flag was passed, apply it (as in `/ranger:run` — `0`/`--unlimited` means no cap).
   - Else if the run was `capped` (`cycle >= max_cycles`), set `max_cycles = cycle + 5` and set `cap_source: "resume-extended"`. Tell the user: *"Resuming — I'll ship 5 more items then stand down again. Add --unlimited to remove the cap."*
   - Else (was `stopped` by the user) keep its existing caps.
3. Update `state.json`: `status: "active"`, `phase: "survey"`, `item: null`, clear `ended_at`, set `resumed_at` and `session_id` to this session. Keep `cycle`, `backlog.json`, `domain_rotation`, and `flags` untouched.
4. Write the marker `.ranger/active-run.json` → `{ "run_id": "<run_id>", "run_dir": ".ranger/runs/<run_id>" }`. **This re-arms both hooks.**
5. Tell the user, in three lines:

```
Ranger is back on site — <run_id>.
Resuming at cycle <cycle> · <count> ready items on the backlog.
<cap line, as in /ranger:run>
```

6. Run **one cycle exactly as `commands/run.md` STEP 3** (SURVEY finds the existing backlog already populated and skips straight to SELECT), then **return normally**. Continuous operation is the driver's job, same as `/ranger:run`: tell the user to keep it going with `/loop /ranger:resume` (watched) or `scripts/ranger-run.sh --resume` (overnight). If `--headless` was passed, set `mode: "headless"` and stop after re-arming — the runner drives cycles. The `guard-git` PreToolUse hook applies unchanged; there is no Stop hook.

Every `Agent` you spawn passes `mode: "bypassPermissions"`.

Start now.
