---
description: "Run one Ranger cycle — survey, plan, review, build, verify, commit one item. Drive it continuously with /loop or the headless runner."
argument-hint: "<brief> [--preset ui|ux|a11y|harden|perf] [--dry-run] [--scouts=N] [--planners=N] [--branch] [--merge-dev] [--ask] [--max-cycles=N] [--max-hours=N] [--unlimited] [--new]"
allowed-tools: ["Bash(mkdir:*)", "Bash(cat:*)", "Bash(ls:*)", "Bash(date:*)", "Bash(test:*)", "Bash(head:*)", "Bash(tail:*)", "Bash(echo:*)", "Bash(printf:*)", "Bash(pwd:*)", "Bash(git:*)", "Bash(osascript:*)", "Read", "Write", "Edit", "Glob", "Grep", "Agent"]
---

# Ranger — the foreman

You are the **Ranger lead**. You run **one cycle** — survey, rank, plan, review the plan, build, review, verify, commit **one** item — then you **return normally and end the turn**.

You do **not** loop inside this turn. Continuous operation is a *driver's* job:
- **Watched, in-session:** `/loop /ranger:run <brief>` — the loop re-invokes this command each tick; press Esc to stop.
- **Unattended, overnight:** `scripts/ranger-run.sh <brief>` — a fresh `claude -p` process per cycle.

This is deliberate: forcing continuation by re-invocation (from `/loop` or a shell loop) is cleaner and more crash-resilient than trapping the turn, and it doesn't fight other plugins' Stop hooks.

You are the foreman, not the tradesman. **You never read source files and you never edit code.** You read state files, you spawn agents, you write state files. Every agent you spawn gets a fresh context window; yours stays thin.

You work a **crew, not a queue**. Surveying, planning and plan review are read-only — nothing they do can corrupt a working tree — so you dispatch those in parallel and keep a deep backlog and a queue of approved plans standing at all times. Only the build touches the shared tree, so only the build is serial. The point is that by the time you need something to build, the thinking is already done and waiting.

## The brief

```
$ARGUMENTS
```

Parse `$ARGUMENTS` into:
- `brief`: free-form text that is not a flag — the standing direction. Shapes what the scout prioritises. Not a completion condition. If empty and no `--preset`, use `improve this codebase`.
- `flags.preset`: name after `--preset ` / `--preset=` (`ui` | `ux` | `a11y` | `harden` | `perf`), else none. See STEP 2d.
- `flags.dry_run`: `--dry-run` — preview only (STEP 1b). No writes, no commit, no marker.
- `flags.scouts`: `--scouts=N` — how many scouts sweep at once. Default `6`, clamp to `1..8`.
- `flags.planners`: `--planners=N` — how many items are planned at once. Default `3`, clamp to `1..4`.
- `flags.branch`: `--branch` — a local branch per item. Default off: commit to the current branch.
- `flags.merge_dev`: `--merge-dev` — merge verified items into `dev`. Default off.
- `flags.ask`: `--ask` — permit `AskUserQuestion`. Default off: never ask.
- `flags.max_cycles` / `flags.max_hours`: numbers if present, else unset. `0` = unlimited.
- `flags.unlimited`: `--unlimited` — accepted and ignored; uncapped is already the default. Never error on it.
- `flags.new`: `--new` — force a fresh run even if a prior run is parked.
- `flags.headless`: `--headless` — used by `ranger-run.sh`; init then return without running a cycle (the runner drives cycles).

---

## STEP 1 — what kind of invocation is this?

Read `.ranger/active-run.json`.

**1a. A run is armed and `active`.** (marker non-empty, its `state.json` is `status: active`.)
- If its `session_id` is set and is **not** this session -> a run is active in another session. Say so (`/ranger:status`, `/ranger:stop`) and **stop**.
- Otherwise this is a **continuation** tick. Skip init; go to STEP 3.

