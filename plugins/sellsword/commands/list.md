---
description: "List recent Sellsword runs"
argument-hint: "[--all | --active | --completed]"
allowed-tools: ["Bash(ls:*)", "Bash(cat:*)", "Bash(test:*)", "Bash(head:*)", "Bash(tail:*)", "Read", "Glob"]
---

# Sellsword List

Show recent Sellsword runs from `.sellsword/runs/`.

```
FILTER="$ARGUMENTS"
```

Default filter: show all runs, most recent first.

- `--active` -> only `status` in {initialized, scouting, recon_complete, executing, active} — the last one (`active`) is `/sellsword:goal`'s in-progress marker; `/sellsword:do` runs never use it.
- `--completed` -> only `status` in {completed, goal_met}
- `--all` -> everything including cancelled, capped, blocked, and stuck

## Behavior

1. List `.sellsword/runs/` if it exists. If not, tell the user "No Sellsword runs in this project yet."

2. For each run dir, read `state.json` and extract:
   - `run_id`
   - `intent` (truncate to 80 chars)
   - `status`
   - `phase`
   - `created_at`
   - `completed_at` (if present)

3. Render a table in chat:

```markdown
| run id | status | intent | started | finished |
|---|---|---|---|---|
| sellsword-20260512-143218-a3f9 | ✓ completed | deploy Keycloak to Azure on RHEL | 14:32:18 | 15:47:02 |
| sellsword-20260512-131045-7c1e | ⚠ stuck | get the airgap bundle pulling all… | 13:10:45 | — |
| sellsword-20260512-094500-2bd1 | ↻ executing | rotate the prod DB creds and upd… | 09:45:00 | — |
```

Status icons:
- ✓ completed
- ↻ in-progress (any active phase)
- ⚠ stuck
- ✗ cancelled
- — failed / unknown

4. If there are active runs, remind the user they can resume with `/sellsword:resume <run-id>`.

## Rules

- Read-only. Never modify state.json or run artifacts.
- Sort by `created_at` descending (newest first).
- If a state.json is malformed or unreadable, render the row with `status: ✗ unreadable` rather than failing the whole list.
