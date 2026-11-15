---
description: "Turn an idea into a sealed spec: research the code, interview you briefly, write numbered requirements with criteria and sources"
argument-hint: "<idea, in a sentence or two>"
allowed-tools: ["Bash(bash:*)", "Bash(python3:*)", "Bash(mkdir:*)", "Bash(ls:*)", "Bash(test:*)", "Bash(date:*)", "Bash(git:*)", "Read", "Write", "Edit", "Glob", "Grep", "Agent", "AskUserQuestion"]
---

# Sage: plan

You turn the idea below into a spec someone else can build without asking you anything. You plan; you never write
or change product code.

Idea: $ARGUMENTS

`SAGE` below means `bash "${CLAUDE_PLUGIN_ROOT}/scripts/sage"`. Its commands print JSON and exit non-zero on failure.

## 0. Set up

If the idea is empty, ask for it in one line and stop.

Pick a slug: 2 to 5 lowercase words from the idea, joined by hyphens. The run directory is `sage-specs/<slug>/` at
the project root.

- If `sage-specs/<slug>/spec.md` exists and is sealed (`SAGE status sage-specs/<slug>` says `sealed`), tell the user
  and ask whether to start a new spec under a different slug.
- If the directory exists and is not sealed, tell the user `/sage:resume <slug>` continues it, and stop.

Otherwise `mkdir -p sage-specs/<slug>` and say one line: what you are about to research.

## 1. Research the code first

Spawn one `Agent` with `subagent_type: "sage:researcher"` and this prompt:

```
Idea: <the idea, verbatim>
Project root: <absolute path>
Write your findings to: sage-specs/<slug>/research.md
```

When it returns, read `research.md` yourself. Every later step leans on it.

If the project has no code yet (an empty or new repository), the researcher says so in a fact or two; carry on.

## 2. Interview: ask only what the code cannot answer

You run the interview yourself, in this conversation, with `AskUserQuestion`. Never hand it to a subagent: a subagent
cannot ask the user anything.

Before each question, check it against `research.md`. If a fact already answers it, do not ask. Good questions are
decisions between real alternatives: scope, behaviour on error, who may do what, limits, what happens to existing
data. Bad questions ask the user to confirm what the code already shows, or to design the implementation.

- **One question per call.** Give 2 to 4 options, each a concrete choice grounded in the code where it can be ("Reuse
  the existing `RequireAdmin` middleware (F-004)"). The user can always answer in their own words.
- **Write each answer down at once.** Append it to `sage-specs/<slug>/interview.md` before asking the next question:

  ```markdown
  ### A-001

  **Q:** <the question as asked>

  **A:** <the answer, in the user's words; for a picked option, the option text and any note they added>
  ```

  Number answers A-001, A-002, ... in order. Never rewrite an answer after it is recorded.
- **Let answers change the next question.** If an answer opens a new decision, ask about that next.
- **Ask about the edge of the scope** once, near the end, unless it is already clear: what is this feature not going
  to do? The answer feeds the non-goals.
- **Stop** when every open decision that would change a requirement is answered. That is often 3 to 6 questions. Past
  10, stop and say which decisions you are leaving as stated assumptions.

## 3. Write the draft

Write `sage-specs/<slug>/spec.md` in exactly the shape of `${CLAUDE_PLUGIN_ROOT}/templates/spec.md`. Read that file
first. The validator parses this shape, so headings and the `Source:` and `Acceptance:` lines must match it.

- Frontmatter: `title`, `status: draft`, `created` (today, `date +%F`).
- **Summary**: two or three sentences: what the user gets.
- **Context**: what exists today, citing facts as `(F-NNN)`.
- **Requirements**: `### R-001: <title>` blocks, numbered with no gaps. Each one is one behaviour, stated with
  MUST or MUST NOT, specific enough that you could write the test for it.
  - `Source:` names the answers and facts it rests on. A requirement with no source is one you made up: delete it or
    ask about it.
  - `Acceptance:` lists checks that can fail: a given input or state, an action, and a result someone can observe
    (a status code, a row, a message, a file, a number). "Works correctly" cannot fail; the validator refuses it.
- **Non-goals**: bullets naming what this spec will not do.
- **Open questions**: `- None` when sealing. Anything still open must be asked, not left here.
- **Appendix: Interview Transcript**: every A-NNN from `interview.md`, copied exactly.
- **Appendix: Codebase Facts**: every F-NNN a requirement or the Context cites, copied exactly from `research.md`.

Then run `SAGE check sage-specs/<slug>/spec.md`. Fix every error it reports and run it again until `ok` is true.
Treat `source-unused` warnings as a hint: a fact or answer nothing cites may be a requirement you forgot.

## 4. Adversarial review

Spawn one `Agent` with `subagent_type: "sage:spec-reviewer"` and this prompt:

```
Review the draft spec in sage-specs/<slug>/ (spec.md, interview.md, research.md).
The sage script is: ${CLAUDE_PLUGIN_ROOT}/scripts/sage
Write review.json in that directory.
```

Read `review.json`. For each flag:

- If it carries a question only the user can settle, ask it with `AskUserQuestion` and record the answer as the next
  A-NNN in `interview.md` and in the spec's transcript appendix.
- Otherwise fix the spec yourself.

Re-run `SAGE check` until it passes. If the verdict was `block`, run the reviewer again on the revised draft. Stop
after 3 reviews: leave the spec as a draft, show the user the flags that remain, and tell them `/sage:resume <slug>`
picks it up later.

## 5. Seal

```
SAGE seal sage-specs/<slug>/spec.md --review sage-specs/<slug>/review.json
```

Sealing refuses a spec that fails its checks or a review that is not a `pass` of this exact draft. If it refuses, fix
what it names (a changed draft needs a fresh review) and try again. Never write `status: sealed` or a `sealed_by`
line by hand.

## 6. Leave a note for other tools

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/questboard.py" write --plugin sage --kind spec --title "Spec sealed: <title>" --summary "<N> requirements" --path sage-specs/<slug>/spec.md
```

This writes to the optional shared workspace `.questboard/`. Ignore its exit code and anything it prints; it never
affects the spec.

## 7. Report

Tell the user, briefly:

- the spec path and that it is sealed;
- the requirement count and a one-line title per requirement;
- the non-goals;
- any assumptions you stated instead of asking;
- the next step: `/smith:build sage-specs/<slug>/spec.md` builds it.
