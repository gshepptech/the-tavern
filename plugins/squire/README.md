# Squire

*The squire takes a small, well-defined task and sees it through, checking each step.*

**A single-lane build, verify and fix loop for small specs that already say what done means.**

[![version](https://img.shields.io/badge/version-1.0.0-1E88E5?style=flat-square)](.claude-plugin/plugin.json)
[![license](https://img.shields.io/badge/license-Apache--2.0-4C9A2A?style=flat-square)](../../LICENSE)
[![python](https://img.shields.io/badge/python-3.10%2B-3776AB?style=flat-square)](scripts/squire.py)

## What it does

You have a spec with requirement IDs and acceptance criteria, and it is small: a handful of requirements, one
engineer's afternoon. You do not need a planner, slices or a dependency graph. You need it built, checked honestly,
and fixed until it is right. `/squire:build <spec>` does that. One builder writes the change test-first. A verifier that
sees only the spec and the code gives every requirement a verdict with `file:line` evidence and runs the project's
checks. A fixer fixes only what was listed. The loop repeats until nothing is open or three fix rounds are used, and
then Squire writes a report.

The failure Squire is built against is drift: the build that grows a flag nobody asked for, stamps `// R-003` through
the production code, or "fixes" a gap by adding something new. Drift is checked in code every round, and anything the
spec does not need comes back as a gap to remove.

## Features

- **No planning step.** The spec is indexed in code and handed to one builder. A clean first round is five agent
  calls.
- **Spec-only verifier.** The verifier gets the spec, the requirement index and the diff. It never sees the builder's
  or fixer's notes, so it cannot be talked into a verdict.
- **Verdicts are checked in code.** One verdict per requirement from a fixed set (MET, PARTIAL, MISSING, WRONG). MET
  must cite a `path:line` that exists at HEAD; anything else must say why. A file that breaks the contract is sent back
  once with the exact errors.
- **Drift is a gap.** Requirement IDs on lines the build added to production code, code no requirement needs, and work
  left uncommitted all go on the fixer's list.
- **Fair checks.** Build, lint and test run once at the base commit, so a test that was already failing is reported
  but not blamed on the build.
- **Bounded.** At most three fix rounds by default, then the report says what is still open. Nothing is pushed or
  merged.

## Squire or Smith

Both build a spec and verify it independently. They are sized for different jobs.

| | Squire | [Smith](../smith/README.md) |
|---|---|---|
| Spec size | small: up to about fifteen requirements | large: many requirements across several areas |
| Planning | none; the spec is the brief | a planner splits the spec into slices with file ownership |
| Builders | one, in one lane | several, in parallel waves |
| Verification | one verifier re-checks every requirement each round | verifiers per slice, with a ledger of evidence |
| Best for | a well-scoped change you could hand to one engineer | a feature big enough to need a plan |

If a spec has more than fifteen requirements, Squire still runs, but says that it may be better split.

## Quick start

```bash
claude plugin marketplace add gshepptech/the-tavern
claude plugin install squire@the-tavern
```

In a git repository whose tracked files are committed:

```
/squire:build docs/specs/csv-export.md
```

You need `python3`, `git` and the project's own toolchain. The engine is a script for Claude Code's Workflow tool, so
your Claude Code version must have Workflow available. Squire works on a new branch, `squire/<run>`, and writes its files
to `squire-runs/<run>/`, which git ignores.

A spec Squire can read defines each requirement in a heading, a list item or a table row:

```markdown
### R-001: Export orders as CSV

`GET /admin/orders.csv?from=&to=` MUST return the orders created in the range.

Acceptance:
- With 3 orders in range and 2 outside it, the response has a header row and exactly 3 data rows.
- The response `Content-Type` is `text/csv; charset=utf-8`.

- **FR-2**: Only admins can export.
  - A request with no session gets 401.
  - A non-admin session gets 403.
```

## How it works

```
index (code) -> build (builder) -> verify (verifier + checks in code) -> gaps (code)
                                       ^                                  |
                                       |------- fix (fixer) <-- open? ----|
                                                                          |
                                                          clean or out of rounds -> report (code)
```

| Step | What happens | Done by |
|---|---|---|
| Index | Refuses a tree with uncommitted tracked changes or a spec with no requirement IDs. Indexes every requirement's text and acceptance criteria. Detects the check commands (Makefile targets, package.json scripts, Go, Cargo, pytest) or takes `--check`, and runs them at the base commit. Creates the `squire/<run>` branch. | code |
| Build | One builder, test-first: a failing test per acceptance criterion, then the code. Commits by file name. | builder |
| Verify | The verifier writes its expectations from the spec, runs `squire check` (the checks, the requirement-ID scan of added lines, uncommitted work), reads the code, and writes one verdict per requirement plus a list of unrequested code. | verifier, code |
| Gaps | Code validates the verifier file and turns it, with the check results, into the round's gap list. | code |
| Fix | One fixer gets the gap list and fixes only those items. Unrequested code and IDs in code are removed, not justified. A gap it believes is wrong is disputed with a quote from the spec, and the next round judges it from scratch. | fixer |
| Report | `report.md`: a verdict per requirement with evidence or reason, other open gaps, the checks at HEAD against the base, and open gaps per round. | code |

The Workflow script has no filesystem, so each code step is a `squire` command that a low-effort clerk agent runs and
copies back. Every decision that can be made in code (what counts as a requirement, whether a citation is real,
whether a check failure is new, what goes on the fixer's list) is made in `scripts/`.

| Run | Agent calls |
|---|---|
| Clean first round | 5: init clerk, builder, verifier, gaps clerk, report clerk |
| Each fix round | +3: fixer, verifier, gaps clerk |
| A refused verifier file | +2: one retry and its gaps clerk |

## Reference

```
/squire:build <spec> [--max-rounds N] [--timeout S] [--check CMD]
/squire:help
```

| Flag | Default | Meaning |
|---|---|---|
| `--max-rounds N` | 3 | Fix rounds before what remains goes to the report. 0 to 5; 0 reports without fixing. |
| `--timeout S` | 300 | Seconds each check command may run. |
| `--check CMD` | detected | A check command to run instead of the detected ones. Repeat for more than one. |

| Result | Meaning |
|---|---|
| `done` | Every requirement MET, no gap open. |
| `done_with_gaps` | The rounds ran out with gaps open; the report lists them. |
| `unverified` | The verifier's file was refused twice, so the last round was not judged. |
| `stopped` | Squire refused to start. Nothing was built. |

Run directory:

```
squire-runs/<run>/
  state.json             base commit, branch, check commands and their result at base
  spec.md, index.json    the spec as built, and every requirement with its acceptance criteria
  verify/check-r<N>.json      the checks, ID scan and uncommitted files at the round's HEAD
  verify/verify-r<N>.json     the verifier's verdicts
  verify/gaps-r<N>.json       the fixer's list for the round
  report.md, report.json
```

## Development

```bash
cd plugins/squire
uv run --with pytest python -m pytest -q
```

The helpers are Python standard library only. The tests build real git repositories in a temporary directory, and the
Workflow script is driven through `tests/workflow_harness.mjs` with scripted agents, which needs `node` on `PATH`.
From the repository root, `python3 .github/scripts/check_js.py` checks that the Workflow script parses.

## License

Apache-2.0. See [LICENSE](../../LICENSE).
