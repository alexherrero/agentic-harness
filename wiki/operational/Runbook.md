# Runbook

Operational reference for the harness itself: updating an installed copy, cutting a release, reading CI gate output, and the dogfood-freshness check that keeps this wiki honest. For first-time install instructions see [Getting-Started](Getting-Started).

## ⚡ Quick Reference

| Task | Command |
|---|---|
| Refresh an installed harness | `./install.sh --update /path/to/project` |
| Cut a release | Invoke the `ship-release` skill (or `/ship-release [size]`) |
| Run all gates locally (POSIX) | `bash scripts/smoke-install-bash.sh && bash scripts/check-parity.sh && bash scripts/check-syntax.sh && python3 scripts/validate-adapters.py && python3 scripts/check-references.py` |
| Run all gates locally (Windows) | `pwsh -NoProfile -File scripts/smoke-install-pwsh.ps1; pwsh -NoProfile -File scripts/check-syntax.ps1` |
| Check CI status | `gh run list --workflow "[T] Linux Tests" --limit 3` (and the Mac / Windows variants) |
| Dogfood-freshness pre-release | See "Dogfood-freshness check" below |

## Updating an installed harness

`install.sh --update` (POSIX) and `install.ps1 -Update` (Windows) refresh harness-authored files in place without touching user-authored ones.

| File | Owner | Touched by `--update`? |
|---|---|---|
| `PLAN.md`, `progress.md`, `features.json`, `init.sh`, `verify.{sh,ps1}`, `known-migrations.md` | User | No |
| `AGENTS.md`, `CLAUDE.md` | User | No |
| `wiki/` scaffold | User | Per-file walk — missing files filled in, existing files preserved |
| `.harness/scripts/`, `.harness/hooks/` | Harness | Yes (overwritten) |
| `.claude/`, `.agent/`, `.agents/`, `.codex/`, `.gemini/` | Harness | Yes (overwritten) |
| `.github/workflows/wiki-sync.yml` | Harness | Yes (overwritten) |
| `.harness/.version` | Harness | Written after a successful update (so future runs can show a delta) |

Run `--update` after pulling a new harness version. It's idempotent — safe to re-run.

