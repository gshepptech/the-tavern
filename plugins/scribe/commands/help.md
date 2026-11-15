---
description: What scribe does and the order to run it in
---

Reply with exactly the text below and nothing else.

```
scribe writes and audits documentation for an application you built. Every claim on a page it
writes is anchored to a file:line or a command it ran.

/scribe:plan [focus]                  survey the repo, propose pages and a docs layout, write .scribe/plan.md
/scribe:write [page-path ...]         write the planned pages, read each as a newcomer, fix, gate
/scribe:audit [docs-path] [--no-readers]
                                   run the gates over existing docs, return a ranked punch list
/scribe:help                          this text

Order: plan, confirm the plan, write, audit. The gates also run on their own:
python3 <plugin>/scripts/scribe_check.py docs --repo .
```
