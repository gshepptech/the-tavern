# The .questboard contract

An optional shared workspace so the plugins in this marketplace can tell each other what they learned about a project.

Each plugin keeps its own state. Sage writes a spec to `sage-specs/`, Ranger keeps a backlog in `.ranger/runs/`, Cleric files assessments in `.cleric/runs/`, Seer drops casefiles in `.seer/casefiles/`, Sellsword keeps journals in `.sellsword/runs/`. Without a shared place to look, none of them can see any of the others, and a spec reaches a builder only when a person copies the path across.

This contract is the smallest thing that fixes that without breaking the promise the marketplace is built on:

> Every one of them works entirely on its own. Install a single plugin, use it, and never touch the others.

So: **read if present, write if useful.** A plugin that requires `.questboard/` is a bug. A plugin whose behaviour changes when `.questboard/` is absent, empty, or full of garbage is a bug. The workspace is a side channel, and a side channel that can break a run is worse than no side channel at all.

## Contents

- [The directory](#the-directory)
- [The note format](#the-note-format)
- [Kinds](#kinds)
- [The read rule](#the-read-rule)
- [The write rule](#the-write-rule)
- [Concurrency](#concurrency)
- [Malformed and partial files](#malformed-and-partial-files)
- [Declaring participation](#declaring-participation)
- [The reference implementation](#the-reference-implementation)
- [The validator](#the-validator)
- [Who is wired in, and who is not](#who-is-wired-in-and-who-is-not)
- [Writing a new plugin against this](#writing-a-new-plugin-against-this)
- [What this deliberately does not do](#what-this-deliberately-does-not-do)

## The directory

```
.questboard/
  notes/
    20260727T103015Z-sage-a3f4.json
    20260727T141032Z-seer-91bc.json
    20260728T090411Z-ranger-4d02.json
```

At the project root, resolved relative to the current working directory. Every plugin here already resolves its own state that way (`.ranger/`, `.sellsword/`, `.cleric/`, `.seer/`) and every one of them is invoked from the project root. There is no upward search for a `.git` directory, because introducing a second convention would mean two plugins in the same session could disagree about where the workspace is.

One directory, one kind of file. No index, no manifest, no lock file, no per-plugin subdirectory. An index is a shared mutable file, and a shared mutable file is the thing that forces locking. See [Concurrency](#concurrency).

`.questboard/` is **local and disposable**. Deleting it costs nothing but re-discovery. It is not a team artifact, it does not belong in version control, and nothing in it is authoritative about anything. If a finding matters enough to share with people, it belongs in the repo's own docs, not here.

That has one operational consequence worth stating loudly: **a plugin that runs `git clean -fd` will delete an untracked `.questboard/`.** Ranger does exactly that on its reject path, which is why its preflight adds `.questboard/` to `.gitignore` before arming a run, and only if the directory already exists. Any plugin that cleans the tree owes the workspace the same courtesy.

## The note format

One note is one JSON object in one file. Files are named:

```
<created compacted>-<plugin>-<4 hex chars>.json
```

where the compacted timestamp is `YYYYMMDDTHHMMSSZ`. Sorting filenames lexically sorts notes by time. The `id` field is the filename without `.json`.

```json
{
  "questboard": 1,
  "id": "20260727T103015Z-sage-a3f4",
  "kind": "spec",
  "plugin": "sage",
  "created": "2026-07-27T10:30:15Z",
  "title": "Spec sealed: workloads page",
  "summary": "Lists running pods with status and logs. spec_type GREENFIELD, 14 requirements.",
  "paths": ["sage-specs/workloads-page/spec.md"],
  "tags": ["k8s", "ui", "greenfield"]
}
```

| field | required | type | meaning |
|---|---|---|---|
| `questboard` | yes | integer | format version. Currently `1`. |
| `id` | yes | string | non-empty. By convention the filename stem, but nothing enforces that. |
| `kind` | yes | string | one of the [kinds](#kinds). |
| `plugin` | yes | string | lowercase slug matching `^[a-z][a-z0-9-]*$`. Who wrote it. |
| `created` | yes | string | `YYYY-MM-DDTHH:MM:SSZ`. Second-resolution UTC, always with the `Z`. |
| `title` | yes | string | one line. What another tool would need to see in a list. |
| `summary` | no | string | a sentence or three. |
| `paths` | no | array of strings | files this note points at. The first is the primary. Project-relative. |
| `tags` | no | array of strings | free-form. |
| `outcome` | on `attempt` | string | `done`, `abandoned` or `failed`. Required when `kind` is `attempt`. |
| `body` | no | string | longer markdown, if a summary genuinely is not enough. |

**Unknown top-level keys are allowed and must be preserved by anything that copies a note.** A future writer adding a field must not make its notes unreadable to a reader written today. That is the whole reason `questboard` is an integer and not a semver string: readers do an equality check, not a range check, and a note from a version they do not speak is skipped rather than misread.

Notes are **immutable**. Nothing updates a note and nothing deletes one. Superseding information is a new note with a later `created`. This is not fastidiousness: it is what removes read-modify-write from the contract, and read-modify-write is the only operation that would need a lock.

## Kinds

A closed vocabulary of four. A reader that meets a kind it does not know skips the note, so adding one is a change to this document, not a local decision.

| kind | when to write one | what a reader does with it |
|---|---|---|
| `spec` | a written specification now exists on disk | build from it, or know that the work it names is planned rather than missing. `paths[0]` is the spec file. |
| `finding` | something was learned about the project and deliberately not acted on | raw material. Seer calling a subsystem accreted, Cleric listing what it would not auto-apply, Sellsword recording a constraint it hit. |
| `attempt` | a piece of work was tried, and here is how it went | do not re-propose what is `done`. Read the summary before going near what is `abandoned` or `failed`. Requires `outcome`. |
| `other` | none of the above, and it is genuinely worth recording | nothing generic. Name the real kind in the title. |

`other` exists so a plugin is never forced to lie about a kind to record something. If you find yourself writing several `other` notes with the same shape, that is a request to add a kind here.

## The read rule

A reader:

1. Looks for `<root>/.questboard/notes/`. If it does not exist, the result is zero notes. This is not an error, it produces no warning, and it produces no output the user sees. **The reader never creates the directory.**
2. Globs `*.json` and sorts. Newest first is the useful order.
3. Parses each file. If it does not parse, is not an object, is missing a required field, has a field of the wrong type, has an unknown `kind`, or has a `questboard` value it does not speak: **skip that file and continue with the rest.** Do not repair it, do not delete it, do not rename it, do not stop.
4. Never writes anything to `.questboard/` as part of reading.

Absent, empty, and every-note-malformed are three ways of arriving at the same place: an empty list, and a run that behaves exactly as it did before the workspace existed. A reader must not distinguish between them in its behaviour and should not distinguish between them in what it tells the user.

Notes are advisory. **A note is never grounding.** It is somebody's summary of something they saw at some point, in a file nothing keeps up to date. Anything a plugin acts on has to be re-verified against the project as it is now, which is why `resolve` (below) checks that a referenced file still exists before handing back its path, and why Ranger's scout is forbidden from citing `prior_work` as evidence for a backlog item.

## The write rule

A writer:

1. Writes only what a **different tool** could act on. Not progress, not heartbeats, not one note per turn, not a log. If the information is already visible in the git log or in the plugin's own run directory, that is where it lives. The test to apply: would another plugin, reading this six weeks from now, do something different because of it? If not, do not write it.
2. Creates `.questboard/notes/` on demand, then writes to a filename that does not already exist.
3. Writes to a temp file in the same directory and renames it into place, if it has the means to. See [Concurrency](#concurrency).
4. **Never fails the run over a failed write.** Read-only checkout, full disk, permission denied, no interpreter: log one line to stderr and carry on. A lost note costs a later run some re-discovery. An aborted build costs the user their afternoon.

Rule 4 is worth being blunt about, because it is the one that gets violated by accident. `questboard.py write` exits 0 whether or not it wrote anything, and every plugin wired below is told in its own command file that a non-zero exit or a line on stderr from that command is to be ignored rather than retried, reported or acted on.

## Concurrency

Two plugins running at once is normal, not exotic. Ranger dispatches Cleric and Seer from inside a cycle; a user can have `/sellsword:goal` running in one terminal and `/sage:plan` in another.

The contract handles it by having nothing to contend over:

- **Every write creates a new file.** The name is built from the timestamp, the writing plugin's name and two random bytes, so two writers never target the same path. There is no append, no merge and no shared index.
- **No reader ever modifies.** There is no read-modify-write cycle anywhere in the contract, so there is nothing a lock would protect.
- **Notes are immutable**, so a reader that read a note a second ago still holds something true.
- **The rename makes a write atomic.** A reader globbing mid-write sees the finished file or does not see the file, never half of one. `os.replace` within a single directory is atomic on POSIX and on Windows.

There is no lock file, and adding one would be a mistake: a lock file is state that outlives a crashed process, and the failure mode of a stale lock in an unattended overnight run is much worse than the failure mode this design has.

That design has exactly one soft spot, and it is deliberate. A plugin that writes with an editor tool rather than with `questboard.py` cannot rename atomically. Sellsword, Cleric and Seer are in that position: they have `Write` and no reason to shell out. A reader that globs during one of those writes can see a truncated file. That is safe, because rule 3 of the read rule skips it, and the next read sees the finished note. It costs one read, once, in a race that is already unlikely. It is the reason skip-on-malformed is load-bearing rather than defensive.

**Ordering.** `created` is second-resolution, so two notes written in the same second have no defined order. No plugin may depend on a total order. Newest-first is a heuristic for relevance, not a guarantee about causality.

## Malformed and partial files

At runtime, a malformed file is skipped and nothing is said about it. That is not sloppiness, it is the read rule doing its job: an optional side channel must not be able to fail a run, and there is no user-facing action a mid-run warning would prompt.

Being loud is [the validator's](#the-validator) job, and only the validator's job. It is the one entry point that exits non-zero, and nothing invokes it during a run.

The two cases behave differently in one respect worth knowing:

- **A partial file** (a write in flight) is transient. The next read sees it whole. Nothing needs to happen.
- **A permanently malformed file** (hand-edited, truncated by a crash, written by a buggy plugin) is skipped on every read forever. It is invisible until someone runs the validator, at which point the fix is to delete it. Nothing in the workspace is worth recovering.

## Declaring participation

A participating plugin ships `plugins/<name>/questboard.json`:

```json
{
  "questboard": 1,
  "plugin": "ranger",
  "reads": ["spec", "finding", "attempt"],
  "writes": ["attempt"]
}
```

| field | meaning |
|---|---|
| `questboard` | format version, `1`. |
| `plugin` | must match the directory name and the plugin's manifest name. |
| `reads` | kinds this plugin consumes. May be empty. |
| `writes` | kinds this plugin produces. May be empty. |

At least one of `reads` and `writes` must be non-empty, or the plugin does not participate and should not ship the file.

**Nothing reads this file at runtime.** It is not configuration and it is not a capability check: a plugin does not consult its own declaration before reading or writing, because that would be a second source of truth for behaviour that is already in its command files. The declaration exists so the participant set is legible without grepping six command files, and so the validator has something to check against.

A participating plugin also documents the same thing in prose, in a `## Shared workspace (optional)` section of its own README, saying what it reads, what it writes, and that it behaves identically when `.questboard/` is absent. A user who installed one plugin should never have to read this document to understand what that plugin does to their project.

## The reference implementation

`questboard.py` is the executable half of this contract. It ships in three plugins:

- `plugins/sage/scripts/questboard.py`
- `plugins/smith/scripts/questboard.py`
- `plugins/ranger/scripts/questboard.py`

**The three copies are byte-identical, and that duplication is intentional.** Sage cannot import from Ranger, because a user who installed only Sage does not have Ranger on disk. The alternatives were a base plugin everyone installs first, which breaks the independence promise outright, or a runtime download, which is worse. Vendoring is the cheapest option that keeps every plugin standalone. Drift is caught by a test in each of the three plugins that hashes every copy it can find in the repo and asserts they agree.

```
questboard.py read     [--kind K] [--limit N]   valid notes as JSON, newest first
questboard.py write    --plugin P --kind K --title T [--summary S] [--path P]...
                   [--tag T]... [--outcome O] [--body-file F]
questboard.py resolve  [--kind K]               newest still-existing artifact path
questboard.py validate [--declarations DIR]     report malformed files
```

All four take `--root DIR` (default: the current directory).

`resolve` deserves its own name rather than being a flag on `read`, because it is a distinct operation: give me the newest note of this kind whose primary path **still exists on disk**. Notes are never deleted, so the workspace accumulates references to files the user has since moved or removed, and a stale reference silently redirecting a build is the obvious way this design could hurt someone. `resolve` prints nothing and exits 0 when there is no match, which is what makes it safe to call from a `set -e` shell script.

`read`, `write` and `resolve` **always exit 0** unless the arguments themselves are invalid, in which case argparse exits 2. There is no runtime condition under which they exit 1.

The three plugins that do not ship `questboard.py` write their notes with the `Write` tool from a template in their own command file. They read nothing, so they need no globbing, no parsing and no skip logic, and adding a Python dependency to a plugin that ships no code today would be a real cost for no gain.

## The validator

```bash
python3 plugins/sage/scripts/questboard.py validate
python3 plugins/sage/scripts/questboard.py validate --declarations plugins
```

The first checks every note in `./.questboard/notes/` and names each malformed file with the reason. The second additionally checks every `plugins/*/questboard.json` participation declaration, including that each one names the directory it lives in.

Exit 0 clean, exit 1 with a list of problems, in the same shape as the repo's other validators under `.github/scripts/`.

This is the only place a malformed file is ever reported. Running it is a deliberate act by a person who wants to know, which is the right shape for a workspace whose worst-case failure is that a plugin re-discovers something.

## Who is wired in, and who is not

Six of the ten participate. For the other four, taking part would be symmetry for its own sake.

### Wired in

**Sage writes `spec`.** The producing half of the spec-to-build handoff, which would otherwise need a person to pass the path along. When a spec seals, Sage writes one note pointing at `spec.md`. Nothing else about `/sage:plan` changes, and the note is written after the deterministic gate has already passed, so a workspace problem cannot affect whether a spec seals.

**Smith reads `spec` and writes `attempt`.** The consuming half. When `/smith:build` is given no spec path, it asks the workspace for the newest spec that still exists and builds from that, announcing the path in one line so the user can stop it if it picked wrong. An explicit path always wins and the workspace is not consulted at all. With no workspace, `/smith:build` without a path asks for one. When a run ends, Smith writes one `attempt` note pointing at its report, with outcome `done` or `failed`.

**Ranger reads every kind, and writes `attempt`.** The clearest case in the set. Ranger's whole design problem is not running out of work without inventing churn, and its `backlog_done` only covers the current run. `prior_work` gives its scouts what the project has already tried across runs and across plugins. It writes an `attempt` on every committed item and, more usefully, on every quarantined one: a finished item is visible in the git log, but three failed attempts at the same thing are visible nowhere else and are exactly what the next run needs before proposing it again.

**Sellsword writes `finding`.** Sellsword is the plugin that goes outside the repo, which makes it the plugin most likely to learn something the repo does not record. `/sellsword:goal` is unattended, so a chat debrief nobody reads is the only other place that knowledge goes. Sellsword already reads optional `.sellsword/hosts.yml` and `.sellsword/access.yml` if they happen to exist, so read-if-present is already its idiom. It carries an explicit rule against putting hostnames, credentials or anything from `access.yml` into a note.

**Cleric writes `finding`.** Cleric's defining behaviour is restraint: it auto-applies only high-confidence changes and deliberately leaves MEDIUM, LOW and UNCERTAIN items alone. Those held-back items are the single most re-discovered thing in this repo's tool set, and a note pointing at the assessment files stops the next tool starting from zero. A sweep that held nothing back writes nothing.

**Seer writes `finding`.** Seer is report-only by design, so its output has no other route into anything. A structural verdict dies in `.seer/casefiles/` unless a human reads it and acts. A note carrying the verdict and the casefile path is the only thing that gets "this subsystem is accreted" in front of the tool that is about to work on it. Nothing is written when no finding survived cross-examination, because an empty verdict is not actionable.

### Not wired in

**Warden** operates on a single conversational turn. It has no project-level knowledge to contribute and nothing in the workspace would change how it gates a response. Wiring it would mean either a note per turn, which is exactly the log this contract forbids, or a write that never fires.

**Scout** produces `*.spec.ts` files in the repository. Those are already visible to every tool that can list a directory, and they are the actual artifact rather than a summary of one. A note would restate what `ls tests/` says, and would go stale the first time someone edits a spec.

**Tactician** generates a standalone Workflow script and hands it over. It learns nothing about the project in the process and consumes nothing that would help it. There is no note it could honestly write.

**Tinker** always takes an explicit spec path and records everything about a run in its own `tinker-archive/<run>/` directory and on its `tinker/<run>` branch. It checks a Sage seal by reading the spec file itself, so it needs nothing from the workspace.

## Writing a new plugin against this

To read:

1. Look for `.questboard/notes/*.json` relative to the project root. If the directory is not there, you have zero notes. Stop looking.
2. Parse each file. Skip anything that does not parse, is not an object, is missing `questboard`, `id`, `kind`, `plugin`, `created` or `title`, has `questboard != 1`, has a `kind` outside the four, or has `kind == "attempt"` without a valid `outcome`.
3. Filter to the kinds you care about. Sort by filename descending for newest-first.
4. Treat what you get as advisory. Re-verify anything you act on.
5. Behave identically when the list is empty. Say nothing to the user about the workspace.

To write:

1. Decide whether a *different* tool would act differently because of this. If not, do not write.
2. `mkdir -p .questboard/notes`.
3. Build the object. `questboard: 1`, an ISO-8601 UTC `created` with second resolution, your plugin's slug, one-line title, and the optional fields you can fill honestly.
4. Write it to `<created compacted>-<your plugin>-<4 hex>.json`. If you can write-then-rename, do. If you cannot, write directly and accept that a reader may briefly see a partial file.
5. If any of that fails, drop it and continue. Never retry in a loop, never surface it to the user, never let it change your exit status.

Then ship `plugins/<you>/questboard.json`, add a `## Shared workspace (optional)` section to your README, and run `questboard.py validate --declarations plugins` before you open the pull request.

You do not need to ask anyone about any of this, and you do not need `questboard.py`. The format is the contract; the helper is one implementation of it.

## What this deliberately does not do

- **No schema evolution machinery.** One integer version, equality check, skip on mismatch. If v2 is ever needed, v1 readers skip v2 notes and keep working, which is the only compatibility guarantee worth having here.
- **No querying.** Read everything, filter in the caller. The workspace holds tens of notes, not thousands. If it ever holds thousands, something upstream is writing a log and should stop.
- **No deletion or compaction.** The user deletes `.questboard/` when they want it gone. Automatic pruning means a tool deciding on the user's behalf which of another tool's records are stale, and nothing here knows enough to make that call.
- **No cross-plugin invocation.** A note is data. It never names a command to run, and no reader may treat a note's contents as an instruction. Notes are written by other tools, and a tool that executes what another tool wrote in a file is a much larger design than this one.
- **No promises about ordering, completeness or freshness.** The workspace is best-effort by construction. Every plugin here has to work when it is empty, which means every plugin here works when it is wrong.
