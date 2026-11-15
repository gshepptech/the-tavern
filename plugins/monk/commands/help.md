---
description: What monk does and the commands it takes
---

The monk UserPromptSubmit hook has put a `monk:` line in your context with the current state. Reply with exactly
the text below, replacing `<state>` with the part of that line after `monk: ` (or with "unknown, the hook did not
run" if there is no such line). Add nothing else.

```
monk keeps replies short: answer first, numbered steps, one next action, no preamble or sign-off,
real time units, a flat tone on failure, and lists of five or fewer.

Now: <state>

/monk:on                         rules on for this session (the default)
/monk:off                        rules and length gate off for this session
/monk:verbose [question]         exempt one turn: this one with a question, otherwise the next
/monk:status                     show the state above
/monk:gate-on [words] [items]    send an over-budget reply back once to be shortened
/monk:gate-off                   stop checking length
/monk:help                       this text
```
