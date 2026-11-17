"""Mode files, the one-shot trust-me marker, and the tuning log."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .config import LOG_FILE, TRUST_ME_ARMED_FILE


def read_mode(path: Path) -> str:
    if not path.exists():
        return "default"
    try:
        return path.read_text().strip().lower() or "default"
    except OSError:
        return "default"


def consume_trust_me() -> bool:
    """Check and delete the ARMED one-shot trust-me flag.

    Deliberately reads TRUST_ME_ARMED_FILE, not the marker /warden:trust-me
    writes. The Stop hook also fires at the end of the turn that ran
    /warden:trust-me, so consuming the raw marker here would spend the bypass
    before the user's next prompt. The UserPromptSubmit hook promotes it to the
    armed marker, and only the armed marker is consumed.
    """
    if not TRUST_ME_ARMED_FILE.exists():
        return False
    try:
        TRUST_ME_ARMED_FILE.unlink()
    except OSError:
        pass
    return True


LOG_MAX_BYTES = 2 * 1024 * 1024


def _redact_for_log(event: dict) -> dict:
    """Strip response prose and absolute paths before anything is written down.

    This log lives at a single path in $HOME and accumulates across every
    project you ever use Warden in, including private ones. It exists to tune the
    gates -- which gate fired, how often, on what shape of input -- and that
    needs counts and categories, not content. Prose or absolute paths here
    would be a transcript fragment of someone's private work sitting in a
    file nobody remembers is there.
    """
    def scrub(node):
        if isinstance(node, dict):
            out = {}
            for key, value in node.items():
                if key == "match":
                    # Keep the length so tuning can still see what tripped it.
                    out["match_len"] = len(str(value))
                elif key == "path":
                    # The filename is enough to spot a pattern; the directory
                    # tree is somebody's private client work.
                    out["path"] = os.path.basename(str(value))
                elif key in ("phrase", "text", "excerpt", "reason", "prompt"):
                    out[f"{key}_len"] = len(str(value))
                else:
                    out[key] = scrub(value)
            return out
        if isinstance(node, list):
            return [scrub(item) for item in node]
        return node

    try:
        return scrub(json.loads(json.dumps(event)))
    except (TypeError, ValueError):
        return {"ts": event.get("ts"), "redaction_failed": True}


def log_event(event: dict) -> None:
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        # Rotate rather than growing without bound in the user's home directory.
        try:
            if LOG_FILE.stat().st_size > LOG_MAX_BYTES:
                LOG_FILE.replace(LOG_FILE.with_suffix(".jsonl.1"))
        except OSError:
            pass
        with LOG_FILE.open("a") as fh:
            fh.write(json.dumps(_redact_for_log(event)) + "\n")
    except (OSError, TypeError, ValueError):
        pass
