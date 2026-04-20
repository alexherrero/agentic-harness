# Architecture Overview

How agentic-harness is organized on disk and how the pieces fit together at install time. This page is the map — for *why* the shape is this way, see [ADR 0001](0001-phase-gated-workflow) and [ADR 0002](0002-documentation-convention).

## ⚡ Quick Reference

| Question | Answer |
|---|---|
| Where does a phase spec live? | [`harness/phases/`](https://github.com/alexherrero/agentic-harness/tree/main/harness/phases) — one canonical `.md` per phase |
| Where does an adapter live? | [`adapters/<tool>/`](https://github.com/alexherrero/agentic-harness/tree/main/adapters) — claude-code, antigravity, codex, gemini |
| Where does the install scaffold live? | [`templates/`](https://github.com/alexherrero/agentic-harness/tree/main/templates) — state files, hooks, wiki scaffold |
| Where does the test infra live? | [`scripts/`](https://github.com/alexherrero/agentic-harness/tree/main/scripts) — **never propagated to target projects** |
| Where does this wiki get copied from on install? | Nowhere. Target projects get `templates/wiki/` (empty scaffold), not this one. See [ADR 0002](0002-documentation-convention). |

## 📁 Top-level layout

```
agentic-harness/
├── install.sh                 # POSIX installer (bash)
├── install.ps1                # Windows installer (PowerShell 7+)
├── README.md                  # the pitch + install instructions
├── AGENTS.md                  # universal agent entry point
├── CLAUDE.md                  # Claude Code entry (links back to AGENTS.md)
├── CHANGELOG.md               # Keep-a-Changelog format; written by ship-release
├── LICENSE                    # MIT
├── harness/                   # canonical specs (source of truth)
│   ├── phases/                # 01-setup .. 05-release + bugfix pipeline
│   ├── agents/                # canonical sub-agent specs (explorer, adversarial-reviewer, documenter)
│   ├── skills/                # canonical skill specs (dependabot-fixer, ship-release)
│   ├── pipelines/             # bugfix pipeline spec
│   ├── principles.md          # design calls behind the harness
│   ├── documentation.md       # wiki convention
│   ├── hooks.md               # hook design (PostToolUse / PreCompact / SessionStart)
│   ├── telemetry.md           # telemetry signals + thresholds
│   └── verification.md        # deterministic-gate definitions
├── adapters/                  # per-tool shims that point at harness/ specs
│   ├── claude-code/           # .claude/commands + .claude/agents + .claude/skills
│   ├── antigravity/           # .agent/workflows + .agent/skills + .agent/rules
│   ├── codex/                 # .agents/skills + .codex/agents
│   └── gemini/                # .gemini/commands + .gemini/agents + settings.json
├── templates/                 # what install.sh drops into a target project
│   ├── PLAN.md, features.json, progress.md, init.sh, verify.{sh,ps1}, known-migrations.md
│   ├── hooks/                 # hook scripts + settings-fragment JSON (bash + pwsh)
│   ├── scripts/               # cross-review.{sh,ps1}, telemetry.sh, etc.
│   └── wiki/                  # empty scaffold (Home.md, _Sidebar.md, 4 subdirs)
├── scripts/                   # test infra — NEVER propagated by install.sh
│   ├── smoke-install-{bash.sh,pwsh.ps1}
│   ├── check-integrity-{bash.sh,pwsh.ps1}
│   ├── check-parity.sh
│   ├── check-syntax.{sh,ps1}
│   ├── check-references.py
│   └── validate-adapters.py
├── wiki/                      # THIS wiki — dogfood docs for the harness repo itself
│   ├── Home.md, _Sidebar.md
│   ├── development/, operational/, design/, architecture/
└── .github/workflows/
    ├── tests-linux.yml, tests-mac.yml, tests-windows.yml   # CI (never propagated)
    └── (wiki-sync.yml lives under templates/ — target projects get it)
```

## 🏗 How phases, adapters, and templates fit together

```
         ┌──────────────────────────────────────────┐
         │   harness/phases/*.md   (source of truth) │
         │   harness/agents/*.md                     │
         │   harness/skills/*.md                     │
         └────────┬─────────────────────────┬────────┘
                  │                         │
                  │ referenced-by            │ referenced-by
                  ▼                         ▼
         ┌──────────────────┐      ┌──────────────────┐
         │  adapters/       │      │  wiki/           │
         │  claude-code/    │      │  (THIS repo's    │
         │  antigravity/    │      │   own docs only) │
         │  codex/          │      │                  │
         │  gemini/         │      └──────────────────┘
         └────────┬─────────┘
                  │ copied-by
                  ▼
         ┌───────────────────────────────────────────┐
         │  install.sh / install.ps1                  │
         │  reads ONLY from templates/ + adapters/    │
         │  (NEVER from wiki/ — installer boundary)   │
         └────────┬───────────────────────────────────┘
                  │ drops into
                  ▼
         ┌───────────────────────────────────────────┐
         │  target-project/                           │
         │    .harness/  .claude/  .agent/            │
         │    .agents/  .codex/  .gemini/             │
         │    AGENTS.md  CLAUDE.md                    │
         │    wiki/  (empty scaffold from templates/) │
         │    .github/workflows/wiki-sync.yml          │
         └────────────────────────────────────────────┘
```

**Key property:** the phase specs in `harness/` are authoritative. Every adapter file is expected to cite a `harness/<phases|agents|skills>/` path; [`scripts/check-references.py`](https://github.com/alexherrero/agentic-harness/blob/main/scripts/check-references.py) fails CI if an adapter references a spec that doesn't exist. This is what keeps the four adapters in sync — they're all pointers at the same canonical text.

## 🎨 The four adapters

Every adapter ships the same canonical set of phase commands, sub-agents, and skills. Their *shape* differs per tool, but the names and jobs match. [`scripts/check-parity.sh`](https://github.com/alexherrero/agentic-harness/blob/main/scripts/check-parity.sh) asserts this.

| Adapter | Phase commands | Sub-agents | Skills |
|---|---|---|---|
| `adapters/claude-code/` | `.claude/commands/*.md` | `.claude/agents/*.md` | `.claude/skills/*/SKILL.md` |
| `adapters/antigravity/` | `.agent/workflows/*.md` | (via skills) | `.agent/skills/*/SKILL.md` |
| `adapters/codex/` | (skills double as phases) | `.codex/agents/*.toml` | `.agents/skills/*/SKILL.md` |
| `adapters/gemini/` | `.gemini/commands/*.toml` | `.gemini/agents/*.md` | (reuses codex skills) |

Canonical sub-agents: `explorer`, `adversarial-reviewer`, `documenter`.
Canonical skills: `dependabot-fixer`, `ship-release`.

## 📁 The installer boundary

`install.sh` and `install.ps1` read **only** from two roots:

1. `$HARNESS_ROOT/templates/` — the scaffold every project gets (state files, hooks, wiki scaffold, wiki-sync workflow).
2. `$HARNESS_ROOT/adapters/` — tool-specific commands / agents / skills.

They **never** read from:

- `$HARNESS_ROOT/wiki/` — dogfood docs for the harness repo (this one).
- `$HARNESS_ROOT/scripts/` — test infra for the harness repo.
- `$HARNESS_ROOT/.github/workflows/tests-*.yml` — CI for the harness repo.

The boundary is enforced by the top-of-file comment in [`install.sh`](https://github.com/alexherrero/agentic-harness/blob/main/install.sh#L23-L28) and by the installer-boundary assertions in [`scripts/smoke-install-bash.sh`](https://github.com/alexherrero/agentic-harness/blob/main/scripts/smoke-install-bash.sh) / [`scripts/smoke-install-pwsh.ps1`](https://github.com/alexherrero/agentic-harness/blob/main/scripts/smoke-install-pwsh.ps1). See [ADR 0002](0002-documentation-convention) for the full rationale.

## ⚙️ Verification infrastructure

CI runs on Linux, macOS, and Windows in parallel. All gates are documented in the [Runbook](Runbook) under "CI gates". For an ADR on why the test infra lives at repo root and not under `templates/`, see the installer-boundary section of [ADR 0002](0002-documentation-convention).

## Related

- [Product-Intent](Product-Intent) — what problem the harness solves.
- [Runbook](Runbook) — CI gates and release procedure.
- [ADR 0001](0001-phase-gated-workflow) — why phase gates.
- [ADR 0002](0002-documentation-convention) — why this wiki is never installed into target projects.
