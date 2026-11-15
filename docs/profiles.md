# Install profiles

Fifteen regulars is fifteen decisions, and nobody walking into the tavern for the
first time has the information to make them. A profile is a named party of
plugins that gets you a sensible setup in one step, so you can start working and
hire the rest when you find out you want them.

Nothing here replaces installing one plugin on its own. That is still the
supported path, still the first-class path, and every plugin still works with
none of the others present. A profile is a shortcut for people who do not yet
have an opinion, not a bundle you are expected to buy into.

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
claude plugin install sage@the-tavern
claude plugin install smith@the-tavern
claude plugin install warden@the-tavern
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
| [`builder`](#builder) | sage, smith, warden | Specifying a feature and having it built out and verified |
| [`lean`](#lean) | sage, tinker, squire | The same pipeline with fewer agents, for small and medium work |
| [`solo`](#solo) | sellsword, warden, monk | Handing one hard problem to a single owner. Bypasses permissions in `/sellsword:goal` |
| [`review`](#review) | seer, cleric, bard | Assessing structure, tidying code and testing the UX |
| [`unattended`](#unattended) | sellsword, ranger, raven | Work that runs while you are away. Bypasses permissions |
| [`full`](#full) | all fifteen | You want every regular in the tavern |

Still unsure? Take `lean` if you build features, `review` if you inherited a
codebase. Adding a regular later costs one line.

## Three ways to install one

**Copy and paste.** Every profile below has its literal command block. This
needs no clone, no script and no trust in anything you have not read.

**The script**, if you have the repo cloned:

```bash
./scripts/install-profile.sh builder
./scripts/install-profile.sh --list
./scripts/install-profile.sh unattended --dry-run
```

It prints what it is about to do, warns about the permission-bypassing tools
before it installs them, and tells you the one-time setup each plugin still
needs afterwards. `--dry-run` prints the commands and runs nothing.

There is no `curl ... | bash` one-liner, on purpose. These plugins run code on
your machine, several of them install hooks that fire on every turn, and a
project shipping that has no business teaching anyone to execute a remote
script unread.

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
    "sage@the-tavern": true,
    "smith@the-tavern": true,
    "warden@the-tavern": true
  }
}
```

Scope matters here. `.claude/settings.json` is committed, so it applies to
everyone who clones the repo. `.claude/settings.local.json` is gitignored and
applies only to you. `~/.claude/settings.json` applies to you in every project,
and is what you get by default. The script takes `--scope user|project|local`
and defaults to `user`, matching the CLI.

Think twice before committing an `enabledPlugins` block containing Warden, Monk
or Raven. Each installs hooks that run for every one of your colleagues, and
they did not choose that.

---

### builder

**Plugins:** sage, smith, warden

For someone with a feature to build who wants it specified properly first, then
built out and verified without babysitting each step.

```bash
claude plugin marketplace add gshepptech/the-tavern
claude plugin install sage@the-tavern
claude plugin install smith@the-tavern
claude plugin install warden@the-tavern
```

**Why these three.** [Sage](../plugins/sage/README.md) writes a sealed spec with
numbered requirements, testable acceptance criteria and a cited source for each.
[Smith](../plugins/smith/README.md) splits it into slices, builds them in
parallel and has independent verifiers check every requirement. With both
installed, `/smith:build` with no argument picks up the spec Sage sealed most
recently. [Warden](../plugins/warden/README.md) covers the turns between the
two: the conversation where you read the spec, ask about the code and decide
what to change. Its citation verifier blocks a `file:line` Claude never opened
rather than letting you believe it.

Neither half of the pipeline requires the other. Sage's spec is useful whoever
builds from it, and Smith builds from any hand-written spec with requirement
IDs in it.

**What it leaves out.** Scout and Bard, which are the natural next step after a
build lands but drag in Node, a browser download and a running dev server that a
Go or Python project will never use. Add them when you have a web app in front
of you.

**The honest cost.** This is an expensive profile to run. Sage's interview needs
you present. Smith spawns one planner, one builder per slice, verifiers and
fixers, running up to `--max-parallel` agents at once (default 4) for up to
`--max-rounds` fix rounds (default 3). Lower both on your first run against an
unfamiliar codebase. Smith needs `python3`, a git repository and a clean working
tree; it builds on its own `smith/<run>` branch and never pushes. Warden is not
dormant: it installs `UserPromptSubmit` and `Stop` hooks that run on every
prompt and every response, in every project, and with `strict-on` (the default)
every response over 240 characters spawns at least one critic subagent, usually
a cheap Haiku one. `/warden:strict-off` drops the model-calling gates and keeps
the pattern-matching ones. `/warden:off` silences it entirely.

---

### lean

**Plugins:** sage, tinker, squire

The same spec-then-build shape as `builder`, sized down. For features one
builder can carry, and for teams that want a capped, predictable number of
agent calls per build.

```bash
claude plugin marketplace add gshepptech/the-tavern
claude plugin install sage@the-tavern
claude plugin install tinker@the-tavern
claude plugin install squire@the-tavern
```

**Why these three.** [Sage](../plugins/sage/README.md) writes the spec.
[Tinker](../plugins/tinker/README.md) builds it with one builder, a code check
beside one spec-to-code checker, and at most two batched fix rounds.
[Squire](../plugins/squire/README.md) is smaller again: one test-first builder,
a verifier that sees only the spec and the code, and a fixer limited to the
listed gaps, for a spec of up to about fifteen requirements. Between them they
cover the afternoon-sized change and the hour-sized feature.

**What it leaves out.** Smith, whose parallel slices and evidence ledger are
worth their cost on a large spec and overkill on a small one. Warden, which adds
a critic pass to every turn of a session whose main work is already being
verified by the build tools. Both are one line to add.

**The honest cost.** Tinker and Squire both run as scripts for Claude Code's
Workflow tool, so your Claude Code version needs Workflow available. Both want a
git repository with a clean working tree, work on their own `tinker/<run>`
or `squire/<run>` branch and never push. A clean first Squire round is five
agent calls; each fix round adds three.

---

### solo

**Plugins:** sellsword, warden, monk

For someone with one hard problem who wants a single owner to see it through:
investigate, plan, execute and prove the outcome, often across the repo
boundary into deploy config or a box you have to SSH into.

> [!WARNING]
> **`/sellsword:goal` runs with permissions bypassed.** It executes tools
> without asking: file writes, shell commands, network calls, SSH into real
> infrastructure. There is no human present to answer a prompt, so nothing
> prompts. The attended `/sellsword:do` asks before side effects; start there.
>
> Installing it is safe. Nothing runs until you invoke it.

```bash
claude plugin marketplace add gshepptech/the-tavern
claude plugin install sellsword@the-tavern
claude plugin install warden@the-tavern
claude plugin install monk@the-tavern
```

**Why these three.** [Sellsword](../plugins/sellsword/README.md) owns the
problem: five agents investigate, plan, execute and verify, with two independent
verifiers that must both pass. [Warden](../plugins/warden/README.md) keeps the
conversation around it honest, so the questions you ask before and after a run
get answers grounded in files Claude actually opened.
[Monk](../plugins/monk/README.md) keeps every reply short, which matters most
when you are reading a debrief at the end of a long run and want the outcome in
the first line.

**What it leaves out.** Ranger, which is unattended in a different shape: a
standing sweep that finds its own work, not one problem with a finish line. Take
[`unattended`](#unattended) for that.

**The honest cost.** Every agent Sellsword hires is Opus. `/sellsword:do` is
five spawns minimum, with recon capped at 30 tool calls and the builder at 120.
`/sellsword:goal` defaults to 15 cycles or 6 hours. Its preflight refuses to
start while Warden's strict gates are on, because an unattended run cannot
answer an interactive block, so run `/warden:strict-off` first. Monk installs
`SessionStart`, `UserPromptSubmit` and `Stop` hooks and is on in every new
session; `/monk:off` turns it off for one session.

---

### review

**Plugins:** seer, cleric, bard

For someone who wants to understand and tidy an existing codebase, and see how
the running app treats its users, without anything building features on its
own initiative.

```bash
claude plugin marketplace add gshepptech/the-tavern
claude plugin install seer@the-tavern
claude plugin install cleric@the-tavern
claude plugin install bard@the-tavern
```

**Why these three.** [Seer](../plugins/seer/README.md) answers whether a
subsystem was shaped deliberately or just accreted, with `file:line` evidence
and a reshaping plan, and it never edits anything.
[Cleric](../plugins/cleric/README.md) is the other half: Seer names what is
accreted, Cleric clears what is simply dead. [Bard](../plugins/bard/README.md)
looks at the same product from the outside, using it in a real browser as named
personas and writing a ranked report where every finding has steps to
reproduce and a screenshot.

**What it leaves out.** Warden, deliberately. Someone who asked for a review set
should not silently acquire hooks that fire on every turn in every project.
Everything autonomous is out by definition.

**The honest cost.** **Cleric does write code.** `/cleric:run` is a dry run and
changes nothing, but `/cleric:apply` auto-applies high-confidence low-risk
changes and commits them, one atomic commit per batch, running your type
checks, tests and lints after each. If "review" means literally nothing may edit
the tree, use Cleric in dry-run only. Seer fans out a couple of dozen subagents
per review and scales with how messy the target is, so start narrow. Bard needs
the Playwright MCP server, Node.js and a running instance of the app; point it
at development or staging, because its personas submit forms with fake data
unless you pass `--read-only`.

---

### unattended

**Plugins:** sellsword, ranger, raven

For someone who wants to set work going and walk away. Read the warning before
you decide.

> [!WARNING]
> **Sellsword and Ranger run with permissions bypassed in their unattended
> modes.** Ranger's headless runner and `/sellsword:goal` execute tools without
> asking: file writes, shell commands, network calls. There is no human present
> to answer a prompt, so nothing prompts. Sellsword reaches real infrastructure
> over SSH. Ranger's git guard still hard-denies push, remote mutation and PR
> creation, but only git is guarded.
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
claude plugin install raven@the-tavern
```

**Why these three.** Sellsword and Ranger are unattended in two different shapes
and neither substitutes for the other. [Sellsword](../plugins/sellsword/README.md)
owns one hard problem to a finish line. [Ranger](../plugins/ranger/README.md)
owns a standing quality sweep with no particular finish line, finding its own
work and shipping one local commit per item. [Raven](../plugins/raven/README.md)
posts to Slack when a Claude Code session finishes a reply or is waiting for
you, which is the message you want from a session you walked away from.

**What it leaves out.** Smith, Tinker and Squire, which are autonomous but do a
different job: they build a spec you already have, in your session, under your
normal permissions. If that is what you want, take [`builder`](#builder) or
[`lean`](#lean). Warden is out because neither of these runs its work in your
session, so a per-turn gate has little to act on.

**The honest cost.** Every agent Sellsword hires is Opus. `/sellsword:goal`
defaults to 15 cycles or 6 hours. Ranger dispatches up to fifteen agents per
cycle to produce one commit, and cycles that do not land work still spend. Both
want a git repo, and Ranger wants a project with tests or a linter the assessor
can actually run, because verification degrades to reading the diff without
one. Raven needs a Slack incoming webhook exported as `RAVEN_SLACK_WEBHOOK_URL`
and sends nothing without it. Start with `/ranger:run <brief> --dry-run` and
`/sellsword:do` before you touch the unattended modes.

---

### full

**Plugins:** sage, smith, tinker, squire, sellsword, ranger, warden, seer, cleric, scout, bard, tactician, scribe, raven, monk

Every regular in the tavern. Reasonable if you are evaluating the marketplace
and want to see everything, or if you already know these tools and want them
present.

> [!WARNING]
> This includes Sellsword and Ranger, which **run with permissions bypassed** in
> their unattended modes, and Warden, Monk and Raven, which install hooks that
> run in every project from the moment they are installed. Read the
> [`unattended`](#unattended) warning above. Nothing runs until you invoke it.

```bash
claude plugin marketplace add gshepptech/the-tavern
claude plugin install sage@the-tavern
claude plugin install smith@the-tavern
claude plugin install tinker@the-tavern
claude plugin install squire@the-tavern
claude plugin install sellsword@the-tavern
claude plugin install ranger@the-tavern
claude plugin install warden@the-tavern
claude plugin install seer@the-tavern
claude plugin install cleric@the-tavern
claude plugin install scout@the-tavern
claude plugin install bard@the-tavern
claude plugin install tactician@the-tavern
claude plugin install scribe@the-tavern
claude plugin install raven@the-tavern
claude plugin install monk@the-tavern
```

**The honest cost.** Every command from all fifteen appears in your
slash-command list at once, which is a real cost when you are learning them.
Scout and Bard still need per-project browser setup, and Raven still needs a
webhook. If you are new here, this is the wrong starting point. Take a smaller
profile and add from there.

---

## The plugins in no smaller profile

[Scout](../plugins/scout/README.md), [Tactician](../plugins/tactician/README.md)
and [Scribe](../plugins/scribe/README.md) appear only in `full`, and that is
deliberate rather than an oversight.

**Scout** is shaped by your project, not your habits. It needs
`@playwright/test` installed, several hundred megabytes of browsers downloaded,
an MCP server registered, Claude Code restarted, and a dev server running at a
reachable `baseURL`. That is the correct amount of setup for a web app with
flows worth covering, and pure overhead for anything else. Install it when you
have a web app in front of you: `claude plugin install scout@the-tavern`, then
`/scout:init` inside the project you want to test.

**Tactician** is a meta-tool. It writes multi-agent Workflow scripts you then own
and run, which is a thing you want occasionally and deliberately, never as a
default.

**Scribe** is for the point where a project needs documentation, which is a
task you take on once and revisit, not a habit. `/scribe:audit` is useful on any
repository with docs, so it is worth one line when you get there.

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
