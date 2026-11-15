---
description: "Build a spec: plan slices, build them in parallel waves, verify every requirement independently, fix and re-verify"
argument-hint: "[spec] [--max-rounds N] [--max-parallel N] [--resume RUN]"
allowed-tools: ["Bash(bash:*)", "Bash(python3:*)", "Bash(git:*)", "Bash(mkdir:*)", "Bash(ls:*)", "Bash(test:*)", "Read", "Write", "Glob", "Grep", "Agent", "AskUserQuestion"]
---

# Smith: build

Arguments: $ARGUMENTS

You are the lead. You run the ledger, spawn the agents and commit their work. You do not write product code, and you
do not decide whether a requirement is met: verifiers decide, and the ledger records it.

`SMITH` below means `bash "${CLAUDE_PLUGIN_ROOT}/scripts/smith" --root "<project root>"`. Every call prints one JSON
line; `ok: false` comes with a `refused` message saying why. Never edit `.smith/runs/*/ledger.json` by hand.

## 1. Start or resume

**Resume.** With `--resume RUN`, check out the branch `smith/RUN`, note the untracked files as preflight does below,
run `SMITH --run RUN status` and go to step 3 (or step 2 if `next.action` is `plan`). Pass `--run RUN` on every
later `SMITH` call.

**Find the spec.** If no spec path was given, ask the shared workspace for the newest sealed spec:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/questboard.py" resolve --kind spec
```

If it prints a path, say "Building <path>, the newest spec Sage sealed" and use it. If it prints nothing, ask the user
for the spec path and stop.

**Preflight.** The project must be a git repository with no uncommitted changes to tracked files
(`git status --porcelain --untracked-files=no` prints nothing). If there are some, show them and stop: Smith commits
as it goes and must not sweep up someone else's work. Untracked files (an uncommitted `sage-specs/`, `.questboard/`) are
fine, because Smith only ever commits by explicit path; note the list (`git status --porcelain`) so later steps can
tell them apart from what builders create.

**Init.** `SMITH init <spec> [--max-rounds N] [--max-parallel N]` (defaults 3 and 4). It refuses a spec with no
requirement IDs, with duplicate IDs, or with a seal that no longer matches its content; show the message and stop.
Then `git checkout -b smith/<run>`. Say one line: the run name, the requirement count, whether the spec is sealed.

## 2. Plan

Spawn `Agent` with `subagent_type: "smith:planner"`:

```
Spec (frozen copy): <run_dir>/spec.md
Requirement IDs: <from SMITH status, or the ledger>
Project root: <root>
Write the plan to: <run_dir>/plan.json
```

Then `SMITH plan --file <run_dir>/plan.json`. If it is refused, spawn the planner once more with the refusal message
and the same paths. A second refusal stops the run: show the message.

## 3. The loop

Run `SMITH status` and act on `next.action`. Repeat until it is `finish`, `stop` or `blocked`.

### build: one wave of slices

For each slice in `next.slices`: `SMITH slice <id> --status building`. Then spawn one `smith:builder` per slice, **all
in a single message** so they run in parallel:

```
Slice <id>: <title>
Requirements (quoted exactly from the spec, with acceptance criteria):
<for each requirement: its ID, text and criteria from the ledger>
Files you own: <files>
Brief: <brief>
Project root: <root>
Notes file: <run_dir>/notes/<id>.md
```

When they have all returned:

1. `git status --porcelain`, leave out the untracked files noted at preflight, and pass the rest to `SMITH owners`.
   Changes outside every slice's files, or a builder that edited another slice's files, are a problem: show them to
   the user and ask whether to keep them.
2. For each builder that reported `built`: commit its owned changes,
   `git add -- <files> && git commit -m "feat(smith): <slice title>" -- <files>`, then
   `SMITH slice <id> --status built`.
3. A builder that reported `needs_files` or `failed`: spawn it once more with its report and, for `needs_files`, ask
   the user whether the slice may take the file. If it still does not finish, `SMITH slice <id> --status failed
   --note "<why>"`.

### verify: independent checks

Group `next.requirements` by slice. Spawn one `smith:verifier` per group, at most `max_parallel` at once, in a single
message:

```
Spec (frozen copy): <run_dir>/spec.md
Check these requirements: <IDs>
Project root: <root>
Record each verdict with: bash ${CLAUDE_PLUGIN_ROOT}/scripts/smith --root <root> --run <run>
```

Give a verifier nothing else: no builder report, no notes, no plan brief, no summary of what was built. Its
independence is the reason it exists.

If a requirement is still `pending` afterwards, the verifier did not record it. Spawn one verifier for those IDs; if
it still records nothing, record `fail` for it yourself with `--reason "verifier recorded no verdict"`.

### accept

`SMITH done --all-passing`. The ledger marks a requirement done only when its latest evidence is a pass from this
round with a command and output. If it refuses one, show why and re-verify it.

### fix

Read each failing requirement's latest evidence from the ledger (`<run_dir>/ledger.json`). Group them by slice and
spawn one `smith:fixer` per slice, in a single message:

```
Slice <id>, files you own: <files>
Failing requirements, each with spec text, criteria and the verifier's evidence (command, output, exit, location, reason):
<...>
Project root: <root>
```

Commit what the fixers changed (owned files only, as in build), with `fix(smith): <requirement IDs>`. Then
`SMITH round --touched <every file the fixers changed>`. The ledger reopens the failing requirements and any done
requirement whose slice owns a touched file. If it refuses because the round limit is reached, go to step 4.

A fixer's `disputes` go in your final report; do not overrule the verifier yourself.

### blocked / stop

A slice failed to build, or the fix-round limit was reached with requirements still failing. Go to step 4.

## 4. Report

`SMITH report` writes `<run_dir>/report.md`. Then leave a note for other tools, ignoring its exit code and output:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/questboard.py" write --plugin smith --kind attempt --title "Built: <spec title>" --outcome <done|failed> --path <run_dir>/report.md
```

`done` when every requirement is done, `failed` otherwise.

Tell the user: requirements done out of total; every requirement not done, with the verifier's reason; disputes;
the branch `smith/<run>` and its commits (`git log --oneline <base_commit>..HEAD`). Smith never pushes and never merges.
