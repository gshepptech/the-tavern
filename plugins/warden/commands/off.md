---
description: Disable warden methodical-mode injection until /warden:on is run
---

The user wants to silence the warden UserPromptSubmit hook. This writes a marker file, so it persists across restarts and future sessions — it is not scoped to the current conversation — until `/warden:on` removes it.

Run exactly this Bash command:

```
mkdir -p ~/.claude && echo off > ~/.claude/.warden-state && echo "warden methodical-mode: OFF. Persists until /warden:on is run (survives restarts, not just this session)."
```

After it succeeds, reply to the user with one short line confirming methodical-mode is off, that it persists until `/warden:on` is run, and that it is not limited to the current session. Do not add anything else.
