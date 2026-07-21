---
description: "Tell Ranger to down tools — the only clean way to end a run"
argument-hint: "[run-id]"
allowed-tools: ["Bash(cat:*)", "Bash(ls:*)", "Bash(date:*)", "Bash(test:*)", "Bash(tail:*)", "Read", "Write", "Edit"]
hide-from-slash-command-tool: "true"
---

# Stop Ranger

End the active run. This is the intended exit — the Stop hook blocks everything else.

1. Read `.ranger/active-run.json`. If it is missing, empty, or `{}`, say "No active Ranger run." and stop.

2. If `$ARGUMENTS` names a run id that does not match the marker's `run_id`, say so and stop — do not stop someone else's run.

3. Read `<run_dir>/state.json`. Set:
   - `status: "stopped"`
   - `ended_at: "<ISO-8601 UTC>"`

4. **Disarm the hooks**: overwrite `.ranger/active-run.json` with `{}`.

   Do this even if step 3 failed — a broken state file must never leave the gate armed. If you cannot write the marker, tell the user to delete `.ranger/active-run.json` by hand.

5. Report:

```
Ranger stood down — <run_id>
<cycle> item(s) committed · <elapsed>
Last: <final line of journal.md>
Backlog and journal kept at .ranger/runs/<run_id>/ — /ranger:run picks up where this left off.
```

Nothing is reverted and nothing is cleaned up. Every item Ranger finished is already its own local commit.
