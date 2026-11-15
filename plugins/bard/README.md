# Bard

**A UX review of your running app, done by using it: named personas, a real browser, and a finding you can reproduce
for everything that got in their way.**

[![version](https://img.shields.io/badge/version-1.0.0-1E88E5?style=flat-square)](.claude-plugin/plugin.json)
[![license](https://img.shields.io/badge/license-Apache--2.0-4C9A2A?style=flat-square)](../../LICENSE)
[![python](https://img.shields.io/badge/python-3.10%2B-3776AB?style=flat-square)](scripts/bard.py)

## What it does

Reading a UI's source tells you what it is meant to do. Using it tells you what it does. `/bard:run <url>` opens the
running app in a real browser through Playwright MCP and uses it as several people would: someone who has never seen
it, a daily power user, someone on a keyboard only, someone on a phone. Each persona tries the tasks they came for in
one area of the product, and every defect they meet is screenshotted on the spot. The console and network are read
after every task, so a request that fails behind a screen that looks fine is caught too.

The output is a ranked report. Every finding has the page, steps to reproduce, what was expected and what happened,
a screenshot, a severity and a suggested fix. A small validator refuses any finding that lacks one of those, so the
report is a list of things to fix, not a list of impressions.

## Features

- **Personas, not checklists.** Five built-in personas with their own jobs, constraints and viewport, or your own
  with `--personas "Clinic admin: books for three doctors at once"`.
- **Seven lenses.** Task completion, clarity of copy, feedback and errors, empty and loading states, accessibility
  basics, responsive layout, and silent failures in the console and network.
- **Evidence for everything.** Each finding carries a screenshot copied into the run directory, and the console
  lines or failed requests behind it.
- **Context stays small.** Each persona-in-area slice runs in its own agent, so browser snapshots never reach the
  main conversation. Only short summaries come back.
- **Merged and ranked.** A synthesizer merges the same defect seen by several personas, keeps every source, and
  ranks by severity, then by how many personas it hit.
- **Checked in code.** Severity from a fixed set, reproduction steps present, screenshots that exist, rank order, no
  dropped or double-counted slice finding, every planned slice accounted for.

## Quick start

```bash
claude plugin marketplace add gshepptech/the-tavern
claude plugin install bard@the-tavern
claude mcp add playwright -- npx @playwright/mcp@latest
```

Restart Claude Code so the browser tools load, start your app, then:

```
/bard:run http://localhost:3000
```

You need `python3` and Node.js (for the Playwright MCP server). Point bard at a development or staging instance:
personas fill in forms and submit them with obviously fake data unless you pass `--read-only`. They never pay, send
messages to real people or delete anything they did not create.

## How it works

```
init + preflight (code)          the URL answers; the browser tools are loaded
      |
map (one driver)                 up to six areas a user comes for, and what the product promises
      |
plan (code)                      every persona x area, ordered so a cap still covers all of both
      |
slices (one driver each, in turn)
      persona tries 2-3 tasks -> works 7 lenses -> screenshots each defect
      -> reads console + network -> writes slices/<id>.json -> validated in code
      |
synthesize (one agent)           merge duplicates, rank, write report.json -> validated in code
      |
render (code)                    report.md
```

Slices run one at a time because the Playwright MCP server drives a single browser.

| Severity | Meaning |
|---|---|
| `blocker` | The persona cannot complete a core task, or data is lost or wrong. |
| `major` | The task gets done only with real difficulty, a workaround, or luck. |
| `minor` | Friction or confusion that slows the persona down. |
| `polish` | Cosmetic or wording issues that do not affect the task. |

| Persona | Viewport | What they test |
|---|---|---|
| `first-time` | 1280x800 | Whether the product explains itself and the main task works without help |
| `power-user` | 1440x900 | Repeated work: extra clicks, lost state, slow responses, settings that do not stick |
| `keyboard-only` | 1280x800 | Focus visibility, tab order, dialogs that trap and return focus; never clicks |
| `mobile` | 390x844 | Tap targets, horizontal scroll, content hidden behind fixed bars |
| `low-vision` | 640x400 | Reflow at 200% zoom (as a half-size viewport), contrast, meaning not carried by colour |

## Usage

```
/bard:run <url> [--personas LIST] [--areas LIST] [--max-slices N] [--read-only] [--login TEXT]
/bard:help
```

| Flag | Default | Meaning |
|---|---|---|
| `--personas LIST` | `first-time,power-user,keyboard-only,mobile` | Built-in keys or `Name: description` entries, comma separated. |
| `--areas LIST` | mapped | `Name=/path` entries, comma separated. Skips the map step. |
| `--max-slices N` | 12 | The most persona-in-area slices to run, 1 to 40. |
| `--read-only` | off | Fill forms but never submit anything that creates or changes data. |
| `--login TEXT` | none | How to sign in, for example a seeded development account. Without it, a slice behind a login is reported as blocked. |

Each run writes to `.bard/runs/<timestamp>-<host>/`, which git ignores:

```
run.json, plan.json      the arguments, personas, areas and slices
slices/<id>.json         one persona in one area: tasks attempted with outcomes, findings
screenshots/             every screenshot a finding cites
report.json, report.md   the merged, ranked report
```

## Development

```bash
cd plugins/bard
uv run --with pytest python -m pytest -q
```

`scripts/bard.py` (arguments, personas, the slice plan) and `scripts/report.py` (the slice and report validator and
the renderer) are Python standard library only. The tests run them against a fixture run directory with slice files
and screenshots on disk.

## License

Apache-2.0. See [LICENSE](../../LICENSE).
