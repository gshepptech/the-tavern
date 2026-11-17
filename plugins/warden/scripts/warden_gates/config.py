"""Mode-file paths, thresholds and the regexes every gate matches against."""

from __future__ import annotations

import os
import re
from pathlib import Path

HOME = Path(os.environ.get("HOME", os.path.expanduser("~")))
CITATIONS_MODE_FILE = HOME / ".claude" / ".warden-citations-mode"
UNCERTAINTY_MODE_FILE = HOME / ".claude" / ".warden-uncertainty-mode"
STRICT_MODE_FILE = HOME / ".claude" / ".warden-strict-mode"
FABLE_MODE_FILE = HOME / ".claude" / ".warden-fable-mode"
TRUST_ME_FILE = HOME / ".claude" / ".warden-trust-me"
# /warden:trust-me writes TRUST_ME_FILE; the UserPromptSubmit hook promotes it to
# this armed marker at the start of the NEXT turn. Only the armed marker is
# honoured here - see consume_trust_me() for why.
TRUST_ME_ARMED_FILE = HOME / ".claude" / ".warden-trust-me-armed"
LOG_FILE = HOME / ".claude" / ".warden-citations-log.jsonl"

# Critic agent identifiers - two tiers
FAST_CRITIC_AGENT_TYPE = "warden:fast-critic"
DEEP_CRITIC_AGENT_TYPE = "warden:pre-stop-critic"

# Sentinel markers - first line of each critic's output. Recursion guard.
FAST_CRITIC_SENTINEL = "[warden:fast-critic-output]"
DEEP_CRITIC_SENTINEL = "[warden:pre-stop-critic-output]"
CRITIC_SENTINELS = (FAST_CRITIC_SENTINEL, DEEP_CRITIC_SENTINEL)

# Iterative gate-dialog: max 6 rounds per turn.
# Rounds 1-3: fast-critic (Haiku). Rounds 4-6: pre-stop-critic (opus escalation).
# At round 6 reached without CONCUR: HARD block until trust-me consumed.
MAX_CRITIC_ROUNDS = 6
FAST_CRITIC_LAST_ROUND = 3  # rounds 1..3 use fast-critic; rounds 4..6 escalate

# Length thresholds (chars)
GROUNDING_MIN_RESPONSE_CHARS = 240
CRITIC_MIN_RESPONSE_CHARS = 240  # catch short ritual responses, slightly above the citation-shaped floor
CLARIFYING_GATE_LENGTH = 1200  # asks shorter than this skip critic gate

# Code-file extensions (used by both citation regex and grounding heuristic)
CODE_EXT = (
    "go|ts|tsx|js|jsx|mjs|cjs|py|rb|rs|java|kt|swift|c|cc|cpp|cxx|h|hpp|"
    "cs|php|scala|clj|ex|exs|erl|hs|ml|fs|fsx|sh|bash|zsh|"
    "proto|sql|yaml|yml|toml|ini|json|jsonl|"
    "md|mdx|tf|hcl|dockerfile|"
    "html|css|scss|sass|less|vue|svelte"
)

CITATION_RE = re.compile(
    rf"(?P<path>(?:[\w\-./]+/)*[\w\-.]+\.(?:{CODE_EXT})):(?P<line>\d+)",
    re.IGNORECASE,
)

FENCED_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
DIFF_LINE_RE = re.compile(r"^[+\-@]{1,3}\s")

VERIFICATION_TOOLS = {"Read", "Grep", "Glob"}
AGENT_TOOLS = {"Task", "Agent"}

# (b) Uncertainty-tell scanner - narrow regex, only the specific failure mode
UNCERTAINTY_TELLS_RE = re.compile(
    r"\b("
    r"not\s+yet\s+verified|"
    r"haven't\s+(?:verified|checked|confirmed|read)|"
    r"have\s+not\s+(?:verified|checked|confirmed|read)|"
    r"didn't\s+(?:verify|check|confirm|read)|"
    r"did\s+not\s+(?:verify|check|confirm|read)|"
    r"unverified|"
    r"still\s+need\s+to\s+(?:verify|check|confirm)|"
    r"i\s+assumed|"
    r"i'm\s+assuming|"
    r"todo:\s*verify"
    r")\b",
    re.IGNORECASE,
)

