---
description: Write the planned documentation pages, every claim anchored to a file:line or a command that was run
argument-hint: [page-path ...]
---

You are writing documentation pages from the agreed plan in `.scribe/plan.md`. If the file does not exist, tell the user
to run `/scribe:plan` first and stop.

`$ARGUMENTS` lists the page paths to write. Empty means every page in the plan that does not exist yet, plus every
page the plan marks for rewrite.

The plugin root is `${CLAUDE_PLUGIN_ROOT}`. The gate script is `${CLAUDE_PLUGIN_ROOT}/scripts/scribe_check.py`.

## 1. Write

For each page, spawn one agent with `subagent_type: "scribe:writer"`. Pages are independent, so spawn them in one
message and let them run at the same time. Give each writer:

- its page's row from the plan (path, kind, reader, outcome, evidence);
- the survey appendix from the plan;
- the paths of the other planned pages, so it can link to them;
- the plugin root above, so it can run the gate script on its own page.

## 2. Read as a newcomer

When the writers are done, spawn one agent per written page with `subagent_type: "scribe:reader"`, all in one message.
Give each one only the page path and the reader sentence from the plan. Do not give it the plan, the survey or the
writer's report.

For every page where the reader reports a stopping point that blocks the task, send the reader's entries back to a
`scribe:writer` for that page once, with the instruction to fix those points and nothing else. Do not loop further; what
is still open goes in the report.

## 3. Gate

Run the gates over everything written:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/scribe_check.py" docs --repo .
```

(Use the docs root from the plan if it is not `docs`.) Fix any `high` finding directly. If the plan named a site
generator, add the new pages to its nav file.

## 4. Report

Reply with a table of pages written (path, kind, reader verdict), the claims writers left out for lack of evidence,
the reader stopping points still open, and the final gate output. Do not commit.
