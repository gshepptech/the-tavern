"""Tests for the monk hooks.

Each test runs scripts/monk.py as Claude Code would, with a hook event on
stdin, against a temporary data directory.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "monk.py"
SESSION = "session-123"


@pytest.fixture
def run(tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.startswith("MONK_")}
    env.pop("CLAUDE_PLUGIN_DATA", None)
    env["MONK_DATA_DIR"] = str(tmp_path / "data")

    def _run(hook: str, event: dict | None = None, **extra_env: str) -> dict | None:
        payload = {"session_id": SESSION, **(event or {})}
        result = subprocess.run(
            [sys.executable, str(SCRIPT), hook],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env={**env, **extra_env},
            check=True,
        )
        return json.loads(result.stdout) if result.stdout.strip() else None

    _run.data = tmp_path / "data"
    return _run


def context_of(output: dict | None) -> str:
    assert output is not None
    return output["hookSpecificOutput"]["additionalContext"]


def prompt(run, text: str, **extra_env: str) -> dict | None:
    return run("prompt", {"prompt": text}, **extra_env)


def stop(run, reply: str, **event) -> dict | None:
    return run("stop", {"last_assistant_message": reply, **event})


LONG = " ".join(["word"] * 400)
SEVEN_ITEMS = "\n".join(f"- item {i}" for i in range(7))


def test_session_start_loads_rules(run):
    text = context_of(run("session-start", {"source": "startup"}))
    assert "Answer first" in text
    assert "at most five items" in text


def test_session_start_respects_default_off(run):
    assert run("session-start", {}, MONK_DEFAULT="off") is None


def test_prompt_injects_one_line_reminder(run):
    text = context_of(prompt(run, "how do I rebase?"))
    assert text.startswith("monk:")
    assert "\n" not in text


def test_off_then_on(run):
    assert "off" in context_of(prompt(run, "/monk:off"))
    assert prompt(run, "next question") is None
    assert "on" in context_of(prompt(run, "/monk:on"))
    assert prompt(run, "another") is not None


def test_state_is_per_session(run):
    prompt(run, "/monk:off")
    other = run("prompt", {"session_id": "other-session", "prompt": "hi"})
    assert other is not None


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("/monk:status", "length gate off"),
        ("/monk:gate-on", "length gate on (budget 250 words, 5 list items)"),
        ("/monk:gate-on 120 3", "budget 120 words, 3 list items"),
        ("/monk:gate-on lots", "usage: /monk:gate-on"),
        ("/monk:gate-off", "length gate off"),
        ("/monk:nonsense", "unknown command"),
    ],
)
def test_commands_confirm(run, command, expected):
    assert expected in context_of(prompt(run, command))


def test_gate_is_off_by_default(run):
    prompt(run, "explain everything")
    assert stop(run, LONG) is None


def test_gate_blocks_long_reply_once(run):
    prompt(run, "/monk:gate-on")
    prompt(run, "explain everything")
    first = stop(run, LONG)
    assert first["decision"] == "block"
    assert "400 words" in first["reason"]
    # The same turn is never blocked twice, whether or not Claude Code says so.
    assert stop(run, LONG) is None
    assert stop(run, LONG, stop_hook_active=True) is None
    # A new turn is checked again.
    prompt(run, "and again")
    assert stop(run, LONG)["decision"] == "block"


def test_gate_honours_stop_hook_active(run):
    prompt(run, "/monk:gate-on")
    prompt(run, "explain")
    assert stop(run, LONG, stop_hook_active=True) is None


def test_gate_blocks_long_list(run):
    prompt(run, "/monk:gate-on")
    prompt(run, "list things")
    result = stop(run, "Here:\n\n" + SEVEN_ITEMS)
    assert result["decision"] == "block"
    assert "list of 7 items" in result["reason"]


def test_gate_passes_short_reply(run):
    prompt(run, "/monk:gate-on")
    prompt(run, "quick one")
    assert stop(run, "Yes. Run `make test` next.") is None


def test_gate_ignores_code_blocks(run):
    prompt(run, "/monk:gate-on")
    prompt(run, "show code")
    code = "```\n" + "\n".join(f"- line {i} " + "x " * 50 for i in range(20)) + "\n```"
    assert stop(run, "Here it is.\n\n" + code) is None


def test_gate_skips_command_turns(run):
    prompt(run, "/monk:gate-on 5")
    assert stop(run, LONG) is None


def test_verbose_with_question_exempts_this_turn(run):
    prompt(run, "/monk:gate-on")
    assert "this turn" in context_of(prompt(run, "/monk:verbose explain the design"))
    assert stop(run, LONG) is None


def test_verbose_alone_exempts_next_turn_only(run):
    prompt(run, "/monk:gate-on")
    prompt(run, "/monk:verbose")
    assert prompt(run, "explain the design") is None  # no reminder on the exempt turn
    assert stop(run, LONG) is None
    prompt(run, "and now briefly")
    assert stop(run, LONG)["decision"] == "block"


def test_off_disables_gate(run):
    prompt(run, "/monk:gate-on")
    prompt(run, "/monk:off")
    prompt(run, "explain")
    assert stop(run, LONG) is None


def test_reply_read_from_transcript_when_not_passed(run, tmp_path):
    transcript = tmp_path / "t.jsonl"
    entries = [
        {"type": "user", "message": {"role": "user", "content": "old question"}},
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": LONG}]}},
        {"type": "user", "message": {"role": "user", "content": "new question"}},
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "text", "text": "Checking."},
            {"type": "tool_use", "id": "1", "name": "Bash", "input": {}},
        ]}},
        {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "1", "content": "ok"},
        ]}},
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "Done."}]}},
    ]
    transcript.write_text("\n".join(json.dumps(e) for e in entries))
    prompt(run, "/monk:gate-on 10")
    prompt(run, "new question")
    # Only "Checking." and "Done." belong to this turn: two words, under budget.
    assert run("stop", {"transcript_path": str(transcript)}) is None


def test_bad_input_never_fails_the_hook(run, tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "stop"],
        input="not json",
        capture_output=True,
        text=True,
        env={**os.environ, "MONK_DATA_DIR": str(tmp_path)},
    )
    assert result.returncode == 0
    assert result.stdout == ""


def test_session_id_cannot_escape_data_dir(run):
    run("prompt", {"session_id": "../../etc/passwd", "prompt": "/monk:off"})
    files = list((run.data / "sessions").iterdir())
    assert len(files) == 1
    assert files[0].parent == run.data / "sessions"


@pytest.mark.parametrize(
    ("text", "words", "items"),
    [
        ("one two three", 3, 0),
        ("- a\n- b\n- c", 6, 3),
        ("1. a\n2. b\n   - x\n   - y\n3. c", 10, 3),
        ("- a\n- b\n\nParagraph.\n\n- c", 7, 2),
        ("- a\n  continued\n- b", 5, 2),
    ],
)
def test_measure(text, words, items):
    sys.path.insert(0, str(SCRIPT.parent))
    try:
        import monk
    finally:
        sys.path.pop(0)
    assert monk.measure(text) == (words, items)
