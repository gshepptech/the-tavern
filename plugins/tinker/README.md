# Tinker

*The tinker builds from the plan with a small kit and a fixed budget.*

**A lean spec-to-code build: one builder, a code check and a spec check, and at most two fix rounds.**

[![version](https://img.shields.io/badge/version-0.1.0-1E88E5?style=flat-square)](.claude-plugin/plugin.json)
[![license](https://img.shields.io/badge/license-Apache--2.0-4C9A2A?style=flat-square)](../../LICENSE)
[![python](https://img.shields.io/badge/python-3.10%2B-3776AB?style=flat-square)](scripts/tinker.py)

## What it does

Tinker builds a spec into code with as few agents as the job allows. You run `/tinker:build <spec>`. It checks the
environment, builds with one builder, has code run every check while one spec-checker reads the spec against the code,
fixes what they found in one batch, and writes a report with a verdict and evidence for every requirement.

A single agent with a good prompt gets most of a feature right. Where it tends to fall short is in two places: it
reports success before its own integration suite has run, and it misses domain bugs that only show in a state the spec
implies (after a rotation, after a restart, while a dependency is down). Tinker adds exactly two things aimed at
those: the integration check is run to completion and read, by the builder and again by code, and a spec-checker
reads the spec before the code and assumes the code is broken.

## Features

- **Code does the bookkeeping.** Preflight, planning checks, commits, verification and the report are Python, not
  agents. The workflow counts and caps every agent call.
- **One builder unless the spec is too big.** A size budget measured from the spec decides; only an over-budget spec
  gets a planner and parallel slices.
- **The integration check must actually run.** Preflight proves it can start here; the builder must run it and read
  the result; code runs it again against HEAD.
- **No new failures.** Build, lint and the full unit suite are compared against the base commit by failing test name,
  so pre-existing failures are not blamed on the build.
- **Spec before code.** The spec-checker forms expectations from the spec alone, then gives each requirement a verdict
  with `file:line` evidence, and flags code the spec does not need.
- **Fixes prove themselves.** A behavioural fix comes with a test that code re-runs against the pre-fix commit: it must
  fail there and pass at HEAD.
- **Resumable.** A stopped run continues from its last completed step on its own branch.

## Quick start

```bash
claude plugin marketplace add gshepptech/the-tavern
claude plugin install tinker@the-tavern
```

In a git repository with a clean working tree:

```
/tinker:build docs/specs/metrics/spec.md
```

You need `python3` and the project's own toolchain. Tinker works on a new branch, `tinker/<run>`, commits there and
never pushes. Everything else it writes goes to `tinker-archive/<run>/`, which ignores itself in git.

## How it works

```
preflight (code) -> plan (code; planner only if over budget) -> build (builder per slice)
      -> verify: code check  +  spec-checker        (side by side)
      -> fix (one fixer per slice, one batch)  -> re-verify  ... at most --max-rounds
      -> report (code)
```

| Step | What happens | Done by |
|---|---|---|
| 1. Preflight | The spec's seal (if [Sage](../sage/README.md) sealed it: broken stops, unsealed warns), clean tree, the spec indexed by requirement ID, build/lint/test commands from marker files, base commit and run branch. The spec's integration or end-to-end check is named from the spec and the repository's targets (Makefile, magefile, package.json, justfile). Code then proves it can start: its runner on PATH, `docker info` when it uses containers, a dry start (`make -n`, `mage -l`, `go vet`, `pytest --collect-only`) and the build at the base commit. A failure stops the run with the command and its output. | code; one low-effort finder agent only when code cannot name the check |
| 2. Plan | Code measures the spec against the S4 budget: the existing files it names, their lines, and a new-code estimate per requirement. If it fits, one builder and no planner. If not, one planner splits it by the S1-S10 rules in [`prompts/planner.md`](prompts/planner.md), and code checks the plan and writes each slice's brief from the spec text. One revision, then the run stops. | code; planner only when over budget |
| 3. Build | One Opus builder per slice (one for a spec that fits), test-first. It must run the integration check to completion and read its result before reporting, and must not put requirement IDs in production code. | builder |
| 4. Verify | Side by side. **Code:** every change committed, no requirement IDs in production code, slice ownership in a split, build, lint and the full unit suite with no failure the base did not have, and the integration check (reused if the builder already ran it at HEAD). **Spec-checker:** spec before code, every gap in one pass with the spec text and `file:line`, read-only probes allowed. | code + spec-checker |
| 5. Fix | One fixer per slice gets every failure and gap in one batch. A behavioural gap's fix needs a test that fails before the fix and passes after, which code re-runs in a checkout of the pre-fix commit. Code then re-runs step 4 in full, and the spec-checker re-checks only the gaps it reported. Hard stop after `--max-rounds`. | fixer, then code + spec-checker |
| 6. Report | `report.md`: a verdict per requirement with evidence, gaps fixed and still open, failures left, the integration result, timings per step and agent calls by kind. | code |

### Agents

| Agent | Role |
|---|---|
| `builder` | builds the spec or a slice, test-first, and runs the integration check (Opus) |
| `spec-checker` | reads the spec, then the code; a verdict per requirement with evidence; assumes the code is broken |
| `fixer` | every failure and gap in one pass, each behavioural fix with a fail-before/pass-after test (Opus) |

The planner and the finder are general-purpose agents: the planner reads `prompts/planner.md`, the finder gets a short
prompt in the script. A clerk is a low-effort agent that runs one `tinker` command and copies its JSON line back,
because a Workflow script has no filesystem. Clerks count as agent calls.

| Single-builder run | Calls |
|---|---|
| Best case: nothing found in round 1 | 5: init clerk, builder, verify clerk, spec-checker, report clerk |
| Code could not name the integration check | +1 finder |
| Worst case at `--max-rounds 2` | 12: init, finder, builder, 3 x (verify + spec-checker), 2 fixers, report |
| Over budget, but the planner keeps one builder | +1 or +2 planner calls |

A split adds one builder and, per fix round, at most one fixer per slice. A re-check round with no open gaps skips the
spec-checker.

## Reference

| Flag | Default | Meaning |
|---|---|---|
| `--max-rounds N` | 2 | Fix rounds before what remains goes to the report. 0 reports without fixing. |
| `--max-agents N` | 40 | Hard cap on agent calls. The last call is kept for the report, so a capped run still reports. |
| `--resume RUN` | none | Continue a run from its last completed step, on its `tinker/<run>` branch. |

| `tinker` command | What it decides |
|---|---|
| `args` | the flags and the run name |
| `init` / `resume` | seal, clean tree, run dir, branch, spec index, commands, the S4 measure, integration detection and preflight / where a run left off |
| `preflight` | the integration check's needs, its dry start, the base build |
| `plan` | the planner's plan obeys S1-S10 and S4; writes the slice briefs |
| `commit --as <actor>` | how builders and fixers commit; owned files only in a split |
| `integration` | runs the integration check and records its exit code against HEAD |
| `verify --round N` | the round's code check, and fail-before/pass-after for the previous round's fixes |
| `report` | `report.md` and `report.json` |

Run directory:

```
tinker-archive/<run>/
  state.json            steps done with timestamps, plan, commits per actor, round bases, agent calls
  spec.md               the spec as built
  spec-index.json       every requirement ID and the clause that defines it
  plan.json, slices/    the planner's plan and the slice briefs (split builds only)
  checks/verify-r<N>.json   each round's code check
  checks/spec-r<N>.json     the spec-checker's verdicts and gaps (round 1) or re-checks (later rounds)
  checks/integration-latest.json, checks/<hash>.json   the integration record and cached command results
  fixes/r<N>-<slice>.json   each fixer's report
  report.md, report.json
```

### Limits

- **The single-or-split decision uses a proxy.** Code cannot know a build's new lines before it is planned, so it
  estimates 25 new lines per requirement ID (`gates.NEW_LOC_PER_REQUIREMENT`) and counts only the paths the spec
  names. A spec that names many files goes to the planner even when one builder could carry it.
- **Integration detection is heuristic.** It reads backticked commands on spec lines that mention integration,
  end-to-end, acceptance or smoke checks, and target names with those words.
- **No validator between checker and fixer.** A wrong gap goes straight to a fixer. The fixer can dispute it, and the
  report shows the dispute.
- **Parallel slices share one working tree.**
- **Failure names are parsed from output** for Go, pytest, Jest/Vitest, cargo, Maven/Gradle, .NET and compiler-style
  errors; another runner's failures are compared by exit code only.

## Development

```bash
cd plugins/tinker
uv run --with pytest python -m pytest -q tests
```

`tests/workflow_harness.mjs` runs `workflows/build.js` with scripted agents and command results through every branch:
single and split, a plan refused then revised or never fixed, a preflight stop, the finder, verify then fix then
re-verify, the round cap, the agent cap, and resuming at each stage. The helpers are tested against real git
repositories in temporary directories.

## License

Apache-2.0. See [LICENSE](../../LICENSE).
