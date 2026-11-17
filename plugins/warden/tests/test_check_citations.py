#!/usr/bin/env python3
"""Offline tests for check-citations.py.

Builds synthetic transcript JSONL files matching the Stop hook input format,
runs the hook against each, and asserts the decision (block / pass) and the
specific unverified citations the hook reports.

Test cases:
  1. UNREAD   - assistant cites file:line that wasn't Read; expect BLOCK
  2. CLEAN   - every cited file was Read in the turn; expect PASS
  3. FENCED  - citation appears only inside a ``` block; expect PASS (skipped)
  4. SUBAGENT - only a Task/Agent call touched the file; expect BLOCK
  5. DIFF    - citation-shaped text in diff lines (---/+++); expect PASS
  6. PROSE   - file path mentioned without :line; expect PASS (tier A only)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
HOOK = PLUGIN_ROOT / "scripts" / "check-citations.py"

assert HOOK.exists(), f"hook not found at {HOOK}"


# --- transcript builder ---------------------------------------------------

def msg(role: str, content) -> dict:
    return {"role": role, "content": content}


def text_block(text: str) -> dict:
    return {"type": "text", "text": text}


def tool_use_block(name: str, params: dict) -> dict:
    return {"type": "tool_use", "name": name, "input": params, "id": "tu_1"}


def write_transcript(messages: list[dict]) -> str:
    """Write messages as JSONL, return path."""
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    with os.fdopen(fd, "w") as fh:
        for m in messages:
            fh.write(json.dumps(m) + "\n")
    return path


def run_hook(transcript_path: str, *, mode: str | None = "default") -> dict:
    """Invoke check-citations.py with a Stop event for the given transcript.

    Returns a dict: {"exit": int, "stdout": str, "stderr": str, "decision": parsed}
    """
    # Set up isolated HOME so we don't pollute the user's real config
    home = tempfile.mkdtemp()
    claude_dir = Path(home) / ".claude"
    claude_dir.mkdir(parents=True)
    if mode is not None:
        (claude_dir / ".warden-citations-mode").write_text(mode)

    event = {
        "session_id": "test-session",
        "transcript_path": transcript_path,
        "stop_hook_active": False,
        "hook_event_name": "Stop",
    }

    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        env={**os.environ, "HOME": home},
        timeout=10,
    )

    decision = None
    if proc.stdout.strip():
        try:
            decision = json.loads(proc.stdout)
        except json.JSONDecodeError:
            pass

    return {
        "exit": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "decision": decision,
        "log_path": str(claude_dir / ".warden-citations-log.jsonl"),
    }


# --- test cases -----------------------------------------------------------

def test_unread_citation_blocks():
    """The assistant cites a file:line it never Read."""
    t = write_transcript([
        msg("user", "How can we add compliance results to the deployment report?"),
        msg("assistant", [
            tool_use_block("Read", {"file_path": "/repo/internal/api/report/handler.go"}),
            text_block(
                "The handler is at internal/api/report/handler.go:73 and the proto "
                "definition lives at proto/acme/v1/report.proto:11 where "
                "REPORT_TYPE_COMPLIANCE is reserved."
            ),
        ]),
    ])
    result = run_hook(t)
    assert result["exit"] == 0, result
    assert result["decision"] is not None, "expected a decision payload"
    assert result["decision"]["decision"] == "block", result
    reason = result["decision"]["reason"]
    # handler.go was Read → should be considered verified
    assert "handler.go:73" not in reason, f"handler.go was Read, should not be flagged: {reason}"
    # report.proto was NOT Read → must be flagged
    assert "report.proto:11" in reason, f"report.proto was not Read, should be flagged: {reason}"
    print("  ✓ unread_citation_blocks")


def test_clean_response_passes():
    """All cited files were Read in this turn - should pass."""
    t = write_transcript([
        msg("user", "What's at handler.go:73?"),
        msg("assistant", [
            tool_use_block("Read", {"file_path": "/repo/internal/api/handler.go"}),
            text_block("The function lives at internal/api/handler.go:73."),
        ]),
    ])
    result = run_hook(t)
    assert result["exit"] == 0, result
    assert result["decision"] is None, f"expected no block, got: {result['decision']}"
    print("  ✓ clean_response_passes")


def test_fenced_block_skipped():
    """Citations only appearing in ``` code fences should NOT trigger block."""
    t = write_transcript([
        msg("user", "Show me an example."),
        msg("assistant", [
            text_block(
                "Here's a hypothetical:\n\n"
                "```go\n"
                "// example/path/foo.go:42\n"
                "func Foo() {}\n"
                "```\n\n"
                "That's the shape."
            ),
        ]),
    ])
    result = run_hook(t)
    assert result["decision"] is None, (
        f"citation in fenced block should be skipped, got: {result['decision']}"
    )
    print("  ✓ fenced_block_skipped")


