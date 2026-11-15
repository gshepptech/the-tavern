---
description: "Use the running app as named personas in a real browser and write a ranked UX report with steps, screenshots, severity and a fix for every finding"
argument-hint: "<url> [--personas LIST] [--areas LIST] [--max-slices N] [--read-only] [--login TEXT]"
allowed-tools: ["Bash(${CLAUDE_PLUGIN_ROOT}/scripts/bard:*)", "Bash(curl:*)", "Read", "Agent", "ToolSearch"]
---

# bard run

```!
"${CLAUDE_PLUGIN_ROOT}/scripts/bard" --root "${CLAUDE_PROJECT_DIR:-$PWD}" init $ARGUMENTS
```

You run an experiential UX review. Persona drivers use the running app in a real browser, one persona in one area at a
time, and write what they find to slice files. A synthesizer merges and ranks them. You orchestrate and report. You do
not drive the browser yourself: snapshots are large and belong in the drivers' context, not yours.

`BARD` below means `"${CLAUDE_PLUGIN_ROOT}/scripts/bard" --root "${CLAUDE_PROJECT_DIR:-$PWD}"`, and `RUN` is the
`run_dir` the line above printed.

## 1. Read the parsed arguments

The command above printed one JSON line. If `ok` is false, show `stop` and end here. Otherwise keep `run_dir`, `url`,
`personas`, `areas`, `read_only` and `login`.

## 2. Preflight

1. Check the app answers: `curl -s -o /dev/null -w '%{http_code}' --max-time 10 '<url>'`. Anything other than a 2xx or
   3xx status stops the review: say the app is not reachable at that address and that bard reviews a running app.
2. Check the Playwright MCP tools are loaded: search with ToolSearch for `browser_navigate`. If nothing is found, stop
   and tell the user to add the server and restart Claude Code:

   ```
   claude mcp add playwright -- npx @playwright/mcp@latest
   ```

Say one line: `bard is reviewing <url> as <persona names>. Run directory: <RUN>.`

## 3. Map the areas

If `areas` is empty, spawn one driver with the Agent tool, `subagent_type="bard:persona-driver"`, and this prompt:

```
mode: map
url: <url>
run dir: <RUN>
maximum areas: 6
```

It returns `{"areas": [...], "promises": [...]}`. Keep `promises`. Then plan the slices:

```bash
BARD plan --run "<RUN>" --areas-json '<the areas array as JSON>'
```

If `areas` came from `--areas`, run `BARD plan --run "<RUN>"` with no `--areas-json`. The plan lists every slice, a
persona in an area, ordered so that a `--max-slices` cap still spreads over every persona and every area. Tell the user
how many slices will run and how many the cap skipped.

## 4. Run the slices, one at a time

The Playwright MCP server has one browser, so slices run in sequence, never in parallel. For each slice in the plan,
spawn a driver with `subagent_type="bard:persona-driver"` and this prompt, filled from the slice and the persona it
names:

```
mode: slice
slice: <id>
url: <slice url>
persona: <name>: <who>. Jobs: <jobs>. Constraints: <constraints>
viewport: <viewport>
run dir: <RUN>
slice file: <RUN>/<file>
screenshot prefix: <screenshot_prefix>
read_only: <true or false>
login: <login notes, or none>
product promises: <promises from the map, or none>
plugin root: ${CLAUDE_PLUGIN_ROOT}
```

After each one, confirm the file with `BARD validate --run "<RUN>" --slice <id>`. If it is not valid, spawn the driver
once more for that slice with the errors and the instruction to repair the file only, without driving the browser
again. If it is still not valid, leave it; the synthesizer reports it as missing. After each slice, print one line:
the slice, the persona, the area, and the finding count.

## 5. Synthesize

Spawn one agent with `subagent_type="bard:synthesizer"` and this prompt:

```
run dir: <RUN>
plugin root: ${CLAUDE_PLUGIN_ROOT}
```

Then render:

```bash
BARD render --run "<RUN>"
```

If it prints `ok: false`, spawn the synthesizer once more with the errors it lists, then render again. If it still
fails, show the errors and stop.

## 6. Report

Show, in this order:

1. The counts by severity and the path to `report.md`.
2. The top findings from `top`: id, severity, title.
3. Any slice that did not run, and why.

Do not paste the whole report. Do not change the app's code; bard reports, and fixing is a separate step the user
decides on.