# (c) Grounding - three independent signals that a prompt is "codebase-shaped"
CODEBASE_PATH_RE = re.compile(r"\b[\w\-.]+/[\w\-./]+\b")
CODEBASE_EXT_RE = re.compile(rf"\.(?:{CODE_EXT})\b", re.IGNORECASE)
CODEBASE_ACTION_RE = re.compile(
    r"\b("
    r"function|file|files|code|fix|implement|modify|add|remove|delete|"
    r"refactor|rename|where\s+is|how\s+does|"
    r"this\s+(?:codebase|project|repo|repository|file|function|module)|"
    r"the\s+(?:codebase|project|repo|function|file|code|module|handler|endpoint|hook|script|plugin|agent|skill|command)|"
    r"our\s+(?:codebase|project|repo)|"
    r"my\s+(?:codebase|project|repo)|"
    r"in\s+(?:the\s+)?codebase|"
    # Marketplace plugin identity tokens. These are LOAD-BEARING: a user
    # prompt containing one of these words is treated as codebase-shaped so
    # the grounding gate fires.
    r"sage|smith|warden|sellsword|cleric|scout|tactician|seer"
    r")\b",
    re.IGNORECASE,
)

# (c) Grounding - markers that the assistant is asking, not answering
CLARIFYING_QUESTION_RE = re.compile(
    r"\b("
    r"want\s+me\s+to|"
    r"should\s+i|"
    r"which\s+(?:would|of\s+these|do\s+you)|"
    r"do\s+you\s+(?:want|prefer|need)|"
    r"would\s+you\s+(?:like|prefer)|"
    r"is\s+that\s+(?:right|what\s+you\s+meant)"
    r")\b",
    re.IGNORECASE,
)

# (e) Completion - first-person intent-to-act in the closing prose. Two clauses
# must both hit: a first-person promise opener AND an action verb after it. The
# first clause is anchored to first-person so "next time you can run X" (advice,
# not a dodge) does not match. Scanned only in the closing window of the prose.
COMPLETION_PROMISE_RE = re.compile(
    r"\b("
    r"i'?ll|i\s+will|let\s+me|i'?m\s+going\s+to|i'?m\s+about\s+to|"
    r"now\s+i'?ll|now\s+i\s+will|next\s+i'?ll|next\s+i\s+will|i\s+can\s+now"
    r")\b[^.\n?!]{0,80}\b("
    r"now|next|then|implement|create|write|add|run|fix|save|build|start|"
    r"proceed|continue|wire|set\s+up|begin|make\s+the|apply|update|refactor"
    r")\b",
    re.IGNORECASE,
)

# (e) Completion - minimum prose length below which the gate stays quiet.
COMPLETION_MIN_RESPONSE_CHARS = 40
# (e) Completion - only the closing prose is a "promise instead of doing it".
COMPLETION_TAIL_CHARS = 600

# (d) Critic - verdict extraction from critic output (used for gate decision)
CRITIC_VERDICT_RE = re.compile(
    r"^###\s+Verdict\s*\n\s*(CONCUR(?:\s+WITH\s+CAVEATS)?|PUSH\s+BACK|WRONG\s+SHAPE)\b",
    re.IGNORECASE | re.MULTILINE,
)

# (d) Critic - round number extraction
CRITIC_ROUND_RE = re.compile(
    r"^###\s+Round\s*\n\s*(\d+)\b",
    re.IGNORECASE | re.MULTILINE,
)

# (d) Critic - "Specific feedback for Claude" section extraction
CRITIC_FEEDBACK_RE = re.compile(
    r"^###\s+Specific\s+feedback\s+for\s+Claude\s*\n(.*?)(?=^###\s|\Z)",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)

# (d) Critic - "Compliance audit" section extraction
CRITIC_AUDIT_RE = re.compile(
    r"^###\s+Compliance\s+audit\s*\n(.*?)(?=^###\s|\Z)",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)
