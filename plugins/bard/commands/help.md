---
description: "Explain what bard reviews, how a run works, and its flags"
hide-from-slash-command-tool: "true"
---

# bard help

Explain the following to the user, compactly and in your own words.

## What bard is

An experiential UX review of a running web app. `/bard:run <url>` uses the app in a real browser through Playwright MCP
as named personas, each in one area of the product, and writes a ranked report. Every finding has steps to
reproduce, a screenshot, a severity and a suggested fix. bard reads the screen, not the source, and it never changes
the app's code.

## How a run works

1. **Init and preflight**: the URL must answer, and the Playwright MCP tools must be loaded.
2. **Map**: unless `--areas` is given, one driver reads the app's navigation and picks up to six areas a user comes for,
   plus the promises the product makes about itself.
3. **Plan**, in code: every persona in every area, ordered so a `--max-slices` cap still covers every persona and
   every area.
4. **Slices**, one at a time: a persona driver becomes the persona, attempts two or three tasks, works seven lenses
   (task completion, copy, feedback, empty and loading states, accessibility, responsive layout, silent failures in
   the console and network), screenshots every defect, and writes a slice file. Code checks the file.
5. **Synthesize**: one agent merges duplicates across personas and areas and ranks by severity and reach. Code checks
   the report and renders `report.md`.

## Personas

Built in: `first-time`, `power-user`, `keyboard-only`, `mobile` (390x844) and `low-vision` (200% zoom, as a half-size
viewport). The first four run by default. A custom persona is `name: description`, for example
`--personas "first-time,Clinic admin: books appointments for three doctors at once"`. Descriptions cannot contain
commas.

## Flags

- `--personas LIST`: comma-separated personas (default `first-time,power-user,keyboard-only,mobile`).
- `--areas LIST`: comma-separated `Name=/path` entries; skips the map step.
- `--max-slices N`: the most persona-in-area slices to run (default 12, at most 40).
- `--read-only`: drivers fill forms but never submit anything that creates or changes data.
- `--login TEXT`: how a driver signs in, for example `use the seeded demo account on the login page`.

Severity is one of `blocker`, `major`, `minor`, `polish`. Point bard at a development or staging instance: drivers
create test data unless `--read-only` is set.