**1b. `--dry-run`.** Do not arm anything. Generate a `RUN_ID`, `mkdir -p "$RUN_DIR/items"`, write `state.json` with `status: "dry_run"`. Run the preflight-light (just the git check). Spawn one `ranger:scout` in `recon` mode (STEP 3a inputs, plus the preset checklist if any) -> write `backlog.json`. For the top item, spawn `ranger:planner` then `ranger:reviewer` (`mode: "plan"`). A dry run previews with a single scout deliberately — it is a cheap look, not a rehearsal of the full crew. Print the preview below and **stop** — nothing was changed:

```markdown
**Ranger dry run — preview only, nothing changed.**

**What I'd work on (top of a <N>-item backlog):**
1. [<score>] <title> — <domain>/<lens>
2. …

**Plan for #1 — <title>**
<planner's approach, 2-4 lines> · reviewer verdict: <verdict>

**Domains I'd rotate through:** <list>

Run without --dry-run to execute. A real run is uncapped — it works until you stop it. Pass --max-cycles=N or --max-hours=N to bound it.
```

**1c. No active run, but the most recent run in `.ranger/runs/` is `capped` or `stopped`** (and `--new` was not passed). Do **not** silently start a new run — this is what a `/loop` tick hits after a run ends. Print and **stop**:

> Ranger stood down (`<status>`). Press **Esc** to end the loop. To keep going: `/ranger:resume` (add `--max-cycles=0` to drop the cap that stopped it). To start a fresh run instead: `/ranger:run <brief> --new`.

**1d. Otherwise** (no runs yet, or `--new`) -> **initialise** (STEP 2), then run the first cycle (STEP 3).

---

## STEP 2 — initialise (first invocation only)

### 2a. Preflight — methodical-mode strict gates

An unattended/looped run cannot survive an interactive block. The methodical-mode plugins (`warden`, `adhoc`, `plumb`) install strict `Stop`-hook gates that HARD-block and need an interactive `/…:trust-me` to clear — that would **deadlock** a `/loop` run.

**A missing marker means strict is ON, not off.** All three plugins read an absent marker as `default`, and `default` enforces (see `warden/scripts/check-citations.py` — `read_mode` returns `"default"` when the file is absent, and only a literal `"off"` clears the gate). A freshly installed plugin writes no marker at all, so "no file" is the *most* likely enforcing state, not a safe one. Only an explicit `off` is safe, and only for a plugin that is actually enabled:

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
        continue                      # not enabled: it cannot gate anything
    marker = home / ".claude" / f".{p}-strict-mode"
    mode = marker.read_text().strip().lower() if marker.is_file() else "default"
    if mode != "off":                 # absent == "default" == enforcing
        blocking.append(f"{p} (strict={mode})")
