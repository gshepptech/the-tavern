---
description: "Explain how Ranger works and what the flags do"
hide-from-slash-command-tool: "true"
---

# Ranger Help

Explain the following to the user, in your own words and compactly.

## What Ranger is

A self-directing engineering loop. You give it one brief and walk away; it finds work, builds it one item at a time and keeps going until you stop it.

It is a **thin lead**: it spawns agents and manages state files, and it never edits code. It *will* read a file when reading settles a question faster than dispatching an agent to go and find out, but that is the exception. That thinness is what lets a run go for hours: every agent gets a fresh context, and the lead's own window stays small.

## The cycle

`survey -> triage -> plan -> claims-check -> plan-review -> select -> build -> review -> verify -> commit`

It works a **team, not a queue**. Surveying, planning, claims-checking and plan review are read-only. They cannot corrupt a working tree, so it dispatches them in parallel pools: six scouts sweeping different slices of the app at once, three planners, three checkers, three plan reviewers. Only the build touches the shared tree, so only the build is serial, one item at a time. The payoff is that by the time it needs something to build, the thinking is already done and queued.

**Not every item gets the whole team.** It triages first. A copy fix or a one-line constant is `trivial` and gets two agents, an implementer and one diff review. Concurrency, migrations, auth and shared components are `risky` and get two plan reviewers plus a mandatory fresh-eyes gate. Everything else is `standard`. Running five agents on a label reword isn't rigour, it's waste competing with the item that deserved it.

Plan review comes before implementation on purpose: a rejected plan costs one agent, a bad implementation costs five. And a **claims check** comes before *that*: a cheap pass that opens every source the plan cites and reports which claims actually held, because most revision rounds in a mature run are citation defects rather than design defects, and catching those with an `opus` reviewer is the expensive way to do it.

Verification is fresh-eyes. The assessor never sees the plan, only the acceptance criteria and the code. UI items get driven through a real browser as a user would. For pure logic already pinned by a test it has watched fail against the pre-change code, that test *is* the evidence and the assessor is skipped.

One item, one local commit. So any single change is one `git revert` away.

## Why it never runs out of work

A *thinning* backlog is the survey trigger, not an empty one. It refills while the current item is still being built, so it never stalls waiting for work to be found.

The first survey maps the app's real domains: **every tier that runs code**, not just the one with a UI. After that it crosses those domains with nine lenses (correctness, UI/UX, visual polish, real-user flows, performance, accessibility, security, DX, feature gaps) and hands one domain×lens **pair** to each scout. A persistent map of swept pairs means no ground is covered twice, and a yield count means pairs that come back clean twice go cold and stop getting swept.

It will not invent churn to look busy. A scout that finds nothing worth doing reports its pair **clean**, which is a real answer; the lead responds by dispatching more pairs, never by pressing a scout to come back with something. Keeping the backlog full is the lead's job, not theirs. That split is exactly what stops an idle loop from refactoring healthy code.

## …and how it gets pickier instead of stopping

**It never stands down on its own.** `/ranger:stop`, Esc, or a cap you set. That's the whole list. On a maturing codebase, though, "never runs out of work" turns into a treadmill: the real defects clear and the loop grinds ever more marginal items at full cost. So instead of stopping, it raises its standards:

- **The floor rises.** It starts at 6, climbs every 10 lean cycles, never falls. A run at cycle 100 refuses work a run at cycle 5 would take.
- **The backlog is capped** at 40. At the cap, filing an item means dropping one, and there's a prune pass where killing items *is* the work.
- **Lean runs get reported.** Five consecutive cycles of nothing above the floor and it says so in one line, then carries on sweeping. Whether that's worth continuing is yours to decide.

The survey is the uncapped part of a cycle on purpose: a scout team that comes back empty is answered with another team, and another, until it finds work above the floor or has swept every remaining pair.

Review findings never become backlog items. That would be a loop generating its own demand, and it's how a backlog reaches 120 items with nothing important in it.

## `.ranger/FACTS.md`

One short file every agent reads before it reasons: the north star, the settled constraints, how the repo is *really* tested, the conventions agents trip on, what's out of bounds. The recon scout seeds it, the lead corrects it, **you can edit it by hand.** It stops agents re-deriving settled facts every cycle and occasionally getting them wrong.

If `cleric`, `seer` or `scout` are installed, the scout uses them for their specialisms instead of duplicating them.

## Commands

