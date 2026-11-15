#!/usr/bin/env python3
"""raven: post Claude Code session events to a Slack incoming webhook.

Entry points:

  stop           Stop hook          a reply finished
  notification   Notification hook  Claude Code needs attention
  test           /raven:test          send one test message and report the result
  status         /raven:status        show configuration and recent log lines

The webhook URL comes from RAVEN_SLACK_WEBHOOK_URL and is never printed or
logged. A hook never blocks or fails the turn: every problem (no webhook, Slack
down, bad input) is written to the log and the hook exits 0 with no output.
Every message is passed through redact() before it leaves the machine.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

WEBHOOK_ENV = "RAVEN_SLACK_WEBHOOK_URL"
DEFAULT_DEDUP_SECONDS = 60
TIMEOUT_SECONDS = 5
PROMPT_CHARS = 200
REPLY_CHARS = 400
LOG_KEEP_BYTES = 256 * 1024

# Slack attachment colours by what the reader needs to do.
COLOURS = {
    "done": "#2EB67D",       # a reply finished
    "attention": "#ECB22E",  # waiting on a permission or an answer
    "idle": "#1D9BD1",       # sitting idle
    "test": "#6B7280",
}

REDACTED = "[redacted]"
# (pattern, replacement). Replacements keep the label so the reader can still
# see that a token was there.
SECRET_PATTERNS = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S), REDACTED),
    (re.compile(r"https://hooks\.slack\.com/\S+"), REDACTED),
    (re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}"), REDACTED),
    (re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"), REDACTED),
    (re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}\b"), REDACTED),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}\b"), REDACTED),
    (re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b"), REDACTED),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"), REDACTED),
    (re.compile(r"\bAIza[A-Za-z0-9_-]{35}\b"), REDACTED),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"), REDACTED),
    (re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{16,}"), r"\1 " + REDACTED),
    (re.compile(r"\b([a-z][a-z0-9+.-]*://[^\s:/@]+:)[^\s@/]+@"), r"\1" + REDACTED + "@"),
    (
        re.compile(
            r"(?i)\b([a-z0-9_]*(?:password|passwd|secret|token|api[_-]?key|access[_-]?key)[a-z0-9_]*"
            r"[\"']?\s*[:=]\s*[\"']?)[^\s\"',;]{4,}"
        ),
        r"\1" + REDACTED,
    ),
]


# --- paths and config -----------------------------------------------------

def state_dir() -> Path:
    for var in ("RAVEN_STATE_DIR", "CLAUDE_PLUGIN_DATA"):
        value = os.environ.get(var, "").strip()
        if value:
            return Path(value).expanduser()
    return Path.home() / ".claude" / "plugins" / "data" / "raven"


def log_path() -> Path:
    return state_dir() / "raven.log"


def dedup_seconds() -> int:
    try:
        return max(0, int(os.environ.get("RAVEN_DEDUP_SECONDS", DEFAULT_DEDUP_SECONDS)))
    except ValueError:
        return DEFAULT_DEDUP_SECONDS


def webhook_url() -> tuple[str | None, str | None]:
    """Return (url, problem). Exactly one of the two is set."""
    url = os.environ.get(WEBHOOK_ENV, "").strip()
    if not url:
        return None, f"{WEBHOOK_ENV} is not set"
    parts = urlsplit(url)
    local = parts.hostname in ("localhost", "127.0.0.1", "::1")
    if parts.scheme == "https" and parts.hostname:
        return url, None
    if parts.scheme == "http" and local:
        return url, None
    return None, f"{WEBHOOK_ENV} must be an https URL"


# --- logging --------------------------------------------------------------

def log(message: str) -> None:
    """Append one line to the log. Never raises."""
    url = os.environ.get(WEBHOOK_ENV, "").strip()
    if url:
        message = message.replace(url, REDACTED)
    line = f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {redact(message)}\n"
    try:
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > LOG_KEEP_BYTES:
            tail = path.read_bytes()[-LOG_KEEP_BYTES // 2:]
            path.write_bytes(tail[tail.find(b"\n") + 1:])
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)
    except OSError:
        pass


# --- content --------------------------------------------------------------

def redact(text: str) -> str:
    """Replace anything that looks like a credential with a marker."""
    for pattern, replacement in SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def first_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


def read_transcript(path: str | None) -> tuple[str, str]:
    """Return (last real user prompt, assistant text after it)."""
    prompt, reply = "", []
    if not path:
        return prompt, ""
    try:
        lines = Path(path).expanduser().read_text(encoding="utf-8").splitlines()
    except OSError:
        return prompt, ""
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        message = entry.get("message") or {}
        role = message.get("role") or entry.get("type")
        content = message.get("content")
        if role == "user":
            if isinstance(content, str):
                prompt, reply = content, []
            elif isinstance(content, list):
                texts = [b.get("text", "") for b in content
                         if isinstance(b, dict) and b.get("type") == "text"]
                if texts and not any(isinstance(b, dict) and b.get("type") == "tool_result"
                                     for b in content):
                    prompt, reply = "\n".join(texts), []
        elif role == "assistant":
            if isinstance(content, str):
                reply.append(content)
            elif isinstance(content, list):
                reply.extend(b.get("text", "") for b in content
                             if isinstance(b, dict) and b.get("type") == "text")
    return prompt, "\n".join(t for t in reply if t)


def git_branch(cwd: str) -> str:
    """The branch name, a short commit id when detached, or "" outside a repo."""
    for args in (["symbolic-ref", "--short", "HEAD"], ["rev-parse", "--short", "HEAD"]):
        try:
            result = subprocess.run(
                ["git", "-C", cwd, *args], capture_output=True, text=True, timeout=2,
            )
        except (OSError, subprocess.SubprocessError):
            return ""
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    return ""


def build_message(kind: str, event: dict) -> tuple[dict, str]:
    """Return (Slack payload, dedup key) for a hook event."""
    cwd = event.get("cwd") or os.getcwd()
    session = str(event.get("session_id") or "unknown")
    prompt, reply = read_transcript(event.get("transcript_path"))
    if isinstance(event.get("last_assistant_message"), str):
        reply = event["last_assistant_message"]
    # Redact before clipping: a clip through the middle of a token would leave a
    # fragment no pattern matches.
    prompt, reply = redact(prompt), redact(reply)

    if kind == "stop":
        title, colour = "Reply finished", COLOURS["done"]
        body = clip(reply, REPLY_CHARS) or "(no text in the reply)"
    else:
        ntype = str(event.get("notification_type") or "")
        body = clip(redact(str(event.get("message") or "Claude Code needs your attention")), REPLY_CHARS)
        if ntype == "idle_prompt":
            title, colour = "Waiting for input", COLOURS["idle"]
        else:
            title, colour = str(event.get("title") or "Needs attention"), COLOURS["attention"]

    folder = Path(cwd).name or cwd
    branch = git_branch(cwd)
    fields = [
        {"title": "Prompt", "value": clip(first_line(prompt), PROMPT_CHARS) or "(none)", "short": False},
        {"title": "Folder", "value": folder, "short": True},
        {"title": "Branch", "value": branch or "(not a git repo)", "short": True},
        {"title": "Session", "value": session[:8], "short": True},
    ]
    text = f"{title} in {folder}"
    attachment = {
        "color": colour,
        "fallback": redact(f"{text}: {body}"),
        "title": redact(title),
        "text": redact(body),
        "fields": [{**f, "value": redact(f["value"])} for f in fields],
        "footer": f"session {redact(session)}",
    }
    payload = {"text": redact(text), "attachments": [attachment]}
    key = hashlib.sha256(f"{kind}\0{session}\0{title}\0{body}".encode()).hexdigest()
    return payload, key


# --- rate limit -----------------------------------------------------------

def seen_recently(key: str, now: float) -> bool:
    """True when the same message went out inside the dedup window. Records it otherwise."""
    window = dedup_seconds()
    path = state_dir() / "sent.json"
    try:
        sent = json.loads(path.read_text())
    except (OSError, ValueError):
        sent = {}
    sent = {k: t for k, t in sent.items() if isinstance(t, (int, float)) and now - t < max(window, 1)}
    if window and key in sent:
        return True
    sent[key] = now
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(sent))
        tmp.replace(path)
    except OSError:
        pass
    return False


# --- sending --------------------------------------------------------------

def post(url: str, payload: dict) -> tuple[bool, str]:
    """POST the payload. Return (ok, what happened) with no URL in the text."""
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            body = response.read(200).decode(errors="replace").strip()
            return True, f"HTTP {response.status} {body}".strip()
    except urllib.error.HTTPError as exc:
        body = exc.read(200).decode(errors="replace").strip()
        return False, f"Slack returned HTTP {exc.code} {body}".strip()
    except urllib.error.URLError as exc:
        return False, f"could not reach Slack: {type(exc.reason).__name__}"
    except (OSError, ValueError) as exc:
        return False, f"could not reach Slack: {type(exc).__name__}"


def enabled_events() -> set[str]:
    raw = os.environ.get("RAVEN_EVENTS", "stop,notification")
    return {part.strip().lower() for part in raw.split(",") if part.strip()}


def deliver(kind: str, event: dict) -> str:
    """Send one hook event. Return a one-line outcome for the log."""
    if kind not in enabled_events():
        return f"{kind}: not sent, not listed in RAVEN_EVENTS"
    url, problem = webhook_url()
    if problem:
        return f"{kind}: not sent, {problem}"
    payload, key = build_message(kind, event)
    if seen_recently(key, time.time()):
        return f"{kind}: not sent, duplicate inside {dedup_seconds()}s"
    ok, detail = post(url, payload)
    return f"{kind}: {'sent' if ok else 'failed'}, {detail}"


def run_hook(kind: str) -> int:
    try:
        event = json.loads(sys.stdin.read() or "{}")
        log(deliver(kind, event))
    except Exception as exc:  # noqa: BLE001 - a hook must never break the turn
        log(f"{kind}: skipped, {type(exc).__name__}: {exc}")
    return 0


# --- commands -------------------------------------------------------------

def run_test() -> int:
    url, problem = webhook_url()
    if problem:
        print(f"raven: not sent: {problem}.")
        log(f"test: not sent, {problem}")
        return 1
    cwd = os.getcwd()
    branch = git_branch(cwd)
    payload = {
        "text": f"raven test message from {Path(cwd).name}",
        "attachments": [{
            "color": COLOURS["test"],
            "title": "raven is connected",
            "text": "Stop and Notification events from Claude Code will be posted here.",
            "fields": [
                {"title": "Folder", "value": Path(cwd).name, "short": True},
                {"title": "Branch", "value": branch or "(not a git repo)", "short": True},
            ],
        }],
    }
    ok, detail = post(url, payload)
    log(f"test: {'sent' if ok else 'failed'}, {detail}")
    print(f"raven: {'sent' if ok else 'failed'}: {detail}")
    return 0 if ok else 1


def run_status() -> int:
    url, problem = webhook_url()
    if url:
        print(f"webhook: set (host {urlsplit(url).hostname})")
    else:
        print(f"webhook: not usable, {problem}")
    print(f"events: {', '.join(sorted(enabled_events())) or 'none'}")
    print(f"dedup window: {dedup_seconds()}s")
    print(f"log: {log_path()}")
    try:
        lines = log_path().read_text(encoding="utf-8").splitlines()[-5:]
    except OSError:
        lines = []
    print("recent:" if lines else "recent: nothing logged yet")
    for line in lines:
        print(f"  {line}")
    return 0


COMMANDS = {
    "stop": lambda: run_hook("stop"),
    "notification": lambda: run_hook("notification"),
    "test": run_test,
    "status": run_status,
}


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in COMMANDS:
        print(f"usage: raven.py {{{'|'.join(COMMANDS)}}}", file=sys.stderr)
        return 2
    return COMMANDS[argv[1]]()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
