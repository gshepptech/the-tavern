# tinker

tinker builds a spec into code with as few agents as the job allows. You run `/tinker:build <spec>`; it checks the
environment, builds with one builder, has code run every check and one spec-checker read the spec against the code,
fixes what they found in one batch, and writes a report with a verdict and evidence for every requirement.

It is a cut-down copy of [tinker](../tinker/README.md). The target is about an hour per feature and a score of 35-40 of
50 on the benchmark below, with a small, counted number of agent calls.

## Use

```
/tinker:build docs/specs/metrics/spec.md
/tinker:build spec.md --max-rounds 1
/tinker:build --resume metrics-20261016-101500
```

| Flag | Default | Meaning |
|---|---|---|
| `--max-rounds N` | 2 | Fix rounds before what remains goes to the report. 0 reports without fixing. |
| `--max-agents N` | 40 | Hard cap on agent calls. The last call is kept for the report, so a capped run still reports. |
| `--resume RUN` | none | Continue a run from its last completed step, on its `tinker/<run>` branch. |

You need a git repository with a clean working tree, `python3`, and the project's own toolchain. tinker works on a new
branch, `tinker/<run>`, commits there and never pushes. Everything else it writes goes to `tinker-archive/<run>/`,
which ignores itself in git.

## Why it is this small

One feature (benchmark P1.1, supervisor `/metrics`) was built from the same sealed spec several ways and reviewed blind.
The reviews are in tinker's [`docs/research/`](../tinker/docs/research/); the tinker row is from its benchmark run.

| Build | Score of 50 | Time | Cost |
|---|---|---|---|
| the earlier build plugin | 35-41 | 2h42m | |
| plain Claude Code, one prompt | 33 | 30m | one agent |
| tinker | 36 | about 4h+ | hit the account usage limit 5 times: about 28 QA agent reports, per-slice QA, mutation testing, repeated live-cluster runs |

Reviewer variance is about 6 points, so tinker's extra machinery bought no score anyone can measure, at eight times
plain Claude's time. Plain Claude lost its points on exactly two things
([`benchmark-old-vs-plain-claude.md`](../tinker/docs/research/benchmark-old-vs-plain-claude.md), X is plain Claude):

> X's integration suite cannot pass. It panics on a zero-value `expfmt.TextParser`, and with that fixed it still fails
> on two of its own test bugs.

> X has one confirmed metric bug that ships: `node_cert_days_until_expiry` reports kubelet certificates that have
> already been replaced, under names that change on every rotation, and it never deletes a series.

The first is a run it never looked at: plain Claude finished before its own suite had run. The second is a domain bug
that only the earlier build plugin's spec-to-code PROVE reviewer caught. So tinker is plain Claude's single builder plus exactly
two things aimed at those two losses: the integration check run to completion and read (by the builder, and again by
code), and one PROVE spec-checker.

## The flow

