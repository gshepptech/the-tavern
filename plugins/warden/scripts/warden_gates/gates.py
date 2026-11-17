"""Gates (a), (b), (c) and (e): citations, uncertainty, grounding and completion."""

from __future__ import annotations

from .config import (
    CITATION_RE,
    CITATIONS_MODE_FILE,
    CLARIFYING_QUESTION_RE,
    CODEBASE_ACTION_RE,
    CODEBASE_EXT_RE,
    CODEBASE_PATH_RE,
    COMPLETION_MIN_RESPONSE_CHARS,
    COMPLETION_PROMISE_RE,
    COMPLETION_TAIL_CHARS,
    DIFF_LINE_RE,
    FABLE_MODE_FILE,
    FENCED_BLOCK_RE,
    GROUNDING_MIN_RESPONSE_CHARS,
    UNCERTAINTY_MODE_FILE,
    UNCERTAINTY_TELLS_RE,
)
from .state import read_mode


def strip_non_citations(text: str) -> str:
    """Remove fenced code blocks and diff lines before regex-scanning prose."""
    no_fences = FENCED_BLOCK_RE.sub("", text)
    kept = []
    for line in no_fences.splitlines():
        if DIFF_LINE_RE.match(line):
            continue
        kept.append(line)
    return "\n".join(kept)


def find_citations(text: str) -> list[tuple[str, str]]:
    cleaned = strip_non_citations(text)
    seen = set()
    out: list[tuple[str, str]] = []
    for m in CITATION_RE.finditer(cleaned):
        key = (m.group("path"), m.group("line"))
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def path_matches_verified(cited: str, verified: set[str]) -> bool:
    cited_norm = cited.lstrip("/")
    for v in verified:
        v_norm = v.lstrip("/")
        if v_norm == cited_norm or v_norm.endswith("/" + cited_norm):
            return True
        if cited_norm.endswith("/" + v_norm):
            return True
    return False


def is_codebase_shaped(prompt_text: str) -> bool:
    if CODEBASE_PATH_RE.search(prompt_text):
        return True
    if CODEBASE_EXT_RE.search(prompt_text):
        return True
    if CODEBASE_ACTION_RE.search(prompt_text):
        return True
    return False


def is_clarifying_response(response_text: str) -> bool:
    stripped = response_text.strip()
    if stripped.endswith("?"):
        return True
    if CLARIFYING_QUESTION_RE.search(stripped):
        return True
    return False


def check_citations(
    response_text: str, verified_paths: set[str]
) -> tuple[bool, str, list]:
    if read_mode(CITATIONS_MODE_FILE) == "off":
        return False, "", []
    citations = find_citations(response_text)
    unverified = [
        {"path": path, "line": line}
        for (path, line) in citations
        if not path_matches_verified(path, verified_paths)
    ]
    if not unverified:
        return False, "", []
    cited_lines = "\n".join(f"  - {c['path']}:{c['line']}" for c in unverified)
    reason = (
        "[warden:citations] Response contains "
        f"{len(unverified)} file:line citation(s) that were NOT Read or Grep'd "
        "by you in this turn:\n"
        f"{cited_lines}\n"
        "Subagent (Task/Agent) calls do NOT count as direct verification; their "
        "internal Reads are not visible here. For each unverified citation, "
        "either:\n"
        "  1. Read the file yourself now and confirm the line is correct, or\n"
        "  2. Remove the citation from your response.\n"
        "Then continue. Do not stop until every file:line citation is backed "
        "by a Read/Grep tool call you made directly in this turn.\n"
        "(To disable this check: /warden:citations-off)"
    )
    return True, reason, unverified


def check_uncertainty(response_text: str) -> tuple[bool, str, list]:
    if read_mode(UNCERTAINTY_MODE_FILE) == "off":
        return False, "", []
    cleaned = strip_non_citations(response_text)
    hits = [m.group(0) for m in UNCERTAINTY_TELLS_RE.finditer(cleaned)]
    if not hits:
        return False, "", []
    sample = "\n".join(f'  - "{t}"' for t in hits[:5])
    reason = (
        f"[warden:uncertainty] Response contains {len(hits)} self-flagged "
        "uncertainty marker(s). You are reporting back work you know is "
        "incomplete:\n"
        f"{sample}\n"
        "Either verify the flagged items now (Read/Grep) and update the "
        "response, or stop and ASK the user before continuing. Don't ship "
        "with known gaps.\n"
        "(To disable this check: /warden:uncertainty-off)"
    )
    return True, reason, hits


