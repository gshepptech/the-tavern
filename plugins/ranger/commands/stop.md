---
description: "Tell Ranger to down tools — mark the run stopped and disarm the guard"
argument-hint: "[run-id]"
allowed-tools: ["Bash(cat:*)", "Bash(ls:*)", "Bash(date:*)", "Bash(test:*)", "Bash(tail:*)", "Read", "Write", "Edit"]
hide-from-slash-command-tool: "true"
---

# Stop Ranger

End the active run: mark it stopped and disarm, so a `/loop` driving it winds down (press Esc to end the loop) and the next `/ranger:run` starts fresh instead of continuing this one.

1. Read `.ranger/active-run.json`. If it is missing, empty, or `{}`, say "No active Ranger run." and stop.

2. If `$ARGUMENTS` names a run id that does not match the marker's `run_id`, say so and stop — do not stop someone else's run.

3. Read `<run_dir>/state.json`. Set:
   - `status: "stopped"`
   - `ended_at: "<ISO-8601 UTC>"`

4. **Disarm the guard hook**: overwrite `.ranger/active-run.json` with `{}`.

   Do this even if step 3 failed — a broken state file must never leave the gate armed. If you cannot write the marker, tell the user to delete `.ranger/active-run.json` by hand.

5. Report:

```
Ranger stood down — <run_id>
<cycle> item(s) committed · <elapsed>
Last: <final line of journal.md>
Backlog and journal kept at .ranger/runs/<run_id>/ — /ranger:resume picks up exactly where this left off.
```

Nothing is reverted and nothing is cleaned up. Every item Ranger finished is already its own local commit.