def test_subagent_read_does_not_count():
    """Only a Task (subagent) call touched the file; no direct Read.

    An Explore subagent Read the files and returned a summary, and Claude
    cited from the summary.
    The hook MUST treat subagent invocations as non-verification.
    """
    t = write_transcript([
        msg("user", "Where is X defined?"),
        msg("assistant", [
            tool_use_block("Task", {
                "description": "Find X",
                "subagent_type": "Explore",
                "prompt": "Find X",
            }),
            text_block("X is defined at internal/foo/bar.go:99."),
        ]),
    ])
    result = run_hook(t)
    assert result["decision"] is not None and result["decision"]["decision"] == "block", (
        f"subagent calls must not count as verification, got: {result['decision']}"
    )
    assert "bar.go:99" in result["decision"]["reason"]
    print("  ✓ subagent_read_does_not_count")


def test_diff_lines_skipped():
    """`+++ b/foo.go` and similar diff markers should not be treated as citations."""
    t = write_transcript([
        msg("user", "Show me a diff."),
        msg("assistant", [
            text_block(
                "The change:\n"
                "--- a/internal/foo.go\n"
                "+++ b/internal/foo.go\n"
                "@@ -10,5 +10,7 @@\n"
                " unchanged line\n"
                "+new line\n"
            ),
        ]),
    ])
    result = run_hook(t)
    assert result["decision"] is None, (
        f"diff markers should be skipped, got: {result['decision']}"
    )
    print("  ✓ diff_lines_skipped")


def test_bare_path_without_line_skipped():
    """Tier A only fires on path:line. A bare path mention is not a citation."""
    t = write_transcript([
        msg("user", "What does the codebase look like?"),
        msg("assistant", [
            text_block(
                "The main entry is internal/api/handler.go and the proto lives "
                "in proto/acme/v1/report.proto. Lots of code."
            ),
        ]),
    ])
    result = run_hook(t)
    assert result["decision"] is None, (
        f"bare paths (no :line) should not trigger tier A, got: {result['decision']}"
    )
    print("  ✓ bare_path_without_line_skipped")


def test_off_mode_short_circuits():
    """When mode is 'off', the hook must do nothing - no decision, no block."""
    t = write_transcript([
        msg("user", "Where is X?"),
        msg("assistant", [
            text_block("X is at totally/made/up/file.go:999."),
        ]),
    ])
    result = run_hook(t, mode="off")
    assert result["decision"] is None, (
        f"off mode must short-circuit, got: {result['decision']}"
    )
    print("  ✓ off_mode_short_circuits")


def _run_hook_with_home(transcript_path: str, home: str) -> dict:
    """Run the Stop hook against a caller-owned HOME so markers can be inspected."""
    event = {
        "session_id": "test-session",
        "transcript_path": transcript_path,
        "stop_hook_active": False,
        "hook_event_name": "Stop",
    }
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        env={**os.environ, "HOME": home},
        timeout=10,
    )
    return {"exit": proc.returncode, "stdout": proc.stdout}


