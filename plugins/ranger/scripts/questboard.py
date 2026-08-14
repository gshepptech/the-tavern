#!/usr/bin/env python3
"""Reference implementation of the .questboard shared workspace contract.

The contract is specified in docs/questboard-contract.md. Read that first. This
file is the executable half: the exact behaviour every participating plugin
agrees to, so that "read if present, write if useful" means the same thing in
all of them.

WHY THIS FILE IS DUPLICATED

Every plugin in this marketplace installs on its own. Sage cannot import from
Ranger, because a user who installed only Sage does not have Ranger on disk.
So the shared code is vendored: an identical copy of this file ships in each
participating plugin's scripts/ directory, and a test in each of those plugins
asserts the copies have not drifted. Duplication is the price of the
independence promise, and it is cheaper than the alternative, which is a base
plugin everyone has to install first.

WHAT IT DOES

    questboard.py read     list the valid notes, newest first, as JSON
    questboard.py write    add one note
    questboard.py resolve  print the newest still-existing artifact of a kind
    questboard.py validate report every malformed file, and exit 1 if there are any

Two rules govern everything here:

  1. A missing or malformed workspace is never an error at runtime. `read` and
     `resolve` on an absent .questboard/ print an empty result and exit 0. A note
     that does not parse is skipped, not repaired and not deleted. A plugin
     must behave exactly as it did before the workspace existed.

  2. A failed write never fails the caller. `write` exits 0 even when it could
     not write, and says why on stderr. Losing a note costs a later run some
     re-discovery. Aborting a build because a side channel was read-only is a
     much worse trade.

Loudness is `validate`'s job, and only `validate`'s job. It is the one
subcommand that exits non-zero, and nothing invokes it during a run.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

FORMAT_VERSION = 1

# Closed vocabulary. `other` is the escape hatch: name the real kind in the
# title. A reader that meets an unknown kind skips the note, so adding a kind
# is a contract change, not a local decision.
KINDS = ("spec", "finding", "attempt", "other")

# Only meaningful on kind == "attempt", where it is required. Without it an
# attempt note cannot answer the question it exists to answer, which is
# "has someone already tried this, and how did it go?"
OUTCOMES = ("done", "abandoned", "failed")

REQUIRED_STRING_KEYS = ("id", "kind", "plugin", "created", "title")
STRING_LIST_KEYS = ("paths", "tags")
OPTIONAL_STRING_KEYS = ("summary", "body", "outcome")

# Second-resolution UTC, always with the trailing Z. Two notes written in the
# same second have no defined order, which is why nothing may depend on a
# total ordering of the workspace.
CREATED_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

PLUGIN_RE = re.compile(r"^[a-z][a-z0-9-]*$")


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def workspace(root: str | Path | None = None) -> Path:
    """The .questboard directory for a project root (default: the cwd).

    Every plugin in this repo resolves its own state directory relative to the
    cwd (.ranger/, .sellsword/, .cleric/, .seer/), and they are all invoked from
    the project root. This follows the same convention rather than inventing a
    second one by walking up for a .git directory.
    """
    return Path(root or Path.cwd()) / ".questboard"


def notes_dir(root: str | Path | None = None) -> Path:
    return workspace(root) / "notes"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def note_problems(obj: object) -> list[str]:
    """Every reason `obj` is not a valid v1 note. Empty list means valid.

    Unknown top-level keys are deliberately allowed. A v2 writer adding a
    field must not make its notes unreadable to a v1 reader.
    """
    if not isinstance(obj, dict):
        return ["not a JSON object"]

    problems: list[str] = []

    version = obj.get("questboard")
    if version != FORMAT_VERSION:
        # Reported first and on its own: a note from a future format version is
        # not corrupt, it is just not ours. Listing its other "problems" would
        # be noise.
        return [f"unknown format version {version!r} (this reader speaks {FORMAT_VERSION})"]

    for key in REQUIRED_STRING_KEYS:
        value = obj.get(key)
        if not isinstance(value, str) or not value.strip():
            problems.append(f"missing or empty required key {key!r}")

    kind = obj.get("kind")
    if isinstance(kind, str) and kind not in KINDS:
        problems.append(f"unknown kind {kind!r} (expected one of {', '.join(KINDS)})")

    plugin = obj.get("plugin")
    if isinstance(plugin, str) and plugin and not PLUGIN_RE.match(plugin):
        problems.append(f"plugin {plugin!r} is not a lowercase slug")

    created = obj.get("created")
    if isinstance(created, str) and created and not CREATED_RE.match(created):
        problems.append(f"created {created!r} is not YYYY-MM-DDTHH:MM:SSZ")

    if kind == "attempt":
        outcome = obj.get("outcome")
        if outcome not in OUTCOMES:
            problems.append(
                f"kind 'attempt' requires outcome in {', '.join(OUTCOMES)}, got {outcome!r}"
            )

    for key in STRING_LIST_KEYS:
        if key in obj:
            value = obj[key]
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                problems.append(f"{key!r} must be a list of strings")

    for key in OPTIONAL_STRING_KEYS:
        if key in obj and not isinstance(obj[key], str):
            problems.append(f"{key!r} must be a string")

    return problems


def declaration_problems(obj: object) -> list[str]:
    """Every reason `obj` is not a valid participation declaration.

    A participating plugin ships plugins/<name>/questboard.json saying which kinds
    it reads and which it writes. Nothing consults it during a run. It exists
    so the participant set is legible without grepping six command files.
    """
    if not isinstance(obj, dict):
        return ["not a JSON object"]

    problems: list[str] = []

    if obj.get("questboard") != FORMAT_VERSION:
        return [f"unknown format version {obj.get('questboard')!r}"]

    plugin = obj.get("plugin")
    if not isinstance(plugin, str) or not PLUGIN_RE.match(plugin or ""):
        problems.append(f"plugin {plugin!r} is not a lowercase slug")

    for key in ("reads", "writes"):
        value = obj.get(key)
        if not isinstance(value, list):
            problems.append(f"{key!r} must be a list of kinds")
            continue
        for kind in value:
            if kind not in KINDS:
                problems.append(f"{key!r} names unknown kind {kind!r}")

    if not obj.get("reads") and not obj.get("writes"):
        problems.append("declares neither reads nor writes, so it does not participate")

    return problems


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def read_notes(root: str | Path | None = None, kind: str | None = None) -> list[dict]:
    """Valid notes, newest first. Malformed and unreadable files are skipped.

    An absent workspace yields an empty list. This function never creates a
    directory, never writes, and never raises for anything it finds on disk.
    """
    directory = notes_dir(root)
    try:
        candidates = sorted(directory.glob("*.json"), reverse=True)
    except OSError:
        return []

    notes: list[dict] = []
    for path in candidates:
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            # A half-written file from a plugin that writes with an editor tool
            # rather than this helper looks exactly like this. Skipping is what
            # makes that safe: the next read sees the finished file.
            continue
        if note_problems(obj):
            continue
        if kind is not None and obj.get("kind") != kind:
            continue
        notes.append(obj)
    return notes


def resolve_artifact(
    root: str | Path | None = None, kind: str = "spec"
) -> str | None:
    """The newest note of `kind` whose first path still exists on disk.

    Notes are never rewritten or deleted, so the workspace accumulates
    references to files a user has since moved or removed. Checking existence
    here is what keeps a stale note from silently redirecting a build.
    """
    base = Path(root or Path.cwd())
    for note in read_notes(root, kind=kind):
        paths = note.get("paths") or []
        if not paths:
            continue
        candidate = Path(paths[0])
        absolute = candidate if candidate.is_absolute() else base / candidate
        if absolute.exists():
            return paths[0]
    return None


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


def _note_filename(created: str, plugin: str) -> str:
    compact = created.replace("-", "").replace(":", "")
    return f"{compact}-{plugin}-{secrets.token_hex(2)}.json"


def write_note(
    plugin: str,
    kind: str,
    title: str,
    *,
    root: str | Path | None = None,
    summary: str | None = None,
    paths: list[str] | None = None,
    tags: list[str] | None = None,
    outcome: str | None = None,
    body: str | None = None,
) -> Path | None:
    """Write one note. Returns its path, or None if it could not be written.

    Two writers never contend for a filename, because every note gets a fresh
    one built from the timestamp, the plugin name and two random bytes. That
    is the whole concurrency design: no shared mutable file means no lock.

    The write goes to a temp file in the same directory and is then renamed
    into place, so a concurrent reader sees the note or does not see it, never
    half of it.
    """
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    directory = notes_dir(root)

    for _ in range(5):
        name = _note_filename(created, plugin)
        target = directory / name
        note = {
            "questboard": FORMAT_VERSION,
            "id": name[: -len(".json")],
            "kind": kind,
            "plugin": plugin,
            "created": created,
            "title": title,
        }
        if summary:
            note["summary"] = summary
        if paths:
            note["paths"] = list(paths)
        if tags:
            note["tags"] = list(tags)
        if outcome:
            note["outcome"] = outcome
        if body:
            note["body"] = body

        problems = note_problems(note)
        if problems:
            # A caller-side mistake, not a disk problem. Worth being loud about
            # on stderr, but still not worth failing the run for.
            print(f"questboard: refusing to write an invalid note: {problems[0]}", file=sys.stderr)
            return None

        if target.exists():
            continue

        try:
            directory.mkdir(parents=True, exist_ok=True)
            temp = directory / f".{name}.tmp"
            temp.write_text(json.dumps(note, indent=2) + "\n", encoding="utf-8")
            os.replace(temp, target)
        except OSError as exc:
            print(f"questboard: could not write note ({exc}); continuing", file=sys.stderr)
            return None
        return target

    print("questboard: could not find a free note filename; continuing", file=sys.stderr)
    return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def cmd_read(args: argparse.Namespace) -> int:
    notes = read_notes(args.root, kind=args.kind)
    if args.limit:
        notes = notes[: args.limit]
    json.dump(notes, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def cmd_write(args: argparse.Namespace) -> int:
    body = None
    if args.body_file:
        try:
            body = Path(args.body_file).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"questboard: could not read --body-file ({exc}); continuing", file=sys.stderr)
    path = write_note(
        args.plugin,
        args.kind,
        args.title,
        root=args.root,
        summary=args.summary,
        paths=args.path,
        tags=args.tag,
        outcome=args.outcome,
        body=body,
    )
    if path is not None:
        print(path)
    return 0


def cmd_resolve(args: argparse.Namespace) -> int:
    found = resolve_artifact(args.root, kind=args.kind)
    if found:
        print(found)
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    problems: list[str] = []
    checked = 0

    directory = notes_dir(args.root)
    if directory.is_dir():
        for path in sorted(directory.glob("*.json")):
            checked += 1
            try:
                obj = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, UnicodeDecodeError) as exc:
                problems.append(f"{path}: unreadable or not JSON ({exc})")
                continue
            for problem in note_problems(obj):
                problems.append(f"{path}: {problem}")

    declared = 0
    if args.declarations:
        for path in sorted(Path(args.declarations).glob("*/questboard.json")):
            declared += 1
            try:
                obj = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, UnicodeDecodeError) as exc:
                problems.append(f"{path}: unreadable or not JSON ({exc})")
                continue
            for problem in declaration_problems(obj):
                problems.append(f"{path}: {problem}")
            if isinstance(obj, dict) and obj.get("plugin") != path.parent.name:
                problems.append(
                    f"{path}: declares plugin {obj.get('plugin')!r} but lives in "
                    f"{path.parent.name}/"
                )

    if problems:
        print(f"questboard check FAILED ({len(problems)} problem(s)):")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print(
        f"questboard check passed - {checked} note(s), {declared} declaration(s), "
        "nothing malformed"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="questboard.py",
        description="Read and write the optional .questboard shared workspace.",
    )
    parser.add_argument(
        "--root",
        default=None,
        help="project root holding .questboard/ (default: the current directory)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    read = subparsers.add_parser("read", help="print valid notes as JSON, newest first")
    read.add_argument("--kind", choices=KINDS, default=None, help="only this kind")
    read.add_argument("--limit", type=int, default=0, help="at most N notes (0 = all)")
    read.set_defaults(func=cmd_read)

    write = subparsers.add_parser("write", help="add one note")
    write.add_argument("--plugin", required=True, help="the plugin writing the note")
    write.add_argument("--kind", required=True, choices=KINDS)
    write.add_argument("--title", required=True, help="one line, no trailing period")
    write.add_argument("--summary", default=None, help="a sentence or three")
    write.add_argument(
        "--path",
        action="append",
        default=None,
        help="a file this note points at; repeatable, first one is the primary",
    )
    write.add_argument("--tag", action="append", default=None, help="repeatable")
    write.add_argument(
        "--outcome", choices=OUTCOMES, default=None, help="required for kind 'attempt'"
    )
    write.add_argument("--body-file", default=None, help="file holding longer markdown")
    write.set_defaults(func=cmd_write)

    resolve = subparsers.add_parser(
        "resolve", help="print the newest still-existing artifact path of a kind"
    )
    resolve.add_argument("--kind", choices=KINDS, default="spec")
    resolve.set_defaults(func=cmd_resolve)

    validate = subparsers.add_parser(
        "validate", help="report malformed files; the only subcommand that can exit 1"
    )
    validate.add_argument(
        "--declarations",
        default=None,
        help="also check <dir>/*/questboard.json participation declarations",
    )
    validate.set_defaults(func=cmd_validate)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
