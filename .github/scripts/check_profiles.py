#!/usr/bin/env python3
"""Keep the install profiles honest.

Profiles are a convention of this repo, not a Claude Code feature. Nothing in
the platform validates them, which means every failure mode here is the
documented-but-unwired class that check_flags.py exists to catch - a profile
that reads fine and silently does the wrong thing.

Four checks:

  1. PROFILE MEMBERSHIP. Every plugin named in scripts/install-profile.sh must
     exist in marketplace.json. A plugin rename would otherwise leave a profile
     pointing at a name the marketplace no longer serves, and the script would
     fail one plugin into a five-plugin install.

  2. DOC PARITY. docs/profiles.md must document exactly the profiles the script
     defines, with exactly the same plugin lists. The script is the source of
     truth; the doc is checked against it. This is the drift that matters most,
     because the doc is what someone reads before deciding to trust the thing.

  3. THE UNATTENDED WARNING. Two plugins run with permissions bypassed. Any
     profile containing one of them must repeat that warning where it is
     documented. A profile that quietly bundles an unattended tool is a defect,
     not an omission - the whole point of a curated set is that the person
     installing it has not read every README.

  4. NAMED PROFILES RESOLVE. Any `install-profile.sh <name>` written in any
     tracked markdown must name a profile that exists. This is what catches a
     typo in a README section written months from now by someone who never read
     this script.

Exit 0 if clean, 1 otherwise. Run from the repo root.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

SCRIPT = ROOT / "scripts" / "install-profile.sh"
DOC = ROOT / "docs" / "profiles.md"
MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"

# Plugins whose unattended modes run with permissions bypassed. This list is
# duplicated in install-profile.sh as UNATTENDED_PLUGINS; check 3 below is what
# makes the duplication safe, because a plugin added to one and not the other
# shows up as a missing warning rather than as silence.
UNATTENDED_PLUGINS = {"sellsword", "ranger"}

# `    daily)      echo "warden sage cleric" ;;`
CASE_ARM = re.compile(r'^\s*([a-z][a-z0-9-]*)\)\s*echo\s+"([^"]*)"\s*;;', re.M)
# `### daily` followed somewhere by `**Plugins:** warden, sage, cleric`
DOC_SECTION = re.compile(r"^### `?([a-z][a-z0-9-]*)`?\s*$", re.M)
DOC_PLUGINS = re.compile(r"^\*\*Plugins:\*\*\s*(.+?)\s*$", re.M)
# The profile can sit after flags, and --scope takes a separate-word value that
# must not be mistaken for the profile name.
INVOCATION = re.compile(
    r"install-profile\.sh(?:\s+(?:--scope[= ]\S+|--[a-z-]+))*\s+([a-z][a-z0-9-]*)"
)


def script_profiles() -> dict[str, list[str]]:
    """Parse the profile_plugins() case statement. The script is the source."""
    text = SCRIPT.read_text(encoding="utf-8")
    start = text.find("profile_plugins()")
    if start == -1:
        raise SystemExit("check_profiles: profile_plugins() not found in the script")
    end = text.find("profile_blurb()", start)
    body = text[start : end if end != -1 else len(text)]
    return {name: plugins.split() for name, plugins in CASE_ARM.findall(body)}


def doc_profiles() -> dict[str, list[str]]:
    """Parse `### <name>` sections and their `**Plugins:**` line."""
    text = DOC.read_text(encoding="utf-8")
    found: dict[str, list[str]] = {}
    marks = list(DOC_SECTION.finditer(text))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        section = text[m.end() : end]
        listed = DOC_PLUGINS.search(section)
        if listed:
            found[m.group(1)] = [p.strip() for p in listed.group(1).split(",") if p.strip()]
    return found


def doc_sections() -> dict[str, str]:
    """Section name -> its raw text, for the warning check."""
    text = DOC.read_text(encoding="utf-8")
    out: dict[str, str] = {}
    marks = list(DOC_SECTION.finditer(text))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        out[m.group(1)] = text[m.end() : end]
    return out


def tracked_markdown() -> list[Path]:
    try:
        out = subprocess.run(
            ["git", "ls-files", "*.md"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout
        paths = [ROOT / line for line in out.splitlines() if line]
    except (subprocess.CalledProcessError, FileNotFoundError):
        paths = sorted(ROOT.rglob("*.md"))
    # An untracked new doc still counts - it is about to be committed.
    for extra in (DOC,):
        if extra.exists() and extra not in paths:
            paths.append(extra)
    return [p for p in paths if p.exists() and ".git" not in p.parts]


def main() -> int:
    problems: list[str] = []

    if not SCRIPT.exists():
        print(f"profile check FAILED: {SCRIPT.relative_to(ROOT)} does not exist")
        return 1
    if not DOC.exists():
        print(f"profile check FAILED: {DOC.relative_to(ROOT)} does not exist")
        return 1

    if not SCRIPT.stat().st_mode & 0o111:
        problems.append(
            f"{SCRIPT.relative_to(ROOT)} is not executable - the docs tell people to "
            f"run it directly, so a missing +x is a broken first experience"
        )

    known = {p["name"] for p in json.loads(MARKETPLACE.read_text())["plugins"]}
    profiles = script_profiles()
    documented = doc_profiles()
    sections = doc_sections()

    if not profiles:
        problems.append("no profiles parsed out of install-profile.sh - has the case statement changed shape?")

    # 1. Every plugin in every profile is a plugin this marketplace ships.
    for name, plugins in sorted(profiles.items()):
        if not plugins:
            problems.append(f"profile '{name}' is empty")
        for plugin in plugins:
            if plugin not in known:
                problems.append(
                    f"profile '{name}' includes '{plugin}', but marketplace.json "
                    f"ships no plugin by that name (stale rename?)"
                )
        if len(set(plugins)) != len(plugins):
            problems.append(f"profile '{name}' lists a plugin twice: {' '.join(plugins)}")

    # 2. The doc says the same thing the script does.
    for name in sorted(set(profiles) | set(documented)):
        in_script = profiles.get(name)
        in_doc = documented.get(name)
        if in_script is None:
            problems.append(
                f"docs/profiles.md documents a '{name}' profile that "
                f"install-profile.sh does not define"
            )
        elif in_doc is None:
            problems.append(
                f"install-profile.sh defines a '{name}' profile that "
                f"docs/profiles.md does not document (needs a '### {name}' section "
                f"with a '**Plugins:**' line)"
            )
        elif in_script != in_doc:
            problems.append(
                f"profile '{name}' disagrees: script says [{' '.join(in_script)}], "
                f"docs/profiles.md says [{', '.join(in_doc)}]"
            )

    # 3. Bundling a permissions-bypassing tool means repeating the warning.
    for name, plugins in sorted(profiles.items()):
        unattended = sorted(UNATTENDED_PLUGINS & set(plugins))
        if not unattended:
            continue
        text = sections.get(name, "").lower()
        if not text:
            continue  # already reported as undocumented above
        if "permission" not in text or "bypass" not in text:
            problems.append(
                f"profile '{name}' includes {', '.join(unattended)}, which "
                f"run with permissions bypassed, but its section in "
                f"docs/profiles.md does not say so. Repeat the warning."
            )

    # 4. Every profile named in prose is a profile that exists.
    for path in tracked_markdown():
        text = path.read_text(encoding="utf-8", errors="replace")
        for named in sorted(set(INVOCATION.findall(text))):
            if named in profiles:
                continue
            problems.append(
                f"{path.relative_to(ROOT)}: names profile '{named}', but "
                f"install-profile.sh defines only: {', '.join(sorted(profiles))}"
            )

    if problems:
        print(f"profile check FAILED ({len(problems)} problem(s)):")
        for p in problems:
            print(f"  - {p}")
        return 1

    print(
        f"profile check passed - {len(profiles)} profiles, every plugin exists, "
        f"docs agree, unattended warnings present"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
