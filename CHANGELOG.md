# Changelog

All notable changes to this marketplace are documented here. The format is based
on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Individual plugins
carry their own versions (shown in the [Crew table](README.md#-the-crew)); this
file tracks the marketplace as a whole.

## [Unreleased]

### Added
- **Ranger** `v0.1.0` — the ninth crew member: a self-directing, unattended senior-engineering loop. A thin lead drives five Opus sub-agents (scout, planner, implementer, reviewer, assessor) through survey → plan → plan-review → build → review → verify → commit, one local commit per item. `/ranger:run`, `/ranger:stop`, `/ranger:resume`, `/ranger:status`, `/ranger:help`.
  - `--dry-run` preview (survey + top plan, no writes); first-run safety cap (5 items, overridable with `--unlimited`); `--branch` / `--merge-dev` / `--ask` all default off.
  - A `Stop` hook makes the loop unstoppable while active; a `PreToolUse` hook hard-denies `git push`, remote mutation, and PR creation. Subprocess tests cover both hooks.
- Community health files: contributing guide, code of conduct, security policy, issue forms, and PR template.
- Expanded README: status badges, table of contents, per-crew deep-dives, and a "which crew member do I need?" picker.

### Changed
- Security and Code-of-Conduct contacts now use GitHub-native reporting (Security Advisories + maintainer handle) instead of a personal email address.

## [0.1.0] — 2026-06-26

### Added
- Initial public release of the **The Tavern** marketplace with all eight crew members:
  Sage, Smith, Warden, Sellsword, Cleric, Scout, Tactician, and Seer.

[Unreleased]: https://github.com/gshepptech/the-tavern/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/gshepptech/the-tavern/releases/tag/v0.1.0