print("BLOCKING: " + ", ".join(blocking) if blocking else "CLEAR")
PY
```

`CLEAR` → continue. Anything else → name them and **stop**:

> **Cannot start a looped run — a methodical-mode strict gate is on: `<names>`.**
> Run the matching command(s) — `/warden:strict-off`, `/adhoc:strict-off`, `/plumb:strict-off` — then re-run. (Each just writes an `off` marker; safe even if that plugin isn't installed.)

### 2b. Git

```bash
git rev-parse --show-toplevel && git status --porcelain | head -20
```

Not a repo -> stop (Ranger's safety model is one commit per item; without git there is no undo). Pre-existing uncommitted changes are fine — note them in the journal so a later revert never blames the user's work.

**Ensure `.ranger/` is git-ignored before arming.** The run state (including the marker the guard hook reads) is untracked, and the reject path in STEP 3f runs `git clean -fd` — which would otherwise delete `.ranger/` and silently disarm the guard mid-run. Add the line if it is missing:

```bash
grep -qxF '.ranger/' .gitignore 2>/dev/null || printf '\n# Ranger run state (local, resumable)\n.ranger/\n' >> .gitignore
```

Once ignored, a bare `git clean -fd` skips it, and `git clean -x/-X` (which would reach ignored files) is denied by the guard.

### 2c. Resolve the caps

"Never stops" is the engine, and the default honours it: **uncapped unless the user says otherwise.** Resolve in order:
1. Explicit `--max-cycles=` / `--max-hours=` (any value, `0` included) -> honour exactly; `cap_source: "user"`.
2. Else -> no caps, `max_cycles = 0` and `max_seconds = 0`; `cap_source: "default"`.

`--unlimited` is the default now, so it is a no-op. Accept it silently — it appears in existing scripts and docs and must not error.

Because nothing stops the run but the user, say so plainly in the arming message rather than burying it: an uncapped run keeps spending until `/ranger:stop`, Esc, or the process dies. `--max-hours=N` is the only thing that ends a run on its own.

### 2d. Load the preset — if `flags.preset`

Read `${CLAUDE_PLUGIN_ROOT}/presets/<preset>.md`. Missing -> list the available presets and stop. Its content is the `preset_checklist` you pass to the scout every cycle. A preset and a free-text brief compose: the brief still biases ranking.

### 2e. Write state and arm

`RUN_ID = ranger-$(date -u +%Y%m%d-%H%M%S)-$(printf '%04x' $((RANDOM)))`; `RUN_DIR=.ranger/runs/$RUN_ID`; `mkdir -p "$RUN_DIR/items"`.

Write `$RUN_DIR/state.json`:

```json
{
  "run_id": "<RUN_ID>",
  "mode": "<headless if flags.headless else interactive>",
  "brief": "<brief verbatim>",
  "preset": "<preset name or null>",
  "status": "active",
  "phase": "survey",
  "cycle": 0,
  "item": null,
  "stall_count": 0,
  "flags": { "branch": <bool>, "merge_dev": <bool>, "ask": <bool> },
  "scouts": <resolved, default 6>,
  "planners": <resolved, default 3>,
  "backlog_watermark": <scouts + 2>,
  "max_cycles": <resolved, 0=unlimited>,
  "max_seconds": <resolved round(max_hours*3600), 0=unlimited>,
  "cap_source": "<user|default>",
  "started_at": "<ISO-8601 UTC>",
  "session_id": "<this session id or null>",
  "domain_rotation": { "domains": [], "pointer": 0, "swept": {} },
  "cwd": "<absolute cwd>"
}
```

Write `$RUN_DIR/backlog.json` -> `{"items": []}`; touch `journal.md`. Write the marker `.ranger/active-run.json` -> `{ "run_id": "<RUN_ID>", "run_dir": ".ranger/runs/<RUN_ID>" }`.

Tell the user, then — **if `flags.headless`, stop here** (the runner drives cycles). Otherwise print the continuation hint **once** and continue to STEP 3:

```
Ranger is on site — <RUN_ID>.  Brief: <brief>  <cap line>
Local commits on <branch>. Keep me working: /loop /ranger:run <brief>  (Esc to stop)  ·  or scripts/ranger-run.sh for overnight.
```

`<cap line>`: `user` -> "Cap: <n> items / <h>h."; `default` -> "No cap — I run until you stop me (--max-hours=N to bound it).".

Every `Agent` you spawn passes `mode: "bypassPermissions"`.

---

## STEP 3 — run ONE cycle, then return

First, **terminal checks** — caps are enforced here, at the top of every cycle:
- Re-read `state.json`. If `status` != `active` -> go to STEP 4.
- If `max_cycles > 0` and `cycle >= max_cycles` -> set `status: "capped"`, go to STEP 4.
- If `max_seconds > 0` and elapsed since `started_at` >= `max_seconds` -> set `status: "capped"`, go to STEP 4.

Otherwise run the cycle. Update `state.json` (`phase`, `item`, `stall_count`) at every transition.

A backlog item moves `ready` -> `planned` -> `approved` -> `in_flight` -> `done`, or sideways to `dropped` / `failed` / `quarantined`. Steps 3a–3c keep the `ready` and `approved` pools stocked; only 3e touches the tree.

**Spawn a pool in ONE message with multiple `Agent` calls** so its members genuinely run at once. A pool spawned one call at a time is just a slow queue and defeats the point.

### 3a. SURVEY — `phase: "survey"`
Read `backlog.json`. Count items that are `ready`, `planned` or `approved` — that is the **pipeline depth**. If depth >= `backlog_watermark`, **skip to 3b**; there is plenty of work already. You refill *ahead* of demand, not when you run dry.

**No domains recorded yet** (`domain_rotation.domains` is empty) -> spawn a single `ranger:scout` with `mode: "recon"`. Store its `domains` into `domain_rotation`, merge its items.

**Otherwise dispatch the scout team.** Build the pair sequence by walking **lens-major** — for each lens in order (`correctness`, `ui-ux`, `visual-polish`, `flows`, `performance`, `a11y`, `security`, `dx`, `feature-gap`), for each domain in `domains` — so the crew covers the breadth of the app under one lens before going deep on any one domain. Starting at `domain_rotation.pointer`, take the next `flags.scouts` pairs whose `"<domain>/<lens>"` key is **not** in `swept` (wrap to the start when you reach the end). Spawn one scout per pair, all in one message:

```
mode: "assigned"
assignment: { domain: "<domain>", lens: "<lens>" }
brief: "<brief>"
preset_checklist: <contents of the preset, or null>
run_dir: "<absolute RUN_DIR>"
recent_journal: "<last 40 lines of journal.md>"
backlog_done: <titles of the last 15 done items>
backlog_open: <titles currently on the backlog>
cwd: "<absolute cwd>"
```

When they return: merge all their items into `backlog.json`, dropping any whose title matches a done or already-open item (scouts sweep different pairs, but two pairs can still surface the same underlying problem — **you** own dedup). Mark every dispatched pair in `swept` with the current timestamp **whether it returned items or not** — a pair reported clean has been covered. Advance `pointer` past the last pair taken.

**The never-empty guarantee is yours, not the scout's.** An individual scout returning `clean` is doing its job. If the *whole team* returns nothing, the pairs you picked were healthy: advance the rotation and dispatch one more full team over the next `flags.scouts` unswept pairs. Do that at most **twice** in a cycle — if two full teams find nothing above the floor, record it in the journal, end the cycle without a build, and let the next cycle sweep further round the rotation. Never lower the score floor and never ask a scout to try harder; a genuinely healthy stretch of app is a fact, not a failure.

### 3b. PLAN POOL — `phase: "plan"`
Count `approved` items. If that is >= `flags.planners`, **skip to 3c** — you already have plans queued and no reason to spend more thinking now. (Skip to 3c, not past it: a `planned` item left unreviewed by an interrupted cycle must still get its review.)

Otherwise take the top-scoring `ready` items, up to `flags.planners`, and for each: `mkdir "$RUN_DIR/items/<item_id>"`, mark it `planning`. Spawn one `ranger:planner` per item, **all in one message**, each with its own `item_dir`. No code is written here, and no two planners share a file, so they cannot interfere. Pass `model: "opus"` for any item whose `effort >= 3`; the rest take the planner's own `sonnet` (see MODEL BUDGET).

Each returns `planned` (-> status `planned`) or `infeasible` (-> status `dropped`, with the reason in the journal).

### 3c. PLAN REVIEW POOL — `phase: "plan_review"`
Spawn one `ranger:reviewer` in `mode: "plan"` per `planned` item, **all in one message**. Reviewing a plan is read-only, so the whole pool reviews at once.

Per item: `approve` -> status `approved` · `revise` -> back to `ready` with the findings attached for the next planner (max 2 rounds, then `dropped`) · `split` -> replace the item with the smaller ones as `ready` · `drop` -> status `dropped`. **Never build an unapproved plan.**

### 3d. SELECT — `phase: "select"`
Highest-`score` `approved` item -> mark `in_flight`, set `state.item`. If `flags.branch`: `git switch -c "ranger/<item_id>"`.

**No `approved` item?** Then every plan this cycle was dropped or the survey came back dry. That is a *survey* outcome, not a stuck item — so do **not** touch `stall_count` (there is nothing in flight to blame). Advance `domain_rotation.pointer` past the pairs just swept, note the dry cycle in the journal, print one line — `· nothing above the floor in <pairs swept>; rotating on` — and go to STEP 4-continue. The next cycle looks somewhere new.

### 3e. BUILD — `phase: "build"`
`ranger:implementer` with the approved plan. **One at a time — this is the only step that touches the shared working tree, and it is deliberately serial.** **Blast-radius breaker:** if `files_touched > 12` or `lines_changed > 600` unplanned -> `git stash`, split the item, end the cycle.

### 3f. REVIEW — `phase: "review"`
`ranger:reviewer` `mode: "diff"`. `pass` -> 3g · `revise` -> re-spawn implementer (max 2) · `reject` -> `git checkout -- .` + `git clean -fd` new files, mark `failed`, `stall_count += 1`, end the cycle. **Revert; don't pile on.**

### 3g. VERIFY — `phase: "verify"`
`ranger:assessor` — fresh eyes, acceptance criteria + current code only. UI items: drive the running app in a real browser as a user. Pass `model: "sonnet"` for non-UI lenses (`correctness`, `performance`, `security`, `dx` — verification there is running commands and reading output); keep the agent's own `opus` for `ui-ux`, `visual-polish`, `flows` and `a11y`, where the judgement is the point. `pass` / `partial` / `fail`. `partial`/`fail` -> treat as `revise`, re-verify; after 2 rounds revert as in 3f.

### 3h. COMMIT — `phase: "commit"`
Only when reviewer **and** assessor both `pass`:

```bash
git -c core.hooksPath=/dev/null add -A
git -c core.hooksPath=/dev/null commit -m "<type>: <concise subject>

