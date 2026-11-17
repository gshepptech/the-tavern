"""Gate (d): the iterative two-tier critic dialog."""

from __future__ import annotations

from .config import (
    CLARIFYING_GATE_LENGTH,
    CRITIC_MIN_RESPONSE_CHARS,
    DEEP_CRITIC_AGENT_TYPE,
    FAST_CRITIC_AGENT_TYPE,
    FAST_CRITIC_LAST_ROUND,
    MAX_CRITIC_ROUNDS,
)
from .gates import is_clarifying_response
from .transcript import (
    collect_critic_calls_by_type,
    find_all_critic_outputs,
    summarize_tool_calls,
)


def critic_tier_for_round(round_num: int) -> str:
    """Map round number to critic agent type: rounds 1-3 fast, 4+ deep."""
    if round_num <= FAST_CRITIC_LAST_ROUND:
        return FAST_CRITIC_AGENT_TYPE
    return DEEP_CRITIC_AGENT_TYPE


def format_prior_feedback(prior_outputs: list[dict]) -> str:
    """Format prior critic outputs for inclusion in the next round's spawn prompt."""
    if not prior_outputs:
        return ""
    lines: list[str] = []
    for i, p in enumerate(prior_outputs, start=1):
        round_label = p.get("round") or i
        verdict = p.get("verdict") or "(unknown)"
        lines.append(f"  Round {round_label} verdict: {verdict}")
        if p.get("audit"):
            audit_lines = [
                f"    {ln}" for ln in p["audit"].splitlines() if ln.strip()
            ]
            if audit_lines:
                lines.append("    Compliance audit:")
                lines.extend(audit_lines)
        if p.get("feedback"):
            fb_lines = [
                f"    {ln}" for ln in p["feedback"].splitlines() if ln.strip()
            ]
            if fb_lines:
                lines.append("    Specific feedback:")
                lines.extend(fb_lines)
    return "\n".join(lines)


