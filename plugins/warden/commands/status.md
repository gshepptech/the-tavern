---
description: Show the current warden methodical-mode and citation-verifier state
---

The user wants to see the warden state values: methodical-mode (the UserPromptSubmit preamble injection), citation-verifier (the Stop hook), and fable-mode (the completion gate).

Run exactly this Bash command:

```
methodical="on"; [ -f ~/.claude/.warden-state ] && methodical=$(cat ~/.claude/.warden-state | tr -d '[:space:]'); citations="default"; [ -f ~/.claude/.warden-citations-mode ] && citations=$(cat ~/.claude/.warden-citations-mode | tr -d '[:space:]'); fable="default"; [ -f ~/.claude/.warden-fable-mode ] && fable=$(cat ~/.claude/.warden-fable-mode | tr -d '[:space:]'); echo "warden methodical-mode: ${methodical}"; echo "warden citation-verifier: ${citations}"; echo "warden fable-mode: ${fable}"
```

After it succeeds, reply to the user with three short lines:

- methodical-mode: explain the value
  - `on` — methodical preamble fires every turn (default)
  - `off` — silenced until `/warden:on` re-enables it (marker file — persists across restarts, not scoped to this session)
  - `casual` — next turn skips, then auto-reverts to on
- citation-verifier: explain the value
  - `default` — Stop hook blocks responses with unverified file:line citations (default)
  - `off` — hook disabled; `/warden:citations-on` re-enables
- fable-mode: explain the value
  - `default` — Stop hook blocks responses that end by promising work without doing it (default)
  - `off` — gate disabled; `/warden:fable-on` re-enables

Keep it short — one line per state. Do not add anything else.
