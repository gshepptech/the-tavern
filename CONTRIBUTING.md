# Contributing to The Tavern

Pull up a chair. Whether you're fixing a typo, sharpening a plugin, or proposing a
new regular for the tavern, contributions are welcome.

## Ground rules

- **Be kind.** This project follows the [Code of Conduct](CODE_OF_CONDUCT.md).
- **Open an issue first** for anything non-trivial, so we can agree on the shape before you build.
- **Every plugin must stand alone.** Each regular is usable by itself, with no
  other plugin installed. A change that makes one plugin depend on another needs a
  very good reason - optional composition is fine, a hard dependency is not.
- **Keep the spec format stable.** Sage writes specs that Smith, Tinker and Squire read.
  A change to the requirement IDs, the acceptance-criteria shape or the `sealed_by` line
  has to keep all four working.
- **No emoji in documentation.** Headings, tables and prose stay plain text. GitHub
  alert callouts (`> [!NOTE]`), mermaid diagrams and `<details>` blocks are fine;
  decorative Unicode is not - no emoji, no dingbats, and no arrow glyphs (write
  `->` instead). Images are limited to each plugin's own SVG and shields.io badges.
  The exception is a glyph that defines runtime output, such as the state markers
  in Sellsword's run table - those are part of what an agent prints, not decoration,
  and they stay.

## Repo layout

```
.claude-plugin/marketplace.json     # the marketplace manifest (lists all fifteen plugins)
.github/scripts/                    # the consistency checks CI runs
docs/                               # install profiles and the quest board contract
scripts/install-profile.sh          # installs a named set of plugins
plugins/<name>/                     # one directory per regular
  .claude-plugin/plugin.json        # that plugin's manifest - name and version
  README.md                         # per-plugin docs, self-contained
  <name>.svg                        # that plugin's artwork      (some plugins)
  commands/                         # slash commands
  agents/                           # sub-agent definitions        (most plugins)
  skills/                           # skills, with references/     (some plugins)
  hooks/hooks.json                  # hook wiring                  (warden, sellsword, ranger, monk, raven)
  scripts/                          # hook and helper scripts      (some plugins)
  workflows/                        # Workflow scripts             (seer, tinker, squire)
  presets/                          # curated briefs               (ranger)
  tests/                            # test suite                   (ten plugins, see below)
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

# 6. Syntax-check JavaScript (Workflow scripts are wrapped first) and shell
python3 .github/scripts/check_js.py
git ls-files '*.sh' | xargs -I{} bash -n {}
```

Ten plugins carry test suites. Run the ones your change touches; run all ten if
you're not sure:

```bash
# Warden - citation verifier and hook gates
cd plugins/warden && uv run --with pytest python -m pytest -q

# Sage - spec validator, seal and the shared-workspace helper
cd plugins/sage && uv run --with pytest python -m pytest -q

# Ranger - the git guard hook and the shared-workspace helper
cd plugins/ranger && uv run --with pytest python -m pytest -q

# Smith - spec parsing, plan checks and the ledger's evidence rule
cd plugins/smith && uv run --with pytest python -m pytest -q

# Tinker - preflight, command detection, gates and the Workflow script
cd plugins/tinker && uv run --with pytest python -m pytest -q

# Squire - spec indexing, check detection, verdict validation and the Workflow script
cd plugins/squire && uv run --with pytest python -m pytest -q

# Scribe - each documentation gate against temporary repositories
cd plugins/scribe && uv run --with pytest python -m pytest -q

# Bard - persona and slice planning, the finding validator and the report renderer
cd plugins/bard && uv run --with pytest python -m pytest -q

# Monk - the hook script, commands and the length gate
cd plugins/monk && uv run --with pytest python -m pytest -q

# Raven - message contents, redaction and failure handling against a local server
cd plugins/raven && uv run --with pytest python -m pytest -q
```

> [!NOTE]
> `uv run --with` keeps the dependencies scoped to the run instead of installing
> into your environment. If you'd rather use pip, install `pytest` first and call
> `pytest` directly. Tinker's and Squire's Workflow tests also need `node` on `PATH`.

## Versioning

**The plugin cache is version-keyed.** An installed plugin only picks up your change
when its version number moves. A fix shipped without a bump reaches nobody who
already installed the plugin, so treat the bump as part of the fix, not paperwork.

A version is written in four places and `check_versions.py` enforces that all four agree:

1. `plugins/<name>/.claude-plugin/plugin.json`: the one that controls delivery
2. `.claude-plugin/marketplace.json`: the marketplace entry
3. `plugins/<name>/README.md`: the shields.io badge
4. `README.md`: the roster table row

Which level to bump:

| Change | Bump |
|---|---|
| Anything under `commands/`, `agents/`, `skills/`, `hooks/`, `scripts/` | at least patch - this is runtime |
| A new command, flag, or capability | minor |
| A behaviour change a user could be surprised by | minor, and say so in the changelog |
| README wording only | none - nothing to deliver |

## Adding or changing a plugin

1. Each plugin lives in `plugins/<name>/` with a `.claude-plugin/plugin.json` whose
   `name` matches the entry in `marketplace.json` (the manifest check above verifies this).
2. Update the plugin's own `README.md` and bump its `version` everywhere listed above.
3. Keep the README self-contained. Someone may land on it directly and install only
   that plugin, so it needs its own install steps, commands and caveats without
   assuming the root README has been read. Sibling plugins belong in a
   "Pairs well with" section at the bottom, not as framing at the top.
4. If you add a new plugin, add an entry to `marketplace.json`, a row to the
   roster table in the root `README.md`, a test matrix entry in
   `.github/workflows/ci.yml` if it has tests, and its name in the issue templates.
5. Note anything user-visible in the [Changelog](CHANGELOG.md).

## Documentation accuracy

Docs drift faster than code. When you change behaviour, grep for every place that
describes it - the plugin's `commands/*.md` (especially `help.md`), its
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

Every plugin is named for a regular you would find in a fantasy tavern, and the name
hints at the job: the sage writes the plan down, the smith builds from it, the warden
keeps watch, the scribe writes the docs. A new plugin gets a name in the same spirit:
one lowercase word, a role rather than a person.
