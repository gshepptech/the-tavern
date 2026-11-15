# scribe

**Writes documentation for an application you built, with every claim traced to the code, and audits the docs you
already have.**

[![version](https://img.shields.io/badge/version-1.0.0-1E88E5?style=flat-square)](.claude-plugin/plugin.json)
[![license](https://img.shields.io/badge/license-Apache--2.0-4C9A2A?style=flat-square)](../../LICENSE)
[![python](https://img.shields.io/badge/python-3.10%2B-3776AB?style=flat-square)](scripts/scribe_check.py)

## What it does

scribe plans, writes and checks the documentation for a repository. It surveys the code to find what the application
really does, proposes a page set split by what each reader needs (a first-run tutorial, how-to guides, reference,
explanation), and writes those pages with every factual claim tied to the line of code or the command output it came
from. A separate reader who knows nothing about the code then reads each page and reports where it got stuck.

Generated docs usually fail in two ways: they describe what the code was meant to do rather than what it does, and
they skip the step the author no longer notices. scribe deals with the first by refusing a claim it cannot anchor, and
with the second by testing each page on a reader with no context. The same gates run over hand-written docs, so
`/scribe:audit` is useful on its own.

## Features

- **A survey before a plan.** The surveyor lists the real surface (commands, flags, config keys, environment
  variables, endpoints) with a `file:line` for each, and the docs that already exist.
- **Pages by reader need.** Overview, getting started, how-to, reference and explanation, each page with one stated
  reader and one stated outcome. Every surface item lands on exactly one reference page.
- **Anchored claims.** Writers record evidence on the same line as each claim, as an HTML comment the rendered page
  does not show: `<!-- evidence: cmd/server/main.go:41 -->` or ``<!-- evidence: ran `app --help` -->``.
- **A newcomer read.** One reader per page, given only the page. It reports each stopping point and whether it could
  finish the task; writers get one round to fix what blocks.
- **Deterministic gates.** `scribe_check.py` finds broken links, missing anchors, evidence that no longer resolves,
  stale commands, pages with no stated reader, and unexpanded acronyms.
- **A ranked punch list.** `/scribe:audit` orders findings by how badly they stop a reader, with the fix for each.

## Quick start

```bash
claude plugin marketplace add gshepptech/the-tavern
claude plugin install scribe@the-tavern
```

In the repository you want documented:

```
/scribe:plan
```

Confirm or change the proposed pages, then run `/scribe:write`. To check docs you already have, run `/scribe:audit docs`.
You need `python3` 3.10 or later on `PATH`.

## How it works

```
/scribe:plan    surveyor (read-only) -> page set + layout -> .scribe/plan.md -> you confirm
/scribe:write   writer per page (parallel) -> reader per page (parallel, page only)
                 -> blocking stopping points back to the writer, once -> scribe_check.py -> report
/scribe:audit   scribe_check.py + reader per page + flag lookups -> ranked punch list (no edits)
```

| Agent | Sees | Does |
|---|---|---|
| `surveyor` | the repository | maps what the app is, its readers, its surface with evidence, and the existing docs; edits nothing |
| `writer` | one plan entry and the survey | writes one page to its type and reader, anchoring every claim, then runs the gates on it |
| `reader` | one page and its links | reads as a newcomer and reports where it stopped and whether it could finish |

The reader is given the Read tool only and is told not to open source code, so its report reflects the page and not
what the code would have told it.

## Reference

| Command | What it does |
|---|---|
| `/scribe:plan [focus]` | Survey and propose pages and a layout; writes `.scribe/plan.md` and stops for your confirmation |
| `/scribe:write [page-path ...]` | Write the planned pages (default: all new and rewrite pages), read, fix, gate. Does not commit |
| `/scribe:audit [docs-path] [--no-readers]` | Gates plus newcomer reads over existing docs; returns a ranked punch list and edits nothing |
| `/scribe:help` | Commands and order |

The gate script runs without Claude Code:

```bash
python3 plugins/scribe/scripts/scribe_check.py docs --repo . [--gate links,commands] [--json]
```

| Gate | Flags | Severity |
|---|---|---|
| `links` | relative links to missing files; `#anchors` matching no heading, `{#id}` or `<a id>` in the target page | high |
| `evidence` | `<!-- evidence: path:line -->` whose file is gone or whose line is past the end | high, medium |
| `commands` | shell-block commands naming a missing Makefile target, npm/pnpm/yarn/bun script, just recipe or script path; follows `cd` | high |
| `readers` | no `reader:` or `audience:` front matter and no "who this is for" line near the top | medium |
| `jargon` | an acronym used with no expansion on the page and no entry in a `glossary` page | low |

External links are not fetched. Anchors follow GitHub's heading slugs, including the `-1`, `-2` suffixes for repeated
headings. The script exits 1 when it finds anything, 0 when clean.

## Development

```bash
cd plugins/scribe
uv run --with pytest python -m pytest -q
```

The tests build small documentation trees and repositories (a Makefile, a `package.json`, a justfile, scripts) in a
temporary directory and assert each gate's findings, the severity ordering, the JSON output and the exit codes.

## License

Apache-2.0. See [LICENSE](../../LICENSE).