def check_critic(
    response_text: str,
    user_prompt: str,
    turn_messages: list[dict],
    verified_paths: set[str],
    strict_off: bool,
    trust_me_consumed: bool,
) -> tuple[bool, str, dict]:
    """Layer (d) - iterative two-tier critic gate-dialog.

    Up to MAX_CRITIC_ROUNDS rounds per turn:
      - Rounds 1..FAST_CRITIC_LAST_ROUND: require warden:fast-critic call
      - Rounds FAST_CRITIC_LAST_ROUND+1..MAX_CRITIC_ROUNDS: require warden:pre-stop-critic

    Gate passes when most recent critic returns CONCUR or CONCUR WITH CAVEATS.
    At MAX_CRITIC_ROUNDS with non-CONCUR: HARD block (no pass-through) until
    trust-me consumed.
    """
    details: dict = {}
    if strict_off:
        details["skipped"] = "strict-off"
        return False, "", details
    if trust_me_consumed:
        details["skipped"] = "trust-me"
        return False, "", details
    if len(response_text) < CRITIC_MIN_RESPONSE_CHARS:
        details["skipped"] = f"response<{CRITIC_MIN_RESPONSE_CHARS}"
        return False, "", details
    if (
        is_clarifying_response(response_text)
        and len(response_text) < CLARIFYING_GATE_LENGTH
    ):
        details["skipped"] = "short-clarifying-response"
        return False, "", details

    fast_count = collect_critic_calls_by_type(turn_messages, FAST_CRITIC_AGENT_TYPE)
    deep_count = collect_critic_calls_by_type(turn_messages, DEEP_CRITIC_AGENT_TYPE)
    rounds_completed = fast_count + deep_count
    next_round = rounds_completed + 1
    details["fast_critic_calls"] = fast_count
    details["deep_critic_calls"] = deep_count
    details["rounds_completed"] = rounds_completed
    details["next_round"] = next_round

    prior_outputs = find_all_critic_outputs(turn_messages)
    details["prior_verdicts"] = [p.get("verdict") for p in prior_outputs]

    if rounds_completed > 0:
        last_verdict = prior_outputs[-1].get("verdict") if prior_outputs else None
        details["last_verdict"] = last_verdict
        if last_verdict in ("CONCUR", "CONCUR WITH CAVEATS"):
            return False, "", details

    if rounds_completed >= MAX_CRITIC_ROUNDS:
        prior_summary = format_prior_feedback(prior_outputs)
        reason = (
            f"[warden:critic-hard-block] Round {MAX_CRITIC_ROUNDS} reached "
            "WITHOUT a CONCUR verdict from the methodical-mode gate-critic. "
            "Per your /warden:strict-on configuration, this Stop is HARD-blocked "
            "until /warden:trust-me is invoked by the user.\n\n"
            f"Accumulated critic flags across {MAX_CRITIC_ROUNDS} rounds:\n"
            f"{prior_summary}\n\n"
            "Required action: STOP attempting to revise the response. Instead, "
            "send the user a message stating:\n"
            "  1. You've been blocked by the methodical-mode gate-critic after "
            f"{MAX_CRITIC_ROUNDS} rounds.\n"
            "  2. The accumulated unresolved flags (summarized above).\n"
            "  3. Ask the user to either (a) guide you on what's still wrong, "
            "or (b) invoke /warden:trust-me to bypass the gate for this turn.\n\n"
            "Then WAIT for the user. Do not silently retry Stop. The Stop "
            "hook will continue to BLOCK every Stop attempt until the trust-me "
            "bypass is invoked or you abandon this turn."
        )
        details["hard_block"] = True
        return True, reason, details

    next_tier = critic_tier_for_round(next_round)
    tool_calls_summary = summarize_tool_calls(turn_messages)
    files_touched = sorted(verified_paths) if verified_paths else []
    files_summary = (
        "\n".join(f"  - {p}" for p in files_touched) if files_touched else "  (none)"
    )

    if rounds_completed == 0:
        reason = (
            f"[warden:critic] Round 1 of {MAX_CRITIC_ROUNDS}: methodical-mode "
            f"gate-critic required. Response is substantive ({len(response_text)} "
            f"chars). Spawn the {next_tier} subagent to run the 10-item rule "
            "compliance audit:\n\n"
            "  Agent({\n"
            f"    subagent_type: '{next_tier}',\n"
            "    description: 'Methodical-mode gate-critic round 1',\n"
            "    prompt: <see input contract below>\n"
            "  })\n\n"
            "Required spawn-prompt sections (label each clearly):\n"
            f"  - User prompt: {user_prompt[:600]}"
            f"{'...' if len(user_prompt) > 600 else ''}\n"
            "  - Draft response: <quote your full draft response here>\n"
            "  - Tool calls this turn:\n"
            f"{tool_calls_summary}\n"
            "  - Files Claude touched:\n"
            f"{files_summary}\n"
            "  - Round number: 1\n"
            "  (No prior-round feedback on round 1.)\n\n"
            "Critic returns CONCUR / CONCUR WITH CAVEATS / PUSH BACK / WRONG SHAPE.\n"
            "  - CONCUR or CONCUR WITH CAVEATS: response lands.\n"
            "  - PUSH BACK or WRONG SHAPE: revise based on the critic's "
            f"specific feedback, attempt Stop again. The hook will run round 2.\n"
            f"  - Maximum {MAX_CRITIC_ROUNDS} rounds per turn. At round "
            f"{MAX_CRITIC_ROUNDS}: HARD block until /warden:trust-me invoked.\n"
            "One-shot bypass: /warden:trust-me. Disable: /warden:strict-off."
        )
        details["blocked"] = True
        details["block_kind"] = "first-round-spawn"
        return True, reason, details

    prior_summary = format_prior_feedback(prior_outputs)
    escalation_note = ""
    if next_round == FAST_CRITIC_LAST_ROUND + 1:
        escalation_note = (
            f"\n  ESCALATION: rounds 1..{FAST_CRITIC_LAST_ROUND} used the "
            "fast-critic (Haiku). Rounds "
            f"{FAST_CRITIC_LAST_ROUND + 1}..{MAX_CRITIC_ROUNDS} use the "
            "deep-tier pre-stop-critic (opus). Persistent non-CONCUR from "
            "fast-critic triggered this escalation, so the issues are real, "
            "not Haiku-tier judgment limits.\n"
        )
    reason = (
        f"[warden:critic] Round {next_round} of {MAX_CRITIC_ROUNDS}: the prior "
        "round did NOT return CONCUR. Methodical-mode gate-critic requires "
        f"another round.{escalation_note}\n"
        "Prior-round feedback:\n"
        f"{prior_summary}\n\n"
        f"Spawn the {next_tier} subagent for round {next_round}:\n\n"
        "  Agent({\n"
        f"    subagent_type: '{next_tier}',\n"
        f"    description: 'Methodical-mode gate-critic round {next_round}',\n"
        "    prompt: <see input contract below>\n"
        "  })\n\n"
        "Required spawn-prompt sections:\n"
        f"  - User prompt: {user_prompt[:600]}"
        f"{'...' if len(user_prompt) > 600 else ''}\n"
        "  - Draft response: <quote your revised draft>\n"
        "  - Tool calls this turn:\n"
        f"{tool_calls_summary}\n"
        "  - Files Claude touched:\n"
        f"{files_summary}\n"
        f"  - Round number: {next_round}\n"
        "  - Prior-round feedback (CRITICAL: the critic uses this to check "
        "you actually addressed prior flags, not just rephrased the same "
        "dodge):\n"
        f"{prior_summary}\n\n"
        "The critic will flag each prior-round item as ADDRESSED, STILL "
        "FAILING, or REPHRASED-NOT-FIXED. Any non-ADDRESSED prior flag "
        "guarantees PUSH BACK.\n"
        f"At round {MAX_CRITIC_ROUNDS}: HARD block. Bypass: /warden:trust-me."
    )
    details["blocked"] = True
    details["block_kind"] = "next-round-spawn"
    details["escalation"] = next_round == FAST_CRITIC_LAST_ROUND + 1
    return True, reason, details
