---
description: "Show where a Smith build stands: slices, requirement verdicts and the next step"
argument-hint: "[run]"
allowed-tools: ["Bash(bash:*)", "Read"]
---

# Smith: status

```!
bash "${CLAUDE_PLUGIN_ROOT}/scripts/smith" --root "${CLAUDE_PROJECT_DIR:-$PWD}" ${ARGUMENTS:+--run $ARGUMENTS} status
```

The line above is the ledger's status for the run (the newest run if none was named). If it says `ok: false`, show
`refused` and stop.

Otherwise show, compactly:

- the run, the spec and whether it was sealed;
- requirements by status (`done`, `passing`, `failing`, `pending`) out of the total;
- each slice and its status, in wave order;
- the fix round, out of the limit;
- the next step in plain words, from `next.action`: `plan`, `build` (which slices), `verify`, `accept`, `fix`,
  `finish`, `stop` or `blocked`.

For a failing requirement, read its latest evidence in `<run_dir>/ledger.json` and give the verifier's reason.

If the run is not finished, say that `/smith:build --resume <run>` continues it.
