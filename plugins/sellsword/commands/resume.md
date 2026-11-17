---
description: "Resume an interrupted Sellsword run from .sellsword/runs/<run-id>/"
argument-hint: "<run-id>"
allowed-tools: ["Bash(cat:*)", "Bash(ls:*)", "Bash(test:*)", "Bash(date:*)", "Bash(head:*)", "Bash(tail:*)", "Read", "Write", "Edit", "Glob", "Grep", "Agent", "AskUserQuestion"]
---

# Sellsword Resume

Resume an interrupted Sellsword run from where it left off.

```
RUN_ID="$ARGUMENTS"
```

If `$ARGUMENTS` is empty, list available runs from `.sellsword/runs/` (filter to ones with `state.json.status != "completed"`) and ask the user to pick one.

## Steps

1. Verify the run exists:

```bash
test -d ".sellsword/runs/$RUN_ID" || { echo "No such run: $RUN_ID"; exit 1; }
```

2. Read `.sellsword/runs/$RUN_ID/state.json`. Inspect `mode`, `status` and `phase`.

   **If `mode == "goal"`, use the goal branch in step 4b instead of 4a.** The two run kinds keep different vocabularies and only a goal run is driven by the Stop hook, so resuming one means re-arming that hook rather than just picking a phase back up.

3. Tell the user what state the run is in:

```
Run <RUN_ID>:
  status: <status>
  phase: <phase>
  intent: <intent>
  last activity: <last journal entry timestamp>
```

### 4a. `/sellsword:do` runs (no `mode` field, or `mode != "goal"`)

4. Branch on `phase`. Note: `do.md` only ever writes `phase` to `dispatcher`, `recon`, `decide_checkpoint`, `builder_execute`, or `debrief`. It does not have separate values for "plan approved, awaiting execution" or "dual verification in flight." `builder_execute` covers everything from plan-approved execution through dual verification, so for that phase you must inspect which artifacts exist to know exactly where the run stopped:

   - `dispatcher`: restart from PHASE 1 of `/sellsword:do`. Treat as new run with same intent.
   - `recon`: re-run recon (PHASE 2). Brief may exist partial; recon will overwrite or extend.
   - `decide_checkpoint`: re-render `plan.md` if it exists and re-prompt the user (PHASE 4 from `/sellsword:do`); if `plan.md` doesn't exist yet, the run stopped before the builder produced one, so re-enter PHASE 4 from the top.
   - `builder_execute`: check for `auditor-verdict.md` / `fresh-eyes-verdict.md` (dual verification already ran, so re-render or re-run PHASE 7 from `/sellsword:do`), else check for `verification.md` (builder finished its own pass but dual verification hadn't started, so go to PHASE 7), else re-spawn the builder in its last known mode with existing brief/plan/reflections/journal as inputs (PHASE 6).
   - `debrief`: read all verdicts and render debrief (PHASE 8 from `/sellsword:do`).
   - `completed`: tell user the run is already done, point them at `.sellsword/runs/<RUN_ID>/`.
   - `cancelled_at_plan`: tell user the run was cancelled, offer to restart with `/sellsword:do`.

### 4b. `/sellsword:goal` runs (`mode == "goal"`)

A goal run is not driven by the conversation. It is driven by the `Stop` hook in `scripts/goal-gate.py`, which blocks the turn from ending while `.sellsword/active-goal.json` points at a run whose `state.json` is `status: "active"`. Resuming one therefore means **re-arming that marker**, not just resuming a phase. Get the order right: fix the caps first, then re-arm, or the gate lets go again on the very first turn.

1. **Refuse to double-arm.** If `.sellsword/active-goal.json` is non-empty and points at a *different* run whose `state.json` is still `active`, stop and tell the user to cancel that one with `/sellsword:cancel` first. Two armed goal runs would have the gate enforcing against the wrong state file.

2. **Clear the terminal status that stopped it,** so the gate does not immediately allow the next Stop:
   - `capped` (`cycle >= max_cycles`, or the wall-clock cap was hit): the user set that bound deliberately, so do not silently remove it. Raise it by the same size again (`max_cycles += the original cap`, minimum `+3`; likewise `max_seconds`) and say so plainly: *"Resuming: <n> more cycles then I stand down again."*
   - `stuck`: the builder gave up. Do not simply re-arm into the same wall: read the last journal entry and `reflections.md`, tell the user what it got stuck on, and ask (via `AskUserQuestion`) whether to retry with a revised goal, retry with `--thorough`, or abandon. Re-arming a stuck run unchanged just burns cycles on the same obstacle.
   - `blocked`: same as `stuck`: surface the blocker and ask before re-arming.
   - `goal_met`: already finished. Say so and point at the debrief; offer `/sellsword:goal` with a new goal instead.
   - `cancelled`: the user ended it. Confirm they want it going again before re-arming.

3. **Reset the run to running:** set `status: "active"`, clear `ended_at`, set `resumed_at`. **Keep `cycle`, `goal`, `mode`, and the verdict fields as they are**. The cycle counter is what the caps are measured against, and resetting it would silently uncap the run.

4. **Pick the phase back up.** `goal.md` writes `phase` as `dispatcher`, `recon`, `production_gate`, or `cycle`:
   - `dispatcher` / `recon`: restart from the corresponding phase of `/sellsword:goal`.
   - `production_gate`: the run stopped at the production-safety gate; re-render it and re-ask.
   - `cycle`: mid-loop. Read `last_auditor_verdict` and `last_fresh_eyes_verdict`: if both are `pass` the goal was actually met and the run should be marked `goal_met` rather than resumed; if either is `fail`, `conditional-pass` or `partial`, re-enter the verify loop by spawning the builder for the next cycle with the existing brief, journal and verdicts as inputs.

5. **Re-arm last.** Write `.sellsword/active-goal.json` pointing at this run. **This re-arms the Stop hook.** From here the loop drives itself until the auditor and fresh-eyes both return `pass`, a cap is reached, or the run goes `stuck`.

6. Tell the user it is running again, at which cycle, and what the caps now are.

### Both kinds

5. Update `state.json` with `resumed_at: "<ISO timestamp>"` before proceeding.

6. Read the relevant phase logic from `commands/do.md` (or `commands/goal.md` for a goal run) and follow it from that phase forward. **You do not have to re-execute earlier phases**; trust the on-disk state.

## Rules

- **Don't lose work.** If existing files (`brief.md`, `plan.md`, `journal.md`) are present, treat them as authoritative. Append, don't overwrite, unless re-running the producing phase.
- **Confirm with user before re-running expensive phases.** Recon takes minutes; the builder can take much longer. If you're about to re-run something the user might prefer to skip, ask via `AskUserQuestion`.
- **State.json is the source of truth.** Trust it over your own inference.