def test_trust_me_survives_its_own_turn():
    """The raw /warden:trust-me marker must NOT be consumed by the Stop hook.

    The Stop hook also fires at the end of the turn that ran /warden:trust-me,
    so consuming the raw marker there would spend the bypass before the user's
    next prompt. The UserPromptSubmit hook promotes it to the armed marker, and
    only the armed marker is consumed.
    """
    home = tempfile.mkdtemp()
    claude_dir = Path(home) / ".claude"
    claude_dir.mkdir(parents=True)
    raw = claude_dir / ".warden-trust-me"
    raw.write_text("")

    t = write_transcript([
        msg("user", "/warden:trust-me"),
        msg("assistant", [
            text_block("Strict gates bypassed for your next turn."),
        ]),
    ])
    _run_hook_with_home(t, home)

    assert raw.exists(), (
        "the raw .warden-trust-me marker was consumed by the Stop hook on the turn "
        "that created it, so the bypass is spent before the user's next prompt"
    )
    print("  ✓ trust_me_survives_its_own_turn")


def test_trust_me_armed_marker_is_consumed():
    """The armed marker IS consumed, so the bypass stays one-shot."""
    home = tempfile.mkdtemp()
    claude_dir = Path(home) / ".claude"
    claude_dir.mkdir(parents=True)
    armed = claude_dir / ".warden-trust-me-armed"
    armed.write_text("")

    t = write_transcript([
        msg("user", "What is a monad?"),
        msg("assistant", [
            text_block("A monad is a structure for sequencing computations."),
        ]),
    ])
    _run_hook_with_home(t, home)

    assert not armed.exists(), (
        "the armed marker survived the Stop hook, so the bypass would leak into "
        "later turns instead of being one-shot"
    )
    print("  ✓ trust_me_armed_marker_is_consumed")


def test_inject_promotes_trust_me_marker():
    """UserPromptSubmit must promote the raw marker to the armed one, once."""
    inject = PLUGIN_ROOT / "scripts" / "inject.sh"
    assert inject.exists(), f"inject.sh not found at {inject}"

    home = tempfile.mkdtemp()
    claude_dir = Path(home) / ".claude"
    claude_dir.mkdir(parents=True)
    raw = claude_dir / ".warden-trust-me"
    armed = claude_dir / ".warden-trust-me-armed"
    raw.write_text("")

    subprocess.run(
        ["bash", str(inject)],
        capture_output=True, text=True,
        env={**os.environ, "HOME": home}, timeout=10,
    )
    assert not raw.exists() and armed.exists(), (
        "inject.sh did not promote .warden-trust-me to .warden-trust-me-armed"
    )

    # Promotion must also happen while the preamble is silenced: /warden:off
    # stops injection but the Stop gates keep firing, so a bypass must arm.
    (claude_dir / ".warden-state").write_text("off")
    armed.unlink()
    raw.write_text("")
    subprocess.run(
        ["bash", str(inject)],
        capture_output=True, text=True,
        env={**os.environ, "HOME": home}, timeout=10,
    )
    assert armed.exists(), "inject.sh skipped trust-me promotion while warden was off"
    print("  ✓ inject_promotes_trust_me_marker")


def _run_hook_raw(transcript_bytes: bytes) -> int:
    """Run the Stop hook against a transcript written as raw bytes.

    Returns the exit code. The hook must never exit non-zero: it runs at the
    end of every turn in every project, so a traceback surfaces as a hook error
    on work that has nothing to do with Warden.
    """
    home = tempfile.mkdtemp()
    (Path(home) / ".claude").mkdir(parents=True)
    tpath = Path(home) / "transcript.jsonl"
    tpath.write_bytes(transcript_bytes)
    event = {
        "session_id": "test-session",
        "transcript_path": str(tpath),
        "stop_hook_active": False,
        "hook_event_name": "Stop",
    }
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        env={**os.environ, "HOME": home},
        timeout=10,
    )
    return proc.returncode


def test_malformed_transcripts_never_crash():
    """A transcript the hook cannot parse must mean 'no opinion', not a crash.

    Regression test. Each of these raised a traceback (exit 1) on every Stop
    event, in every project:
      - non-UTF-8 bytes anywhere in the file (UnicodeDecodeError is not an
        OSError, so it escaped load_transcript's handler)
      - a line that is valid JSON but not an object
      - content: null, which is a legal message shape
    """
    cases = {
        "non-utf8 bytes": b'{"role":"user","content":"hi"}\n'
                          b'{"role":"assistant","content":[{"type":"text","text":"caf\xe9"}]}\n',
        "content is null": b'{"role":"user","content":"hi"}\n'
                           b'{"role":"assistant","content":null}\n',
        "json line is not an object": b'{"role":"user","content":"hi"}\n["not","an","object"]\n',
        "empty file": b"",
        "not json at all": b"this is not json\nnor is this\n",
    }
    for label, payload in cases.items():
        rc = _run_hook_raw(payload)
        assert rc == 0, f"hook exited {rc} on a transcript with {label} - must fail open"
    print("  ✓ malformed_transcripts_never_crash")


