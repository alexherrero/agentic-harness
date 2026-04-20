# Getting Started

How to install the agentic-harness into a target project, run the local test suite, and contribute a change back. This page is for a human picking up the repo for the first time, and for an agent resuming contribution work without prior context.

## ⚡ Quick Reference

| Question | Answer |
|---|---|
| Where's the installer? | [`install.sh`](https://github.com/alexherrero/agentic-harness/blob/main/install.sh) (POSIX), [`install.ps1`](https://github.com/alexherrero/agentic-harness/blob/main/install.ps1) (Windows / PowerShell 7+) |
| Install into a project? | `./install.sh [--hooks] /path/to/your-project` |
| Refresh an installed harness? | `./install.sh --update /path/to/your-project` |
| How do phases work? | [Product-Intent](Product-Intent), [ADR 0001](0001-phase-gated-workflow) |
| What gates run in CI? | [Runbook](Runbook) — "CI gates" |
| Repo layout? | [Overview](Overview) |

## Prerequisites

| Tool | Why |
|---|---|
| `bash` 4+ or `pwsh` 7+ | The installer is one shell script per host. |
| `git` | Version discovery (`git describe`) and all update/release flows. |
| `python3` | Validation + integrity scripts ([`scripts/validate-adapters.py`](https://github.com/alexherrero/agentic-harness/blob/main/scripts/validate-adapters.py), [`scripts/check-references.py`](https://github.com/alexherrero/agentic-harness/blob/main/scripts/check-references.py)). |
| `jq` | Only needed for `install.sh --hooks` on POSIX hosts. PowerShell uses native JSON cmdlets. |
| `gh` | Release creation (`ship-release` skill) and any issue/PR work. |

## Install into a project

The installer is a one-shot copy. It reads only from `$HARNESS_ROOT/templates/` and `$HARNESS_ROOT/adapters/`; this repo's own `wiki/` is never propagated (see [ADR 0002](0002-documentation-convention) and the [installer boundary](https://github.com/alexherrero/agentic-harness/blob/main/install.sh#L23-L28) block in the script).

```bash
# First install:
/path/to/agentic-harness/install.sh [--hooks] /path/to/your-project

# Refresh harness-authored files to the current version (leaves your edits alone):
/path/to/agentic-harness/install.sh --update /path/to/your-project
```

On Windows (PowerShell 7+), the semantic twin:

```powershell
pwsh -NoProfile -File C:\path\to\agentic-harness\install.ps1 [-Hooks] C:\path\to\your-project
pwsh -NoProfile -File C:\path\to\agentic-harness\install.ps1 -Update C:\path\to\your-project
```

Both installers ship both `.sh` and `.ps1` helpers, so mixed-OS teams stay in sync regardless of who ran the installer.

### What lands in a target project

| Tree | Owner | `--update` behavior |
|---|---|---|
| `.harness/PLAN.md`, `progress.md`, `features.json`, `init.sh`, `verify.{sh,ps1}`, `known-migrations.md` | User | Left alone |
| `.harness/scripts/` (telemetry, cross-review) | Harness | Overwritten |
| `.harness/hooks/` (only with `--hooks` / `-Hooks`) | Harness | Overwritten |
| `.claude/commands/`, `.claude/agents/`, `.claude/skills/` | Harness | Overwritten |
| `.agent/`, `.agents/`, `.codex/`, `.gemini/` (adapter trees) | Harness | Overwritten |
| `AGENTS.md`, `CLAUDE.md` | User (skip-if-exists) | Left alone |
| `wiki/` scaffold (landing, sidebar, four empty subdirs) | User | Per-file walk; missing files filled in |
| `.github/workflows/wiki-sync.yml` | Harness | Overwritten |

## Run the test suite locally

CI runs on Linux, macOS, and Windows in parallel. Reproduce any of the CI jobs from a clone:

```bash
bash scripts/smoke-install-bash.sh      # fresh install + idempotence + --update + integrity
bash scripts/check-parity.sh            # adapter name-set invariants
bash scripts/check-syntax.sh            # bash -n on every .sh
python3 scripts/validate-adapters.py    # TOML/YAML/JSON + canonical-spec backing
python3 scripts/check-references.py     # cross-reference integrity
```

On Windows:

```pwsh
pwsh -NoProfile -File scripts/smoke-install-pwsh.ps1   # fresh install + integrity
pwsh -NoProfile -File scripts/check-syntax.ps1          # AST-parse every .ps1
```

The [smoke installer](https://github.com/alexherrero/agentic-harness/blob/main/scripts/smoke-install-bash.sh) exercises first-install, idempotent re-run, `--update` refresh behavior (including preservation of user edits to `wiki/Home.md` and `AGENTS.md`), and calls [`check-integrity-bash.sh`](https://github.com/alexherrero/agentic-harness/blob/main/scripts/check-integrity-bash.sh) to verify the installed tree is actually usable. The pwsh equivalent is [`smoke-install-pwsh.ps1`](https://github.com/alexherrero/agentic-harness/blob/main/scripts/smoke-install-pwsh.ps1) plus [`check-integrity-pwsh.ps1`](https://github.com/alexherrero/agentic-harness/blob/main/scripts/check-integrity-pwsh.ps1).

## Make a change

1. Branch from `main`, write the change, run the gates above locally.
2. Open a PR — CI runs the same matrix on Linux, macOS, and Windows.
3. When the feature lands, the `ship-release` skill (see [Runbook](Runbook)) cuts a tagged release sized from the commit log.

Architectural changes (new phase, new adapter, change to the installer boundary) need an ADR under [`wiki/architecture/decisions/`](https://github.com/alexherrero/agentic-harness/tree/main/wiki/architecture/decisions) before the code PR. See [ADR 0002](0002-documentation-convention) for the rationale.
