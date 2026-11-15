---
description: Exempt one turn from the monk rules and the length gate
argument-hint: [question]
---

The monk UserPromptSubmit hook has already applied this command for the current session. Its confirmation is in
your context as a line that starts with `monk:`.

If `$ARGUMENTS` is empty, reply with the confirmation line and nothing else: the user's next message is the exempt one.

If `$ARGUMENTS` holds a question or request, this turn is the exempt one. Answer it in full, at whatever length it
needs, without the monk rules: $ARGUMENTS

If there is no `monk:` line in your context, the hook did not run: say so in one line and suggest checking that the
plugin is enabled with `/plugin`.