| Step | What happens | Done by |
|---|---|---|
| 1. Preflight | sage's seal (broken stops, unsealed warns), clean tree, the spec indexed by requirement ID, build/lint/test commands from marker files, base commit and run branch. The spec's integration or end-to-end check is named from the spec and the repository's targets (Makefile, magefile, package.json, justfile). Code then proves it can start here: its runner on PATH, `docker info` when its definition uses containers, a dry start (`make -n`, `mage -l`, `go vet`, `pytest --collect-only`) and the build at the base commit. A failure stops the run with the command and its output. | code; one low-effort finder agent only when code cannot name the check |
| 2. Plan | Code measures the spec against tinker's S4 budget: the existing files it names, their lines, and a new-code estimate per requirement. If it fits, one builder and no planner. If not, one planner splits it by tinker's S1-S10 rules (tinker's planner text, `prompts/planner.md`), and code checks the plan and writes each slice's brief from the spec verbatim. One revision, then the run stops. | code; planner only when over budget |
| 3. Build | One Opus builder per slice (one for a spec that fits), test-first. A single builder gets the whole spec verbatim. It must run the integration check to completion and read its result before reporting, and must not put requirement IDs in production code. | builder |
| 4. Verify | Side by side. **Code:** every change committed, no requirement IDs in production code, slice ownership in a split, build, lint and the full unit suite with no failure the base did not have (failing test names compared), and the integration check (reused if the builder already ran it at HEAD). **One spec-checker:** the earlier build plugin's PROVE method verbatim, spec before code, every gap in one pass with the spec text and file:line, read-only probes allowed. | code + spec-checker |
| 5. Fix | One fixer per slice (one for a single build) gets every failure and gap in one batch. A behavioural gap's fix needs a test that fails before the fix and passes after, which code re-runs in a checkout of the pre-fix commit. Then code re-runs step 4a in full, and the spec-checker re-checks only the gaps it reported. Hard stop after `--max-rounds`. | fixer, then code + spec-checker |
| 6. Report | `report.md`: a verdict per requirement with evidence, the gaps fixed and still open, the failures left, the integration result, timings per step and the agent calls by kind. | code |

## Agent calls

A clerk is a low-effort agent that runs one `tinker` command and copies its JSON line back, because a Workflow script
has no filesystem. Clerks count as agent calls.

| Single-builder run | Calls |
|---|---|
| Best case: nothing found in round 1 | 5: init clerk, builder, verify clerk, spec-checker, report clerk |
| Code could not name the integration check | +1 finder |
| Worst case at `--max-rounds 2` | 12: init, finder, builder, 3 x (verify + spec-checker), 2 fixers, report |
| Over budget, but the planner keeps one builder | +1 or +2 planner calls |

A split adds one builder and, per fix round, at most one fixer per slice. A re-check round with no open gaps skips
the spec-checker. tinker's best case for a single builder was 13 calls, before any validator or fix round.

## What was taken out of tinker, and why

| tinker piece | Why tinker drops it |
|---|---|
| Contract agent (frozen done-checklist with an oracle per requirement) and its gate | An agent and a revision loop on every run. Neither of plain Claude's two losses was a missing checklist item, and the PROVE checker already forms its expectations from the spec before reading code. |
| Probe agent | Code detects the check and runs its prerequisites itself. An agent is called only when detection fails. |
| Run-it verifier agent | Plain Claude's suite failure is a fact an exit code shows. Code runs the integration check and records it; the builder must run it and read it. |
| Test-strength agent and mutation testing | In the plain-Claude review both builds killed all 12 requested mutations with unit tests, so mutation testing did not separate the builds, and it was a large part of tinker's cost. |
| Refute-first validator per finding | One agent per finding (about 28 QA reports in tinker's run). The spec-checker must cite the spec text and the file:line for every gap instead, and the fixer may dispute one. |
| Per-slice QA beside the whole-feature pass | One spec-checker over the whole feature, once per round. |
| Builder retry after a rejected acceptance | A rejected build's problems are failures in the round-1 batch; the fixer takes them. |
| Frozen tests and QA test commits | No QA agent writes tests. Pre-existing tests stay off limits by the builder's and fixer's rules. |
| `--url` and browser checks | They belonged to the run-it verifier. |
| The research copies | tinker's [`docs/research/`](../tinker/docs/research/) is the source; tinker links to it. |

## What is code and what is an agent

| Command | What it decides |
|---|---|
| `args` | the flags and the run name |
| `init` / `resume` | seal, clean tree, run dir, branch, spec index, commands, the S4 measure, integration detection and preflight / where a run left off |
| `preflight` | the integration check's needs, its dry start, the base build (for the finder's answer, and on resume) |
| `plan` | the planner's plan obeys S1-S10 and S4; writes the slice briefs |
| `commit --as <actor>` | how builders and fixers commit; owned files only in a split |
| `integration` | runs the integration check and records its exit code against HEAD |
| `verify --round N` | the round's code check, and fail-before/pass-after for the previous round's fixes |
| `report` | `report.md` and `report.json` |

| Agent | Role | Source of its method |
|---|---|---|
| `builder` | builds the spec or a slice, test-first, runs the integration check (Opus) | tinker's builder, ImpossibleBench prompt D |
| `spec-checker` | spec-to-code, spec before code, assumes the code is broken | the earlier build plugin PROVE (`smith/skills/prove/SKILL.md`, `agents/assayer.md`), verbatim as tinker quoted it |
| `fixer` | every failure and gap in one pass, fail-before/pass-after tests (Opus) | tinker's fixer, Agentless reproduction tests |

The planner and the finder are general-purpose agents: the planner reads `prompts/planner.md`, the finder gets a short
prompt in the script.

## Run directory

```
tinker-archive/<run>/
  state.json            steps done with timestamps, plan, commits per actor, round bases, agent calls
  spec.md               the spec as built
  spec-index.json       every requirement ID and its verbatim clause
  plan.json, slices/    the planner's plan and the slice briefs (split builds only)
  checks/verify-r<N>.json   each round's code check
  checks/spec-r<N>.json     the spec-checker's verdicts and gaps (round 1) or re-checks (later rounds)
  checks/integration-latest.json, checks/<hash>.json   the integration record and cached command results
  fixes/r<N>-<slice>.json   each fixer's report
  report.md, report.json
```

## Tests

```
cd plugins/tinker && uv run --with pytest pytest -q tests
```

`tests/workflow_harness.mjs` (adapted from tinker's) runs `workflows/build.js` with scripted agents and command
results through every branch: single and split, a plan refused then revised or never fixed, a preflight stop, the
finder, verify then fix then re-verify, the round cap, the agent cap, and resuming at each stage. The helpers are
tested against real git repositories in temporary directories.

## Limits

- **Not yet run end to end with real agents.** The harness tests the routing and the Python tests test the helpers.
  Whether tinker reaches 35-40 of 50 in about an hour is untested.
- **The single-or-split decision uses a proxy.** Code cannot know a build's new lines before it is planned, so it
  estimates 25 new lines per requirement ID (`gates.NEW_LOC_PER_REQUIREMENT`), and counts only the paths the spec
  names. Both are choices, not measurements. A spec that names many files goes to the planner even when one builder
  could carry it.
- **Integration detection is heuristic.** It reads backticked commands on spec lines that mention integration,
  end-to-end, acceptance or smoke checks, and target names with those words. Docker is required only when the
  target's definition, or the files under the command's paths, mention containers.
- **No validator.** A wrong gap goes straight to a fixer. The fixer can dispute it, and the report shows the dispute.
- **Parallel slices share one working tree**, as in tinker.
- **Failure names are parsed from output** for Go, pytest, Jest/Vitest, cargo, Maven/Gradle, .NET and compiler-style
  errors; another runner's failures are compared by exit code only.
