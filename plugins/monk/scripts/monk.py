#!/usr/bin/env python3
"""monk: response shaping hooks for Claude Code.

One script, three hook entry points:

  session-start   SessionStart      load the ruleset into the session
  prompt          UserPromptSubmit  apply /monk:* commands, inject the reminder
  stop            Stop              the optional length gate

The /monk:* commands are applied here rather than by the command files,
because only a hook is told which session it is running in. The hook writes the
state change and returns a one-line confirmation that the command file tells
the model to repeat.

State is one JSON file per session under the plugin data directory. A hook
never fails the turn: any error is swallowed and the hook exits 0 with no
output, so a broken monk leaves Claude Code exactly as it would be without it.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

RULES = """\
monk response rules (on for this session; /monk:off turns them off):
1. Answer first. The opening sentence is the answer, the result, or the decision you need.
2. Multi-step work goes in numbered steps, one action per step.
3. End with one concrete next action when there is one. Only one.
4. No preamble, no restating the question, no recap of what you just did, no sign-off.
5. Give time in real units ("about 10 minutes", "2 hours"), never "shortly" or "a moment".
6. When something fails, say what failed and what you saw, in a flat tone. No apology, no drama.
7. A list has at most five items. Group or cut the rest."""

REMINDER = "monk: answer first; no preamble, recap or sign-off; lists of five or fewer; one next action."

DEFAULT_MAX_WORDS = 250
DEFAULT_MAX_ITEMS = 5
SESSION_TTL_SECONDS = 7 * 24 * 3600

COMMAND = re.compile(r"^\s*/monk:([a-z-]+)\b\s*(.*)$", re.S)
FENCE = re.compile(r"^\s*(```|~~~)")
LIST_ITEM = re.compile(r"^(\s*)(?:[-*+]|\d+[.)])\s+\S")
SAFE_ID = re.compile(r"[^A-Za-z0-9_.-]")


# --- state ----------------------------------------------------------------

def data_dir() -> Path:
    for var in ("MONK_DATA_DIR", "CLAUDE_PLUGIN_DATA"):
        value = os.environ.get(var, "").strip()
        if value:
            return Path(value).expanduser()
    return Path.home() / ".claude" / "plugins" / "data" / "monk"


def state_path(session_id: str) -> Path:
    name = SAFE_ID.sub("_", session_id or "unknown")[:128]
    return data_dir() / "sessions" / f"{name}.json"


def env_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name, "").strip().lower()
    if value in ("1", "on", "true", "yes"):
        return True
    if value in ("0", "off", "false", "no"):
        return False
    return default


def env_int(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, ""))
    except ValueError:
        return default
    return value if value > 0 else default


def default_state() -> dict:
    return {
        "enabled": env_flag("MONK_DEFAULT", True),
        "gate": env_flag("MONK_GATE", False),
        "max_words": env_int("MONK_MAX_WORDS", DEFAULT_MAX_WORDS),
        "max_items": env_int("MONK_MAX_ITEMS", DEFAULT_MAX_ITEMS),
        "turn": 0,
        "command_turn": -1,
        "exempt_turn": -1,
        "verbose_pending": False,
        "blocked_turn": -1,
    }


def load_state(session_id: str) -> dict:
    state = default_state()
    try:
        state.update(json.loads(state_path(session_id).read_text()))
    except (OSError, ValueError):
        pass
    return state


def save_state(session_id: str, state: dict) -> None:
    path = state_path(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(path)


def prune_sessions(now: float) -> None:
    """Delete session files nobody has touched in a week."""
    for path in (data_dir() / "sessions").glob("*.json"):
        try:
            if now - path.stat().st_mtime > SESSION_TTL_SECONDS:
                path.unlink()
        except OSError:
            continue


# --- output ---------------------------------------------------------------

def context(event: str, text: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {"hookEventName": event, "additionalContext": text}
    }))


def describe(state: dict) -> str:
    shaping = "on" if state["enabled"] else "off"
    gate = "on" if state["gate"] else "off"
    return (
        f"shaping {shaping}; length gate {gate} "
        f"(budget {state['max_words']} words, {state['max_items']} list items)"
    )


# --- commands -------------------------------------------------------------

def parse_budget(args: str, state: dict) -> str | None:
    """Read optional `[max-words] [max-items]` for /monk:gate-on."""
    parts = args.split()
    if len(parts) > 2 or not all(p.isdigit() and int(p) > 0 for p in parts):
        return "usage: /monk:gate-on [max-words] [max-items], both positive whole numbers"
    if parts:
        state["max_words"] = int(parts[0])
    if len(parts) == 2:
        state["max_items"] = int(parts[1])
    return None


def apply_command(name: str, args: str, state: dict) -> str:
    """Change state for one /monk:<name> command and return the confirmation."""
    if name == "on":
        state["enabled"] = True
        return "monk: response rules are on for this session. " + RULES
    if name == "off":
        state["enabled"] = False
        return "monk: response rules and the length gate are off for this session."
    if name == "verbose":
        if args.strip():
            state["exempt_turn"] = state["turn"]
            return "monk: this turn is exempt from the rules and the gate. Answer in full."
        state["verbose_pending"] = True
        return "monk: your next message is exempt from the rules and the gate."
    if name == "gate-on":
        problem = parse_budget(args, state)
        if problem:
            return "monk: " + problem
        state["gate"] = True
        return f"monk: {describe(state)}."
    if name == "gate-off":
        state["gate"] = False
        return f"monk: {describe(state)}."
    if name == "status":
        return f"monk: {describe(state)}."
    if name == "help":
        return "monk: " + describe(state) + "."
    return f"monk: unknown command /monk:{name}. Run /monk:help for the list."


# --- hooks ----------------------------------------------------------------

def on_session_start(event: dict) -> None:
    prune_sessions(time.time())
    session = event.get("session_id", "")
    state = load_state(session)
    save_state(session, state)
    if state["enabled"]:
        context("SessionStart", RULES)


def on_prompt(event: dict) -> None:
    session = event.get("session_id", "")
    state = load_state(session)
    state["turn"] += 1

    match = COMMAND.match(event.get("prompt", ""))
    if match:
        state["command_turn"] = state["turn"]
        message = apply_command(match.group(1), match.group(2), state)
        save_state(session, state)
        context("UserPromptSubmit", message)
        return

    if state["verbose_pending"]:
        state["verbose_pending"] = False
        state["exempt_turn"] = state["turn"]
    save_state(session, state)

    if state["enabled"] and state["exempt_turn"] != state["turn"]:
        context("UserPromptSubmit", REMINDER)


def last_reply(event: dict) -> str:
    """The text of the reply being stopped on.

    Newer Claude Code versions pass it as `last_assistant_message`. Older ones
    only pass the transcript, so read the assistant text after the last real
    user message from it.
    """
    direct = event.get("last_assistant_message")
    if isinstance(direct, str) and direct.strip():
        return direct
    path = event.get("transcript_path")
    if not path:
        return ""
    texts: list[str] = []
    try:
        lines = Path(path).expanduser().read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        message = entry.get("message") or {}
        role = message.get("role") or entry.get("type")
        content = message.get("content")
        if role == "user":
            # A tool result is a user message too; only a real prompt ends the reply.
            is_tool_result = isinstance(content, list) and any(
                isinstance(b, dict) and b.get("type") == "tool_result" for b in content
            )
            if not is_tool_result:
                texts = []
        elif role == "assistant":
            if isinstance(content, str):
                texts.append(content)
            elif isinstance(content, list):
                texts.extend(
                    b.get("text", "") for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                )
    return "\n".join(t for t in texts if t)


def prose_lines(text: str) -> list[str]:
    """Lines outside fenced code blocks. Code is not prose and is not budgeted."""
    lines, in_fence = [], False
    for line in text.splitlines():
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            lines.append(line)
    return lines


def measure(text: str) -> tuple[int, int]:
    """Return (words outside code, items in the longest single list)."""
    lines = prose_lines(text)
    words = sum(len(line.split()) for line in lines)

    longest = 0
    counts: dict[int, int] = {}
    for line in lines:
        item = LIST_ITEM.match(line)
        if item:
            indent = len(item.group(1).expandtabs(4))
            # A new item closes every list nested deeper than it.
            counts = {i: n for i, n in counts.items() if i <= indent}
            counts[indent] = counts.get(indent, 0) + 1
            longest = max(longest, counts[indent])
        elif line.strip() and not line[:1].isspace():
            counts = {}
    return words, longest


def gate_message(words: int, items: int, state: dict) -> str:
    over = []
    if words > state["max_words"]:
        over.append(f"{words} words against a budget of {state['max_words']}")
    if items > state["max_items"]:
        over.append(f"a list of {items} items against a budget of {state['max_items']}")
    return (
        "monk length gate: the reply has " + " and ".join(over) + ". "
        "Rewrite it shorter and send only the shortened reply. Keep the answer and the one "
        "next action. Cut preamble, recap, caveats nobody asked for and repeated points. "
        f"Merge or drop list items past {state['max_items']}. Code blocks do not count toward "
        "the budget. If the user needs the long version they can run /monk:verbose."
    )


def on_stop(event: dict) -> None:
    session = event.get("session_id", "")
    state = load_state(session)
    turn = state["turn"]
    if (
        not state["enabled"]
        or not state["gate"]
        or event.get("stop_hook_active")
        or state["blocked_turn"] == turn
        or state["command_turn"] == turn
        or state["exempt_turn"] == turn
    ):
        return

    words, items = measure(last_reply(event))
    if words <= state["max_words"] and items <= state["max_items"]:
        return

    state["blocked_turn"] = turn
    save_state(session, state)
    print(json.dumps({"decision": "block", "reason": gate_message(words, items, state)}))


HANDLERS = {"session-start": on_session_start, "prompt": on_prompt, "stop": on_stop}


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in HANDLERS:
        print(f"usage: monk.py {{{'|'.join(HANDLERS)}}} < hook-event.json", file=sys.stderr)
        return 2
    try:
        event = json.loads(sys.stdin.read() or "{}")
        HANDLERS[argv[1]](event)
    except Exception as exc:  # noqa: BLE001 - a hook must never break the turn
        print(f"monk: {argv[1]} hook skipped: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