**When in doubt about ownership**, see the `cp_managed` function in [`install.sh`](https://github.com/alexherrero/agentic-harness/blob/main/install.sh#L103-L120) — "managed" files are harness-authored and overwritten on `--update`; anything not wrapped in `cp_managed` is user-authored and preserved.

## Cutting a release

Releases are cut by the [`ship-release` skill](https://github.com/alexherrero/agentic-harness/blob/main/harness/skills/ship-release.md), not by hand. The skill computes the next semver from conventional-commit prefixes in the range since the last tag, drafts notes in Keep-a-Changelog format, prepends to `CHANGELOG.md`, tags, pushes, and creates the GitHub release via `gh`. All steps confirm with the user before acting.

### Prerequisites

1. `/release` passed — clean tree, full test suite green, feature flags flipped truthfully.
2. The branch is merged to `main` and pushed (the tag must point at a commit on `origin/main`, otherwise collaborators can't resolve it).
3. CI on `main` is green (`gh run list --branch main --status success --limit 1`).

### Procedure

Invoke the skill — exact surface depends on the adapter:

| Adapter | How to invoke |
|---|---|
| Claude Code | `/ship-release [size-or-version]` or phrase like "ship a release" |
| Antigravity | "Run the ship-release skill" (optionally with a size) |
| Codex | `/ship-release` |
| Gemini | Reads from `.agents/skills/ship-release/SKILL.md` |

Size arguments: `patch` / `minor` / `major` override the auto-sized bump. A literal version like `0.8.0` pins the tag exactly (used when the commit range's auto-size undershoots — see the [v0.8.0 entry in `CHANGELOG.md`](https://github.com/alexherrero/agentic-harness/blob/main/CHANGELOG.md) for a worked example).

### Semver classification

| Commit prefix(es) | Bump |
|---|---|
| `feat!:`, any body with `BREAKING CHANGE:` | major |
| `feat:` | minor |
| `fix:`, `perf:`, `refactor:` | patch |
| `docs:`, `chore:`, `ci:`, `test:` | no bump (skill aborts unless the user passes an explicit size) |

User-supplied size hints larger than the commit range suggests are honored. Smaller hints trigger a confirmation prompt.

### Failure modes (from the skill)

| Symptom | Cause | Fix |
|---|---|---|
| "Unpushed commits on main" | Local `main` ahead of `origin/main` | `git push origin main`, retry |
| "Dirty working tree" | Uncommitted changes | Commit or stash, retry — the skill will not force-stash |
| "Existing tag collision" | The computed tag already exists | Bump the size hint, or cut a `-fix` patch on top |
| `gh release create` fails after tag push | Auth / network / protected branch | Tag is already pushed; run the `gh release create` invocation by hand, the skill prints it |

See [ship-release spec](https://github.com/alexherrero/agentic-harness/blob/main/harness/skills/ship-release.md#L129-L135) for the full list.

## CI gates

Three per-OS workflows run on every `push` to `main` and every `pull_request:`. They run in parallel.

| Workflow | Runs on | Jobs |
|---|---|---|
| [`[T] Linux Tests`](https://github.com/alexherrero/agentic-harness/blob/main/.github/workflows/tests-linux.yml) | `ubuntu-latest` | install-smoke + adapter-parity + validate + syntax |
| [`[T] Mac Tests`](https://github.com/alexherrero/agentic-harness/blob/main/.github/workflows/tests-mac.yml) | `macos-latest` | install-smoke + validate + syntax (both shells) |
| [`[T] Windows Tests`](https://github.com/alexherrero/agentic-harness/blob/main/.github/workflows/tests-windows.yml) | `windows-latest` | install-smoke (pwsh) + validate + pwsh syntax |

### What each gate proves

| Gate | Invariant | Script |
|---|---|---|
| install-smoke | Fresh install succeeds; re-run is idempotent; `--update` refreshes managed files but preserves user edits to `wiki/` and `AGENTS.md`; test infra never propagates to scratch. | [`scripts/smoke-install-bash.sh`](https://github.com/alexherrero/agentic-harness/blob/main/scripts/smoke-install-bash.sh), [`scripts/smoke-install-pwsh.ps1`](https://github.com/alexherrero/agentic-harness/blob/main/scripts/smoke-install-pwsh.ps1) |
| post-install integrity | Hook-command paths resolve; every `.sh`/`.ps1` parses; bash installer produces bash commands, pwsh installer produces pwsh commands; `settings.json` has the expected schema; `.harness` state files are valid. | [`scripts/check-integrity-bash.sh`](https://github.com/alexherrero/agentic-harness/blob/main/scripts/check-integrity-bash.sh), [`scripts/check-integrity-pwsh.ps1`](https://github.com/alexherrero/agentic-harness/blob/main/scripts/check-integrity-pwsh.ps1) |
| adapter-parity | Every adapter ships the canonical set of phase-commands, sub-agents, and skills. | [`scripts/check-parity.sh`](https://github.com/alexherrero/agentic-harness/blob/main/scripts/check-parity.sh) |
| validate | Every TOML, YAML frontmatter, and JSON parses and has required keys. | [`scripts/validate-adapters.py`](https://github.com/alexherrero/agentic-harness/blob/main/scripts/validate-adapters.py) |
| check-references | Every `harness/<phases\|agents\|skills\|pipelines>/*.md` mentioned in an adapter file exists; phase-spec "dispatch the `<name>` sub-agent / invoke the `<name>` skill" lines point at a canonical spec; `settings-fragment-{bash,pwsh}.json` have matching schemas. | [`scripts/check-references.py`](https://github.com/alexherrero/agentic-harness/blob/main/scripts/check-references.py) |
| syntax | `bash -n` on every `.sh`; PowerShell AST parse on every `.ps1` across repo root + `scripts/` + `templates/` + `adapters/`. | [`scripts/check-syntax.sh`](https://github.com/alexherrero/agentic-harness/blob/main/scripts/check-syntax.sh), [`scripts/check-syntax.ps1`](https://github.com/alexherrero/agentic-harness/blob/main/scripts/check-syntax.ps1) |

### Reading red CI

```bash
gh run list --workflow "[T] Linux Tests"    --limit 3
gh run list --workflow "[T] Mac Tests"       --limit 3
gh run list --workflow "[T] Windows Tests"   --limit 3
gh run view <run-id> --log-failed             # drill into the failing step
```

Red-on-Windows but green-on-POSIX almost always indicates a path-separator or pwsh-host assumption regression. Red-on-all is usually a canonical-spec or adapter-parity drift (try `bash scripts/check-parity.sh` locally).

## Dogfood-freshness check

This repo's own `wiki/` is hand-maintained dogfood. It references specific line ranges in `install.sh` and specific files in `scripts/`; as the harness evolves those can drift. Before cutting a release:

1. Search the wiki for `#L<line>` anchors: `grep -rn '#L[0-9]' wiki/`.
2. For each hit, open the linked file at that line and confirm the referenced block is still there. If it moved, update the anchor or drop the line-precision.
3. Confirm every `(Page-Name)` cross-link resolves: `python3 -c "..."` or visual scan of [`wiki/_Sidebar.md`](https://github.com/alexherrero/agentic-harness/blob/main/wiki/_Sidebar.md).
4. Confirm the Quick Reference tables still match the shipped commands (especially `install.sh --update` ownership and the CI job list).

If any of these drift, the correct response is to refresh the wiki page *before* the release, not to remove the anchor. The installer-boundary test at [`scripts/test-install.sh`](https://github.com/alexherrero/agentic-harness/blob/main/scripts/test-install.sh) proves drift never leaks into target projects (it runs `diff -r templates/wiki/ <scratch>/wiki/` byte-for-byte on every CI run); this manual check keeps drift from misinforming contributors to the harness repo.

## Related

- [Getting-Started](Getting-Started) — install and run gates.
- [Overview](Overview) — what lives where in the repo.
- [ADR 0002](0002-documentation-convention) — why the installer-boundary rule exists.
