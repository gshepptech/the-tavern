---
description: Disable the warden Stop hook citation verifier
---

The user wants to disable the citation-verifier Stop hook. While off, the hook short-circuits and never blocks responses regardless of citation accuracy.

Run exactly this Bash command:

```
mkdir -p ~/.claude && echo off > ~/.claude/.warden-citations-mode && echo "warden citation-verifier: OFF. Responses with unverified file:line citations will not be blocked. Run /warden:citations-on to re-enable."
```

After it succeeds, reply to the user with one short line confirming the citation hook is off. Do not add anything else.
