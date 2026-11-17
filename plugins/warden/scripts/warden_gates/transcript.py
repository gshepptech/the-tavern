"""Reading a Stop-hook transcript: the current turn, its tool calls, and critic outputs."""

from __future__ import annotations

import json
import re

from .config import (
    AGENT_TOOLS,
    CRITIC_AUDIT_RE,
    CRITIC_FEEDBACK_RE,
    CRITIC_ROUND_RE,
    CRITIC_SENTINELS,
    CRITIC_VERDICT_RE,
    VERIFICATION_TOOLS,
)


def load_transcript(path: str) -> list[dict]:
    """Read a transcript, tolerating everything a real transcript throws at us.

    This hook runs at the end of every turn in every project, so a transcript
    it cannot parse must degrade to "no opinion", never to a traceback. Three
    shapes turn up in ordinary use:

      - non-UTF-8 bytes anywhere in the file (a grep result, a binary blob, a
        file path in another encoding), which would raise UnicodeDecodeError,
        not an OSError;
      - a line that is valid JSON but not an object (a bare list or string),
        which would fail on .get();
      - `content: null`, which is a legal shape and is handled downstream.

    errors="replace" keeps the rest of the transcript readable rather than
    discarding the whole file over one bad byte.
    """
    try:
        msgs = []
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # Only objects have the shape the rest of this file expects.
                if isinstance(parsed, dict):
                    msgs.append(parsed)
        return msgs
    except (OSError, UnicodeDecodeError, ValueError):
        return []


def slice_current_turn(messages: list[dict]) -> tuple[list[dict], dict | None]:
    """Slice from the most recent GENUINE user prompt to the last assistant message.

    A "genuine user prompt" is a user-role message containing real text content
    (the user typed something). User-role messages containing only tool_result
    blocks are INTERNAL to Claude's response process - they belong to the same
    turn and must be included in the slice, or multi-round critic counting
    breaks.
    """
    if not messages:
        return [], None
    last_assistant = None
    for msg in reversed(messages):
        if msg.get("role") == "assistant":
            last_assistant = msg
            break
    if last_assistant is None:
        return [], None
    last_user_idx = -1
    for i, msg in enumerate(messages):
        if msg is last_assistant:
            break
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        if isinstance(content, str):
            last_user_idx = i
            continue
        if isinstance(content, list):
            has_text = any(
                isinstance(b, dict) and b.get("type") == "text"
                for b in content
            )
            if has_text:
                last_user_idx = i
    turn_start = last_user_idx if last_user_idx >= 0 else 0
    return messages[turn_start:], last_assistant


def assistant_text(msg: dict) -> str:
    content = msg.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "\n".join(parts)


def last_message_has_tool_use(msg: dict) -> bool:
    """True if the final assistant message ended with a tool call (still working)."""
    content = msg.get("content")
    if not isinstance(content, list):
        return False
    return any(
        isinstance(b, dict) and b.get("type") == "tool_use" for b in content
    )


def find_last_user_prompt(messages: list[dict]) -> str:
    """Return the text of the most recent user-role message with actual user text."""
    for msg in reversed(messages):
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts = []
            has_text = False
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                    has_text = True
            if has_text:
                return "\n".join(text_parts)
    return ""


def summarize_tool_calls(turn_messages: list[dict]) -> str:
    """One-line-per-call summary of tool calls in this turn (for critic spawn input)."""
    summary_lines: list[str] = []
    for msg in turn_messages:
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", [])
        if isinstance(content, str):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "tool_use":
                continue
            tool = block.get("name", "?")
            params = block.get("input", {}) or {}
            target = (
                params.get("file_path")
                or params.get("path")
                or params.get("pattern")
                or params.get("command")
                or params.get("subagent_type")
                or "<no-target>"
            )
            if isinstance(target, str) and len(target) > 120:
                target = target[:117] + "..."
            summary_lines.append(f"  - {tool}: {target}")
    if not summary_lines:
        return "  (none)"
    return "\n".join(summary_lines)


def collect_verified_paths(turn_messages: list[dict]) -> set[str]:
    """Paths Claude directly Read/Grep'd in this turn. Subagent calls excluded."""
    verified: set[str] = set()
    for msg in turn_messages:
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", [])
        if isinstance(content, str):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "tool_use":
                continue
            if block.get("name", "") not in VERIFICATION_TOOLS:
                continue
            params = block.get("input", {}) or {}
            for key in ("file_path", "path"):
                val = params.get(key)
                if isinstance(val, str) and val:
                    verified.add(val)
    return verified


def collect_critic_calls_by_type(turn_messages: list[dict], agent_type: str) -> int:
    """Count Task/Agent tool calls with the given subagent_type in this turn."""
    count = 0
    for msg in turn_messages:
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", [])
        if isinstance(content, str):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "tool_use":
                continue
            if block.get("name") not in AGENT_TOOLS:
                continue
            params = block.get("input", {}) or {}
            if params.get("subagent_type") == agent_type:
                count += 1
    return count


def starts_with_any_sentinel(text: str) -> bool:
    """True if response begins with EITHER critic sentinel (recursion guard)."""
    stripped = text.lstrip()
    return any(stripped.startswith(s) for s in CRITIC_SENTINELS)


def _extract_tool_result_text(content_blocks) -> str:
    """Flatten a tool_result content list to one string."""
    if isinstance(content_blocks, str):
        return content_blocks
    if isinstance(content_blocks, list):
        return "\n".join(
            b.get("text", "")
            for b in content_blocks
            if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


def parse_critic_output(text: str) -> dict:
    """Extract round, verdict, feedback, audit from a critic's output."""
    result = {"verdict": None, "round": None, "feedback": "", "audit": ""}
    if not text or not isinstance(text, str):
        return result
    if not any(s in text for s in CRITIC_SENTINELS):
        return result
    m = CRITIC_VERDICT_RE.search(text)
    if m:
        result["verdict"] = re.sub(r"\s+", " ", m.group(1).upper()).strip()
    m = CRITIC_ROUND_RE.search(text)
    if m:
        try:
            result["round"] = int(m.group(1))
        except (ValueError, TypeError):
            pass
    m = CRITIC_FEEDBACK_RE.search(text)
    if m:
        result["feedback"] = m.group(1).strip()
    m = CRITIC_AUDIT_RE.search(text)
    if m:
        result["audit"] = m.group(1).strip()
    return result


def find_all_critic_outputs(turn_messages: list[dict]) -> list[dict]:
    """Return parsed critic outputs from this turn, in chronological order."""
    out: list[dict] = []
    for msg in turn_messages:
        if msg.get("role") != "user":
            continue
        content = msg.get("content", [])
        if isinstance(content, str):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "tool_result":
                continue
            text = _extract_tool_result_text(block.get("content", ""))
            if not text or not any(s in text for s in CRITIC_SENTINELS):
                continue
            parsed = parse_critic_output(text)
            if parsed["verdict"]:
                out.append(parsed)
    return out