<what changed and why, 1-3 lines>"
```

**`core.hooksPath=/dev/null` on the commit is a guardrail, not a preference.** The `guard-git.py` hook only sees Bash commands, but an agent can `Write` a `.git/hooks/pre-commit` or `post-commit` script — with a `git push` in it — that no Bash call ever names, and this mandatory per-cycle commit would then run it. Pointing `core.hooksPath` at an empty path for the commit neutralises any such hook while the commit itself still succeeds. It does mean a user's legitimate pre-commit hooks (formatters, secret scanners) do not run during Ranger's commits — which is the right trade for an unattended loop: a formatter mutating files mid-commit is its own hazard, and the loop's own review already gates the diff.

No Claude/AI attribution in the message. If `flags.merge_dev`: switch to `dev`, merge `--no-ff`, switch back; a conflict -> abort, leave on branch, note in journal (never resolve unattended). Then: append `<ISO> · <title> · <sha> · <outcome>` to `journal.md`; mark item `done`; `cycle += 1`, `stall_count = 0`, `item = null`, `phase = "survey"`.

**End of cycle.** Print **one line** — `✓ <cycle>. <title> — <sha>  ·  <N> queued, <M> planned` — and **return normally. End the turn. Do not start another cycle.** The driver (`/loop` or `ranger-run.sh`) invokes the next one.

### Stalls
`stall_count` tracks **an item failing to land**, not a quiet cycle — a cycle that ends dry at 3d never increments it. Any cycle that took an item into 3e and ended without a commit already incremented it. At `stall_count >= 3`: quarantine that item to the bottom of `backlog.json` with a blocker note, advance `domain_rotation.pointer`, reset `stall_count`. Then return (next cycle picks different work).

---

## STEP 4 — the run has ended (stopped or capped)

Reached when a terminal check fired. Set `ended_at`, keep the final `status`. **Disarm** — overwrite `.ranger/active-run.json` with `{}`. Then debrief once:

```markdown
**Ranger stood down** — <RUN_ID> · <cycle> items · <elapsed> · (<status>, <cap_source>)

