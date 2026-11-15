# Raven

*The raven carries word to Slack when a session finishes or needs you.*

**Posts Claude Code session events to Slack, so you know when a reply is done or a permission prompt is waiting.**

[![version](https://img.shields.io/badge/version-1.0.0-1E88E5?style=flat-square)](.claude-plugin/plugin.json)
[![license](https://img.shields.io/badge/license-Apache--2.0-4C9A2A?style=flat-square)](../../LICENSE)
[![python](https://img.shields.io/badge/python-3.10%2B-3776AB?style=flat-square)](scripts/raven.py)

## What it does

Raven sends a Slack message through an incoming webhook when Claude Code finishes a reply or stops to wait for you.
Each message says which prompt it was, how the reply starts, and where it ran: folder, git branch and session id.
Messages are colour-coded so a glance at the channel tells you whether anything needs you.

Use it when you start a long task and walk away, or run several sessions at once and want one place that says
which of them is waiting. Raven never blocks Claude: a missing webhook or a Slack outage is written to a log and the
session carries on.

## Features

- **Two events.** A Stop hook posts when a reply finishes; a Notification hook posts when Claude Code needs a
  permission or has been idle.
- **Colour by what you need to do.** Green for done, amber for waiting on you, blue for idle.
- **Useful context.** The prompt's first line, the first 400 characters of the reply, the folder, the branch (or short
  commit when detached) and the session id.
- **Secrets redacted before sending.** Private keys, Slack, AWS, GitHub, GitLab, Google and `sk-` keys, JWTs, bearer
  tokens, passwords in URLs and `password=` style assignments are replaced with `[redacted]`.
- **Repeats suppressed.** An identical message for the same session inside 60 seconds is dropped.
- **Never blocks, never leaks the URL.** Every failure is logged and the hook exits cleanly; the webhook URL is kept
  out of output and logs.
- **Standard library only.** One Python script using `urllib`.

## Quick start

```bash
claude plugin marketplace add gshepptech/the-tavern
claude plugin install raven@the-tavern
```

Create an incoming webhook in Slack (an app with the Incoming Webhooks feature, pointed at a channel), then export it
in the shell that starts Claude Code and restart it:

```bash
export RAVEN_SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
```

Check the connection from inside Claude Code:

```
/raven:test
```

You need `python3` 3.10 or later on `PATH`.

## How it works

```
Stop / Notification hook event (stdin)
  -> read the transcript: last real prompt, reply text after it
  -> folder from cwd, branch from git
  -> redact, then clip
  -> drop if the same message went out inside the dedup window
  -> POST to RAVEN_SLACK_WEBHOOK_URL (5 second timeout)
  -> one line to raven.log: sent, failed, or why not sent
```

The hook prints nothing and always exits 0, so Claude Code never sees an error from it. Redaction runs before
clipping, so a cut through the middle of a token cannot leave an unredacted fragment. The webhook must be `https`;
plain `http` is accepted only for `localhost`, which is what the tests use.

## Reference

| Command | What it does |
|---|---|
| `/raven:test` | Send a test message and report the result |
| `/raven:status` | Whether the webhook is usable (host only), the events posted, the dedup window and the last five log lines |
| `/raven:help` | Setup and commands |

| Environment variable | Default | Meaning |
|---|---|---|
| `RAVEN_SLACK_WEBHOOK_URL` | none | The incoming webhook. Nothing is sent without it |
| `RAVEN_EVENTS` | `stop,notification` | Which hooks post. `notification` alone posts only when you are needed |
| `RAVEN_DEDUP_SECONDS` | `60` | Drop an identical message sent inside this window. `0` turns it off |
| `RAVEN_STATE_DIR` | plugin data dir | Where `raven.log` and the dedup record live |

State lives in `$CLAUDE_PLUGIN_DATA` when Claude Code provides a plugin data directory, otherwise in
`~/.claude/plugins/data/raven/`. The log is trimmed once it passes 256 KB.

Redaction is pattern-based. It catches the common credential shapes listed above, not every secret a reply could
contain. Point Raven at a channel whose members could already see your terminal.

## Development

```bash
cd plugins/raven
uv run --with pytest python -m pytest -q
```

The tests run the hook script as a subprocess against a local HTTP server standing in for Slack, never the real
service. They cover the message contents, colours, deduplication, the event filter, an unset or non-https webhook,
Slack errors and outages, redaction, and that the webhook URL never reaches output or the log.

## License

Apache-2.0. See [LICENSE](../../LICENSE).
