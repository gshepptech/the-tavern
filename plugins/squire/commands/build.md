---
description: "Build a small structured spec with squire: one test-first builder, a spec-only verifier, fixes for the listed gaps only, until clean or out of rounds"
argument-hint: "<spec> [--max-rounds N] [--timeout S] [--check CMD]"
allowed-tools: ["Bash(${CLAUDE_PLUGIN_ROOT}/scripts/squire:*)", "Read", "Workflow"]
disable-model-invocation: "true"
---

# squire build

```!
"${CLAUDE_PLUGIN_ROOT}/scripts/squire" --root "${CLAUDE_PROJECT_DIR:-$PWD}" args $ARGUMENTS
```

You launch squire's build as the `squire-build` workflow (`${CLAUDE_PLUGIN_ROOT}/workflows/build.js`) and report what it
returns. The script holds the whole loop; you do not build, verify, fix or run squire commands yourself.

## 1. Read the parsed arguments

The command above printed one JSON line. If `ok` is false, show `stop` and end here.

## 2. Launch

Call the **Workflow** tool with:

- `scriptPath`: `<args.plugin_root>/workflows/build.js`
- `args`: the `args` object from that line, passed as a JSON object, not a string.

Then say one line and wait; do not poll:

```
squire is building <spec> as run <args.run> on branch squire/<args.run> (workflow <runId>).
```

## 3. When it returns

The workflow returns `{status, message, run, run_dir, report, counts, open, rounds, agent_calls, concerns, timeline}`.

- `done`: every requirement is MET and no gap is open. Show `message` and the path to `report`.
- `done_with_gaps`: show `message`, then read `report` and show every requirement that is not MET with its reason, and
  every other open gap. Say plainly what is not done first.
- `unverified`: the verifier's file was refused twice, so the last round could not be judged. Show `message`,
  `concerns` and the path to `report`.
- `stopped`: squire refused to start (a dirty tree, a spec with no requirement IDs, a run that already exists). Show
  `message`. Nothing was built.
- `error`: show `message` and the last lines of `timeline`.

Always show `concerns` if there are any. Do not retry on your own, and do not merge or push the branch.