def test_stale_trust_me_marker_is_not_promoted():
    """A trust-me left unspent must not bypass an unrelated later session.

    /warden:trust-me means "bypass my next turn". If the user runs it and never
    submits another prompt that session, the raw marker persists; without a
    freshness check the first prompt of a later session would promote and
    consume it, silently bypassing a turn the user never meant to protect.
    """
    inject = PLUGIN_ROOT / "scripts" / "inject.sh"
    home = tempfile.mkdtemp()
    claude = Path(home) / ".claude"
    claude.mkdir(parents=True)
    raw = claude / ".warden-trust-me"
    raw.write_text("")
    # Backdate it well past the freshness window.
    old = 1_600_000_000  # a fixed epoch far in the past
    os.utime(raw, (old, old))

    subprocess.run(["bash", str(inject)], capture_output=True, text=True,
                   env={**os.environ, "HOME": home}, timeout=10)

    assert not raw.exists(), "a stale raw marker should be discarded, not left to fire later"
    assert not (claude / ".warden-trust-me-armed").exists(), (
        "a stale raw marker must not be promoted to armed"
    )
    print("  ✓ stale_trust_me_marker_is_not_promoted")


def test_armed_trust_me_consumed_even_when_strict_off():
    """The armed marker must be cleared even while strict is off, or it strands.

    If strict mode is off when the armed marker exists and it is only consumed
    when strict is on, it survives until strict is re-enabled and then bypasses
    that future turn. Consuming it unconditionally cannot weaken anything: with
    strict off the gates it feeds are skipped anyway.
    """
    home = tempfile.mkdtemp()
    claude = Path(home) / ".claude"
    claude.mkdir(parents=True)
    (claude / ".warden-trust-me-armed").write_text("")
    (claude / ".warden-strict-mode").write_text("off")

    t = write_transcript([
        msg("user", "hi"),
        msg("assistant", [text_block("ok")]),
    ])
    _run_hook_with_home(t, home)

    assert not (claude / ".warden-trust-me-armed").exists(), (
        "armed marker must be consumed even when strict is off, or it strands"
    )
    print("  ✓ armed_trust_me_consumed_even_when_strict_off")


def test_stop_hook_active_short_circuits():
    """When stop_hook_active=true, the hook must not re-block (avoids infinite loop)."""
    t = write_transcript([
        msg("user", "Where is X?"),
        msg("assistant", [
            text_block("X is at made-up/path.go:42."),
        ]),
    ])
    # Build event manually with stop_hook_active=True
    home = tempfile.mkdtemp()
    (Path(home) / ".claude").mkdir()
    event = {
        "session_id": "s",
        "transcript_path": t,
        "stop_hook_active": True,
        "hook_event_name": "Stop",
    }
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        env={**os.environ, "HOME": home},
        timeout=10,
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == "", (
        f"stop_hook_active should suppress decision output, got: {proc.stdout!r}"
    )
    print("  ✓ stop_hook_active_short_circuits")


def test_grep_counts_as_verification():
    """A Grep with path argument should verify that path."""
    t = write_transcript([
        msg("user", "Where is X?"),
        msg("assistant", [
            tool_use_block("Grep", {"path": "/repo/internal/foo.go", "pattern": "X"}),
            text_block("Found X at internal/foo.go:55."),
        ]),
    ])
    result = run_hook(t)
    assert result["decision"] is None, (
        f"Grep on the cited path should count as verification, got: {result['decision']}"
    )
    print("  ✓ grep_counts_as_verification")


