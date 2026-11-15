#!/usr/bin/env python3
"""Catch documented-but-unwired behaviour before it ships.

A flag or a name that appears only in documentation is easy to ship
unimplemented: nothing fails, and nobody notices until someone uses it. This
catches the common shapes of that defect:

  - a `--flag` in a command's argument-hint that the plugin's setup script
    never parses, so it falls through into some other argument;
  - a `subagent_type` naming an agent file that does not exist, so a live run
    fails to spawn it;
  - a `plugins/<name>/...` path left behind by a rename.

Three checks:

  1. FLAG PARITY. Every `--flag` in a command's frontmatter `argument-hint`
     must be handled by that plugin's setup script, if it has one. A plugin
     whose flags are interpreted by the model rather than a script is exempt -
     there is no script to check against.

  2. AGENT REFERENCES. Every `subagent_type` naming `<plugin>:<agent>` must
     correspond to a real file at plugins/<plugin>/agents/<agent>.md.

  3. PLUGIN PATHS. Every `plugins/<name>/...` path outside tests must name a
     plugin this repo ships.

Exit 0 if clean, 1 otherwise. Run from the repo root.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

ARGUMENT_HINT = re.compile(r"^argument-hint:\s*(.+)$", re.M)
FLAG = re.compile(r"--[a-z][a-z0-9-]+")
SUBAGENT_REF = re.compile(r"""subagent_type\s*=?\s*['"]([a-z0-9-]+):([a-z0-9-]+)['"]""")
# A rename leaves stale paths behind as readily as it leaves stale agent types,
# and the subagent_type check above does not see a path.
PLUGIN_PATH_REF = re.compile(r"plugins/([a-z0-9_-]+)/(?:agents|commands|skills|scripts)/")

# Flags consumed by the model reading the command file, never passed to a
# script. Each is genuinely interpreted in prose, verified by reading the
# command's own body.
MODEL_INTERPRETED = {
    "ranger": {"--dry-run", "--branch", "--merge-dev", "--ask", "--max-cycles",
               "--max-hours", "--unlimited", "--new", "--headless", "--preset",
               "--scouts", "--planners", "--sweep"},
    "sellsword": {"--thorough", "--yolo", "--allow-production"},
    "cleric": {"--apply", "--auto", "--dry-run"},
    "scout": {"--headed", "--update-snapshots"},
    "seer": set(),
    "tactician": set(),
    "warden": set(),
}


def plugin_scripts(plugin: Path) -> str:
    """Concatenated text of every shell script a plugin ships."""
    return "\n".join(
        p.read_text(encoding="utf-8", errors="replace")
        for p in sorted((plugin / "scripts").glob("*.sh"))
    )


def check_flag_parity() -> list[str]:
    problems = []
    for plugin in sorted((ROOT / "plugins").iterdir()):
        if not plugin.is_dir():
            continue
        scripts = plugin_scripts(plugin)
        if not scripts.strip():
            continue  # no script to wire flags into
        exempt = MODEL_INTERPRETED.get(plugin.name, set())

        for cmd in sorted((plugin / "commands").glob("*.md")):
            hint = ARGUMENT_HINT.search(cmd.read_text(encoding="utf-8"))
            if not hint:
                continue
            for flag in sorted(set(FLAG.findall(hint.group(1)))):
                if flag in exempt:
                    continue
                # The script must mention the flag somewhere in its parsing.
                if flag not in scripts:
                    problems.append(
                        f"{cmd.relative_to(ROOT)}: argument-hint documents {flag}, "
                        f"but no script in plugins/{plugin.name}/scripts/ handles it"
                    )
    return problems


def check_agent_refs() -> list[str]:
    problems = []
    seen: set[tuple[str, str, str]] = set()
    for path in sorted(ROOT.glob("plugins/**/*")):
        if not path.is_file() or path.suffix not in (".md", ".py", ".js", ".sh"):
            continue
        if "__pycache__" in str(path) or "/tests/" in str(path):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for plugin_name, agent_name in SUBAGENT_REF.findall(text):
            key = (plugin_name, agent_name, str(path))
            if key in seen:
                continue
            seen.add(key)
            agent_file = ROOT / "plugins" / plugin_name / "agents" / f"{agent_name}.md"
            if agent_file.exists():
                continue
            # An unknown namespace is the more dangerous case, not a safer one:
            # after a rename the old directory is gone, so nothing else flags
            # it. This repo should never name a plugin it does not ship.
            if not (ROOT / "plugins" / plugin_name).is_dir():
                problems.append(
                    f"{path.relative_to(ROOT)}: references subagent_type "
                    f"'{plugin_name}:{agent_name}', but this repo ships no "
                    f"plugin named '{plugin_name}' (stale rename?)"
                )
            else:
                problems.append(
                    f"{path.relative_to(ROOT)}: references subagent_type "
                    f"'{plugin_name}:{agent_name}', but "
                    f"plugins/{plugin_name}/agents/{agent_name}.md does not exist"
                )
    return problems


def check_plugin_paths() -> list[str]:
    """A `plugins/<name>/...` path must name a plugin this repo ships."""
    problems = []
    known = {p.name for p in (ROOT / "plugins").iterdir() if p.is_dir()}
    seen: set[tuple[str, str]] = set()
    for path in sorted(ROOT.glob("plugins/**/*")):
        if not path.is_file() or path.suffix not in (".md", ".py", ".js", ".sh"):
            continue
        parts = set(path.parts)
        # Tests and fixtures are DATA. A fixture may legitimately contain a
        # historical path because it captures what some older run produced;
        # rewriting one changes what the test is testing.
        if "__pycache__" in parts or "tests" in parts or "fixtures" in parts:
            continue
        for name in PLUGIN_PATH_REF.findall(path.read_text(encoding="utf-8", errors="replace")):
            if name in known or (name, str(path)) in seen:
                continue
            seen.add((name, str(path)))
            problems.append(
                f"{path.relative_to(ROOT)}: references 'plugins/{name}/...', but this "
                f"repo ships no plugin named '{name}' (stale rename?)"
            )
    return problems


def main() -> int:
    problems = check_flag_parity() + check_agent_refs() + check_plugin_paths()
    if problems:
        print(f"flag/reference check FAILED ({len(problems)} problem(s)):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("flag/reference check passed - documented flags are wired, agent types exist")
    return 0


if __name__ == "__main__":
    sys.exit(main())
