<div align="center">

<img src="cleric.svg" alt="Cleric, one of the regulars at The Tavern" width="100%"/>

# Cleric

*The cleric tends to the codebase carefully: it clears what is dead and leaves alone anything it cannot prove is safe to touch.*

**A careful, low-risk codebase cleanup pass across 7 focused tracks: dedup, type consolidation, dead code, circular deps, type strengthening, error handling, and deprecated code and AI-slop removal.**

[![Version](https://img.shields.io/badge/version-0.2.1-558B2F?style=flat-square)](.claude-plugin/plugin.json)
[![License](https://img.shields.io/badge/License-Apache--2.0-558B2F?style=flat-square)](../../LICENSE)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-plugin-8E44AD?style=flat-square)](https://docs.claude.com/en/docs/claude-code)

</div>

> [!NOTE]
> **Cleric is standalone.** Install it on its own, point it at any repo, and it works by itself. No other plugin from The Tavern is required.

## What it does

Most cleanup tools merge anything that looks similar, delete anything a linter flags, and trust whatever a comment claims. Cleric does the opposite. It finds a lot, but it only touches what it can prove is safe, and it writes down everything it decided *not* to touch and why.

Every candidate is ranked by confidence. Only the HIGH-confidence, LOW-risk slice is ever applied without you. Each applied batch runs your type check, tests and lint, is reverted automatically if any of them fail, and is its own commit, so any change is one `git revert` away.

| Reach for it when | Don't bother when |
|---|---|
| A codebase has been through months of AI-assisted change and nobody is sure what's still load-bearing | The repo has no automated checks at all (no tests, no type check, no lint). Batches are kept or reverted on those checks, so with nothing to run the only safety net left is `git revert` |
| You're about to refactor an area and want the cruft out of the way first | You want a specific known change made. Cleric finds work; it doesn't take instructions about what to fix |
| A release is close and you want the dead exports and swallowed errors gone before it ships | You're on a deadline. Reviewing MEDIUM and LOW findings properly takes real time, and those are where most of the value sits |
| You want a written record of what was *not* touched and why, not just a diff | The tree is dirty or it isn't a git repo. Cleric refuses to start in either case |

## Features

- **Seven tracks.** Deduplication, type consolidation, dead code, circular dependencies, type strengthening, error handling, and deprecated code plus AI artifacts.
- **Call sites over comments.** Behaviour and real callers are the evidence. A comment's claim about what code does never counts.
- **Strict equivalence for dedup.** Only byte- or AST-equivalent, same-signature duplicates with verified callers are merged. Code that merely looks the same is left alone.
- **Dead code is checked, not trusted.** Every static-analysis hit is checked against dynamic imports, config references, framework conventions and codegen before it counts as dead.
- **A confidence gate.** HIGH applies under `--apply`; MEDIUM, LOW and UNCERTAIN are surfaced for you to decide.
- **One commit per batch.** Each batch runs the full check matrix and is reverted automatically on failure.
- **Dry run by default.** A plain `/cleric:run` writes assessments and changes nothing.

## Quick start

```bash
claude plugin marketplace add gshepptech/the-tavern
claude plugin install cleric@the-tavern
```

Then run a dry-run pass. It changes nothing and only reports:

```bash
/cleric:run
```

Everything lives under the `/cleric:*` namespace.

## How it works

Each track inspects read-only, writes its own assessment, and ranks every candidate by confidence before anything is touched.

| # | Track | Looks for |
|---|---|---|
| 1 | **dedup** | Repeated logic, copy-pasted functions, redundant abstractions |
| 2 | **type-consolidate** | Type definitions scattered across files, especially ones that have quietly drifted |
| 3 | **dead-code** | Unused exports, unreferenced functions, orphaned files |
| 4 | **circular-deps** | Import cycles that actually hurt maintainability, testability, or correctness |
| 5 | **type-strengthen** | `any` / `unknown` / `interface{}` / weak generics with a provable real type |
| 6 | **error-cleanup** | try/catch and equivalents that silently swallow or hide failure |
| 7 | **deprecated-slop** | Clearly obsolete legacy code, plus AI artifacts (stubs, edit-narration comments) |

```
/cleric:run
   |
   +- 7 tracks inspect in parallel (read-only) -> tracks/<name>/assessment.md
   |
   +- [checkpoint: apply HIGH only / review MEDIUM first / cancel]   (--apply)
   |
   +- tracks apply HIGH batches in a fixed order, one commit per batch
   |     each batch: type check + tests + lint -> keep, or revert and downgrade
   |
   +- reviewer: full check matrix, cross-track conflicts, debrief
```

Tracks apply in a fixed order, chosen to minimize cross-track interference (dedup runs only after dead code is already gone, for example): `deprecated-slop`, `dead-code`, `dedup`, `type-consolidate`, `type-strengthen`, `error-cleanup`, `circular-deps`. A mandatory reviewer pass runs after every apply. It re-runs the full check matrix, scans for cross-track conflicts (did one track merge something another was about to delete?), and writes a consolidated debrief.

<details>
<summary><b>Per-track tooling and rules</b> (click to expand)</summary>

**1. dedup**: Fingerprints functions by normalized signature + AST shape. TS/JS: `jscodeshift --dry-run` or direct reading; Go: `gofmt -d` + `golangci-lint --enable dupl` (or standalone `dupl`); Python: `pylint --enable=duplicate-code` / `pyflakes`. Forbidden from merging across architectural boundaries (domain versus wire format, public versus private API) without approval, and from inventing a new abstraction just to deduplicate.

**2. type-consolidate**: Finds same-named types across files and diffs them *structurally*, not by name. TS: `tsc --listFiles`; Go: `go doc`; Python: class/`@dataclass`/`TypedDict` scans. When two same-named types have actually drifted apart, that's surfaced as a **drift finding**, a possible bug, and never silently merged.

**3. dead-code**: JS/TS: `knip`, `ts-prune`, `depcheck`. Go: `golangci-lint --enable=unused,deadcode,structcheck,varcheck`, `deadcode`, `unused`. Python: `vulture --min-confidence 80`. Every hit is then manually checked against dynamic imports/`require`, config file references, framework convention paths (`pages/`, `controllers/`, `*.stories.tsx`, etc.), codegen markers, and external consumers before it counts as CONFIRMED dead.

**4. circular-deps**: JS/TS: `madge --circular`. Go: `go mod graph`, `go vet` (import cycle detection), a custom AST scan via `go list -deps -json | jq`. Python: `pycycle`, `pylint --enable=cyclic-import`. Rust: `cargo metadata`. Cycles are scored by impact (maintainability, testability, correctness risk). Only P0/P1 cycles are candidates for a fix, and the fix is always extraction to a neutral module, **never** a new abstraction invented to break the cycle.

**5. type-strengthen**: Greps for `: any`, `<any>`, `: unknown`, `: object`/`{}`, `Record<string, any>`, `: Function` (TS/JS); `interface{}` (Go); `Any` (Python), cross-checked with `tsc --noEmit --strict --noImplicitAny` and `mypy --strict`. Every replacement is researched from real call sites, not guessed. `unknown` at legitimate boundaries (raw JSON, external APIs, FFI, dynamic dispatch) is preserved on purpose, and a cast (`x as Foo`) never counts as strengthening.

**6. error-cleanup**: Pattern-based, not tool-based: greps for try/catch, `.catch()`, `if err != nil`, `recover()`, `except`/bare `except:`, `.unwrap()`/`.expect()` (Rust). Classifies each site as a real boundary/recovery/logging/cleanup/user-facing handler (KEEP) or a silent swallow, default-on-error, or context-losing re-throw (REMOVE). Process/async boundaries and cleanup handlers are never auto-removed even if they look like swallows.

**7. deprecated-slop**: Greps for `@deprecated` markers, `// legacy`/`// fallback`/`// for compat` comments, version gates, and feature flags, cross-checked against call sites and git history. Separately hunts AI artifacts: edit-narration comments (`// updated this to...`), AI-voice comments (`// I noticed...`, `// Let me...`), empty TODOs, and not-implemented stubs. A comment with genuine WHY value gets rewritten for a new engineer. It is never fabricated, and never deleted just for being chatty.

</details>

### The confidence gate

Every track ranks each candidate the same way, and only the top rank is applied without you:

| Rank | Meaning | Behaviour |
|---|---|---|
| **HIGH** | Verified safe: every claim checked, not just plausible | Auto-applies under `--apply` or `--auto` |
| **MEDIUM** | Likely safe, but has a real judgement call | Surfaced, needs your explicit approval |
| **LOW** | Risky, or a track deliberately flags "don't do this" | Surfaced with the reason, never touched |
| **UNCERTAIN** | Track couldn't determine it | Surfaced for your decision |

> [!IMPORTANT]
> **Be clear-eyed about what enforces this.** The confidence rank is a judgement the model makes and is then asked to honour. It is prose discipline in the track specs, not a separate program that reads the assessment and refuses. The real protection is that **every applied change is one atomic commit**, applied only when the working tree is clean, with the pre-run SHA recorded so the entire sweep is one `git reset --hard <sha>` away. Trust the undo, not the label. Review the diff of an auto-applied batch the way you would review a colleague's; that is why Cleric commits each batch separately.

### Restraint in practice

Two candidates from the dead-code track, both flagged unused by `knip`/`ts-prune`:

- `helperFn` in `src/util/foo.ts:42`: no dynamic imports, no config references, no codegen markers, not in a convention directory, no external consumers, last touched 286 days ago. HIGH confidence, removed.
- `webhookHandler` in `src/webhooks/stripe.ts:120`: referenced by name in `config/webhooks.yml:14`. Kept. Static analysis alone would have deleted it.

Same signal, two outcomes, because Cleric checks before it deletes.

## Reference

### Commands

| Command | What it does |
|---|---|
| `/cleric:run` | Default `--dry-run`. Inspects all 7 tracks (or `--tracks=...`), writes assessments, changes nothing. |
| `/cleric:run --apply` | Inspects, then stops at a checkpoint: apply HIGH only, review MEDIUM/LOW first, or cancel. |
| `/cleric:run --apply --auto` | Same as above with no checkpoint. Applies HIGH batch by batch immediately, and still only HIGH. |
| `/cleric:apply <run-id>` | Apply the HIGH-confidence changes from a previous dry-run's assessment. |
| `/cleric:status [<run-id>]` | Show recent runs, or the full state of one run. Read-only. |
| `/cleric:help` | Plugin help text. |

`--tracks=dedup,dead-code` (or `--tracks=1,3`) restricts a run to a subset; default is all 7.

### Prerequisites and refusals

> [!WARNING]
> Cleric **refuses to run on a dirty working tree**. Atomic commits are the safety mechanism, so it checks `git status --porcelain` before doing anything and stops if the tree isn't clean. Commit, stash, or branch first.

- A git repository. This is required, with no exceptions.
- A clean working tree at the start of every run.
- Language tooling on `PATH` where relevant. Cleric detects what's installed and adapts. If nothing is detected for a language, it warns and asks whether to proceed with reduced coverage.

**When to run it:** before a release, after a feature merge, or as scheduled maintenance, for example `/cleric:run --auto --tracks=dead-code,deprecated-slop` on a weekly cron.

### What it costs

Each of the seven tracks is its own Opus agent, and the reviewer is an eighth. Roughly:

- **Dry run**: one agent per selected track, all spawned in parallel. Seven agents for a full sweep.
- **Apply run**: the same inspection, plus a second spawn per track that has HIGH-confidence work (sequential, in a fixed order), plus one mandatory reviewer. Up to fifteen agent runs for a full sweep.
- **The bounding flag is `--tracks=`.** `--tracks=dead-code,deprecated-slop` is two agents instead of seven, which suits scheduled maintenance. `--auto` does not reduce cost; it only removes the checkpoint. Cost also scales with repo size, since every track greps the whole tree.

### What gets written

```
your-repo/
├── (your code, with HIGH-confidence cleanups applied)
└── .cleric/
    └── runs/<run-id>/
        ├── state.json                       # phase, status, tracks, tooling
        ├── tooling.json                     # detected language tools
        ├── tracks/<track>/assessment.md     # findings, ranked by confidence
        ├── tracks/<track>/applied.md        # what actually got applied
        ├── summary.md                       # reviewer's cross-track debrief
        └── checks.md                        # final type check/test/lint/build results
```

Every applied batch is one atomic, revertable commit:

```
chore(cleric): remove 2 unused exports

- `legacyHandler` from src/api/handlers.ts (last referenced 2024-08)
- `oldFormatter` from src/util/format.ts (no static or dynamic references)

Verified: npm test + typecheck pass.
```

### Worked examples

The output below is illustrative. The consolidated table, the per-track status lines and the debrief follow the orchestrator's render templates in `commands/run.md`, and the findings follow each track agent's `assessment.md` format. Your counts will differ.

#### 1. Find out what's actually there

You've inherited a TypeScript service that's been through a lot of hands. You want the survey, not the surgery. The default is a dry run, so this changes nothing:

```bash
/cleric:run
```

All seven tracks inspect in parallel, then report:

```text
Cleric run cleric-20260518-101204-b19e. Mode: dry-run. Tracks: all 7. Inspecting in parallel…

**Cleric assessment: cleric-20260518-101204-b19e**

Across 7 tracks, found 138. Of those:
- HIGH (auto-applicable on `--apply`): 41 · MEDIUM (needs your approval): 62
- LOW (flagged, not changing): 29 · UNCERTAIN: 6

**By track:**
| track | HIGH | MEDIUM | LOW | UNCERTAIN | notes |
|---|---|---|---|---|---|
| dedup | 4 | 9 | 3 | 1 | 3 near-duplicate date formatters; 2 pairs look alike but differ at the wire boundary |
| type-consolidate | 2 | 7 | 1 | 0 | 2 drift findings flagged: same-named `Invoice` differs across modules |
| dead-code | 9 | 6 | 11 | 2 | 28 static candidates, 9 verified dead, 11 kept (config refs / framework paths) |
| circular-deps | 1 | 3 | 5 | 0 | 9 cycles found, 1 P0, 3 P1, 5 cosmetic |
| type-strengthen | 14 | 19 | 6 | 2 | 41 weak types, 14 provable from call sites, 6 boundary-correct and kept |
| error-cleanup | 8 | 12 | 2 | 1 | 96 handling sites examined, 8 silent swallows, the rest serve a real boundary |
| deprecated-slop | 3 | 6 | 1 | 0 | 3 deprecated paths removable, 7 groups of edit-narration comments to rewrite |

**Full assessments:** `.cleric/runs/cleric-20260518-101204-b19e/tracks/<track>/assessment.md`
```

Nothing was changed. The LOW column is the interesting one: that's what a less careful tool would have deleted.

**Next:** read `tracks/dead-code/assessment.md` for the eleven it refused to remove, then apply the HIGH slice with `/cleric:apply cleric-20260518-101204-b19e`.

#### 2. Apply a narrow slice, and watch a batch get reverted

You trust the error-handling and type findings and want them in, but not a structural reshuffle. Restrict the run to two tracks and let it apply:

```bash
/cleric:run --apply --tracks=error-cleanup,type-strengthen
```

It inspects, stops at the checkpoint, and on **Apply HIGH-confidence only** starts committing batch by batch:

```text
Applying HIGH-confidence changes across 2 tracks. Atomic commits per batch. Will revert on check failures.

type-strengthen: applied 11 changes, 1 batch reverted (type check failed), checks: pass
error-cleanup:   applied 8 removals, checks: pass
```

<details>
<summary><b>A HIGH-confidence change, before and after</b></summary>

From `tracks/type-strengthen/assessment.md`, the finding that produced one of those commits:

```markdown
### 1. `processOrder(order: any)` -> `processOrder(order: Order)`
- **Location:** `src/checkout/process.ts:42`
- **Research:** 4 call sites, all pass `Order` from `src/types/Order.ts`; tests construct `Order` shapes consistently
- **Why HIGH:** unambiguous; concrete type already exists.
```

Before:

```ts
export async function processOrder(order: any) {
  try {
    return await gateway.charge(order.total, order.currency);
  } catch (e) {}
}
```

After. Two tracks touched this function, one per commit:

```ts
export async function processOrder(order: Order) {
  return await gateway.charge(order.total, order.currency);
}
```

The empty `catch` came out under error-cleanup as a silent swallow. It had no logging and no recovery, and the caller had no way to learn the charge failed. The error now reaches the request handler's existing error boundary. Each track's change is its own commit, one `git revert` away.

The reverted batch is equally real: three type replacements in one commit, one of which rippled into a consumer's signature. The type check failed, so Cleric reverted the whole batch and downgraded all three to UNCERTAIN with the type-checker output attached as evidence.

</details>

Then the mandatory reviewer pass runs and debriefs:

```text
**Cleric completed: cleric-20260518-113355-c704**

**Net change**
- Files: 14
- Lines: +38 / -96
- Commits: 7

**Per track**
- type-strengthen: 11 applied, 3 reverted · error-cleanup: 8 applied, 0 reverted

**Final checks**
- Type check: pass · Tests: pass · Lint: pass · Build: pass

**Cross-track conflicts:** none

**For your review (not auto-applied)**
- MEDIUM across both tracks: 31 items -> `.cleric/runs/.../tracks/*/assessment.md`
- UNCERTAIN flagged for your decision: 3 (the reverted batch)

**To revert everything**
git reset --hard 4f1c8ab
```

**Next:** work through the 31 MEDIUM items yourself, or re-run with `--tracks=` on a single track to keep the review surface small.

### Shared workspace (optional)

The items Cleric deliberately does not apply (MEDIUM, LOW, UNCERTAIN) are the ones every later tool rediscovers from scratch. If a sweep held anything back, Cleric writes one small JSON note to `.questboard/notes/` summarising what was applied, what was not, and pointing at the assessment files. A sweep that held nothing back writes nothing.

Cleric reads nothing from the workspace, and a failed write is dropped silently. The commits and the assessment files under `.cleric/runs/` are the real record either way.

The format is documented in [the .questboard contract](../../docs/questboard-contract.md).

### Pairs well with

Cleric runs on its own. If you have installed other regulars from The Tavern, a couple of pairings save time:

- **[Seer](../seer/README.md)**: run a design-cohesion review first to find what's mis-shaped, then let Cleric sweep the low-risk cleanup that clears the way.
- **[Ranger](../ranger/README.md)**: its continuous build loop can drive `/cleric:run --auto` as a periodic maintenance pass between feature work.
- **[Scout](../scout/README.md)**: its Playwright suite is a good extra check that Cleric's changes didn't quietly break a real user flow.

## Development

Cleric is prompts and agent definitions only; it has no scripts or test suite of its own. Check the plugin from the repo root with the same manifest and docs checks CI runs:

```bash
python3 .github/scripts/validate_manifests.py
python3 .github/scripts/check_docs.py
```

## License

Apache-2.0. See [LICENSE](../../LICENSE). © 2026 gshepptech
