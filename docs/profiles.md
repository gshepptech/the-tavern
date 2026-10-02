# Install profiles

Nine plugins is nine decisions, and nobody arriving for the first time has the
information to make them. A profile is a named set of plugins that gets you a
sensible setup in one step, so you can start working and add the rest when you
find out you want them.

Nothing here replaces installing one plugin on its own. That is still the
supported path, still the first-class path, and every plugin still works with
none of the others present. A profile is a shortcut for people who do not yet
have an opinion, not a package you are expected to buy into.

## What a profile actually is

Claude Code has no concept of a plugin bundle. There is no `bundles`, `groups`,
`profiles` or `collections` field in the marketplace manifest schema, and no
`recommends` or `suggests` between plugins. The plugin manifest does support a
`dependencies` array, and this repo deliberately does not use it: a hard
dependency between two of these plugins would break the one promise the
marketplace makes, which is that each of them works alone.

So a profile is this repo's own convention. It expands to the ordinary,
supported commands, run one at a time:

```bash
claude plugin marketplace add gshepptech/the-tavern
claude plugin install warden@the-tavern
claude plugin install sage@the-tavern
claude plugin install cleric@the-tavern
```

That is the whole mechanism. Both commands are idempotent, so re-running a
profile is safe, and there is nothing to uninstall except the plugins
themselves. If you would rather read four lines than trust a script, copy the
block from the profile you want below and you are done.

> [!NOTE]
> `claude plugin install a@mkt b@mkt` installs `a` and **silently discards
> `b`**. No error, no warning. One plugin per invocation, always. Verified
> against Claude Code 2.1.220.

## Pick one

