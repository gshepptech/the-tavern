#!/usr/bin/env python3
"""Check sage's seal on a spec before tinker builds from it.

sage seals a finished spec by writing one line into its frontmatter:

    sealed_by: validate-spec.py sha256:<hex>

where <hex> is the sha256 of spec.md with every ``sealed_by:`` line removed
from the frontmatter (the same hash sage's validate-spec.py computes). A spec edited after it
was sealed no longer hashes to its seal.

Three outcomes:

  sealed    the seal is present and holds. When sage's own verifier can be
            found (``sage verify-seal``), it runs too and must pass: it also
            re-runs sage's structural checks on the spec.
  unsealed  no ``sealed_by:`` line: an older or hand-written spec. tinker
            records a warning and builds it.
  broken    a ``sealed_by:`` line that is malformed, does not match the
            spec's bytes, or that sage's verifier refuses. tinker refuses it.

tinker ships separately from sage, so the hash check lives here and needs
nothing from sage. sage's verifier is used when one is found:
``$TINKER_SAGE_VERIFIER`` (a path, or ``none`` to skip it), else sage beside
this plugin in the source repo (``<tinker>/../sage/scripts/sage``), else the
newest installed sage next to this plugin's cache directory
(``<tinker>/../../sage/<version>/scripts/sage``).

CLI (stdlib only):

    seal.py check SPEC_MD

prints one line and exits 0 for sealed or unsealed, 1 for broken, 2 for usage.
The line starts ``SEAL_OK``, ``SEAL_NONE`` or ``SEAL_BROKEN``.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
SEAL_LINE_RE = re.compile(r"^sealed_by:.*\n", re.MULTILINE)
SEAL_KEY_RE = re.compile(r"^sealed_by:(.*)$", re.MULTILINE)
SEAL_VALUE_RE = re.compile(r"^\s*validate-spec\.py\s+sha256:([0-9a-f]{64})\s*$")

# scripts/ -> tinker/
PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def spec_sha256(text: str) -> str:
    """sage's hash: the spec's bytes with any seal line taken out of the frontmatter."""
    m = FRONTMATTER_RE.match(text)
    if m:
        text = SEAL_LINE_RE.sub("", m.group(0)) + text[m.end():]
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def find_sage_verifier() -> Path | None:
    env = os.environ.get("TINKER_SAGE_VERIFIER", "").strip()
    if env:
        if env.lower() == "none":
            return None
        p = Path(env)
        return p if p.is_file() else None
    sibling = PLUGIN_ROOT.parent / "sage" / "scripts" / "sage"
    if sibling.is_file():
        return sibling
    # Installed layout: .../cache/<marketplace>/tinker/<version>/ beside .../sage/<version>/
    installed = sorted(
        (PLUGIN_ROOT.parent.parent / "sage").glob("*/scripts/sage"),
        key=lambda p: [(0, int(x), "") if x.isdigit() else (1, 0, x) for x in re.split(r"[.\-]", p.parent.parent.name)],
    )
    return installed[-1] if installed else None


def check(spec: Path, full: bool = True) -> dict:
    """{status: sealed|unsealed|broken, message, verifier}.

    full=False checks the hash only and never runs sage's verifier."""
    if not spec.is_file():
        return {"status": "broken", "message": f"{spec} does not exist", "verifier": ""}
    text = spec.read_text(encoding="utf-8")
    fm = FRONTMATTER_RE.match(text)
    key = SEAL_KEY_RE.search(fm.group(1)) if fm else None
    if not key:
        return {
            "status": "unsealed",
            "message": f"{spec} carries no sage seal (an older or hand-written spec); building it as given",
            "verifier": "",
        }
    value = SEAL_VALUE_RE.match(key.group(1))
    if not value:
        return {
            "status": "broken",
            "message": f"{spec} has a malformed seal line: sealed_by:{key.group(1)}",
            "verifier": "",
        }
    digest = spec_sha256(text)
    if value.group(1) != digest:
        return {
            "status": "broken",
            "message": (
                f"{spec} changed after sage sealed it (seal sha256:{value.group(1)[:12]}..., "
                f"content sha256:{digest[:12]}...). Re-seal it with sage, or remove the sealed_by line "
                f"to build it as an unsealed spec."
            ),
            "verifier": "hash",
        }
    sage = find_sage_verifier() if full else None
    if sage is None:
        return {"status": "sealed", "message": f"{spec} is sealed and its hash holds", "verifier": "hash"}
    try:
        r = subprocess.run(["bash", str(sage), "verify-seal", str(spec)], capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "sealed", "message": f"{spec} is sealed and its hash holds (sage verify-seal did not run: {exc})",
                "verifier": "hash"}
    if r.returncode == 0:
        return {"status": "sealed", "message": f"{spec} is sealed; sage verify-seal passed", "verifier": str(sage)}
    detail = (r.stderr.strip() or r.stdout.strip()).splitlines()
    return {
        "status": "broken",
        "message": f"sage verify-seal refused {spec}: {' | '.join(detail[:6]) or f'exit {r.returncode}'}",
        "verifier": str(sage),
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] != "check":
        print("usage: seal.py check SPEC_MD", file=sys.stderr)
        return 2
    r = check(Path(argv[1]))
    tag = {"sealed": "SEAL_OK", "unsealed": "SEAL_NONE", "broken": "SEAL_BROKEN"}[r["status"]]
    print(f"{tag}: {r['message']}")
    return 1 if r["status"] == "broken" else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
