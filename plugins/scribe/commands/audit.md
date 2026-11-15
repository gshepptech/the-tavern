---
description: Run the documentation gates over existing docs and return a ranked punch list
argument-hint: [docs-path] [--no-readers]
---

You are auditing existing documentation. The first word of `$ARGUMENTS` that is not a flag is the docs path; default
to `docs` if it exists, otherwise `README.md`. `--no-readers` skips step 2. You report; you do not edit any page.

## 1. Deterministic gates

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/scribe_check.py" <docs-path> --repo . --json
```

Exit 1 means findings, not failure. It covers broken relative links, `#anchors` that match no heading, evidence
comments that no longer resolve, commands in shell blocks the repository no longer has (Makefile targets, package
scripts, just recipes, script paths), pages that never say who they are for, and acronyms used without expansion.

## 2. Newcomer read

Unless `--no-readers` was given, spawn one agent per page with `subagent_type: "scribe:reader"`, all in one message, at
most 12 pages; when there are more, choose the getting-started page, the index, and the pages most linked from them.
Give each reader only the page path. Do not tell it what the gates found.

## 3. Check the commands the script cannot

For each shell block the script did not flag, look for commands whose subcommand or flag no longer exists in the
code: grep for the flag's definition. A flag documented but not defined anywhere is a stale command. Record the
`path:line` you checked.

## 4. Rank and report

Merge every finding into one punch list, ranked in this order:

1. A reader could not finish the page (reader verdict `could not finish`, or a stopping point that blocks the task).
2. Broken links, missing anchors and stale commands: the reader follows them and hits a dead end.
3. Evidence comments that no longer resolve: the claim next to them may now be wrong.
4. Pages with no stated reader.
5. Non-blocking reader stopping points and unexplained jargon.

Within a rank, put pages on the getting-started path first. For each item give `path:line`, what is wrong, and the
fix in one line. End with counts per rank and the one fix that would help the most readers. Do not edit files.
