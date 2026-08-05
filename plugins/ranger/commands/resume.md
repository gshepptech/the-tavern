---
description: "Pick a stopped Ranger run back up where it left off — same backlog, same rotation, same flags"
argument-hint: "[run-id] [--unlimited] [--max-cycles=N] [--max-hours=N]"
allowed-tools: ["Bash(cat:*)", "Bash(ls:*)", "Bash(date:*)", "Bash(test:*)", "Bash(head:*)", "Bash(tail:*)", "Bash(echo:*)", "Bash(git:*)", "Bash(osascript:*)", "Read", "Write", "Edit", "Glob", "Grep", "Agent"]
---

# Ranger — resume

Pick up a previous run exactly where it stood down. The backlog, the domain rotation, the cycle count, and the run's flags are all on disk — resuming re-arms the guard hook and continues from the recorded phase. This is what makes `/ranger:stop`'s promise ("picks up where this left off") true.

## Which run

Parse `$ARGUMENTS`: an optional `run-id`, plus the cap flags (`--unlimited`, `--max-cycles=`, `--max-hours=`), which override the resumed run's caps.

1. If `.ranger/active-run.json` is armed (non-empty, points at a run whose `state.json` is `status: active`):
   - If its `session_id` is set and is **not** this session -> a run is active elsewhere. Say so (`/ranger:status`, `/ranger:stop`) and stop. Do not double-arm.
   - Otherwise this is a **continuation** tick (you are being driven by `/loop /ranger:resume`). Skip re-arming entirely and go straight to "Run one cycle" below.
2. Else pick the run: the `run-id` if given, otherwise the most recently ended run under `.ranger/runs/*/` (highest `ended_at`) whose `status` is `stopped` or `capped`.
3. No resumable run found -> tell the user to start one with `/ranger:run`, and stop.

## Preflight

Same as `/ranger:run` STEP 2a: check the methodical-mode strict gates and confirm the git tree is in a state you can commit against. **Run the exact check from STEP 2a** — a missing marker means strict is ON, not off, because all three plugins read an absent marker as `default` and `default` enforces.

```bash
python3 - <<'PY'
import json, pathlib
home = pathlib.Path.home()
try:
    enabled = json.loads((home / ".claude" / "settings.json").read_text()).get("enabledPlugins", {})
except Exception:
    enabled = {}
blocking = []
for p in ("warden", "adhoc", "plumb"):
    if not any(k.split("@")[0] == p and v for k, v in enabled.items()):
        continue
    marker = home / ".claude" / f".{p}-strict-mode"
    mode = marker.read_text().strip().lower() if marker.is_file() else "default"
    if mode != "off":
        blocking.append(f"{p} (strict={mode})")
print("BLOCKING: " + ", ".join(blocking) if blocking else "CLEAR")
PY
```

Anything other than `CLEAR` — name which and stop. The user clears it with `/warden:strict-off`, `/adhoc:strict-off`, or `/plumb:strict-off`.

## Re-arm and continue

1. Read the chosen `<run_dir>/state.json`.
2. **Lift the cap that stopped it**, so it doesn't halt again on the first cycle:
   - If a cap flag was passed, apply it (as in `/ranger:run` — `0`/`--unlimited` means no cap).
   - Else if the run was `capped` (`cycle >= max_cycles`), the user set that cap deliberately, so do not silently remove it — extend it by the same size again (`max_cycles += the original cap`, minimum `+5`) and set `cap_source: "resume-extended"`. Tell the user: *"Resuming — I'll ship <n> more items then stand down again. Add --max-cycles=0 to remove the cap."*
   - Else (was `stopped` by the user) keep its existing caps.
3. Update `state.json`: `status: "active"`, `phase: "survey"`, `item: null`, clear `ended_at`, set `resumed_at` and `session_id` to this session. Keep `cycle`, `backlog.json`, `domain_rotation`, and `flags` untouched. If the run predates crew sizing and has no `scouts` / `planners` / `backlog_watermark`, fill in the defaults (`6`, `3`, `scouts + 2`). If it predates the backlog economics and has no `backlog_cap` / `floor` / `lean_cycles` / `domain_rotation.yield`, fill in `40` / `6` / `0` / `{}` — **do not** try to reconstruct a risen floor from the journal; starting a resumed run back at the base floor is the safe direction, and it will rise again on its own. Any item left mid-flight from the old serial cycle is still valid — reset a stranded `planning` or `in_flight` item to `ready`.

   Ensure `.ranger/FACTS.md` exists (skeleton in `commands/run.md` STEP 2e). A run that predates it has none; create it empty and let the next recon or your own corrections fill it.

   Keep `lean_cycles` as it stands — it is a gauge of how the run was going, and it never ended anything. If it is `>= 5`, say so in the resume line along with the floor, so the user knows they are picking up a run that was finding thin work.
4. Write the marker `.ranger/active-run.json` -> `{ "run_id": "<run_id>", "run_dir": ".ranger/runs/<run_id>" }`. **This re-arms the guard hook.**
5. Tell the user, in three lines:

```
Ranger is back on site — <run_id>.
Resuming at cycle <cycle> · <count> ready items on the backlog.
<cap line, as in /ranger:run>
```

6. Run **one cycle exactly as `commands/run.md` STEP 3**. A resumed run usually still has a stocked backlog, so SURVEY sees the pipeline above its watermark and skips straight past it — and if the run stood down with approved plans already queued, the first cycle back goes almost directly to BUILD. Then **return normally**. Continuous operation is the driver's job, same as `/ranger:run`: tell the user to keep it going with `/loop /ranger:resume` (watched) or `scripts/ranger-run.sh --resume` (overnight). If `--headless` was passed, set `mode: "headless"` and stop after re-arming — the runner drives cycles. The `guard-git` PreToolUse hook applies unchanged; there is no Stop hook.

Every `Agent` you spawn passes `mode: "bypassPermissions"`.

Start now.
