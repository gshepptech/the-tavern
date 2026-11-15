---
description: "Explain what Smith does and how to use it"
allowed-tools: []
---

# Smith help

Show the user the following, as written.

---

**Smith builds to the plan.** Give it a spec with numbered requirements and acceptance criteria (a sealed Sage spec,
or your own) and it builds the spec, has every requirement checked by a verifier that never saw how it was built,
and fixes what fails until everything passes or a limit is hit.

**Commands**

- `/smith:build [spec] [--max-rounds N] [--max-parallel N]`: build a spec. With no path, it uses the newest spec Sage
  sealed in this project.
- `/smith:build --resume <run>`: continue a run that stopped.
- `/smith:status [run]`: where a run stands and what happens next.
- `/smith:help`: this text.

**How a build runs**

1. **Plan.** A planner splits the requirements into slices, each owning an explicit list of files.
2. **Build.** Builders work on independent slices in parallel waves, test-first, each editing only its own files.
   The lead commits each slice on the branch `smith/<run>`.
3. **Verify.** Verifiers read the spec first, then the code, and run checks. They never see the builders' notes.
   Each verdict is recorded with the command and its output.
4. **Fix.** Fixers get the failing requirements and the verifier's evidence. After a fix, every requirement the fix
   could have affected is verified again.
5. **Report.** `.smith/runs/<run>/report.md` lists every requirement with its evidence.

**The rule the ledger enforces:** a requirement is done only when a verifier recorded a passing check in the current
round, with the command it ran and the output it saw.

**Limits:** `--max-rounds` fix rounds (default 3); `--max-parallel` agents at once (default 4). Smith needs a clean git
tree, commits on its own branch and never pushes.
