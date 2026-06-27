<div align="center">

<img src="sellsword.svg" alt="Sellsword — the general contractor" width="100%"/>

# Sellsword

**Hand Sellsword a gnarly problem — he owns the outcome end to end.**

[![version](https://img.shields.io/badge/sellsword-v0.2.0-1E88E5?style=flat-square)](.claude-plugin/plugin.json)
[![license](https://img.shields.io/badge/license-Apache--2.0-4C9A2A?style=flat-square)](../../LICENSE)
[![Claude Code plugin](https://img.shields.io/badge/Claude%20Code-plugin-8E44AD?style=flat-square)](https://docs.claude.com/en/docs/claude-code)

</div>

> Sellsword is the general contractor. He runs a crew of five Opus sub-agents — dispatcher, recon, builder, auditor, fresh-eyes — that investigate, plan, execute, and verify a free-form intent end to end. You hand Sellsword the problem; he owns the outcome and comes back with an evidence ledger.

---

## ✨ What It Does

Sellsword takes a free-form intent and runs it to completion. His crew of five Opus sub-agents collaborates: the **builder** SSHes into hosts, runs `terraform`, edits code, kicks deploys, debugs airgap bundles — self-switching between **investigating → planning → executing → verifying** as the work evolves. The **auditor** and **fresh-eyes** then verify the result, each forced to produce a real **evidence ledger** of commands they actually ran.

The guarantee: nothing ships on inference. `--yolo` agents that skip verification get you 60% of the way before silently breaking the last 40%. Sellsword refuses to call it done without two independent verifiers — and **fresh-eyes reads only the intent and the current state of the code**, never the builder's notes, so it catches the "the builder convinced itself it worked" failure mode. Production beats yolo, always.

---

## 🚀 Install

```bash
claude plugin marketplace add gshepptech/the-tavern
claude plugin install sellsword@the-tavern
```

Then drive it with the `/sellsword:*` commands:

```
/sellsword:goal every test in test/auth passes and `npm run lint` exits 0
```

---

## 🧩 How It Works

```mermaid
flowchart TB
    intent([your intent]) --> dispatcher[dispatcher classifies]
    dispatcher --> recon[recon maps territory]
    recon --> decide{checkpoint?}
    decide -->|yes| plan[builder plans]
    plan --> approve{plan ok?}
    approve -->|go| exec
    approve -->|revise| plan
    decide -->|no| exec[builder executes]
    exec --> stuck{stuck?}
    stuck -->|yes| mar[multi-angle retry N=2-3]
    mar --> exec
    stuck -->|no| verify
    verify[auditor + fresh-eyes in parallel] --> debrief[debrief in chat]
```

- **Dispatcher** classifies the intent: mode (`investigating` / `planning` / `executing`), tier (`quick` / `standard` / `thorough`), side effects (`none` / `local` / `remote` / `production`), and whether a checkpoint is required.
- **Recon** spends a bounded budget mapping the problem — 30 tool calls / 6 minutes (doubled under `--thorough`).
- **Builder** is one persona that self-switches modes as it works. Not five different agents — one agent that knows when to change gears.
- **Auditor + fresh-eyes verify in parallel.** Auditor reads the brief, plan, and journal. Fresh-eyes reads only the intent and current code state — its job is to catch what the builder convinced itself of.
- **Multi-angle retry** fires when the builder declares `stuck`: N=2-3 variants run in parallel with different framings (config vs environment vs permissions); an arbiter picks the most productive framing and the builder resumes.

### Commands

| Command | What it does |
|---|---|
| `/sellsword:do "<intent>" [--thorough] [--yolo] [--scope=quick\|standard]` | Run the full investigate → plan → execute → verify flow on a free-form intent, with one plan checkpoint for side-effecting work |
| `/sellsword:goal "<condition>" [--max-cycles=N] [--max-hours=N] [--allow-production] [--thorough]` | Set a completion condition and run the builder → auditor → fresh-eyes loop unattended until both verifiers pass — enforced by a `Stop` hook, bounded by cycle and time caps |
| `/sellsword:resume [<run-id>]` | Resume an interrupted run from `.sellsword/runs/<run-id>/` |
| `/sellsword:list [--all\|--active\|--completed]` | List recent runs |
| `/sellsword:cancel [<run-id>]` | Cancel an in-flight run |
| `/sellsword:help` | Plugin help |

### Checkpoints — when Sellsword asks before doing

`/sellsword:do` asks for plan approval **once** if any of these are true: the initial mode is `planning`, the side effects are `remote` (SSH, kubectl, terraform) or `production`, and you did not pass `--yolo`. For pure investigation (`side_effects: none`) it runs end to end with no checkpoint. **Production beats yolo** — `--yolo` is silently overridden when production is in scope.

---

## ⚙️ Configuration

### `.sellsword/hosts.yml` (optional)

Tag your hosts so the dispatcher can detect production scope:

```yaml
hosts:
  staging:
    ssh: ubuntu@staging.example.com
    tags: [dev, azure, rhel]
  prod:
    ssh: deploy@prod.example.com
    tags: [production, azure, rhel]
```

Production-tagged hosts force plan approval regardless of flags.

### Run artifacts

Each run writes to `.sellsword/runs/<run-id>/`:

```
.sellsword/runs/sellsword-20260518-141522-a3f4/
├── state.json              # status, phase, timestamps — drives /sellsword:resume
├── dispatcher-config.json
├── brief.md                # recon's territory map
├── plan.md                 # builder's plan (if checkpoint)
├── journal.md              # builder's progress notes
├── reflections.md          # builder's mode-switch reasoning
├── verification.md         # builder's self-check
├── auditor-verdict.md      # auditor's evidence ledger
├── fresh-eyes-verdict.md   # fresh-eyes' independent ledger
├── followups.md
└── retry/                  # only if multi-angle retry fired
    ├── variant-A/
    ├── variant-B/
    ├── variant-C/
    └── synthesis.md
```

Plan and debrief render in chat — you never have to open these. They exist for resume and audit.

> **Unattended runs:** an unattended `/sellsword:goal` run can't survive an interactive block, so it refuses to start unless the `warden` plugin's strict gates are off. Run `/warden:strict-off` first if you use warden.

---

## 📄 License

Apache-2.0 — see [LICENSE](../../LICENSE). © 2026 gshepptech
