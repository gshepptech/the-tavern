"""Tests for raven.

Every test that sends runs against a local HTTP server standing in for Slack.
No test talks to the real Slack.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "raven.py"
sys.path.insert(0, str(SCRIPT.parent))
import raven  # noqa: E402


class FakeSlack:
    """A local webhook endpoint that records what it receives."""

    def __init__(self) -> None:
        self.received: list[dict] = []
        self.status = 200
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802 - http.server naming
                length = int(self.headers.get("Content-Length", 0))
                outer.received.append(json.loads(self.rfile.read(length)))
                body = b"ok" if outer.status == 200 else b"invalid_payload"
                self.send_response(outer.status)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/services/T000/B000/secretpath"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def slack():
    server = FakeSlack()
    yield server
    server.close()


@pytest.fixture
def env(tmp_path):
    base = {k: v for k, v in os.environ.items() if not k.startswith("RAVEN_")}
    base.pop("CLAUDE_PLUGIN_DATA", None)
    base["RAVEN_STATE_DIR"] = str(tmp_path / "state")
    return base


def run(env: dict, command: str, event: dict | None = None, **extra: str):
    return subprocess.run(
        [sys.executable, str(SCRIPT), command],
        input=json.dumps(event or {}),
        capture_output=True,
        text=True,
        env={**env, **extra},
        timeout=30,
    )


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "my-app"
    path.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "feature/login", str(path)], check=True)
    return path


@pytest.fixture
def transcript(tmp_path):
    path = tmp_path / "transcript.jsonl"
    entries = [
        {"type": "user", "message": {"role": "user", "content": "Fix the login bug\nmore detail here"}},
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "text", "text": "Fixed it. The session cookie had the wrong path."},
        ]}},
    ]
    path.write_text("\n".join(json.dumps(e) for e in entries))
    return path


def log_text(env: dict) -> str:
    path = Path(env["RAVEN_STATE_DIR"]) / "raven.log"
    return path.read_text() if path.exists() else ""


def test_stop_posts_green_message_with_context(env, slack, repo, transcript):
    event = {"session_id": "abcdef1234567890", "cwd": str(repo), "transcript_path": str(transcript)}
    result = run(env, "stop", event, RAVEN_SLACK_WEBHOOK_URL=slack.url)
    assert result.returncode == 0
    assert result.stdout == ""
    [payload] = slack.received
    attachment = payload["attachments"][0]
    fields = {f["title"]: f["value"] for f in attachment["fields"]}
    assert attachment["color"] == raven.COLOURS["done"]
    assert "session cookie" in attachment["text"]
    assert fields["Prompt"] == "Fix the login bug"
    assert fields["Folder"] == "my-app"
    assert fields["Branch"] == "feature/login"
    assert fields["Session"] == "abcdef12"
    assert "abcdef1234567890" in attachment["footer"]


def test_last_assistant_message_wins_over_transcript(env, slack, repo, transcript):
    event = {"cwd": str(repo), "transcript_path": str(transcript), "last_assistant_message": "Direct text."}
    run(env, "stop", event, RAVEN_SLACK_WEBHOOK_URL=slack.url)
    assert slack.received[0]["attachments"][0]["text"] == "Direct text."


@pytest.mark.parametrize(
    ("ntype", "colour"),
    [("permission_prompt", "attention"), ("idle_prompt", "idle"), ("", "attention")],
)
def test_notification_colours(env, slack, repo, ntype, colour):
    event = {"cwd": str(repo), "message": "Claude needs permission to use Bash", "notification_type": ntype}
    run(env, "notification", event, RAVEN_SLACK_WEBHOOK_URL=slack.url)
    assert slack.received[0]["attachments"][0]["color"] == raven.COLOURS[colour]


def test_duplicate_is_suppressed_inside_window(env, slack, repo):
    event = {"session_id": "s1", "cwd": str(repo), "message": "waiting"}
    for _ in range(3):
        run(env, "notification", event, RAVEN_SLACK_WEBHOOK_URL=slack.url)
    assert len(slack.received) == 1
    assert "duplicate" in log_text(env)


def test_different_messages_are_not_suppressed(env, slack, repo):
    for text in ("first", "second"):
        run(env, "notification", {"cwd": str(repo), "message": text}, RAVEN_SLACK_WEBHOOK_URL=slack.url)
    assert len(slack.received) == 2


def test_dedup_window_zero_sends_every_time(env, slack, repo):
    event = {"cwd": str(repo), "message": "waiting"}
    for _ in range(2):
        run(env, "notification", event, RAVEN_SLACK_WEBHOOK_URL=slack.url, RAVEN_DEDUP_SECONDS="0")
    assert len(slack.received) == 2


def test_events_filter(env, slack, repo):
    run(env, "stop", {"cwd": str(repo)}, RAVEN_SLACK_WEBHOOK_URL=slack.url, RAVEN_EVENTS="notification")
    assert slack.received == []
    assert "not listed in RAVEN_EVENTS" in log_text(env)


def test_unset_webhook_logs_and_exits_zero(env, repo):
    result = run(env, "stop", {"cwd": str(repo)})
    assert result.returncode == 0
    assert result.stdout == "" and result.stderr == ""
    assert "RAVEN_SLACK_WEBHOOK_URL is not set" in log_text(env)


def test_plain_http_to_a_remote_host_is_refused(env, repo):
    run(env, "stop", {"cwd": str(repo)}, RAVEN_SLACK_WEBHOOK_URL="http://example.com/hook")
    assert "must be an https URL" in log_text(env)


def test_slack_error_logs_and_exits_zero(env, slack, repo):
    slack.status = 400
    result = run(env, "stop", {"cwd": str(repo)}, RAVEN_SLACK_WEBHOOK_URL=slack.url)
    assert result.returncode == 0
    assert result.stdout == ""
    assert "Slack returned HTTP 400 invalid_payload" in log_text(env)


def test_unreachable_slack_logs_and_exits_zero(env, slack, repo):
    url = slack.url
    slack.close()
    result = run(env, "stop", {"cwd": str(repo)}, RAVEN_SLACK_WEBHOOK_URL=url)
    assert result.returncode == 0
    assert "could not reach Slack" in log_text(env)


def test_bad_hook_input_exits_zero(env):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "stop"], input="{not json", capture_output=True, text=True, env=env
    )
    assert result.returncode == 0
    assert result.stdout == ""


def test_webhook_url_never_appears_in_output_or_log(env, slack, repo):
    slack.status = 500
    run(env, "stop", {"cwd": str(repo), "last_assistant_message": f"see {slack.url}"},
        RAVEN_SLACK_WEBHOOK_URL=slack.url)
    test = run(env, "test", RAVEN_SLACK_WEBHOOK_URL=slack.url, RAVEN_DEDUP_SECONDS="0")
    status = run(env, "status", RAVEN_SLACK_WEBHOOK_URL=slack.url)
    for text in (test.stdout, test.stderr, status.stdout, status.stderr, log_text(env)):
        assert "secretpath" not in text
        assert slack.url not in text
    assert "host 127.0.0.1" in status.stdout


def test_secrets_redacted_before_sending(env, slack, repo, tmp_path):
    token = "ghp_" + "a1B2" * 9
    path = tmp_path / "t.jsonl"
    path.write_text(json.dumps({"type": "user", "message": {"role": "user", "content": f"use key {token}"}}))
    reply = "Set password=hunter2hunter2 and AKIAABCDEFGHIJKLMNOP " + "x" * 500 + " sk-" + "z" * 40
    run(env, "stop", {"cwd": str(repo), "transcript_path": str(path), "last_assistant_message": reply},
        RAVEN_SLACK_WEBHOOK_URL=slack.url)
    sent = json.dumps(slack.received)
    for secret in (token, "hunter2hunter2", "AKIAABCDEFGHIJKLMNOP"):
        assert secret not in sent
    assert "[redacted]" in sent


def test_command_test_sends_and_reports(env, slack):
    result = run(env, "test", RAVEN_SLACK_WEBHOOK_URL=slack.url)
    assert result.returncode == 0
    assert result.stdout.startswith("raven: sent")
    assert slack.received[0]["attachments"][0]["title"] == "raven is connected"


def test_command_test_without_webhook(env):
    result = run(env, "test")
    assert result.returncode == 1
    assert "RAVEN_SLACK_WEBHOOK_URL is not set" in result.stdout


def test_status_without_webhook(env):
    result = run(env, "status")
    assert "webhook: not usable" in result.stdout
    assert "events: notification, stop" in result.stdout


@pytest.mark.parametrize(
    ("text", "kept", "gone"),
    [
        ("Authorization: Bearer abcdefghijklmnop1234", "Bearer [redacted]", "abcdefghijklmnop1234"),
        ("postgres://app:s3cretpw@db:5432/app", "postgres://app:[redacted]@db", "s3cretpw"),
        ('API_KEY="abcd1234efgh"', "API_KEY=", "abcd1234efgh"),
        ("xoxb-1234567890-abcdefghij", "[redacted]", "xoxb-1234567890"),
        ("https://hooks.slack.com/services/T/B/x", "[redacted]", "hooks.slack.com"),
        ("eyJhbGciOiJIUzI1.eyJzdWIiOiIxMjM0.SflKxwRJSMeKKF2QT4", "[redacted]", "eyJhbGci"),
        ("-----BEGIN RSA PRIVATE KEY-----\nMIIE\n-----END RSA PRIVATE KEY-----", "[redacted]", "MIIE"),
        ("ordinary words and a path/to/file.py:12", "path/to/file.py:12", "[redacted]"),
    ],
)
def test_redact(text, kept, gone):
    out = raven.redact(text)
    assert kept in out
    assert gone not in out
