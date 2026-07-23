---
description: Show the Scout plugin commands, skills, and agent
---

The user wants help with the Scout plugin. Reply with exactly this message — verbatim, no additions:

```
Scout — Playwright E2E test authoring + maintenance, driven by Claude

WHAT IT DOES
  Wraps Playwright + Playwright MCP into a slash-command workflow. Claude drives
  a real browser, reads the accessibility tree, writes *.spec.ts files that
  pass, and keeps them passing. Author specs from prompts, generate smoke
  coverage across every route, lock down access control via routes × roles,
  triage failures from trace.zip.

COMMANDS
  /scout:init                  Install Playwright + register MCP + scaffold tests/
  /scout:write <flow>          Claude drives the browser, emits *.spec.ts, runs green
  /scout:crawl [baseURL]       Discover every route → one smoke spec per route
  /scout:matrix                Routes × roles coverage with reused storageState
  /scout:audit [--fix]         Run suite, read trace.zip, triage by root cause
  /scout:record <slug>         Wrap `playwright codegen` for manual recording
  /scout:help                  This message

SKILLS
  scout:author     Selector hygiene, auto-wait discipline, idempotent test design
  scout:diagnose   Trace.zip reading, flaky-test triage, failure taxonomy

SUBAGENT
  scout:spec-writer     Isolated MCP-driven spec authoring. Spawned by /scout:write
                         for multi-step flows. Invoked via Agent tool with
                         subagent_type=scout:spec-writer.

CONFIG
  playwright.config.ts   Scaffolded by /scout:init. baseURL via $BASE_URL env.
  .mcp.json              Playwright MCP entry (headed by default).
  scout.config.json        Roles + login flow for /scout:matrix. Created on first
                         matrix run.
  .auth/                 storageState per role. Gitignored — contains session
                         tokens. Never commit.

TYPICAL FLOW
  1. /scout:init                              (once per project)
     -> restart Claude Code, start the dev server, then continue
  2. /scout:crawl http://localhost:3000       (smoke baseline)
  3. /scout:write "user logs in and adds a todo"   (per-feature specs)
  4. /scout:audit                             (run + triage on each PR)
  5. /scout:matrix                            (when access control matters)

PRINCIPLES
  - getByRole over CSS. Auto-wait over sleep. Idempotent over chained.
  - Observe first, lock assertions second. Especially in /scout:matrix.
  - Trace.zip is the source of truth for failures. Don't guess from messages.
  - Don't commit .auth/.
```

Do not embellish, summarize, or rephrase. The verbatim block IS the help.
