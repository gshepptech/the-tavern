---
description: What raven does and how to set it up
---

Reply with exactly the text below and nothing else.

```
raven posts Claude Code events to Slack: a green message when a reply finishes, amber when Claude Code
is waiting on a permission, blue when it has been idle. Each carries the prompt's first line, the
start of the reply, the folder, the git branch and the session id. Secrets are redacted first.

Setup:   export RAVEN_SLACK_WEBHOOK_URL=<your incoming webhook URL>, then restart Claude Code.

/raven:test      send a test message now
/raven:status    webhook, events, dedup window, last five log lines
/raven:help      this text

Options (environment):
RAVEN_EVENTS          stop,notification   which hooks post
RAVEN_DEDUP_SECONDS   60                  drop an identical message sent inside this window
RAVEN_STATE_DIR       plugin data dir     where the log and dedup record live
```