def check_completion(
    response_text: str, last_had_tool: bool
) -> tuple[bool, str, dict]:
    """Layer (e) - "see it through" / Fable-mode completion gate.

    Blocks a turn that ends by PROMISING first-person work without doing it.
    Skips when the turn is still working (ended on a tool call), when the
    response is a clarifying question (a legitimate stop), or when the prose is
    too short to carry a promise. Only the closing window is scanned - a "let me
    check X" mid-response followed by actually checking does not match, because
    the promise will not sit in the tail.
    """
    details: dict = {}
    if read_mode(FABLE_MODE_FILE) == "off":
        details["skipped"] = "fable-off"
        return False, "", details
    if last_had_tool:
        details["skipped"] = "ended-on-tool-call"
        return False, "", details
    cleaned = strip_non_citations(response_text).strip()
    if len(cleaned) < COMPLETION_MIN_RESPONSE_CHARS:
        details["skipped"] = f"response<{COMPLETION_MIN_RESPONSE_CHARS}"
        return False, "", details
    if is_clarifying_response(cleaned):
        details["skipped"] = "response-is-clarifying"
        return False, "", details
    tail = cleaned[-COMPLETION_TAIL_CHARS:]
    m = COMPLETION_PROMISE_RE.search(tail)
    if not m:
        details["skipped"] = "no-promise-in-tail"
        return False, "", details
    details["blocked"] = True
    details["match"] = m.group(0)[:120]
    reason = (
        "[warden:completion] Your response ends by stating an intent to do work "
        f'("{m.group(0).strip()[:80]}") without actually doing it. This is the '
        "race-to-a-promise pattern Fable-mode exists to catch. Do that work NOW "
        "with tool calls; do not hand back a plan you could execute. End the "
        "turn only when the task is complete (with evidence from a tool result "
        "this turn) or you are genuinely blocked on input that only the user can "
        "provide, in which case ASK a direct question instead of promising.\n"
        "(To disable this check: /warden:fable-off)"
    )
    return True, reason, details


def check_grounding(
    response_text: str,
    user_prompt: str,
    verified_paths: set[str],
    strict_off: bool,
    trust_me_consumed: bool,
) -> tuple[bool, str, dict]:
    details: dict = {}
    if strict_off:
        details["skipped"] = "strict-off"
        return False, "", details
    if trust_me_consumed:
        details["skipped"] = "trust-me"
        return False, "", details
    if len(response_text) < GROUNDING_MIN_RESPONSE_CHARS:
        details["skipped"] = f"response<{GROUNDING_MIN_RESPONSE_CHARS}"
        return False, "", details
    if is_clarifying_response(response_text):
        details["skipped"] = "response-is-clarifying"
        return False, "", details
    if not is_codebase_shaped(user_prompt):
        details["skipped"] = "prompt-not-codebase-shaped"
        return False, "", details
    if verified_paths:
        details["skipped"] = "tool-calls-made"
        return False, "", details
    reason = (
        "[warden:grounding] The user's prompt looks codebase-shaped (mentions "
        "code, files, project terms, or this marketplace's plugin names) but "
        "you made ZERO Read/Grep/Glob calls this turn. Methodical-mode "
        "requires grounding codebase claims in actual code, not training-data "
        "inference. Either:\n"
        "  1. Read or Grep the relevant files now and update the response, or\n"
        '  2. Reply with a clarifying question instead of an answer '
        '("want me to first check X?"). Don\'t answer from inference.\n'
        "One-shot bypass for this turn only: /warden:trust-me. Disable for "
        "the whole session: /warden:strict-off."
    )
    details["blocked"] = True
    return True, reason, details
