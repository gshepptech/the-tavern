# monk

**Keeps Claude Code's replies short: the answer first, one next action, and nothing padded around them.**

[![version](https://img.shields.io/badge/version-1.0.0-1E88E5?style=flat-square)](.claude-plugin/plugin.json)
[![license](https://img.shields.io/badge/license-Apache--2.0-4C9A2A?style=flat-square)](../../LICENSE)
[![python](https://img.shields.io/badge/python-3.10%2B-3776AB?style=flat-square)](scripts/monk.py)

## What it does

monk shapes how replies read. At session start it loads seven rules into the conversation, and on every prompt it adds
a one-line reminder so the rules hold late in a long session. An optional length gate checks each finished reply and,
when one runs over a word or list budget, sends it back once with instructions to cut it down.

Use it when you read replies in a terminal and want the result in the first line, not the fourth paragraph. Turn it
off for a session, or exempt a single turn, when you want the long version.

## Features

- **Seven rules, loaded once.** Answer first, numbered steps for multi-step work, one concrete next action, no
  preamble, recap or sign-off, real time units, a flat tone on failure, and lists of five or fewer.
- **A one-line reminder per prompt.** Short enough to cost almost nothing, so the rules survive a long session.
- **An optional length gate.** A Stop hook measures the reply's words and its longest list, and blocks an over-budget
  reply once with a message that says what to cut. It never blocks the same turn twice.
- **Code is free.** Fenced code blocks count toward neither budget.
- **One-turn exemption.** `/monk:verbose` lifts the rules and the gate for the current question or the next one.
- **Per-session state.** Turning monk off in one session leaves every other session alone.
- **Fails open.** A hook error is swallowed and logged to stderr; Claude Code carries on as if monk were not
  installed.

## Quick start

```bash
claude plugin marketplace add gshepptech/the-tavern
claude plugin install monk@the-tavern
```

The rules are on in every new session. To add the length gate with a 200-word budget:

```
/monk:gate-on 200
```

You need `python3` 3.10 or later on `PATH`.

## How it works

```
SessionStart      -> monk.py session-start -> the seven rules, as session context
UserPromptSubmit  -> monk.py prompt        -> applies /monk:* commands, or adds the reminder line
Stop              -> monk.py stop          -> length gate: block once with a "shorten it" message, or pass
                          |
                          v
            <data dir>/sessions/<session_id>.json
```

All three hooks are one Python script with no dependencies. The `/monk:*` commands are applied by the
UserPromptSubmit hook, not by the command files, because only a hook is told which session it is in. The hook writes
the change to that session's state file and returns a `monk:` confirmation line, and the command file tells Claude to
repeat it.

The gate counts words outside fenced code and the items in the longest single list, with nested lists counted on
their own. It skips a turn that was a `/monk:*` command, a turn exempted by `/monk:verbose`, and any turn it has
already blocked once.

## Reference

| Command | What it does |
|---|---|
| `/monk:on` | Rules on for this session (the default) |
| `/monk:off` | Rules and the length gate off for this session |
| `/monk:verbose [question]` | Exempt one turn: this one when a question follows, otherwise the next |
| `/monk:status` | Show the shaping state, the gate state and the budgets |
| `/monk:gate-on [max-words] [max-items]` | Turn the gate on, optionally setting the budgets |
| `/monk:gate-off` | Turn the gate off |
| `/monk:help` | Commands and current state |

| Environment variable | Default | Meaning |
|---|---|---|
| `MONK_DEFAULT` | `on` | Whether a new session starts with the rules on |
| `MONK_GATE` | `off` | Whether a new session starts with the length gate on |
| `MONK_MAX_WORDS` | `250` | Word budget for a new session |
| `MONK_MAX_ITEMS` | `5` | List budget for a new session |
| `MONK_DATA_DIR` | plugin data dir | Where session state is kept |

State lives in `$CLAUDE_PLUGIN_DATA/sessions/` when Claude Code provides a plugin data directory, otherwise in
`~/.claude/plugins/data/monk/sessions/`. Files untouched for seven days are deleted at the next session start.

## Development

```bash
cd plugins/monk
uv run --with pytest python -m pytest -q
```

The tests run the hook script as a subprocess with real hook events on stdin and a temporary data directory, covering
every command, the gate's block-once rule, the verbose exemption, transcript parsing and bad input.

## License

Apache-2.0. See [LICENSE](../../LICENSE).
