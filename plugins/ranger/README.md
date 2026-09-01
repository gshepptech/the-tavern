<div align="center">

<img src="ranger.svg" alt="Ranger — the foreman" width="100%"/>

# Ranger

**The foreman who never leaves the site. One prompt, then walk away.**

[![Version](https://img.shields.io/badge/version-0.7.0-F9A825?style=flat-square)](.claude-plugin/plugin.json)
[![License](https://img.shields.io/badge/License-Apache--2.0-1E88E5?style=flat-square)](../../LICENSE)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-plugin-8E44AD?style=flat-square)](https://docs.claude.com/en/docs/claude-code)

</div>

> [!NOTE]
> **Ranger stands entirely on its own.** Install it by itself and it runs a full senior-engineering loop — survey, plan, build, verify, commit — with no other plugin present. If `cleric`, `seer`, or `scout` also happen to be installed, a scout will dispatch to them for their specialisms instead of duplicating that work; none of them is required, and Ranger covers the same ground itself if they're absent.

---

## When to use it

| Reach for it when | Don't bother when |
|---|---|
| You have hours you won't be at the keyboard and a codebase worth a standing quality sweep | **You have a specific task in mind.** A direct prompt is faster, cheaper and better aimed — Ranger surveys, and a survey is wasted when you already know the answer |
| The project has tests, a linter or a build the assessor can actually run | **There are no tests and nothing to check against.** Verification degrades to reading the diff, and a loop you can't verify is a loop you can't leave |
| You're under version control and happy with one local commit per item | **You're not in a git repo.** Ranger refuses to start — one commit per item *is* the undo, and without git there isn't one |
| You want breadth — accessibility, polish, performance, real-user flows — swept in rotation rather than chosen | You want one feature built to a spec. Ranger biases toward what already exists; a brief tilts its ranking, it doesn't hand it a backlog |

---

## What it does

Most "autonomous" loops die one of two deaths: they run out of work and stop, or they fill their context window and go stupid. Ranger is built against both.

- **No exit condition.** An empty backlog is a survey trigger, not a finish line, and **nothing but you ends a run** — `/ranger:stop`, Esc, a cap you set. Ranger never decides for itself that the work is finished. Continuous operation is a *driver's* job: `/loop /ranger:run` while you watch, or a headless runner overnight. Each `/ranger:run` does one clean cycle and returns; nothing traps the turn.
- **A thin lead.** The foreman spawns agents and manages state files; he never edits code. Every agent gets a fresh context; his own window stays small, so a run survives for hours.
- **A crew, not a queue.** Surveying, driving, claims-checking and plan-review are read-only, so they run as parallel pools. Only the build touches the shared tree, so only the build is serial — one item at a time, unless two plans provably touch nothing in common, which puts them in separate worktrees behind five conditions and a flag.
- **Effort sized to the item, declared after reading it.** A one-line copy fix gets two agents; a concurrency bug gets the full adversarial pipeline and a mandatory fresh-eyes gate. The lead guesses the tier from the entry and the build agent overrules it from the code — it can raise the tier, never lower it. One fixed pipeline for everything is the most expensive mistake a loop like this can make.
- **An artifact, or it's a hypothesis.** An item carries the command someone ran and what they saw, not just the line they read. Citations prove a line exists; they don't prove the path reaches it or that the behaviour you inferred is the one a user gets. Items with no artifact are quarantined until something reproduces them — never planned.
- **Plan review before code — and a claims check before that.** A rejected plan costs one agent; a bad implementation costs five. Most revision rounds in a mature run are citation defects, not design defects, so a cheap pass verifies every claim against its source before the expensive reviewer is spent.
- **One agent that runs the system instead of reading it.** Everyone else reads. The driver starts the app, clicks the thing, calls the endpoint and measures what can't be eyeballed — which is how you find a control rendering at 12 pixels tall, or an error message sitting at `display: none` in every state a user can reach. "I couldn't reproduce it" is a success verdict, not a failure.
- **Fresh-eyes verification.** The assessor never sees the plan — only the acceptance criteria and the code. It cannot be argued into agreeing. UI items get driven through a real browser, clicked through like a user would.
- **A gate that dies is reported, never replaced.** Every verdict is written to disk before it is returned, so a dead agent degrades to a partial verdict instead of silence — and the foreman is forbidden from writing any gate it commissioned.
- **Local commits only.** `git push` is denied by a `PreToolUse` hook for the whole run, and no flag turns it on.

---

## Install

**1. Install**

```bash
claude plugin marketplace add gshepptech/the-tavern
claude plugin install ranger@the-tavern
```

*(Already installed? `claude plugin marketplace update the-tavern` to get the latest.)*

**2. Preview — changes nothing**

```
/ranger:run make the dashboard genuinely good --dry-run
```

The recommended first contact: you get the ranked backlog and the plan for the top item, and nothing is written. [Worked example 1](#worked-examples) shows what comes back.

**3. Set him going** — `/loop /ranger:run make the dashboard genuinely good`, and press **Esc** to stop.

> [!WARNING]
> **Read this before step 3, not after.** Two things about a real run:
>
> - **It is uncapped by default.** Ranger works until you stop him — `/ranger:stop`, Esc out of the loop, or kill the runner. Nothing else ends it. `--max-hours=N` is the only bound that stops a run on its own. (`--max-cycles=N` counts *shipped* items, so a run that keeps reverting never reaches it.)
> - **Unattended mode runs with permissions bypassed.** With no human present to answer prompts, the headless runner and every agent it spawns execute tools without asking: file writes, shell commands, network calls. The git guard still holds, but **only git is guarded**. Run the headless mode in a container, a VM, or a throwaway clone — never on a machine you care about while you walk away. The watched `/loop` form is lower-risk only because you are sitting there.

If you run a methodical-mode plugin (`warden`, `adhoc`, `plumb`), clear its strict gate first — `/warden:strict-off` etc. — or it will deadlock the loop. Ranger checks this at the start and tells you exactly what to run.

---

## The cycle

Ranger's whole story is its loop: a read-only crew fans out in parallel, then one thread of work goes serial through the tree.

```mermaid
flowchart LR
    classDef pool fill:#FFF3C4,stroke:#F9A825,stroke-width:1px,color:#3a2e00;
    classDef serial fill:#F9A825,stroke:#3a2e00,stroke-width:2px,color:#1a1400,font-weight:bold;
    classDef lead fill:none,stroke:#999,stroke-width:1px,stroke-dasharray:3 3;

    subgraph SU["survey - scouts, default 6"]
        direction TB
        s1[scout]:::pool
        s2[scout]:::pool
    end
    subgraph ESC["escalation only - planners, default 1"]
        direction TB
        p1[planner]:::pool
        c1[claims check]:::pool
        r1[plan reviewer]:::pool
    end

    SU --> TRI[triage - tier hint]:::lead
    TRI --> SEL[select]:::lead
    TRI -.risky.-> ESC --> SEL
    SEL --> BUILD[build — builder]:::serial
    BUILD -.needs-plan.-> ESC
    BUILD --> DIFF[review — diff]:::lead
    DIFF --> VER[verify — assessor]:::lead
    DIFF -.proved by a failing test.-> COM
    VER --> COM[commit]:::lead
    COM -.refills backlog above watermark.-> SU
```

| step | who | what |
|---|---|---|
| **survey** | *N* scouts in parallel | one domain/lens/modality triple each — refills the backlog *before* it runs low |
| **triage** | lead | a `tier_hint` from the entry, and a route: default path, or pre-plan |
| **select** | lead | the highest-scoring item that is ready or already approved |
| **build** | 1 builder — serial | reads, decides, edits, proves; returns the diff **and** the plan it followed |
| **review** | reviewer | correctness, regression, reuse, altitude, honesty — against the real diff |
| **verify** | assessor | fresh eyes, evidence ledger, real browser for UI items — routed, not automatic |
| **commit** | lead | one local commit, one journal line, back to survey |

Reviewer **and** assessor must both return `pass`. Anything else revises, and after two rounds the item is reverted — never patched over.

### The plan is part of the build, until it isn't

Most items go to one agent. A separate planner writing a paragraph, a checker opening the two files it cites and a reviewer approving the paragraph is three agents' worth of ceremony to authorise a one-line edit — and the plan was never the hard part. Reading the code was, and the builder has to do that anyway.

But difficulty isn't knowable from a ticket. "Add a key to this table" turns out to be two tables with opposite defaults. "Replace a repeated literal with a constant" turns out to be two different meanings that coincidentally match. None of that shows up in a backlog entry; all of it shows up ninety seconds into the code. So the builder can **bail** — `needs-plan` returns its reading and no diff, and the item escalates to the full planner -> claims-check -> plan-review path with that reading attached.

The common case costs one agent. The rare case costs two. Every case used to cost three before a line was written.

### Not every item gets the whole crew

The build agent declares the item's real tier after reading it — the lead's hint came from a sentence, the builder's tier comes from the code. It may raise the tier; it may never lower it.

- **`trivial`** — copy, a CSS value, a constant, a pure one-liner in one file. Builder plus one diff review. Two agents.
- **`standard`** — the default, and where most items land. The pipeline above.
- **`risky`** — concurrency, data format or migration, auth and secrets, a component with 3+ call sites. Two plan reviewers instead of one (disagreement is a revision), and the fresh-eyes gate is mandatory and can't be downgraded.

Verification is routed the same way. The assessor is mandatory for anything where the judgement is visual or interactive, for `risky` items, and for any build the diff reviewer flagged. For a pure-logic fix already pinned by a test the lead has **watched fail against the pre-change code**, that test *is* the fresh-eyes evidence and the assessor is skipped — it would only re-derive it. When the assessor genuinely can't drive something, it has a time-boxed fallback ladder (`live` -> `seeded` -> `mechanism` -> `blocked`) and reports which rung it reached, instead of burning an hour fighting a toggle.

---

## Why it never runs out of work

The first survey sends one scout to map the *product* — its real domains, like the checkout flow, the settings page, the CLI, the auth layer. It maps **every tier that runs code**, not just the one with a UI; a pipeline or a scoring module will happily hold the worst bug in the repo while a hundred frontend sweeps go past it. After that the foreman crosses those domains with nine lenses:

**correctness, UI/UX, visual polish, real-user flows, performance, accessibility, security, DX, feature gaps** — swept in that order.

Every domain/lens combination is a **pair**, and each scout in a wave takes one; a persistent `swept` map means no pair is issued twice, so the loop moves forward instead of circling. The survey fires when the backlog drops **below a watermark** (default `scouts + 2` = 8 items), not when it hits zero — so the foreman is stocking up while the current item is still being built, and never stalls waiting for work. It goes out alongside the current build, since reading a half-edited tree is fine for an agent that proposes work rather than asserting a diff.

The rotation also learns. The foreman records a **yield** per pair — sweeps versus items that survived dedup and the floor — and a pair that comes back clean twice goes cold and gets skipped until its domain changes. Breadth-first with no feedback spends the same on the well-hardened area as on the one full of defects.

### When reading stops working, it stops reading

There's a third axis: **modality**. Reading the source and driving the running system see different defects, and a run that has gone quiet is often an exhausted method rather than a healthy codebase — a reader eventually stops finding what a reader can find, and raising the bar just makes it read more selectively over the same ground.

So after three lean cycles the survey switches to driving: start the app, walk the real flows, hit the real endpoints, measure what can't be eyeballed. It's cheaper too — driving one flow beats sweeping nine lenses across every domain to conclude nothing is wrong.

The same agent settles the quarantine. Once three or more unreproduced items pile up, a driver goes and tries them: reproduced items become plannable, disproved ones are closed with evidence, and an item that turns out to be a *different* problem gets rewritten before anyone plans a fix for the wrong thing.

### Entries rot, and closing one counts

Every backlog entry carries a `verified_at` cycle stamp, and one older than 15 cycles has to be re-checked against the tree before it can be built. A loop that files continuously and never re-verifies drifts toward a board describing a codebase that no longer exists — one sweep of one board turned up six entries marked pending or blocked when the work had already shipped, each with a confident-sounding justification.

**"Closed as already shipped" is a real outcome and it's reported as progress.** It's often the most valuable thing a cycle can produce, and it used to look like failure.

**It will not manufacture churn.** Every candidate is scored `value + confidence - effort + consequence`; anything under the floor is dropped. A scout that finds nothing above the floor reports its pair **clean** — a real, useful answer. Keeping the backlog full is the foreman's job, answered by dispatching more pairs, never by pressing a scout to come back with something.

`consequence` (0–5) is what happens to a real person if the thing stays broken, and it's a separate number from `value` on purpose. Without it the formula is blind to stakes: a wrong figure on a page people *act on* scores within a point of a misaligned heading, because both are "one small thing that's wrong" — and then the wrong figure sits mid-backlog for weeks while cosmetics ship above it. It's scored from the failure, not the lens: a visual-polish item is a 5 if the polish is a contrast failure on a warning nobody can now read.

## …and how it raises its standards instead

Never running out of work is right on a young codebase and turns into a treadmill on a maturing one: the real defects clear, and the loop grinds progressively more marginal items at full cost, because any codebase has an infinite supply of small improvements.

The fix is **not** to let it stop — it doesn't, and won't. It's to make it pickier, so an uncapped run spends its cycles on the best work available rather than on whatever it found first:

- **The floor rises.** It starts at 6 and climbs by 1 every 10 cycles whose shipped work averaged below `floor + 4`, to a maximum of 12. It never falls. A run at cycle 100 refuses work a run at cycle 5 would take.
- **The pool is capped.** 40 items across `ready + planned + approved`. At the cap, filing costs something: a new item means dropping one. There's a prune pass — the foreman kills items below the risen floor, items describing code that has since been rewritten, and items that have lost the selection 20 cycles running. **Killing an item counts as progress.**
- **Lean runs are reported, not stopped.** After 5 consecutive cycles producing nothing meaningfully above the floor, you get one line saying so and what's left at the top. Then it keeps sweeping. Whether that's worth continuing is your call — `/ranger:stop` when it isn't.

The survey itself is deliberately the uncapped part of a cycle. If a whole scout team comes back with nothing above the floor, the foreman dispatches another, and another, until it finds work or has swept every remaining pair in the rotation. A cheap read-only sweep that turns up the one real bug is worth many that turn up nothing, and a fixed retry limit is how a loop walks past work it was one team away from reaching.

Review findings never become backlog items. A reviewer's or assessor's finding is feedback on the item in flight — it belongs in that item's revision round or the journal. A loop that files its own commentary as future work is generating its own demand, and that is how a backlog reaches 120 items with nothing important in it.

## `.ranger/FACTS.md`

One short file, outside the run directory so it survives the run that made it, handed to **every** agent before it reasons. The recon scout seeds it; the foreman corrects it when an agent asserts something false about the repo; you can edit it by hand, and that's the point.

It holds the north star (what the project is optimising for right now, so a marginal dashboard tweak can be weighed against it), the hard constraints that shouldn't be re-litigated, how the repo is *really* tested and what it deliberately doesn't use, the conventions agents trip on, and anything out of bounds. It exists because agents re-derive settled facts every cycle and sometimes get them wrong — a plan reviewer asserting the repo tests with `jsdom` when it doesn't costs a full revision round to discover. Keep it under ~60 lines; past that it has stopped being facts and started being a wiki.

---

## Commands & flags

| command | what it does |
|---|---|
| `/ranger:run <brief> [flags]` | Run one cycle — survey, plan, review, build, verify, commit one item — and return. |
| `/ranger:resume [run-id] [--max-cycles=N] [--max-hours=N] [--unlimited]` | Pick a stopped run back up: same backlog, rotation, and flags. |
| `/ranger:stop [run-id]` | Down tools — the only clean way to end a run. |
| `/ranger:status` | Read-only — what he's working on right now. Safe mid-run. |
| `/ranger:help` | Explains the loop and every flag, in chat. |

| flag | default | with the flag |
|---|---|---|
| `--preset <name>` | sweeps every domain in rotation | focuses one curated checklist: `ui`, `ux`, `a11y`, `harden`, `perf` |
| `--sweep[=all]` | the rotation advances a few pairs per cycle | one survey-only pass over the whole domain grid, drivers on the experiential lenses, ending with a ranked board and no build (`=all` = all nine lenses) |
| `--dry-run` | executes for real | previews only — one scout + top plan, no writes, no commit |
| `--scouts=N` | 6 sweep in parallel | resize the survey team (clamped 1–8) |
| `--planners=N` | 1 | resize the pre-plan pool, which now feeds escalations and `risky` items only (clamped 1–4) |
| `--branch` | commits to the current branch | a local branch per item |
| `--merge-dev` | leaves integration to you | merges verified items into `dev` |
| `--ask` | **never asks you anything** | may ask when genuinely blocked |
| `--max-cycles=N` | **unlimited** | stands down after N *shipped* items (`0` = unlimited) |
| `--max-hours=N` | **unlimited** | stands down after N hours (`0` = unlimited) |
| `--unlimited` | — | no-op — kept so older invocations don't error |
| `--new` | continues a parked run | forces a fresh run |

Note `--max-cycles` counts **shipped items**, not attempts — a cycle that reverts, quarantines, or finds nothing above the quality floor spends time without advancing the count. That makes **`--max-hours` the only cap that reliably bounds spend.**

There is no `--push` and no flag that adds one. A `PreToolUse` hook (`scripts/guard-git.py`) denies `git push`, remote mutation (`git remote add/set-url/…`, `git config remote.*`), `git send-email`, PR/release creation (`gh pr create`, `gh release create`) and `gh api` calls that use a write method — for the entire run, with nothing to enable them. Branch creation and merges are allowed only with `--branch` / `--merge-dev`; everything else about git is untouched. Because it runs outside the model, the block holds even under bypassed permissions, and it resolves shell quoting and looks inside `sh -c`, `bash -c` and `eval` wrappers, so the obvious ways past it are closed.

> [!IMPORTANT]
> **It is a guardrail, not a sandbox.** The guard inspects commands as text, and its threat model is an agent publishing by accident — not someone deliberately working around it. A command that writes a script and then runs it, or reaches the network by a route nobody enumerated, gets through. The real containment for an unattended run is running it somewhere disposable. Anyone telling you a text-matching hook is airtight is selling something.

### Presets

`--preset <name>` swaps the broad domain rotation for a curated checklist, skipping any item that doesn't apply to your app instead of inventing the missing feature:

| preset | what it works on |
|---|---|
| `ui` | visual polish — hierarchy, spacing rhythm, type, colour, empty/loading/error states |
| `ux` | real-user flows — drives the app, checks the primary task completes, errors recover |
| `a11y` | keyboard traversal, focus, semantics, names/labels, contrast, reduced motion |
| `harden` | input validation, injection, authz, secrets, error hygiene, dependencies |
| `perf` | N+1s, over-fetching, bundle weight, render cost, blocking work — evidence required |

---

## Worked examples

Output below is **illustrative** — the preview block, the per-cycle line and the stand-down debrief are abbreviated from the templates in `commands/run.md`. Titles and shas are made up; the shapes are not.

<details>
<summary><b>1. Preview before you spend anything</b> — <code>--dry-run</code></summary>

You've just installed it and want to know what it would actually do to your app.

```
/ranger:run make the dashboard genuinely good --dry-run
```

```markdown
**Ranger dry run — preview only, nothing changed.**

**What I'd work on (top of a 7-item backlog):**
1. [8] Dashboard empty state is a bare "No data" string — dashboard/ui-ux
2. [7] Chart re-renders on every poll tick — dashboard/performance
3. [7] Date-range picker cannot be reached by keyboard — dashboard/a11y

**Plan for #1 — Dashboard empty state is a bare "No data" string**
Reuse the EmptyState component the reports page already has rather than adding a
second one; pass the dashboard's copy and primary action through its props. 2 files.
· reviewer verdict: approve

**Domains I'd rotate through:** dashboard, settings, auth, billing, CLI

Run without --dry-run to execute. A real run is uncapped — it works until you stop it.
Pass --max-cycles=N or --max-hours=N to bound it.
```

A dry run spends one scout, one planner and one plan reviewer, and writes nothing but its own state directory. **Next:** if the top of that backlog is work you'd have done yourself, drop `--dry-run`; if it isn't, sharpen the brief and preview again — that's the cheap loop.
</details>

<details>
<summary><b>2. A bounded run you watch</b> — <code>/loop</code> plus <code>--max-hours</code></summary>

An afternoon free, and you want the dashboard genuinely improved rather than one specific fix.

```
/loop /ranger:run make the dashboard genuinely good --max-hours=3
```

```markdown
Ranger is on site — ranger-20260722-093015-1f4a.  Brief: make the dashboard genuinely good  Cap: 3h.
Local commits on main. Keep me working: /loop /ranger:run …  (Esc to stop)

✓ 1. Dashboard empty state reuses EmptyState — 4f2a1c9  ·  6 queued, 2 planned
✓ 2. Debounce poll tick, memoise chart series — 91be07d  ·  5 queued, 3 planned
· nothing above the floor in dashboard/security, settings/security; rotating on
✓ 3. Date-range picker reachable and focus-visible — c30ff41  ·  8 queued, 2 planned

**Ranger stood down** — ranger-20260722-093015-1f4a · 3 items · 3h04m · (capped, user)

**Shipped** — 4f2a1c9 empty state · 91be07d chart re-render · c30ff41 date-picker keyboard
**Left on the backlog** — 5 ready items, top: "Settings save gives no confirmation"
**Quarantined** — none

Continue: /ranger:resume ranger-20260722-093015-1f4a --max-cycles=0  ·  Artifacts: .ranger/runs/ranger-20260722-093015-1f4a/
```

One line per cycle is the whole chat output — the detail lives in `journal.md` and `items/<id>/`. **Next:** read the three commits. Each is one item, so anything you disagree with is one `git revert` away.
</details>

<details>
<summary><b>3. One lens, not the whole rotation</b> — <code>--preset</code></summary>

An accessibility audit is coming and you want the obvious failures gone first.

```
/ranger:run get the checkout flow to WCAG AA --preset a11y --scouts=4 --max-hours=2
```

The preset swaps the broad domain rotation for the `a11y` checklist; the brief still biases ranking, so checkout work sorts above everything else.

```markdown
✓ 1. Focus trap in the payment modal, Esc now closes — 7ab4e10  ·  4 queued, 2 planned
✓ 2. Card fields get labels and error announcements — e59c2d3  ·  3 queued, 3 planned
```

**Next:** re-run with `--preset ui` once the a11y sweep quietens, or drop the preset and let the full rotation carry on.
</details>

---

## Keeping it running

Each `/ranger:run` does **one cycle and returns** — a clean turn, no hook trapping the session. Driving it is your choice: `/loop /ranger:run <brief>` keeps it going in your session (Esc to stop), or run it overnight with a fresh `claude -p` process per cycle, so context never accumulates:

```bash
# from the root of the repo you want worked on.
# The plugin cache keeps one directory per installed version, so resolve to the
# newest rather than globbing — an unquoted glob that matches two versions runs
# the older one and silently folds the other path into your brief.
RANGER=$(ls -d ~/.claude/plugins/cache/the-tavern/ranger/*/scripts/ranger-run.sh | sort -V | tail -1)
"$RANGER" "make the dashboard genuinely good"
```

`/ranger:stop` from any session ends a run; `/ranger:resume` picks it back up.

> [!WARNING]
> **Run unattended mode in a sandbox.** With no human present to answer permission prompts, Ranger runs with permissions bypassed — the `ranger-run.sh` runner and every agent it spawns execute tools without asking. The guard hook blocks `git push`, remote mutation and PR creation even in bypass mode — but **only git is guarded. Everything else runs unprompted**: file writes, shell commands, network calls. That is the cost of an unattended loop, not a defect.
>
> Run overnight/headless mode somewhere a bad command can't hurt you — a container, a VM, or a throwaway clone. Do **not** point it at a machine you care about and walk away. The watched `/loop /ranger:run` is lower-risk because you're right there, but it bypasses prompts too.

---

## Guardrails

| risk | guard |
|---|---|
| publishing unattended | the `PreToolUse` hook denies `git push`, remote mutation, `gh pr`/`release` creation — always, even under bypassed permissions |
| scope creep | an item past ~12 files / ~600 lines unplanned is stashed and split |
| grinding on the impossible | 3 cycles with no commit, and the item is quarantined; rotation advances |
| a bad change compounding | revert, don't pile on — one commit per item, one `git revert` away |
| conflicts | a conflicting merge is aborted and left on its branch, never resolved unattended |
| interactive deadlock | preflight refuses to start unless the methodical-mode strict gates (`warden`, `adhoc`, `plumb`) are off |

---

## Where state lives

```
.ranger/
  active-run.json          the marker that arms the guard hook — {} when idle
  FACTS.md                 repo ground truth — outlives the run; every agent reads it
  runs/<run-id>/
    state.json             status, phase, cycle, flags, crew sizes, rotation + yield, floor, cap
    backlog.json           ranked items: ready / planned / approved / in_flight / done / quarantined
    journal.md             one line per shipped item, with tier, score and sha
    items/<item-id>/       plan.md, build.md, verify.md, screenshots
```

All of it is on disk, not in the context window — a compaction mid-run is survivable, and `/ranger:run` picks up exactly where a stopped run left off.

---

## What it costs

Every cycle is a crew, and the crew is subagents. **The common case is now 6 scouts, then 1 builder, 1 diff reviewer and sometimes 1 assessor** — the builder plans and builds in one pass, so the planner, claims-checker and plan-reviewer pools are spent only on `risky` items and escalations. A `risky` item still dispatches the full stretch, and that is the ceiling rather than the norm:

- A `trivial` item costs **two** agents — builder and one diff review.
- The survey is skipped while the backlog sits above the watermark, and skipped entirely at the cap. It also runs concurrently with the build, so it costs wall-clock only once.
- The plan pool is skipped entirely unless something escalated or the item is `risky`.
- The assessor is skipped for pure-logic work already pinned by a test that was watched failing *for the right reason*.
- Claims checking runs on the cheap model and is *net negative* cost: it catches the citation and artifact defects that would otherwise burn an `opus` reviewer plus a whole re-plan round.

Cycles are dearer when work doesn't land — a revised plan, a rejected diff or a failed verification all spend agents without producing a commit. A builder that bails to `needs-plan` puts an item back on the expensive path, which is why the bail has to be honest rather than frequent: roughly one item in five or fewer is the shape this assumes. `--scouts=N` is the main dial on per-cycle width.

Model follows the *check*, not the role. Claim-vs-source matching is mechanical and runs on `haiku`; mutation runs and criterion mapping are mechanical too. Copy, design judgement and the diff gate get the expensive model, because that's where the judgement actually is.

And it does not stop on its own. **Uncapped is the default**: `/ranger:stop`, Esc, or killing the runner are the only things that end a run. `--max-cycles=N` counts *shipped* items, so a run that keeps reverting spends indefinitely without ever reaching the cap — **`--max-hours=N` is the only bound that terminates a run by itself.** Set one on your first unattended run.

Watch the first few cycles before trusting it overnight; the attended-to-unattended transition is the whole skill. And Ranger is deliberately conservative about what counts as work — if you want him building features rather than sweeping domains, say so in the brief. It biases the scout's ranking; it doesn't limit scope.

---

## Pairs well with

Ranger needs none of these — each is a standalone plugin you can install with or without it:

- **[Cleric](../cleric/README.md)** — if installed, a scout on the `dx` lens dispatches dedup/dead-code/type-consolidation findings to it instead of duplicating the sweep.
- **[Seer](../seer/README.md)** — same `dx` lens, for macro-architecture and design-cohesion findings.
- **[Scout](../scout/README.md)** — a scout on the `flows` lens dispatches to it for end-to-end browser coverage.

---

<div align="center">

Apache-2.0 — see [LICENSE](../../LICENSE). © 2026 gshepptech

</div>
