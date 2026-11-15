---
description: Send a test message to the Slack webhook raven posts to
---

Run exactly this Bash command:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/raven.py" test
```

It prints one line starting with `raven:`. Reply with that line and nothing else, except in one case: if it says
`RAVEN_SLACK_WEBHOOK_URL is not set`, add one line telling the user to export the variable in the shell that starts
Claude Code and restart it. Never print, echo or ask for the webhook URL itself.
