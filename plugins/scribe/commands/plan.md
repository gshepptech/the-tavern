---
description: Survey the repository and propose a documentation page set and site layout
argument-hint: [focus]
---

You are planning documentation for the application in the current repository. `$ARGUMENTS`, if given, narrows the
focus (a component, an audience, or "only the CLI"). You write a plan and nothing else; no pages yet.

## 1. Survey

Spawn one agent with `subagent_type: "scribe:surveyor"`. Give it the repository root and the focus from `$ARGUMENTS`.
Wait for its report. If it lists sticking points or unconfirmed items, keep them; they shape the plan.

## 2. Choose the pages

Propose a page set from these kinds, and only the pages this application needs:

| Kind | Propose one when |
|---|---|
| Overview | always: what it is, who it is for, where to go next (usually the docs index or README) |
| Getting started (tutorial) | there is a first-run path a newcomer can finish in under 30 minutes |
| How-to guides | there are distinct goals a returning user has (one page per goal, named for the goal) |
| Reference | there is a surface: commands, flags, config keys, environment variables, endpoints |
| Explanation | there is a design decision or concept users need to reason about the tool |

For each page give: the file path, its kind, its reader in one sentence, what the reader can do after reading it, and
the surveyor evidence it will draw on. Reference pages list which part of the surface they cover, so that every item
in the surveyor's surface table lands on exactly one reference page.

Existing pages: keep, rewrite, or merge each one, with a reason. Do not plan a page for a feature the survey could
not confirm.

## 3. Choose the layout

If the repository already builds docs with a site generator, use it and its existing nav file. Otherwise, plain
Markdown under `docs/` with `docs/README.md` as the index, which renders on GitHub without a build step. Show the
tree:

```
docs/
  README.md                 overview and index
  getting-started.md
  how-to/<goal>.md
  reference/<surface>.md
  explanation/<topic>.md
  glossary.md               only if the survey found five or more terms that need defining
```

## 4. Write the plan and stop

Write the plan to `.scribe/plan.md`: the page table, the layout tree, the survey report as an appendix, and the open
questions. Then show the user the page table and the layout, list the open questions, and ask them to confirm or
change it before running `/scribe:write`. Do not write any page.
