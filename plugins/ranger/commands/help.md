---
description: "Explain how Ranger works and what the flags do"
hide-from-slash-command-tool: "true"
---

# Ranger Help

Explain the following to the user, in your own words and compactly.

## What Ranger is

The foreman who never leaves the site. You give him one brief and walk away; he runs a senior-engineering loop that never stops and never runs out of work.

He is a **thin lead** — he reads state files and spawns agents, and never opens a source file himself. That is what lets a run go for hours: every agent gets a fresh context, and the lead's own window stays small.

## The cycle

`survey → select → plan → plan-review → build → review → verify → commit`

Plan review comes before implementation on purpose: a rejected plan costs one agent, a bad implementation costs five. Verification is fresh-eyes — the assessor never sees the plan, only the acceptance criteria and the code. UI items get driven through a real browser as a user would.

One item, one local commit. So any single change is one `git revert` away.

## Why it never runs out of work

An empty backlog is a survey trigger, not an exit. When maintenance work is exhausted the scout steps back, enumerates the app's domains, and rotates through them with a persistent pointer so it never sweeps the same ground twice: correctness → UI/UX and visual polish → real-user flows → performance → accessibility → security → DX → feature gaps.

It will not invent churn to look busy. If a domain is genuinely healthy the scout advances the rotation rather than refactoring good code for its own sake.

If `cleric`, `seer` or `scout` are installed, the scout uses them for their specialisms instead of duplicating them.

## Commands

- `/ranger:run <brief> [flags]` — start. One prompt, then walk away.
- `/ranger:stop` — down tools. The only clean exit.
- `/ranger:status` — what he's on right now. Read-only, safe mid-run.
- `/ranger:help` — this.

## Flags — all default OFF

| flag | default | with the flag |
|---|---|---|
| *(none)* | commits locally to the **current branch** | — |
| `--branch` | one branch for everything | a local branch per item |
| `--merge-dev` | leaves integration to you | merges verified items into `dev` |
| `--ask` | **never asks you anything** | may ask when genuinely blocked |
| `--max-cycles=N` | unlimited | stops after N items |
| `--max-hours=N` | unlimited | stops after N hours |

**`git push` is blocked for the entire run and no flag enables it.** A `PreToolUse` hook denies pushes, remote mutation and PR creation outright — instructions are a request, a hook is a guarantee.

## Overnight

```bash
~/.claude/plugins/.../ranger/scripts/ranger-run.sh "make the dashboard genuinely good"
```

Same agents, same state files, but each cycle is a fresh `claude -p` process — nothing accumulates, so it runs indefinitely. `/ranger:stop` from any session ends it.

**Run unattended mode in a sandbox.** With no human to answer permission prompts, Ranger runs with permissions bypassed — the runner and every agent execute tools without asking. `git push`, remote mutation and PR creation are hard-blocked even in that mode, but **only git is guarded — everything else (file writes, shell, network) runs unprompted.** That is the cost of an unattended loop, not a defect. Run overnight/headless mode in a container, VM, or throwaway clone — never on a machine you care about while you walk away.

## Guardrails

- **Blast radius** — an item touching more than ~12 files or ~600 lines unplanned is stashed and split, not merged.
- **Stalls** — three cycles with no commit and the item is quarantined; he moves to different work rather than grinding.
- **Revert, don't pile on** — a rejected change is reverted, never patched over.
- **Conflicts are never resolved unattended** — a conflicting merge is aborted and left on its branch.

## Honest caveats

An unbounded run consumes tokens for as long as it runs. Watch the first few cycles before trusting it overnight — that attended-to-unattended transition is the whole game. And `--max-hours` exists even though it defaults to off; use it the first night.

Unattended mode runs with permissions bypassed — only `git push` is genuinely blocked, everything else runs without asking. Run it in a sandbox, not on a machine you care about.
