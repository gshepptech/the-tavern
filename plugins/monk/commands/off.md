---
description: Turn monk response shaping and the length gate off for this session
---

The monk UserPromptSubmit hook has already applied this command for the current session. Its confirmation is in
your context as a line that starts with `monk:`.

Reply with that confirmation line and nothing else. If there is no `monk:` line in your context, the hook did not
run: say so in one line and suggest checking that the plugin is enabled with `/plugin`.
