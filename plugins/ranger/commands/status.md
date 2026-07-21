---
description: "Show what Ranger is working on right now"
allowed-tools: ["Bash(cat:*)", "Bash(ls:*)", "Bash(date:*)", "Bash(test:*)", "Bash(tail:*)", "Bash(git log:*)", "Read", "Glob"]
hide-from-slash-command-tool: "true"
---

# Ranger Status

Read-only. Never changes a run.

1. Read `.ranger/active-run.json`. If missing/empty, list the most recent directories under `.ranger/runs/` and report the last run's final status instead.

2. Read `<run_dir>/state.json`, `<run_dir>/backlog.json`, and the last 10 lines of `<run_dir>/journal.md`.

3. Report:

```
**<status>** — <run_id> · cycle <cycle><cap> · <elapsed>
Brief: <brief>
Phase: <phase> · In flight: <item or "—"> · Stalls: <stall_count>
Branch: <current git branch> · flags: <the flags that are on, or "defaults (local commits, current branch, never asks)">

**Last 5 shipped**
<the last five journal lines>

**Next up**
<top 5 ready backlog items: score, title>

**Quarantined**
<items with a blocker note, or "none">

**Domain rotation**
<pointer position, current domain, and which domains have been swept>
```

4. If `status` is `active`, close with: `/ranger:stop to end the run.`
