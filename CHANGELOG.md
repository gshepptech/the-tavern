# Changelog

All notable changes to this marketplace are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Each plugin carries its own
[semantic version](https://semver.org/), shown in the [roster](README.md#the-roster), and
entries are grouped by the date they reached `main`.

## 2026-11-15

### Changed
- **The marketplace is The Tavern.** Install it with
  `/plugin marketplace add gshepptech/the-tavern` and each plugin as `<name>@the-tavern`.
  The fifteen regulars at their current versions: Sage 1.0.0, Smith 1.0.0, Tinker 0.1.0,
  Squire 1.0.0, Sellsword 0.4.0, Ranger 0.7.1, Warden 0.5.1, Seer 0.2.0, Cleric 0.2.1,
  Scout 0.2.1, Bard 1.0.0, Tactician 0.2.1, Scribe 1.0.0, Raven 1.0.0 and Monk 1.0.0.
- The shared workspace is the quest board, `.questboard/`. See
  [docs/questboard-contract.md](docs/questboard-contract.md).
- Install profiles are `builder`, `lean`, `solo`, `review`, `unattended` and `full`. See
  [docs/profiles.md](docs/profiles.md).
- Ranger's orchestrating agent is called the lead throughout its prompts and docs.

### Added
- **Squire 1.0.0.** A single-lane build, verify and fix loop for small specs: one
  test-first builder, a verifier that sees only the spec and the code, a fixer limited to
  the listed gaps, and drift checks in code. `/squire:build`.
- **Scribe 1.0.0.** Plans, writes and audits documentation, with every claim anchored to a
  `file:line` or a command that was run, and a newcomer read of every page.
  `/scribe:plan`, `/scribe:write`, `/scribe:audit`.
- **Bard 1.0.0.** A UX review that uses the running app as named personas in a real
  browser and writes a ranked report with a screenshot behind every finding. `/bard:run`.
- **Raven 1.0.0.** Posts to a Slack incoming webhook when a reply finishes or Claude Code
  is waiting for you, with secrets redacted and repeats suppressed. `/raven:test`.
- **Monk 1.0.0.** Seven response-shaping rules loaded at session start, a one-line
  reminder per prompt and an optional length gate. `/monk:gate-on`, `/monk:verbose`.
- CI runs the Squire, Scribe, Bard, Raven and Monk test suites.

## 2026-11-14

### Added
- **Sage 1.0.0.** Turns a feature idea into a sealed spec. A researcher agent reports
  numbered code facts with `path:line` evidence, the interview asks only what the code
  cannot answer, and every requirement cites its sources and carries acceptance criteria
  that can fail. A stdlib validator checks the structure and seals the file with a sha256
  hash; a spec-reviewer agent flags ambiguity before sealing. `/sage:plan`, `/sage:resume`.
- **Smith 1.0.0.** Builds a spec to its requirements. A planner splits the spec into
  slices with explicit file ownership, builders work independent slices in parallel waves,
  and verifiers that never see the builders' notes check every requirement. A stdlib
  ledger refuses to mark a requirement done without a passing command and its output from
  the current round, and a fix reopens every requirement whose files it touched.
  `/smith:build`, `/smith:status`.
- CI checks Workflow scripts by wrapping them the way the runtime runs them, so a
  top-level `return` or `await` no longer fails the syntax step.

### Changed
- **Ranger 0.7.1.** The looped-run preflight checks only Warden's strict gate.
- The executable-bit check in CI applies to scripts with a shebang; imported modules are
  exempt.

## 2026-10-16

### Added
- **Tinker 0.1.0.** A lean spec-to-code build as one Workflow script. Preflight, planning
  checks, commits, verification and the report run in Python; agents only build, check the
  spec against the code and fix. One builder unless the spec is over budget, a code check
  beside one spec-to-code check, at most two batched fix rounds, and a hard cap on agent
  calls. The integration check must run to completion, and each behavioural fix carries a
  test that fails before it and passes after. `/tinker:build`.

## 2026-09-01

### Added
- **Ranger 0.7.0.** `--sweep` runs one survey-only pass over the whole domain grid before
  any build, ending with a ranked backlog. Scouts read for correctness, security,
  performance and developer experience; drivers run the real app for UI, flow and
  accessibility lenses. `--sweep=all` covers all nine lenses.

## 2026-08-26

### Fixed
- **Cleric 0.2.1.** The deduplication track looks for the project's own TypeScript and
  JavaScript parsers before falling back to line-window matching.

## 2026-08-14

### Added
- **The `.questboard/` shared workspace.** An optional directory where plugins leave each other
  immutable JSON notes. Sage records each sealed spec, Smith resolves its spec from the
  newest one, Ranger reads what has already been tried and records each attempt, and Sellsword,
  Cleric and Seer record findings they did not act on. Every plugin behaves the same when
  the directory is absent. See [docs/questboard-contract.md](docs/questboard-contract.md).
- **Install profiles.** Named sets of plugins, installed
  with `scripts/install-profile.sh` (`--list`, `--dry-run`, `--scope`, `--yes`) and checked
  against [docs/profiles.md](docs/profiles.md) in CI.
- **Ranger 0.6.0.** Every backlog item carries an artifact: the command a scout ran and
  what it saw. A new `driver` agent runs the real system to survey or to reproduce a claim,
  and a new `builder` agent handles most items in one pass, escalating to the full
  plan-and-review path only when the work is wider than the item implied. Verdicts are
  written to disk before they are returned, and a red-before-green claim must include the
  failure text.
- **Sellsword 0.4.0, Cleric 0.2.0, Seer 0.2.0.** Each writes its findings to `.questboard/` when
  the directory exists.

### Fixed
- **Ranger 0.6.1.** The shared-workspace helper rejects a trailing newline in the `plugin`
  and `created` fields, which `validate` previously accepted.

## 2026-08-05

### Changed
- **Ranger 0.5.0.** Effort is sized to each item: a small fix costs two agents and a risky
  change gets the full pipeline. The quality floor rises as a run matures and the backlog
  is capped, so a long run gets more selective instead of producing churn.

## 2026-08-01

### Changed
- **Ranger 0.4.0.** Agents run on model tiers matched to their role, and the assessor's
  browser work is bounded.

## 2026-07-23

### Added
- CI: manifest validation, version agreement, documentation, flag-wiring checks, syntax
  checks and the plugin test suites on every push and pull request.
- **Ranger 0.3.0.** Scouts run in parallel pools sized by `--scouts` and `--planners`.
- **Sellsword 0.3.0.** `/sellsword:goal` runs can be resumed.

### Fixed
- **Ranger 0.3.0.** The git guard covers more ways to publish, including `gh api` writes
  and commands hidden behind a launcher.
- **Warden 0.5.1.** `/warden:trust-me` works, the Stop hook tolerates malformed transcripts, and
  the local gate log records counts rather than response text.
- **Cleric 0.1.1.** Corrected static-analysis tool names.
- **Scout 0.2.1.** `/scout:matrix` writes the config its generated specs import.
- **Tactician 0.2.1.** `/tactician:make` declares the `AskUserQuestion` tool it uses.

## 2026-07-21

### Added
- **Ranger 0.2.0.** A self-directing, unattended engineering loop: survey, plan, review,
  build, verify and commit, one local commit per item, until you stop it. A `PreToolUse`
  hook denies `git push`, remote changes and PR creation even with permissions bypassed.
  `/ranger:run`, `/ranger:stop`, `/ranger:resume`, `/ranger:status`.

## 2026-06-26

### Added
- First public release of the marketplace, with:
  - **Warden 0.5.0**: methodical-mode hooks, a citation verifier and a two-tier critic.
  - **Sellsword 0.2.0**: five agents that investigate, plan, execute and verify.
  - **Cleric 0.1.0**: low-risk cleanup across seven tracks.
  - **Scout 0.2.0**: Playwright end-to-end tests written by driving the real app.
  - **Tactician 0.2.0**: generated multi-agent Workflow scripts.
  - **Seer 0.1.0**: architecture and design-cohesion review.