| Profile | Plugins | For |
|---|---|---|
| [`daily`](#daily) | warden, sage, cleric | Working solo on a codebase you did not write |
| [`pipeline`](#pipeline) | sage, smith | Specifying a feature and having it built out |
| [`review`](#review) | seer, cleric | Assessing and tidying, without autonomous writing |
| [`unattended`](#unattended) | sellsword, ranger | Work that runs while you are away. Bypasses permissions |
| [`all`](#all) | all nine | You want the crew |

Still unsure? `daily` is the one to take. It is the only profile whose plugins
are all useful on an ordinary Tuesday, and adding the others later costs one
line each.

## Three ways to install one

**Copy and paste.** Every profile below has its literal command block. This
needs no clone, no script and no trust in anything you have not read.

**The script**, if you have the repo cloned:

```bash
./scripts/install-profile.sh daily
./scripts/install-profile.sh --list
./scripts/install-profile.sh unattended --dry-run
```

It prints what it is about to do, warns about the permission-bypassing tools
before it installs them, and tells you the one-time setup each plugin still
needs afterwards. `--dry-run` prints the commands and runs nothing.

There is no `curl ... | bash` one-liner, on purpose. These plugins run code on
your machine, one of them installs hooks that fire on every turn, and a project
shipping that has no business teaching anyone to execute a remote script unread.

**Declaratively**, if you want a project to arrive pre-configured for whoever
clones it. This is the platform-supported route and it is what the script
writes for you. In `.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "the-tavern": {
      "source": { "source": "github", "repo": "gshepptech/the-tavern" }
    }
  },
  "enabledPlugins": {
    "warden@the-tavern": true,
    "sage@the-tavern": true,
    "cleric@the-tavern": true
  }
}
```

Scope matters here. `.claude/settings.json` is committed, so it applies to
everyone who clones the repo. `.claude/settings.local.json` is gitignored and
applies only to you. `~/.claude/settings.json` applies to you in every project,
and is what you get by default. The script takes `--scope user|project|local`
and defaults to `user`, matching the CLI.

Think twice before committing an `enabledPlugins` block containing Warden. It
installs hooks that run on every turn for every one of your colleagues, and
they did not choose that.

---

### daily

**Plugins:** warden, sage, cleric

For someone working alone, most days, on a codebase they did not write and
cannot hold in their head. The recurring problems are Claude confidently
inventing things about code it has not read, changes that need to attach to the
right place, and accumulated cruft getting in the way.

```bash
claude plugin marketplace add gshepptech/the-tavern
claude plugin install warden@the-tavern
claude plugin install sage@the-tavern
claude plugin install cleric@the-tavern
```

**Why these three.** [Warden](../plugins/warden/README.md) is the only plugin that
improves an ordinary turn, and on an unfamiliar codebase the citation verifier
alone earns its place: a `file:line` Claude never opened gets blocked rather
than believed. [Sage](../plugins/sage/README.md) is for the changes big enough
that guessing the attachment point is expensive, which on inherited code is
most of them. [Cleric](../plugins/cleric/README.md) is the periodic sweep, and
`/cleric:run` on its own is a dry run that changes nothing.

**What it leaves out.** Nothing autonomous. No Smith, so nothing builds a spec
out for you unattended. No Sellsword or Ranger, so nothing runs while you are away.
No Scout, so no browser dependency. Seer is left out because it is a
stand-back-and-look tool you reach for a few times a year, not weekly, and
adding it is one line.

**The honest cost.** Warden is not dormant. It installs `UserPromptSubmit` and
`Stop` hooks that run on every prompt and every response, in every project,
from the moment it is installed. With `strict-on` (the default) every response
over 240 characters spawns at least one critic subagent, usually a cheap Haiku
one. `/warden:strict-off` drops the model-calling gates and keeps the
pattern-matching ones. `/warden:off` silences it entirely and persists across
restarts. Sage and Cleric cost nothing until invoked. Cleric will refuse to start
on a dirty git tree, by design.

---

### pipeline

**Plugins:** sage, smith

For someone with a feature to build who wants it specified properly first, then
built out and verified without babysitting each step. This is the pairing the
marketplace is named around.

```bash
claude plugin marketplace add gshepptech/the-tavern
claude plugin install sage@the-tavern
claude plugin install smith@the-tavern
```

**Why these two.** [Sage](../plugins/sage/README.md) writes a locked, typed,
citation-backed spec; [Smith](../plugins/smith/README.md) reads it byte for
byte and builds it. Neither half requires the other, and that is worth knowing
before you install both: Sage's spec is useful whoever builds from it, and
Smith builds from any hand-written spec with numbered requirements in it.
Install this pair when you want the handoff, not because one needs the other.

**What it leaves out.** Warden, which would otherwise add a critic pass to every
turn of what is already an expensive workflow. Scout, which is the natural next
step after a build lands but drags in Node, a browser download and a running
dev server that a Go or Python project will never use. Add Scout when you have a
web app in front of you.

**The honest cost.** This is the most expensive profile to run and the only one
that does not work out of the box. Smith needs `/smith:setup` once per project,
which writes the Playwright MCP server into `.mcp.json` (Smith's own server
ships inside the plugin) and needs `python3` and `uv` on PATH, and
then a restart of Claude Code. A clean three-casting Smith run is roughly
15 to 20 agents, all on the session's model, and the GRIND loop is not bounded by
default: each cycle adds up to three teammates and re-runs the whole
inspect suite until defects hit zero. Set `--max-cycles=N` on your first run
against an unfamiliar codebase. Smith has no approval gates by design, so if
you want to review each step before the next one, this is the wrong tool.

---

### review

**Plugins:** seer, cleric

For someone who wants to understand and tidy an existing codebase, and does not
want anything writing code on its own initiative.

```bash
claude plugin marketplace add gshepptech/the-tavern
claude plugin install seer@the-tavern
claude plugin install cleric@the-tavern
```

**Why these two.** [Seer](../plugins/seer/README.md) answers whether a
subsystem was shaped deliberately or just accreted, with `file:line` evidence
and a reshaping plan, and it never edits anything. [Cleric](../plugins/cleric/README.md)
is the other half: Seer names what is accreted, Cleric clears what is simply
dead. The two are listed as a pairing in the root README for good reason.

**What it leaves out.** Warden, deliberately. Warden would improve these sessions, but
someone who asked for a narrow review set should not silently acquire hooks
that fire on every turn in every project. It is one line to add if you want it.
Everything autonomous is out by definition.

**The honest cost.** Be clear-eyed about one thing: **Cleric does write code.**
`/cleric:run` is a dry run and changes nothing, but `/cleric:apply` auto-applies
HIGH-confidence low-risk changes and commits them, one atomic commit per batch,
running your type checks, tests and lints after each. MEDIUM and LOW findings
wait for you. If "no autonomous writing" means literally nothing may edit the
tree, install Seer alone and use Cleric in dry-run only. Seer fans out a
couple of dozen subagents per review and scales with how messy the target is,
so start narrow: `pkg/auth` or `the diff`, not `the whole repository`. Cleric
refuses to run on a dirty tree or outside a git repo.

---

### unattended

**Plugins:** sellsword, ranger

For someone who wants to set work going and walk away. Read the warning before
you decide.

> [!WARNING]
> **Both of these run with permissions bypassed in their unattended modes.**
> Ranger's headless runner and `/sellsword:goal` execute tools without asking: file
> writes, shell commands, network calls. There is no human present to answer a
> prompt, so nothing prompts. Sellsword reaches real infrastructure over SSH.
> Ranger's git guard still hard-denies push, remote mutation and PR creation,
> but only git is guarded.
>
> Run these in a container, a VM, or a throwaway clone. Not on a machine you
> care about while you are not watching.
>
> Ranger is also **uncapped by default**. `--max-hours=N` is the only flag that
> ends a run on its own. `--max-cycles=N` counts shipped items, so a run that
> keeps reverting spends indefinitely without ever reaching it.
>
> Installing them is safe. Nothing runs until you invoke it. The warning is
> about the first time you type `/ranger:run` or `/sellsword:goal`.

```bash
claude plugin marketplace add gshepptech/the-tavern
claude plugin install sellsword@the-tavern
claude plugin install ranger@the-tavern
```

**Why these two.** They are unattended in two different shapes and neither
substitutes for the other. [Sellsword](../plugins/sellsword/README.md) owns one gnarly
problem to a finish line, usually one that crosses the repo boundary into
deploy config or a box you have to SSH into. [Ranger](../plugins/ranger/README.md)
owns a standing quality sweep with no particular finish line, finding its own
work and shipping one local commit per item.

**What it leaves out.** Smith, which is autonomous but is a different job: it
builds a spec you already have, in your session, under your normal permissions.
If that is what you want, take [`pipeline`](#pipeline). Warden is out because
neither of these runs its work in your session, so a per-turn gate has little
to act on.

**The honest cost.** Every agent in the Sellsword crew is Opus. `/sellsword:do` is five
spawns minimum with recon capped at 30 tool calls and the builder at 120.
`/sellsword:goal` defaults to 15 cycles or 6 hours. Ranger dispatches up to fifteen
agents per cycle to produce one commit, and cycles that do not land work still
spend. Both want a git repo, and Ranger wants a project with tests or a linter
the assessor can actually run, because verification degrades to reading the
diff without one. Start with `/ranger:run <brief> --dry-run` and `/sellsword:do`
before you touch the unattended modes.

---

### all

**Plugins:** sage, smith, warden, sellsword, cleric, scout, tactician, seer, ranger

The whole crew. Reasonable if you are evaluating the marketplace and want to
see everything, or if you already know these tools and want them present.

> [!WARNING]
> This includes Sellsword and Ranger, which **run with permissions bypassed** in
> their unattended modes, and Warden, which installs hooks that run on every turn
> in every project from the moment it is installed. Read the
> [`unattended`](#unattended) warning above. Nothing runs until you invoke it.

```bash
claude plugin marketplace add gshepptech/the-tavern
claude plugin install sage@the-tavern
claude plugin install smith@the-tavern
claude plugin install warden@the-tavern
claude plugin install sellsword@the-tavern
claude plugin install cleric@the-tavern
claude plugin install scout@the-tavern
claude plugin install tactician@the-tavern
claude plugin install seer@the-tavern
claude plugin install ranger@the-tavern
```

**The honest cost.** Every command from all nine appears in your slash-command
list at once, which is a real cost when you are learning them. Two of them
still need per-project setup and a restart before they work (`/smith:setup`,
`/scout:init`). If you are new here, this is the wrong starting point. Take
`daily` and add from there.

---

## The two plugins in no profile

[Scout](../plugins/scout/README.md) and [Tactician](../plugins/tactician/README.md)
appear only in `all`, and that is deliberate rather than an oversight.

**Scout** is shaped by your project, not your habits. She needs `@playwright/test`
installed, several hundred megabytes of browsers downloaded, an MCP server
registered, Claude Code restarted, and a dev server running at a reachable
`baseURL`. That is the correct amount of setup for a web app with flows worth
covering, and pure overhead for anything else. Bundling it into a general
profile would mean most people paying it for nothing. Install her when you have
a web app in front of you: `claude plugin install scout@the-tavern`, then
`/scout:init` inside the project you want to test.

**Tactician** is a meta-tool. It writes multi-agent Workflow scripts you then own
and run, which is a thing you want occasionally and deliberately, never as a
default. It costs nothing to have installed, spawns no subagents while
authoring, and would still be noise in a starter set.

## Changing your mind

Nothing a profile does is sticky. Uninstall anything individually:

```bash
claude plugin uninstall warden@the-tavern
```

Or edit the `enabledPlugins` block in whichever `settings.json` the scope you
chose wrote to. `claude plugin list` shows what you have and at what scope.

## Adding or changing a profile

`scripts/install-profile.sh` is the single source of truth. The `profile_plugins()`
case statement defines every profile; this document is checked against it by
`.github/scripts/check_profiles.py`, which fails CI if they disagree, if a
profile names a plugin the marketplace does not ship, or if a profile containing
Sellsword or Ranger stops repeating the permissions warning.

So: edit the script, add a matching `### name` section here with a
`**Plugins:**` line, and run `python3 .github/scripts/check_profiles.py`.
