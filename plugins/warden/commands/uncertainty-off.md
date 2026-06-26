---
description: Disable the warden Stop hook uncertainty-tell scanner
---

The user wants to disable the uncertainty-tell scanner Stop hook. While off, the scanner short-circuits and responses containing "not verified" / "haven't checked" / "I assumed" tells will not be blocked.

Run exactly this Bash command:

```
mkdir -p ~/.claude && echo off > ~/.claude/.warden-uncertainty-mode && echo "warden uncertainty-tell scanner: OFF. Responses with self-flagged uncertainty phrases will not be blocked. Run /warden:uncertainty-on to re-enable."
```

After it succeeds, reply to the user with one short line confirming the uncertainty scanner is off. Do not add anything else.
