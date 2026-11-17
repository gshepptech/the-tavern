# Preset: UX & real-user flows

Use the app the way a real person would, end to end, and fix what annoys or blocks them. Don't glance at the code; **drive the running app** (the assessor does this in a browser). Judge the *experience*, not the markup.

Each item is `[applies when] -> what good looks like`. If the `[applies when]` condition is not true of this codebase, **skip the item**. Never invent the flow or propose adding it.

- **The primary task completes**: [app has a main job: checkout, compose, search, upload…] -> a first-time user can finish it without getting stuck, guessing, or hitting a dead end. Walk it start to finish.
- **Feedback on every action**: [any action with a result: submit, save, delete] -> the user sees confirmation, progress, or a clear error, never silence, never a frozen button.
- **Errors are recoverable and legible**: [any form or operation that can fail] -> the message says what went wrong and what to do; the user's input isn't lost; there's a way forward.
- **Maps / data-viz are usable**: [app renders a map or chart] -> it loads, is labeled, pans/zooms/filters where expected, and is correct at the edges (no data, one point, huge data). Actually load it and interact.
- **Navigation & orientation**: [more than one screen] -> the user always knows where they are and how to get back; deep links and browser back behave.
- **Forms respect the user**: [any form] -> sensible defaults, inline validation, correct input types/autocomplete, no needless required fields, no losing work on a mistake.
- **Destructive actions are guarded**: [delete/irreversible actions exist] -> confirmation or undo; not a silent one-click data loss.
- **Latency is handled**: [anything async] -> optimistic or progressive feedback so the app never feels hung; slow paths show progress.
- **First-run / empty account**: [app has per-user state] -> a brand-new user sees guidance, not a broken-looking empty shell.
- **Keyboard & focus**: [interactive UI] -> you can complete key flows by keyboard; focus goes somewhere sensible after actions and in dialogs.

Report each finding as the concrete user moment it breaks ("on submitting the empty search, nothing happens and no message appears"), with the route.
