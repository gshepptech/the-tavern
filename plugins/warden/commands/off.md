---
description: Disable warden methodical-mode injection for the rest of this session
---

The user wants to silence the warden UserPromptSubmit hook for the remainder of this session.

Run exactly this Bash command:

```
mkdir -p ~/.claude && echo off > ~/.claude/.warden-state && echo "warden methodical-mode: OFF for this session. Run /warden:on to re-enable."
```

After it succeeds, reply to the user with one short line confirming methodical-mode is off and noting that `/warden:on` re-enables it. Do not add anything else.