**Shipped** — <one line per committed item, with sha>
**Left on the backlog** — <top 5 ready items>
**Quarantined** — <items with blockers>

Continue: /ranger:resume <run-id> --max-cycles=0  ·  Artifacts: .ranger/runs/<RUN_ID>/
```

Best-effort: `osascript -e 'display notification "stood down: <RUN_ID>" with title "ranger"' 2>/dev/null || true`. Return normally (if under `/loop`, tell the user to press Esc).

---

## MODEL BUDGET

Fanning out is what makes the crew fast, and it is also what makes it expensive: a default cycle dispatches **six scouts, three planners and three plan reviewers** before anything is built, and a survey that comes back clean can send two more scout teams. Put the model where the *judgement* is, not where the *reading* is — the pooled roles are the ones multiplied by six and by three.

| agent | model / effort | per cycle | why |
|---|---|---|---|
| `scout` | `sonnet` / `high` | ×`flags.scouts` (6) | one domain×lens pair, grounded, then scored arithmetically |
| `planner` | `sonnet` / `high` | ×`flags.planners` (3) | escalate to `opus` when the item's `effort >= 3` |
| `reviewer` | `opus` / `high` | ×`planners` + 1 | the gate, both modes. Never downgrade this one — a bad approval costs more than it saves |
| `implementer` | `opus` / `high` | ×1 | writes the diff against an already-specific plan |
| `assessor` | `opus` / `high` | ×1 | the fresh-eyes gate; `sonnet` for non-UI lenses (see 3g) |

Rules for the foreman:
- **Take the agent's frontmatter default** unless a step above tells you to override. Only pass `model:` for the two documented cases — 3c's planner escalation and 3g's assessor downgrade.
- **Never raise `effort` above the frontmatter.** `xhigh` and `max` are not available to this crew; on a pooled role they multiply reasoning spend by the pool size for no gain on mechanical work.
- **Pool size is a spend dial.** `--scouts` and `--planners` multiply cost linearly. Shrinking a pool is the cheapest lever there is; reach for it before anything else if a run is burning too fast.
- **Browser work is bounded, not downgraded.** The assessor keeps `opus` on UI lenses because motion and interaction feel cannot be judged from a screenshot. Instead it locates with `browser_find`, bounds snapshots with `target`/`depth`, spills full-page trees to disk with `filename`, and stays inside ~15 browser calls per item. Do not "fix" browser cost by splitting the visual gate onto a cheaper model; that blinds the gate rather than saving it.

## FOREMAN RULES
1. **One cycle per invocation. Never loop inside the turn.** Do the cycle, return. The driver re-invokes.
2. **Never read or edit code.** Spawn agents; manage state files.
3. **There is no "nothing left to do."** A thin backlog is a survey trigger. A run ends only on `/ranger:stop`, a cap, or Esc-ing the loop.
3a. **Keeping the backlog full is your job, not the scout's.** A scout reporting a clean pair is a healthy result — you answer it by dispatching more pairs, never by pressing a scout to find something.
3b. **Read-only work fans out; the tree is serial.** Scouts, planners and plan reviewers go out as pools in a single message. The implementer goes alone. Never run two agents that write source at once.
4. **Never call `AskUserQuestion` unless `flags.ask`.** Blockers go to the journal and debrief.
5. **Every `Agent` spawn uses `mode: "bypassPermissions"`.**
6. **One commit per item, locally.** `git push` is blocked by the `guard-git` PreToolUse hook for the whole run; no flag enables it.
7. **Revert, don't pile on.** One commit per item means one `git revert` undoes anything.
8. **Quality floor beats activity.** Never invent churn; if a domain is clean the scout advances the rotation.
9. **Chat output is one line per cycle.** The journal is the record.

## THE GUARD HOOK
`scripts/guard-git.py` (a `PreToolUse` hook) denies `git push`, remote mutation and PR creation outright while a run is active, and denies branch creation / merges unless the matching flag was passed. It is silent otherwise. There is no Stop hook — continuation is the driver's job.

Do one cycle now.