- `/ranger:run <brief> --dry-run`: **preview.** See the ranked backlog and the top item's plan without changing anything. The recommended first contact.
- `/ranger:run <brief> [flags]`: run **one** cycle and return. Keep it going with `/loop /ranger:run <brief>` (watched, Esc to stop) or `ranger-run.sh` (overnight).
- `/ranger:run <brief> --preset ui`: run a curated checklist (`ui` / `ux` / `a11y` / `harden` / `perf`), skipping anything the app doesn't have.
- `/ranger:run <brief> --sweep`: **the sprawl.** One survey-only pass over every domain under the shakeout lenses (correctness, UX, visual polish, flows, a11y). Scouts read and drivers run the real app. The pass ends with a full ranked board and no build. `--sweep=all` covers all nine lenses. Then work the board down with `/loop` or overnight.
- `/ranger:stop`: down tools. The clean exit.
- `/ranger:resume [run-id]`: pick a stopped run back up: same backlog, rotation, and flags.
- `/ranger:status`: what it is on right now. Read-only, safe mid-run.
- `/ranger:help`: this.

## Flags (all default OFF)

| flag | default | with the flag |
|---|---|---|
| *(none)* | commits locally to the **current branch** | n/a |
| `--preset <name>` | full domain rotation | focus a curated checklist: `ui`, `ux`, `a11y`, `harden`, `perf` (skips items the app lacks) |
| `--sweep[=all]` | rotation advances a few pairs per cycle | one survey-only pass over the whole grid now, with no build and the board stocked at the end (`=all` for all nine lenses) |
| `--dry-run` | executes | previews only: one scout + top plan, no writes, no commit |
| `--scouts=N` | 6 sweep in parallel | resize the survey team (1–8) |
| `--planners=N` | 3 plan in parallel | resize the plan pool (1–4) |
| `--new` | continues a parked run | forces a fresh run |
| `--branch` | one branch for everything | a local branch per item |
| `--merge-dev` | leaves integration to you | merges verified items into `dev` |
| `--ask` | **never asks you anything** | may ask when genuinely blocked |
| `--max-cycles=N` | **unlimited** | stands down after N shipped items (`0` = unlimited) |
| `--max-hours=N` | **unlimited** | stands down after N hours (`0` = unlimited) |
| `--unlimited` | n/a | no-op, kept so older invocations don't break |

**Runs are uncapped by default.** That is the whole design, but it means nothing ends a run except `/ranger:stop`, Esc, or killing the runner. Caps are checked between items, so bounding a run never leaves a half-finished change behind.

`--max-cycles` counts **shipped items**, not attempts: a cycle that reverts, quarantines, or finds nothing above the quality floor spends tokens without advancing the count. So `--max-cycles` bounds output and **`--max-hours` bounds spend**. The hours cap is the one to reach for overnight.

**`git push` is blocked for the entire run and no flag enables it.** A `PreToolUse` hook denies pushes, remote mutation, `git send-email`, `gh api` writes and PR creation. It is enforced outside the model, so it holds even under bypassed permissions, and it resolves quoting and looks inside `sh -c` / `eval` wrappers. It is a guardrail against an agent publishing by accident, not a sandbox. The real containment for an unattended run is running it somewhere disposable.

## Keeping it running

Each `/ranger:run` does **one cycle and returns**. There is no Stop hook trapping the turn, so no transcript spam and no fighting other plugins' hooks. Two drivers keep it continuous:

- **Watched:** `/loop /ranger:run <brief>`. The native loop re-invokes each tick; **Esc** to stop.
- **Overnight:** `ranger-run.sh "<brief>"`. A fresh `claude -p` process per cycle, so context never accumulates.

`/ranger:stop` ends a run; `/ranger:resume` continues one.

**Run unattended mode in a sandbox.** With no human to answer permission prompts, Ranger runs with permissions bypassed: the runner and every agent execute tools without asking. `git push`, remote mutation and PR creation are hard-blocked even in that mode, but **only git is guarded. Everything else (file writes, shell, network) runs unprompted.** That is the cost of an unattended loop, not a defect. Run overnight/headless mode in a container, VM, or throwaway clone, never on a machine you care about while you walk away.

## Guardrails

- **Blast radius.** An item touching more than ~12 files or ~600 lines unplanned is stashed and split, not merged.
- **Stalls.** Three cycles with no commit and the item is quarantined; it moves to different work rather than grinding.
- **Revert, don't pile on.** A rejected change is reverted, never patched over.
- **Conflicts are never resolved unattended.** A conflicting merge is aborted and left on its branch.

## Honest caveats

An unbounded run consumes tokens for as long as it runs, and **unbounded is the default**. Nothing stops a run but you. Watch the first few cycles before trusting it overnight; that attended-to-unattended transition is the whole game. `--max-hours=N` is the only cap that ends a run on its own, and it is off unless you pass it. Use it the first night.

Unattended mode runs with permissions bypassed. Only `git push` is genuinely blocked; everything else runs without asking. Run it in a sandbox, not on a machine you care about.
