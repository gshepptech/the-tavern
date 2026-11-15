---
description: "Explain what Sage does and how to use it"
allowed-tools: []
---

# Sage help

Show the user the following, as written.

---

**Sage turns a feature idea into a sealed spec:** numbered requirements, each with acceptance
criteria that can fail and a citation of the interview answer or code fact behind it. Sage never writes product code.

**Commands**

- `/sage:plan <idea>`: research the codebase, interview you, write and seal the spec.
- `/sage:resume [slug]`: continue a spec that stopped part way.
- `/sage:help`: this text.

**What happens in `/sage:plan`**

1. A researcher agent reads the code and writes numbered facts (F-001...), each with file:line evidence.
2. Sage asks you only what the code cannot answer, one question at a time. Each answer is recorded as A-001...
3. Sage writes `sage-specs/<slug>/spec.md`. Every requirement R-001... cites the answers and facts behind it.
4. A validator checks the structure: unique IDs, criteria under every requirement, every citation resolves, no vague
   criteria, no placeholders, no open questions.
5. A reviewer agent reads your answers and the code facts, then the spec, and flags anything a builder could read two
   ways. Sage fixes the spec or asks you.
6. The validator seals the spec: it records a hash, so any later edit shows.

**Files**, in `sage-specs/<slug>/`: `research.md`, `interview.md`, `spec.md`, `review.json`.

**Check a spec yourself:** `bash <sage>/scripts/sage check path/to/spec.md` or `verify-seal path/to/spec.md`.

**Next step:** `/smith:build sage-specs/<slug>/spec.md` builds a sealed spec.
