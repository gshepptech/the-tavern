#!/usr/bin/env python3
"""Verify every version reference in the repo agrees.

A plugin's version is written in four places, and they drift silently:

  1. plugins/<name>/.claude-plugin/plugin.json   the plugin's own manifest
  2. .claude-plugin/marketplace.json             the marketplace entry
  3. plugins/<name>/README.md                    the shields.io badge
  4. README.md                                   the roster table row

The plugin cache is version-keyed, so (1) is what decides whether an installed
plugin picks up a change at all. The other three are documentation, and a stale
badge tells a reader they are on a version they are not.

validate_manifests.py already compares (1) and (2). This adds (3) and (4),
which nothing else checks.

Exit 0 if everything agrees, 1 otherwise. Run from the repo root.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def main() -> int:
    marketplace = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    market_versions = {p["name"]: p.get("version") for p in marketplace["plugins"]}
    root_readme = (ROOT / "README.md").read_text()

    problems: list[str] = []
    checked = 0

    for manifest_path in sorted(ROOT.glob("plugins/*/.claude-plugin/plugin.json")):
        manifest = json.loads(manifest_path.read_text())
        name = manifest["name"]
        version = manifest["version"]
        checked += 1

        if market_versions.get(name) != version:
            problems.append(
                f"{name}: marketplace.json says {market_versions.get(name)}, "
                f"plugin.json says {version}"
            )

        readme_path = ROOT / "plugins" / name / "README.md"
        if readme_path.exists():
            readme = readme_path.read_text()
            # Badges are written either as badge/version-X or badge/<name>-vX.
            badge = re.search(
                rf"badge/(?:version|{re.escape(name)})-v?(\d+\.\d+\.\d+)", readme
            )
            if not badge:
                problems.append(f"{name}: README.md has no version badge")
            elif badge.group(1) != version:
                problems.append(
                    f"{name}: README badge says {badge.group(1)}, plugin.json says {version}"
                )

        # Roster table rows look like: | **[Name](plugins/name/README.md)** | ... | `v1.2.3` |
        row = re.search(
            rf"\*\*\[{re.escape(name.capitalize())}\]\([^)]*\)\*\*[^\n]*?`v(\d+\.\d+\.\d+)`",
            root_readme,
        )
        if not row:
            problems.append(f"{name}: missing from the roster table in the root README")
        elif row.group(1) != version:
            problems.append(
                f"{name}: root README roster table says {row.group(1)}, "
                f"plugin.json says {version}"
            )

    orphans = set(market_versions) - {
        json.loads(p.read_text())["name"]
        for p in ROOT.glob("plugins/*/.claude-plugin/plugin.json")
    }
    for name in sorted(orphans):
        problems.append(f"{name}: listed in marketplace.json but has no plugin directory")

    if problems:
        print(f"version check FAILED ({len(problems)} problem(s)):")
        for p in problems:
            print(f"  - {p}")
        return 1

    print(f"version check passed - {checked} plugins, all four references agree")
    return 0


if __name__ == "__main__":
    sys.exit(main())
