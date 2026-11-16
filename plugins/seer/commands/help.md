---
description: "Explain the Seer design-cohesion review plugin"
allowed-tools: ["Read"]
---

# Seer: help

**Seer** runs a senior-engineer **design-quality / cohesion** review. It deduces the real design problem from the detail that's out of place. Not bug-hunting, not lint. It asks the architecture questions:

- Is this shaped right, or thrown together?
- Why are there N packages / N helper functions doing almost-the-same thing?
- Where could this logic have been shared?
- Does the structure flow, or fight you? Is it deliberate or accreted?

…and it **lists the proposed solutions**.

## Commands

- `/seer:review <target>`: review a target and get a per-subsystem deliberate-vs-accreted verdict plus an ordered reshaping plan. Report only; it never edits code.
- `/seer:help`: this.

`<target>` is free-form: a path (`pkg/auth`), a change (`the diff`, `this branch vs main`), a subsystem name, or a description (`the retry logic in the worker`). Omit it and you'll be asked.

## How it earns trust

It's not "ask Claude what it thinks of the architecture." It's a Workflow engine with four trust mechanisms:

1. **Grounded map first.** Builds a structural model (modules, boundaries, intended shape) that every finding must anchor to with `file:line`.
2. **8 blind lenses.** Separate agents, each hunting one class of design problem (package proliferation, missed sharing, helper sprawl, flow & layering, cohesion, consistency, accretion, boundary & dependency direction), none seeing the others.
3. **Adversarial cross-examination.** Every candidate finding goes to a skeptic that tries to *refute* it ("is this split actually intentional?"). Findings that don't survive are dropped.
4. **Completeness critic.** A final agent asks "what area went unexamined?" and re-lenses the gaps.

Seer never takes a comment at its word for what the code does. The code is the evidence and comments go stale, so it reads the actual code.

## Output

A debrief in chat + a saved report under `.seer/casefiles/`. Every finding carries file:line evidence and a concrete proposed solution. An empty result is honest: a well-shaped target should produce few findings.
