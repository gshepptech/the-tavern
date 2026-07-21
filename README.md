<div align="center">

<img src=".github/assets/banner.svg" alt="The Tavern — a crew of AI builders for Claude Code" width="100%"/>

[![License](https://img.shields.io/badge/license-Apache--2.0-2E7D32?style=flat-square)](LICENSE)
[![Plugins](https://img.shields.io/badge/crew-8-1E88E5?style=flat-square)](#-the-crew)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-plugin%20marketplace-8E44AD?style=flat-square&logo=anthropic&logoColor=white)](https://docs.claude.com/en/docs/claude-code)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-43A047?style=flat-square)](CONTRIBUTING.md)
[![Last commit](https://img.shields.io/github/last-commit/gshepptech/the-tavern?style=flat-square&color=607D8B)](https://github.com/gshepptech/the-tavern/commits/main)
[![Stars](https://img.shields.io/github/stars/gshepptech/the-tavern?style=flat-square&color=F9A825)](https://github.com/gshepptech/the-tavern/stargazers)

<br/>

**A crew of AI builders for Claude Code.**
*Sage draws it. Smith builds it. Warden keeps Claude honest. You ship.*

[Install](#-install) · [The Crew](#-the-crew) · [Which one do I need?](#-which-crew-member-do-i-need) · [How they work together](#-how-they-work-together) · [Contributing](#-contributing)

</div>

---

> [!NOTE]
> **The Tavern** is a [Claude Code](https://docs.claude.com/en/docs/claude-code) plugin marketplace. Hire the whole crew for a job or call one tradesperson when you need them: a draftsman who specs your codebase, a builder who builds it autonomously, an always-on hand who keeps the work true — plus a cleanup crew, an inspector, an orchestrator, and a design reviewer. The spec survives the trip. The citations get verified. The code ships.

## 📑 Contents

- [Install](#-install)
- [The Crew](#-the-crew)
- [Which crew member do I need?](#-which-crew-member-do-i-need)
- [How they work together](#-how-they-work-together)
- [Per-plugin docs](#-per-plugin-docs)
- [Contributing](#-contributing)
- [License](#-license)

---

## 🚀 Install

```bash
# In Claude Code: add the marketplace
/plugin marketplace add gshepptech/the-tavern

# Hire the core trio
/plugin install sage@the-tavern
/plugin install smith@the-tavern
/plugin install warden@the-tavern

# ...and the rest of the crew, as you need them
/plugin install sellsword@the-tavern
/plugin install cleric@the-tavern
/plugin install scout@the-tavern
/plugin install tactician@the-tavern
/plugin install seer@the-tavern
/plugin install ranger@the-tavern
```

> [!TIP]
> Warden clocks in immediately — every new conversation runs the methodical preamble plus the Stop-hook gates by default. `/warden:status` to inspect, `/warden:casual` to skip a trivial turn, `/warden:off` to silence the session.

Then, from inside your project:

```bash
# Sage interviews you and writes a locked spec
/sage:plan "add a workloads page that lists running pods with status and logs"

# Smith takes the spec and builds it — autonomously, to F6 DONE
/smith:start lathe --spec docs/specs/workloads-page/spec.md
```

---

## 👷 The Crew

| Who | Trade | Key commands |
|---|---|---|
| **Sage** `v5.0.0` | The draftsman — codebase-aware spec engine; a grounded interview that yields a locked, classified, Smith-ready spec | `/sage:plan`, `/sage:resume`, `/sage:cleanup` |
| **Smith** `v4.4.0` | The builder — autonomous build-verify-fix loop; decompose, validate, build in waves, inspect, grind, assay | `/smith:setup`, `/smith:start`, `/smith:status`, `/smith:stop`, `/smith:resume` |
| **Warden** `v0.5.0` | Keeps the work plumb — methodical-mode guardrails; a pre-response checklist + Stop-hook gates on every ad-hoc turn | `/warden:on`, `/warden:off`, `/warden:casual`, `/warden:trust-me`, `/warden:status` |
| **Sellsword** `v0.2.0` | The GC — a multi-agent crew that owns an outcome; investigate, plan, execute, verify | `/sellsword:do`, `/sellsword:goal`, `/sellsword:list`, `/sellsword:resume`, `/sellsword:cancel` |
| **Cleric** `v0.1.0` | The sweep — careful low-risk cleanup across 7 focused tracks, auto-applying only HIGH-confidence changes | `/cleric:run`, `/cleric:apply`, `/cleric:status` |
| **Scout** `v0.2.0` | The inspector — end-to-end Playwright test authoring and maintenance via Playwright MCP | `/scout:init`, `/scout:write`, `/scout:crawl`, `/scout:matrix`, `/scout:audit`, `/scout:record` |
| **Tactician** `v0.2.0` | The rigger — on-demand generator of self-contained Workflow orchestration scripts | `/tactician:make` |
| **Seer** `v0.1.0` | The surveyor — macro-architecture / design-cohesion review; is this shaped right, or accreted? | `/seer:review` |
| **Ranger** `v0.1.0` | The foreman — one prompt, then walk away; a self-directing loop that never stops and never runs out of work | `/ranger:run`, `/ranger:stop`, `/ranger:resume`, `/ranger:status` |

**Sage draws it. Smith builds it.** The rest of the crew covers the work around the edges.

<div align="center">

<table>
<tr>
<td width="50%"><a href="plugins/sage/README.md"><img src="plugins/sage/sage.svg" alt="Sage — the draftsman" width="100%"/></a></td>
<td width="50%"><a href="plugins/smith/README.md"><img src="plugins/smith/smith.svg" alt="Smith — the builder" width="100%"/></a></td>
</tr>
<tr>
<td width="50%"><a href="plugins/warden/README.md"><img src="plugins/warden/warden.svg" alt="Warden — keeps it plumb" width="100%"/></a></td>
<td width="50%"><a href="plugins/sellsword/README.md"><img src="plugins/sellsword/sellsword.svg" alt="Sellsword — the general contractor" width="100%"/></a></td>
</tr>
<tr>
<td width="50%"><a href="plugins/cleric/README.md"><img src="plugins/cleric/cleric.svg" alt="Cleric — the sweep" width="100%"/></a></td>
<td width="50%"><a href="plugins/scout/README.md"><img src="plugins/scout/scout.svg" alt="Scout — the inspector" width="100%"/></a></td>
</tr>
<tr>
<td width="50%"><a href="plugins/tactician/README.md"><img src="plugins/tactician/tactician.svg" alt="Tactician — the rigger" width="100%"/></a></td>
<td width="50%"><a href="plugins/seer/README.md"><img src="plugins/seer/seer.svg" alt="Seer — the surveyor" width="100%"/></a></td>
</tr>
<tr>
<td width="50%"><a href="plugins/ranger/README.md"><img src="plugins/ranger/ranger.svg" alt="Ranger — the foreman" width="100%"/></a></td>
<td width="50%"></td>
</tr>
</table>

</div>

<details>
<summary><b>📋 Meet each tradesperson (click to expand the full job description)</b></summary>

### 📐 Sage — the draftsman
Codebase-aware specification engine. Runs parallel codebase research, then a grounded interview that captures implicit facts as `A-AUTO-NNN` entries, emits typed **Global Invariants / State Transitions / Contracts** tables, runs an adversarial spec review at R3.5, then writes a Smith-ready spec with version frontmatter — locked, classified, citation-backed. Detects brownfield, greenfield, and cosmetic modes; brownfield runs produce a flow delta against the existing system. *Sage plans. Smith builds.*

### 🧱 Smith — the builder
Autonomous build-verify-fix loop. Reads Sage's spec, decomposes it into castings with pre-authored teammate prompts, validates through an 11-dimension gate (including intent-carrier coverage), builds in parallel waves with server-side evidence re-execution and per-requirement-ID binding, runs up to **8 verification streams** (TRACE, FLOW_TRACE, PROVE, RESEARCH_AUDIT, COVERAGE_DIFF, SIGHT, TEST/PROBE, TEST_OBSERVATIONS), grinds defects to zero, then assays with fresh eyes.

### 📏 Warden — keeps the work plumb
Methodical-mode discipline: *measure twice, cut once.* Injects a pre-response checklist every turn (Restate, Verified/Unverified assumptions, Read Floor, Blast Radius, Competing Hypotheses, and more). A Stop hook enforces five gates: a `file:line` citation verifier, an uncertainty-tell scanner, a completion gate, a zero-tool-call grounding audit, and an iterative two-tier critic-dialog. `/warden:casual`, `/warden:trust-me`, `/warden:off` when you need to step around it.

### 🏗️ Sellsword — the general contractor
Hand Sellsword a gnarly problem and he owns the outcome end to end. Runs a crew of five sub-agents (dispatcher, recon, builder, auditor, fresh-eyes) to investigate, plan, execute, and verify — SSH into systems, spin up infra, edit code, ship features, debug deploys. Bounded recon budget, multi-angle retry on stuck, and evidence ledgers from the auditor and fresh-eyes. `/sellsword:goal` runs the loop unattended until both verifiers pass.

### 🧹 Cleric — the sweep
Careful, low-risk codebase cleanup across **7 focused tracks**: deduplication, type consolidation, dead code removal, circular-dependency untangling, type strengthening, error-handling cleanup, and deprecated/AI-slop removal. Auto-applies **only** HIGH-confidence LOW-risk changes per batch, running type checks, tests, and lints after each. Atomic commits, so any failing check is one `git revert` away.

### 🔍 Scout — the inspector
End-to-end test authoring and maintenance via Playwright + Playwright MCP. Drives a real browser, reads the accessibility tree, and emits `*.spec.ts` files that pass — then keeps them passing. `/scout:crawl` discovers every route; `/scout:matrix` builds a routes × roles suite; `/scout:audit` triages failures from `trace.zip` by root cause. Enforces selector hygiene (`getByRole` over CSS) and auto-wait discipline.

### 🔧 Tactician — the rigger
Generates really good dynamic **Workflow** scripts on demand. `/tactician:make <task>` classifies the task into an orchestration archetype, picks the right fan-out topology (pipeline by default, barrier only when a stage needs all prior results), and authors a self-contained, `node --check`-validated Workflow script — schema'd agent returns, `.filter(Boolean)` after fan-out, adversarial-verify for findings, loop-until-dry for unknown-size work.

### 🦺 Ranger — the foreman
Hand him one prompt and walk away. `/ranger:run <brief>` starts a **self-directing senior-engineering loop that never stops and never runs out of work** — a thin lead (reads state files, never code) drives five Opus sub-agents through *survey → plan → plan-review → build → review → verify → commit*, one local commit per item. Plan review comes before implementation on purpose; verification is fresh-eyes and drives UI in a real browser. When the backlog empties, the scout steps back and rotates a lens across the app's domains, so an empty backlog is a survey trigger rather than a finish line. A Stop hook makes stopping impossible; a PreToolUse hook hard-denies `git push`. Local commits only — branches and dev merges need explicit flags, and it never asks you anything.

### 🕵️ Seer — the surveyor
Macro-architecture / design-cohesion review — the senior-engineer *"is this shaped right or accreted?"* critique, not bug-hunting or lint. `/seer:review <target>` runs **8 blind design lenses** (proliferation, missed reuse, helper sprawl, layering, cohesion, naming, accretion markers, boundary direction), each a separate agent. Findings are adversarially cross-examined by a skeptic, then synthesized into a per-subsystem *deliberate / mixed / accreted* verdict with `file:line` evidence and a concrete reshaping plan. Report only — never edits code.

</details>

---

## 🧭 Which crew member do I need?

| If you want to… | Call | Pairs well with |
|---|---|---|
| Turn a vague idea into a locked, buildable spec | **Sage** | → Smith |
| Build a spec out autonomously, verified | **Smith** | ← Sage |
| Keep Claude methodical on everyday ad-hoc work | **Warden** | everything |
| Throw a team at a gnarly, multi-step problem | **Sellsword** | Warden |
| Safely clean up an existing codebase | **Cleric** | Seer |
| Write & maintain browser end-to-end tests | **Scout** | Smith |
| Generate a custom multi-agent workflow script | **Tactician** | — |
| Find out if a design is intentional or accreted | **Seer** | Cleric |
| Hand over one prompt and let it work unattended | **Ranger** | the whole crew |

> [!TIP]
> New here? Start with **Sage + Smith + Warden**. That trio covers spec → build → discipline, and it's the spine everything else hangs off.

---

## 🔗 How They Work Together

Sage and Smith share one discipline: **plans are prompts**. What Sage writes is what Smith reads, byte for byte — no interpretation layer, no paraphrasing. The spec is the single shared artifact, and every mechanism in the crew exists to keep it intact across the handoff.

```mermaid
flowchart LR
    idea([Your idea]) --> sage
    subgraph sage[Sage — the draftsman]
        direction TB
        Rpre[R-pre Mode detect] --> R0
        R0[R0 Survey: 4 Explore agents] --> R1
        R1[R1 Synthesize reality] --> R15[R1.5 Research]
        R15 --> R2[R2 Interview + implicit-fact extraction]
        R2 --> R3[R3 Spec + typed tables]
        R3 --> R35[R3.5 Adversarial review]
        R35 --> R4[R4 Validate + version frontmatter]
    end
    sage --> spec[(spec.md + flow-delta.json)]
    spec --> smith
    subgraph smith[Smith — the builder]
        direction TB
        F0[F0 Research + map] --> F06[F0.6 Pattern map]
        F06 --> F05[F0.5 Decompose]
        F05 --> F07[F0.7 Intent-Carrier]
        F07 --> F09[F0.9 11-dimension validate]
        F09 --> F1[F1 Cast: parallel build + evidence re-exec]
        F1 --> F2[F2 Inspect: up to 8 streams]
        F2 -->|defects| F3[F3 Grind]
        F3 --> F2
        F2 -->|clean| F4[F4 Assay]
        F4 --> F6[F6 Done]
    end
    smith --> shipped([Shipped feature])
```

Around that core, **Warden** keeps ad-hoc turns honest — a methodical preamble shapes each response, and a Stop hook mechanically blocks any `file:line` citation Claude did not Read or Grep directly in that turn:

```mermaid
flowchart LR
    user([User prompt]) --> up[UserPromptSubmit hook]
    up --> preamble["Inject methodical preamble:<br/>Restate · VERIFIED/UNVERIFIED assumptions<br/>Read floor · Approach deliberation · Blast radius<br/>Competing hypotheses · Citation check"]
    preamble --> claude[Claude generates response]
    claude --> stop["Stop hook gates:<br/>citation verifier · uncertainty scanner<br/>grounding audit · critic-dialog"]
    stop -->|"unverified citation<br/>or open gate"| block[BLOCK: Read the file or remove the claim]
    block --> claude
    stop -->|all gates pass| out([Response delivered])
```

The rest of the crew picks up the surrounding work: **Sellsword** throws a multi-agent team at a problem and owns the outcome; **Cleric** does low-risk cleanup; **Scout** writes and maintains browser tests; **Tactician** generates Workflow orchestration scripts; **Seer** reviews design cohesion.

---

## 📦 Per-Plugin Docs

- [Sage](./plugins/sage/README.md) — spec / planning engine
- [Smith](./plugins/smith/README.md) — autonomous build-verify-fix loop
- [Warden](./plugins/warden/README.md) — methodical-mode guardrails
- [Sellsword](./plugins/sellsword/README.md) — multi-agent dev crew
- [Cleric](./plugins/cleric/README.md) — low-risk cleanup
- [Scout](./plugins/scout/README.md) — Playwright e2e tests
- [Tactician](./plugins/tactician/README.md) — Workflow-script generator
- [Seer](./plugins/seer/README.md) — design-cohesion review
- [Ranger](./plugins/ranger/README.md) — the unattended foreman loop

---

## 🤝 Contributing

Issues and PRs are welcome — typo fixes, sharper plugins, or a whole new tradesperson for the crew.

- 📖 Read the [Contributing guide](CONTRIBUTING.md) for the repo layout and the local checks to run before pushing.
- 🤝 Be kind — we follow the [Code of Conduct](CODE_OF_CONDUCT.md).
- 🔒 Found a vulnerability? See the [Security policy](SECURITY.md) — please report privately.
- 📝 Notable changes land in the [Changelog](CHANGELOG.md).

---

## 📄 License

Apache-2.0 — see [LICENSE](LICENSE). © 2026 gshepptech

---

<div align="center"><i>Sage draws it. Smith builds it. Warden keeps Claude honest. You ship.</i></div>
