---
description: Re-enable warden methodical-mode injection
---

The user wants to re-enable the warden UserPromptSubmit hook.

Run exactly this Bash command:

```
rm -f ~/.claude/.warden-state && echo "warden methodical-mode: ON. Every turn now gets the methodical preamble."
```

After it succeeds, reply to the user with one short line confirming methodical-mode is on. Do not add anything else.
