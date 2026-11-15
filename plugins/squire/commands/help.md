---
description: "Explain what squire does, when to use it, and its flags"
hide-from-slash-command-tool: "true"
---

# squire help

Explain the following to the user, compactly and in your own words.

## What squire is

A compact build, verify and fix loop for a spec that is already written: numbered requirements with acceptance
criteria. `/squire:build <spec>` builds it on a new branch with one builder, checks every requirement with a verifier
that sees only the spec and the code, fixes only what the verifier and the checks list, and repeats until clean or out
of rounds. It does no planning and no splitting. For a large spec that needs parallel slices, a planner is the better
tool; squire is the single lane for small ones (roughly up to fifteen requirements).

## The loop

1. **Index**, in code: the working tree must be clean; the spec must define requirement IDs; each one's text and
   acceptance criteria go into `index.json`. The project's build, lint and test commands are detected (or given with
   `--check`) and run once at the base commit, so failures that were already there are not blamed on the build.
2. **Build**: one builder, test-first, commits by name on `squire/<run>`.
3. **Verify**: one verifier reads the spec before the code, runs the checks through squire, and gives every requirement
   one verdict (MET, PARTIAL, MISSING, WRONG) with `file:line` evidence. It also lists code nobody asked for. Code
   refuses a verdict file that skips a requirement or cites a line that does not exist.
4. **Fix**: one fixer gets the gap list (unmet requirements, unrequested code, requirement IDs in production code,
   uncommitted work, newly failing checks) and fixes only those.
5. Repeat 3 and 4 until no gap is open or `--max-rounds` fix rounds are used, then write `squire-runs/<run>/report.md`.

## Flags

- `--max-rounds N`: fix rounds before what remains goes to the report (default 3, at most 5; 0 reports without fixing).
- `--timeout S`: seconds each check command may run (default 300).
- `--check CMD`: a check command to run instead of the detected ones; repeat it for more than one.
