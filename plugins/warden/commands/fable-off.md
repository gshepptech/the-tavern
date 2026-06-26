---
description: Disable the warden Fable-mode completion gate (see-it-through enforcement)
---

The user wants to disable the warden Fable-mode completion gate (the Stop-hook check that blocks promise-without-action endings).

Run exactly this Bash command:

```
mkdir -p ~/.claude && echo off > ~/.claude/.warden-fable-mode && echo "warden fable-mode: OFF for this session. Run /warden:fable-on to re-enable."
```

After it succeeds, reply to the user with one short line confirming Fable-mode is off and noting that `/warden:fable-on` re-enables it. Do not add anything else.
