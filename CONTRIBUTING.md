# Contributing to The Tavern

Thanks for swinging by the job site. Whether you're fixing a typo, sharpening a
plugin, or pitching a whole new tradesperson for the crew, contributions are welcome.

## Ground rules

- **Be kind.** This project follows the [Code of Conduct](CODE_OF_CONDUCT.md).
- **Open an issue first** for anything non-trivial, so we can agree on the shape before you build.
- **Every plugin must stand alone.** Each crew member is usable by itself, with no
  other plugin installed. A change that makes one plugin depend on another needs a
  very good reason — optional composition is fine, a hard dependency is not.
- **Keep the spec intact.** Sage and Smith share one discipline — *plans are prompts*. Changes
  that touch the handoff format should preserve byte-for-byte fidelity.
- **No emoji in documentation.** Headings, tables and prose stay plain text. GitHub
  alert callouts (`> [!NOTE]`), mermaid diagrams and `<details>` blocks are fine;
  decorative Unicode is not — no emoji, no dingbats, and no arrow glyphs (write
  `->` instead). Images are limited to each plugin's own SVG and shields.io badges.
  The exception is a glyph that defines runtime output, such as the state markers
  in Sellsword's run table or the verdict marks in Smith's TRACE tables — those are part
  of what an agent prints, not decoration, and they stay.

## Repo layout

```
.claude-plugin/marketplace.json     # the marketplace manifest (lists all 9 plugins)
.github/scripts/validate_manifests.py   # local manifest validator
plugins/<name>/                     # one directory per tradesperson
  .claude-plugin/plugin.json        # that plugin's manifest — name and version
  README.md                         # per-plugin docs, self-contained
  <name>.svg                        # that plugin's artwork
  commands/                         # slash commands
  agents/                           # sub-agent definitions        (most plugins)
  skills/                           # skills, with references/     (some plugins)
  hooks/hooks.json                  # hook wiring                  (warden, sellsword, ranger)
  scripts/                          # hook scripts and setup       (some plugins)
  workflows/                        # Workflow scripts             (seer)
  presets/                          # curated briefs               (ranger)
  tests/                            # test suite                   (warden, sage, ranger)
plugins/smith/mcp-server/           # Smith's MCP server and its own test suite
```

## Local checks (run these before you push)

CI runs all of these on every push and pull request (`.github/workflows/ci.yml`),
so anything that fails here fails there. Running them locally is faster than
waiting for the run.

```bash
# 1. Validate the marketplace + every plugin manifest
python3 .github/scripts/validate_manifests.py

# 2. Check every version reference agrees (see "Versioning" below)
python3 .github/scripts/check_versions.py

# 3. Check the docs: no decorative Unicode, all relative links resolve
python3 .github/scripts/check_docs.py

# 4. Check documented flags are actually wired, and agent types exist
python3 .github/scripts/check_flags.py

# 5. Check the install profiles: every plugin exists, the docs agree,
#    and any profile carrying an unattended plugin still warns about it
python3 .github/scripts/check_profiles.py

# 6. Syntax-check JavaScript and shell
git ls-files '*.js' | xargs -I{} node --check {}
git ls-files '*.sh' | xargs -I{} bash -n {}
```

Four plugins carry test suites. Run the ones your change touches; run all four if
you're not sure:

```bash
# Warden — citation verifier and hook gates
cd plugins/warden && uv run --with pytest python -m pytest tests/ -q

# Sage — spec format, typed sections, validation
cd plugins/sage && uv run --with pytest --with jsonschema python -m pytest tests/ -q

# Ranger — the git guard hook
cd plugins/ranger && uv run --with pytest python -m pytest tests/ -q

# Smith — MCP server
cd plugins/smith/mcp-server && uv run --with pytest --with jsonschema --with "mcp>=1.0.0" python -m pytest -q
```

> [!NOTE]
> `uv run --with` keeps the dependencies scoped to the run instead of installing
> into your environment. If you'd rather use pip, install `pytest`, `jsonschema`
> and `mcp>=1.0.0` first and call `pytest` directly.

Some tests are deliberately skipped — they are red-until-implemented markers for
planned work, and each carries a skip reason explaining which plan owns it. Skips
are expected; failures are not.

## Versioning

**The plugin cache is version-keyed.** An installed plugin only picks up your change
when its version number moves. A fix shipped without a bump reaches nobody who
already installed the plugin, so treat the bump as part of the fix, not paperwork.

A version is written in four places and `check_versions.py` enforces that all four agree:

1. `plugins/<name>/.claude-plugin/plugin.json` — the one that controls delivery
2. `.claude-plugin/marketplace.json` — the marketplace entry
3. `plugins/<name>/README.md` — the shields.io badge
4. `README.md` — the Crew table row

Which level to bump:

| Change | Bump |
|---|---|
| Anything under `commands/`, `agents/`, `skills/`, `hooks/`, `scripts/` | at least patch — this is runtime |
| A new command, flag, or capability | minor |
| A behaviour change a user could be surprised by | minor, and say so in the changelog |
| README wording only | none — nothing to deliver |

## Adding or changing a plugin

1. Each plugin lives in `plugins/<name>/` with a `.claude-plugin/plugin.json` whose
   `name` matches the entry in `marketplace.json` (the manifest check above verifies this).
2. Update the plugin's own `README.md` and bump its `version` everywhere listed above.
3. Keep the README self-contained. Someone may land on it directly and install only
   that plugin, so it needs its own install steps, commands and caveats without
   assuming the root README has been read. Sibling plugins belong in a
   "Pairs well with" section at the bottom, not as framing at the top.
4. If you add a new plugin, add an entry to `marketplace.json`, a row to the
   **Crew** table in the root `README.md`, and a line to the Per-plugin docs list.
5. Note anything user-visible in the [Changelog](CHANGELOG.md).

## Documentation accuracy

Docs drift faster than code. When you change behaviour, grep for every place that
describes it — the plugin's `commands/*.md` (especially `help.md`), its
`agents/*.md` frontmatter descriptions, its skills, its script header comments, and
its README. A stale `help.md` is the most common defect in this repo.

Be especially careful with hardcoded counts (of agents, phases, lenses, streams,
tracks, tests). If a number will drift, either verify it at the time of writing or
describe the thing qualitatively instead.

## Pull requests

- Branch off `main`, keep the diff focused, and fill in the PR template.
- Reference the issue it closes.
- Run the local checks above before pushing.

## Naming note

The crew are people — **Sage, Smith, Warden, Sellsword, Cleric, Scout, Tactician, Seer, Ranger**.
One internal note: the `mill_mcp` Python package under `plugins/smith/mcp-server/`
has **frozen** identifiers — they bind MCP tool resolution, so leave them as-is.

Happy building.
