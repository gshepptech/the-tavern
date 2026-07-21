<div align="center">

<img src="ranger.svg" alt="Ranger — the foreman" width="100%"/>

# Ranger

**The foreman who never leaves the site. One prompt, then walk away.**

[![License](https://img.shields.io/badge/License-Apache--2.0-1E88E5?style=flat-square)](../../LICENSE)
[![Version](https://img.shields.io/badge/version-0.1.0-1E88E5?style=flat-square)](.claude-plugin/plugin.json)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-plugin-8E44AD?style=flat-square)](https://docs.claude.com/en/docs/claude-code)

</div>

> Part of the **The Tavern** crew. Ranger runs a self-directing senior-engineering loop that never stops and never runs out of work. A thin lead drives five Opus sub-agents through plan → review the plan → build → review → verify → commit, one local commit per item. When the backlog empties, he steps back, picks a domain, and keeps going.

---

## ✨ What It Does

Most "autonomous" loops die one of two deaths: they run out of work and stop, or they fill their context window and go stupid. Ranger is built against both.

- **No exit condition.** An empty backlog is a survey trigger, not a finish line. The run ends on `/ranger:stop` or a cap you asked for — nothing else. A `Stop` hook enforces it.
- **A thin lead.** The foreman reads state files and spawns agents. He never opens a source file. Every agent gets a fresh context; the lead's window stays small, so the run survives hours.
- **Plan review before code.** A rejected plan costs one agent; a bad implementation costs five.
- **Fresh-eyes verification.** The assessor never sees the plan — only the acceptance criteria and the code. It cannot be argued into agreeing.
- **UI work gets driven, not read.** For interface items the assessor runs the app, clicks through it as a user, checks loading/empty/error states, reads the console, resizes to a phone — then judges how it *looks*, not just whether it renders.
- **Local commits only.** `git push` is denied by a `PreToolUse` hook for the whole run, and no flag turns it on. Instructions are a request; a hook is a guarantee.

---

## 🚀 Install

```bash
claude plugin marketplace add gshepptech/the-tavern
claude plugin install ranger@the-tavern
```

First, see what he'd do — this previews the ranked work and the top plan, and changes nothing:

```
/ranger:run make the dashboard genuinely good --dry-run
```

Happy with it? Hand him the site:

```
/warden:strict-off          # once, so nothing interactive can deadlock the run
/ranger:run make the dashboard genuinely good
```

That is the whole interaction. He will not ask you anything. Your **first run in a repo is capped at 5 items** so you can review before trusting him longer — pass `--unlimited` to let him run without a limit.

---

## 🔁 The Cycle

```
survey → select → plan → plan-review → build → review → verify → commit
```

| step | who | what |
|---|---|---|
| **survey** | `scout` | finds and ranks work; refills the backlog when it empties |
| **select** | lead | takes the highest-scoring ready item |
| **plan** | `planner` | reads what exists, hunts for reuse, writes the smallest correct plan |
| **plan-review** | `reviewer` | approve · revise · split · drop — before a line is written |
| **build** | `implementer` | executes the approved plan, runs the project's own checks |
| **review** | `reviewer` | correctness, regression, reuse, altitude, honesty — against the real diff |
| **verify** | `assessor` | fresh eyes, evidence ledger, real browser for UI |
| **commit** | lead | one local commit, one journal line, next item |

Reviewer **and** assessor must both return `pass`. Anything else revises, and after two rounds the item is reverted — never patched over.

---

## ♾️ Why It Never Runs Out Of Work

When sweep mode finds nothing worth doing, the scout steps back from the code and looks at the *product*. It builds a list of the app's real domains — the checkout flow, the settings page, the CLI, the auth layer — and rotates a lens across them:

**correctness → UI/UX → visual polish → real-user flows → performance → accessibility → security → DX → feature gaps**

A persistent `swept` map of domain × lens pairs means it never covers the same ground twice, so the loop moves forward instead of circling.

**It will not manufacture churn.** Every candidate is scored `value + confidence − effort`, and anything under 6 is dropped. A domain that yields nothing above the floor is healthy — the scout advances the rotation rather than refactoring good code to look busy.

If `cleric`, `seer` or `scout` are installed, the scout dispatches to them for their specialisms instead of duplicating them.

---

## 🎛️ Flags — all default OFF

| flag | default behaviour | with the flag |
|---|---|---|
| `--dry-run` | executes for real | previews only — survey + top plan, no writes, no commit |
| `--branch` | commits to the current branch | a local branch per item |
| `--merge-dev` | leaves integration to you | merges verified items into `dev` |
| `--ask` | **never asks you anything** | may ask when genuinely blocked |
| `--max-cycles=N` | first run 5, then unlimited | stops after N items (`0` = unlimited) |
| `--max-hours=N` | first run 5 items | stops after N hours (`0` = unlimited) |
| `--unlimited` | first run 5, then unlimited | removes the first-run cap |

The **first run in a repo is capped at 5 items** and then stands down, so a newcomer can review before trusting it longer; later runs default to unlimited. Any explicit `--max-*` or `--unlimited` overrides this.

There is no `--push`. Pushing is blocked for the entire run.

---

## 🌙 Overnight

The in-session loop keeps its lead thin, but context still grows. For a genuinely unbounded run:

```bash
plugins/ranger/scripts/ranger-run.sh "make the dashboard genuinely good"
```

Same agents, same `.ranger/` state, but each cycle is a fresh `claude -p` process — nothing accumulates. `/ranger:stop` from any session ends it.

> [!WARNING]
> **Run unattended mode in a sandbox.** Because no human is present to answer permission prompts, Ranger runs with permissions bypassed — the `ranger-run.sh` runner and every agent it spawns execute tools without asking. The `PreToolUse` hook hard-blocks `git push`, remote mutation and PR creation, and that block holds even in bypass mode — but **only git is guarded. Everything else runs unprompted**: file writes, shell commands, network calls. That is the cost of an unattended loop, not a defect, and it is standard for this class of tool.
>
> So run overnight/headless mode somewhere a bad command can't hurt you: a container or devcontainer, a VM, or a throwaway clone of the repo. Do **not** point unattended mode at a machine you care about and walk away. The in-session `/ranger:run` you watch is lower-risk because you are right there — but it bypasses prompts too.

---

## 🛡️ Guardrails

| risk | guard |
|---|---|
| publishing unattended | `PreToolUse` hook denies `git push`, remote mutation, `gh pr create` — always, even under bypassed permissions |
| everything that isn't git | **not guarded** — permissions are bypassed for unattended operation; run in a sandbox (see Overnight above) |
| scope creep | an item past ~12 files / ~600 lines unplanned is stashed and split |
| grinding on the impossible | 3 cycles with no commit → the item is quarantined, rotation advances |
| a bad change compounding | revert, don't pile on — one commit per item, one `git revert` away |
| conflicts | a conflicting merge is aborted and left on its branch, never resolved unattended |
| interactive deadlock | preflight refuses to start unless `warden`'s strict gates are off |
| trapping other sessions | both hooks are session-scoped and fail open |

---

## 📁 Where State Lives

```
.ranger/
  active-run.json          the marker that arms both hooks — {} when idle
  runs/<run-id>/
    state.json             status, phase, cycle, flags, domain rotation
    backlog.json           ranked items: ready / in_flight / done / quarantined
    journal.md             one line per shipped item, with sha
    items/<item-id>/       plan.md · build.md · verify.md · screenshots
```

All of it is on disk, not in the context window. That is why a compaction mid-run is survivable, and why `/ranger:run` picks up exactly where a stopped run left off.

---

## ⚠️ Honest Caveats

An unbounded run consumes tokens for as long as it runs. Watch the first few cycles before you trust it overnight — the attended-to-unattended transition is the whole skill. `--max-hours` exists even though it defaults to off; use it the first night.

Unattended mode runs with permissions bypassed, so only `git push` is genuinely blocked — everything else runs without asking. Run it in a sandbox, not on a machine you care about. See **Overnight** above.

Ranger is deliberately conservative about what counts as work. If you want him building features rather than sweeping domains, put that in the brief — the brief biases the scout's ranking.

---

<div align="center">

**Sage draws it. Smith builds it. Ranger keeps the crew working.**

</div>
