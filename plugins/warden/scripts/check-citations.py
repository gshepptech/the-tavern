#!/usr/bin/env python3
"""warden Stop hook - methodical-mode enforcement gates.

Reads the Stop hook event JSON from stdin, walks the conversation transcript
to find the current turn's last assistant message and tool calls, then runs
five enforcement gates. Any gate firing blocks the Stop with a combined
reason message that Claude reads on the continued turn.

Gates:
  (a) Citations  - file:line citations in the response must be backed by a
                   Read/Grep call Claude made directly in this turn. One block
                   per turn (honors stop_hook_active liveness).

  (b) Uncertainty - response must NOT contain self-flagged uncertainty
                    tells like "not verified", "haven't checked", "I assumed".
                    One block per turn.

  (c) Grounding  - if the user's prompt looks codebase-shaped, the response
                   requires at least one Read/Grep/Glob call this turn.
                   No general-knowledge fallback. One block per turn.

  (d) Iterative Critic - substantive responses must pass an iterative
                         critic-dialog: rounds 1-3 use warden:fast-critic
                         (Haiku), rounds 4-6 escalate to warden:pre-stop-critic
                         (opus). Each critic runs a 10-item rule compliance
                         audit and sees prior-round feedback (continuity
                         check). Up to 6 rounds per turn. At round 6: HARD
                         block (no pass-through) until /warden:trust-me
                         consumed. Round counter replaces stop_hook_active
                         honoring for this gate ONLY.

  (e) Completion  - "see it through" / Fable-mode gate. The response must
                    NOT end by PROMISING work it then declines to do. If the
                    closing prose states a first-person intent to act
                    ("I'll implement…", "let me run…", "now I'll…") but the
                    turn ended with no trailing tool call and no clarifying
                    question, block and force the work to happen now. One block
                    per turn (honors stop_hook_active). Deterministic regex.

One-shot bypass for (c) and (d): ~/.claude/.warden-trust-me (consumed on read).

Recursion guard: if the assistant response starts with EITHER critic sentinel
([warden:fast-critic-output] OR [warden:pre-stop-critic-output]), ALL gates
skip (this turn IS a critic, not the main Claude).

Mode files (all under ~/.claude/):
  .warden-citations-mode     (a)  absent/"default" / "off"
  .warden-uncertainty-mode   (b)  absent/"default" / "off"
  .warden-strict-mode        (c)+(d)  absent/"default" / "off"
  .warden-fable-mode         (e)  absent/"default" / "off"
  .warden-trust-me           one-shot bypass file for (c)+(d), consumed on read

Liveness model:
  - Gates (a)/(b)/(c) honor stop_hook_active: one block per turn each
    so a gate can never trap a turn in a loop
  - Gate (d) uses transcript-based round counter: up to MAX_CRITIC_ROUNDS=6
    block-rounds per turn, then HARD block at round 6
  - Trust-me file consumed before any gate runs; if present, (c)+(d) skip
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

from warden_gates.config import STRICT_MODE_FILE
from warden_gates.critic import check_critic
from warden_gates.gates import (
    check_citations,
    check_completion,
    check_grounding,
    check_uncertainty,
)
from warden_gates.state import consume_trust_me, log_event, read_mode
from warden_gates.transcript import (
    assistant_text,
    collect_verified_paths,
    find_last_user_prompt,
    last_message_has_tool_use,
    load_transcript,
    slice_current_turn,
    starts_with_any_sentinel,
)


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0

    stop_hook_active = bool(event.get("stop_hook_active"))

    transcript_path = event.get("transcript_path")
    if not transcript_path or not os.path.exists(transcript_path):
        return 0

    messages = load_transcript(transcript_path)
    turn_messages, last_assistant = slice_current_turn(messages)
    if last_assistant is None:
        return 0

    response_text = assistant_text(last_assistant)
    last_had_tool = last_message_has_tool_use(last_assistant)

    if starts_with_any_sentinel(response_text):
        log_event(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "session": event.get("session_id"),
                "decision": "pass",
                "reason": "critic-output-sentinel",
            }
        )
        return 0

    user_prompt = find_last_user_prompt(messages)
    verified_paths = collect_verified_paths(turn_messages)
    strict_off = read_mode(STRICT_MODE_FILE) == "off"
    # Consume unconditionally, even when strict is off. The flag is only USED
    # by the strict gates below, but if it were left unconsumed while strict is
    # off it would strand - a stale armed marker would then bypass some future
    # turn once strict is re-enabled. Clearing it here can't weaken anything:
    # with strict off, the gates it feeds are skipped anyway.
    trust_me_consumed = consume_trust_me() and not strict_off

    citations_blocked, citations_reason, citations_details = check_citations(
        response_text, verified_paths
    )
    uncertainty_blocked, uncertainty_reason, uncertainty_details = check_uncertainty(
        response_text
    )
    completion_blocked, completion_reason, completion_details = check_completion(
        response_text, last_had_tool
    )
    grounding_blocked, grounding_reason, grounding_details = check_grounding(
        response_text, user_prompt, verified_paths, strict_off, trust_me_consumed
    )
    critic_blocked, critic_reason, critic_details = check_critic(
        response_text,
        user_prompt,
        turn_messages,
        verified_paths,
        strict_off,
        trust_me_consumed,
    )

    if stop_hook_active:
        citations_blocked = False
        uncertainty_blocked = False
        completion_blocked = False
        grounding_blocked = False

    log_event(
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "session": event.get("session_id"),
            "response_chars": len(response_text),
            "user_prompt_chars": len(user_prompt),
            "verified_paths_count": len(verified_paths),
            "trust_me_consumed": trust_me_consumed,
            "strict_off": strict_off,
            "stop_hook_active": stop_hook_active,
            "unverified": citations_details if citations_blocked else [],
            "checks": {
                "citations": {
                    "blocked": citations_blocked,
                    "details": citations_details,
                },
                "uncertainty": {
                    "blocked": uncertainty_blocked,
                    "details": uncertainty_details,
                },
                "completion": {
                    "blocked": completion_blocked,
                    "details": completion_details,
                },
                "grounding": {
                    "blocked": grounding_blocked,
                    "details": grounding_details,
                },
                "critic": {
                    "blocked": critic_blocked,
                    "details": critic_details,
                },
            },
            "decision": "block"
            if any(
                [
                    citations_blocked,
                    uncertainty_blocked,
                    completion_blocked,
                    grounding_blocked,
                    critic_blocked,
                ]
            )
            else "pass",
        }
    )

    reasons = [
        r
        for r in (
            citations_reason if citations_blocked else "",
            uncertainty_reason if uncertainty_blocked else "",
            completion_reason if completion_blocked else "",
            grounding_reason if grounding_blocked else "",
            critic_reason if critic_blocked else "",
        )
        if r
    ]
    if not reasons:
        return 0

    combined = "\n\n".join(reasons)
    print(json.dumps({"decision": "block", "reason": combined}))
    return 0


if __name__ == "__main__":
    # Last-resort fail-open. This hook runs at the end of every turn in every
    # project; a traceback here would surface as a hook error on work that has
    # nothing to do with Warden. A gate that cannot decide must let the response
    # through, never break the session. Specific failure modes are handled
    # closer to their cause - this only catches what nobody anticipated.
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - deliberate catch-all, see above
        # Fail open, but leave a trace. A silently-crashing gate looks
        # identical to a working one - the user believes they are protected
        # while nothing fires. Record it so a persistent break is findable.
        try:
            log_event({
                "ts": datetime.now(timezone.utc).isoformat(),
                "decision": "error-fail-open",
                "error": f"{type(exc).__name__}: {exc}"[:200],
            })
        except Exception:  # noqa: BLE001 - logging must never break fail-open
            pass
        sys.exit(0)