def test_log_written_on_block():
    """Hook should append a structured log entry for every check."""
    t = write_transcript([
        msg("user", "Where is X?"),
        msg("assistant", [
            text_block("X is at totally/made/up.go:999."),
        ]),
    ])
    result = run_hook(t)
    assert result["decision"]["decision"] == "block"
    log_path = result["log_path"]
    assert os.path.exists(log_path), f"log not written at {log_path}"
    log_lines = Path(log_path).read_text().strip().splitlines()
    assert len(log_lines) >= 1
    entry = json.loads(log_lines[-1])
    assert entry["decision"] == "block"
    assert any(c["path"].endswith("up.go") for c in entry["unverified"])
    print("  ✓ log_written_on_block")


def test_completion_promise_blocks():
    """Gate (e): a response ending by promising first-person work, no trailing
    tool call and no question, must be blocked."""
    t = write_transcript([
        msg("user", "Can you sort out the failing import?"),
        msg("assistant", [
            text_block(
                "I've reviewed the approach. Now I'll implement the change and "
                "run the tests to confirm it passes."
            ),
        ]),
    ])
    result = run_hook(t)
    assert result["exit"] == 0, result
    assert result["decision"] is not None and result["decision"]["decision"] == "block", (
        f"promise-without-action should block, got: {result['decision']}"
    )
    assert "[warden:completion]" in result["decision"]["reason"], result["decision"]["reason"]
    print("  ✓ completion_promise_blocks")


def test_completion_clarifying_question_passes():
    """Gate (e): a response that ends by asking the user is a legitimate stop."""
    t = write_transcript([
        msg("user", "Can you sort out the failing import?"),
        msg("assistant", [
            text_block(
                "There are two ways to fix this import. Do you want me to vendor "
                "the dependency or switch to the stdlib equivalent?"
            ),
        ]),
    ])
    result = run_hook(t)
    assert result["decision"] is None, (
        f"clarifying-question ending should pass, got: {result['decision']}"
    )
    print("  ✓ completion_clarifying_question_passes")


def test_completion_fable_off_passes():
    """Gate (e): with fable-mode off, the promise-without-action gate is silent."""
    t = write_transcript([
        msg("user", "Can you sort out the failing import?"),
        msg("assistant", [
            text_block("Now I'll implement the change and run the tests."),
        ]),
    ])
    home = tempfile.mkdtemp()
    claude_dir = Path(home) / ".claude"
    claude_dir.mkdir(parents=True)
    (claude_dir / ".warden-fable-mode").write_text("off")
    event = {
        "session_id": "s",
        "transcript_path": t,
        "stop_hook_active": False,
        "hook_event_name": "Stop",
    }
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        env={**os.environ, "HOME": home},
        timeout=10,
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == "", (
        f"fable-off must suppress the completion gate, got: {proc.stdout!r}"
    )
    print("  ✓ completion_fable_off_passes")


# --- runner ---------------------------------------------------------------

def main() -> int:
    tests = [
        test_unread_citation_blocks,
        test_clean_response_passes,
        test_fenced_block_skipped,
        test_subagent_read_does_not_count,
        test_diff_lines_skipped,
        test_bare_path_without_line_skipped,
        test_off_mode_short_circuits,
        test_malformed_transcripts_never_crash,
        test_stale_trust_me_marker_is_not_promoted,
        test_armed_trust_me_consumed_even_when_strict_off,
        test_trust_me_survives_its_own_turn,
        test_trust_me_armed_marker_is_consumed,
        test_inject_promotes_trust_me_marker,
        test_stop_hook_active_short_circuits,
        test_grep_counts_as_verification,
        test_log_written_on_block,
        test_completion_promise_blocks,
        test_completion_clarifying_question_passes,
        test_completion_fable_off_passes,
    ]
    print(f"Running {len(tests)} citation-hook tests:\n")
    failed = 0
    for t in tests:
        try:
            t()
        except AssertionError as e:
            print(f"  ✗ {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ✗ {t.__name__}: unexpected error: {e}")
            failed += 1
    print()
    if failed:
        print(f"FAIL: {failed} of {len(tests)} tests failed")
        return 1
    print(f"PASS: all {len(tests)} tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
