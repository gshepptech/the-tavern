---
description: "Continue a Sage spec that stopped part way, from the phase its files show"
argument-hint: "[slug]"
allowed-tools: ["Bash(bash:*)", "Bash(python3:*)", "Bash(ls:*)", "Bash(test:*)", "Bash(date:*)", "Bash(git:*)", "Read", "Write", "Edit", "Glob", "Grep", "Agent", "AskUserQuestion"]
---

# Sage: resume

Slug: $ARGUMENTS

`SAGE` means `bash "${CLAUDE_PLUGIN_ROOT}/scripts/sage"`.

## 1. Find the spec

If no slug was given, list the directories under `sage-specs/` and run `SAGE status sage-specs/<dir>` for each. Show
the unsealed ones with their phase and ask which to continue. If there are none, say so and point at `/sage:plan`.

## 2. Read where it stopped

Run `SAGE status sage-specs/<slug>`. Its `phase` is decided by the files on disk, not by memory:

| phase | meaning | continue at |
|---|---|---|
| `research` | no `research.md` yet | step 1 of `/sage:plan` |
| `interview` | research done, no `spec.md` | step 2: the interview |
| `review` | a draft exists without a passing review of this exact draft | step 3's check, then step 4 |
| `seal` | the current draft has a passing review | step 5 |
| `sealed` | done | nothing; report it as `/sage:plan` step 7 does |

Read `${CLAUDE_PLUGIN_ROOT}/commands/plan.md` and follow it from that step, with the same rules.

When resuming the interview, read `research.md` and every answer already in `interview.md` first. Never ask a question
that a recorded answer settles, and continue numbering from the last A-NNN.

When resuming at `review`, run `SAGE check` first; the draft may have been edited since.

Say one line before you start: the slug, the phase, and what happens next.
