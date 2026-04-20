# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [v0.8.1] — 2026-04-20 — CI hardening + dogfood wiki

Follow-up to v0.8.0. Tightens the cross-platform CI gate suite, ships the agentic-harness repo's own wiki as a worked example of the v0.8.0 documentation convention, and fixes a PowerShell parse regression in the verify.ps1 template.

### Fixed

- `templates/verify.ps1` — empty `switch` statement (all clauses commented out) failed to parse on pwsh hosts with "Missing condition in switch statement clause". Added a required `default { }` clause so the template parses as shipped. Caught by the cross-platform CI added in v0.8.0.

### Internal

- **Cross-platform harness-integrity CI** — beyond install-smoke, the three per-OS workflows now run `check-parity.sh`, `validate-adapters.py`, `check-references.py`, `check-syntax.{sh,ps1}`, and `check-integrity-{bash,pwsh}` against a scratch install on every push / PR. A POSIX path-separator bug in `check-references.py` surfaced as part of this work and was fixed.
- **Dogfood wiki** — `wiki/` at repo root now contains this project's own documentation under the v0.8.0 convention: Home, Sidebar, one page per subdir (Getting-Started / Runbook / Product-Intent / Overview), plus ADRs 0001 (phase-gated workflow) and 0002 (documentation convention). The installer boundary is preserved — `install.sh` still copies only from `templates/wiki/`, never from this repo's own `wiki/`.
- **Dedicated installer-boundary test** — `scripts/test-install.sh` runs `diff -r templates/wiki/ <scratch>/wiki/` byte-for-byte plus a SHA-256 hash-based leak detector for each file under `$HARNESS_ROOT/wiki/`, wired into Linux CI. Proves the boundary on every PR.

[v0.8.1]: https://github.com/alexherrero/agentic-harness/releases/tag/v0.8.1

## [v0.8.0] — 2026-04-19 — Documentation convention, three new full-parity adapters, Windows support, release automation

This is the largest release in the project's history. Four themes: (1) a first-class
documentation convention with a dogfooded wiki scaffold and per-phase documenter
sub-agent; (2) two new full-parity adapters (Codex CLI, Gemini CLI) plus the
existing Antigravity adapter expanded from README-only to full parity with
Claude Code; (3) cross-platform support — `install.ps1` and PowerShell twins
of every Unix helper, with CI validating install + parity on Linux, macOS,
and Windows; (4) a new `ship-release` skill that automates this exact kind
of tag cut going forward.

### Added

- **Documentation convention** — `harness/documentation.md` specifies a
  four-section `wiki/` scaffold (architecture / development / features / operational)
  that `install.sh` drops into every project on `/setup`. A canonical
  `documenter` sub-agent (`harness/agents/documenter.md`) is dispatched post-gates
  during `/work` and does a full-pass sweep during `/release` — flipping
  `Status: pending → implemented` only when the diff proves it.
- **`wiki-sync` GitHub Action** — pushes to the default branch mirror `wiki/`
  content to the GitHub Wiki (collision-checked, graceful-skip when the wiki
  is disabled). Ships via `install.sh` per-file walk.
- **Antigravity adapter full parity** — expanded from README-only to 4 agents
  (adversarial-reviewer, adversarial-reviewer-cross, documenter, explorer),
  6 workflow commands, the `dependabot-fixer` skill, and an always-on rules
  file. Installed into `.agent/`.
- **Codex CLI adapter** — new full-parity adapter. 7 skills (6 phase commands
  prefixed `harness-` to avoid colliding with Codex built-ins, plus
  `dependabot-fixer`), 4 TOML sub-agents with `sandbox_mode` specs, README
  documenting divergences. Installed into `.agents/skills/` and `.codex/agents/`.
- **Gemini CLI adapter** — new full-parity adapter. 6 native TOML slash
  commands, 4 markdown sub-agents with YAML frontmatter + tool allowlists,
  `settings.json` wiring `AGENTS.md` via `context.fileName`. Shared skills
  (`dependabot-fixer`, `ship-release`) reused from the `.agents/skills/`
  delivery. Installed into `.gemini/`.
- **Windows cross-platform support** — `install.ps1` at repo root with
  semantic parity to `install.sh` (PowerShell 7+). PowerShell twins of
  `verify.sh`, `precompact.sh`, `session-start-compact.sh`, and
  `cross-review.sh` ship alongside the Unix versions. Hook JSON is factored
  into canonical `settings-fragment-{bash,pwsh}.json` fragments so each
  installer reads the correct shell invocation.
- **Harness-repo CI** — three per-OS workflows (`tests-linux.yml`,
  `tests-mac.yml`, `tests-windows.yml`) gate every PR. Linux runs
  `install-smoke` + `adapter-parity` + `validate`; macOS and Windows run
  install-smoke via bash and pwsh respectively. Each smoke test asserts
  the installer boundary — `tests-*.yml`, `scripts/*`, and repo-root `wiki/`
  never propagate to installed projects.
- **`ship-release` skill** — auto-sized semver releases from conventional
  commits (`feat!` / `BREAKING CHANGE` → major, `feat:` → minor,
  `fix:`/`perf:`/`refactor:` → patch, `docs:`/`chore:`/`ci:` → no-bump).
  Writes `CHANGELOG.md`, tags, pushes, creates the GitHub release.
  Aborts if the tree is dirty, the default branch isn't pushed, or the
  tag already exists. Canonical spec at `harness/skills/ship-release.md`
  with adapter SKILL.md in claude-code / antigravity / codex.
- **Parity + validation scripts** — `scripts/check-parity.sh` asserts each
  adapter ships the canonical set of phase-commands, sub-agents, and skills
  (with documented divergences). `scripts/validate-adapters.py` parses all
  TOML, YAML frontmatter, and JSON across every adapter.
- **Contributing section** in README documenting CI matrix + local
  invocation commands.

### Changed

- **Phase specs wired to `documenter`** — `/setup`, `/plan`, `/work`
  (post-gates), and `/release` now dispatch the documenter sub-agent;
  `/review` gets an explicit not-invoked note to prevent docs drift from
  biasing the critic. `/bugfix` dispatches documenter on resolution.
- **Phase specs suggest `ship-release`** — `/work` suggests it when a
  feature's `passes` flag flips true; `/release` recommends it as the
  post-merge follow-up to the pre-merge gate.
- **`install.sh` per-file walk semantics** for `wiki/` — user-edited pages
  never get clobbered; new scaffold pages merge in cleanly.
- **`install.sh` boundary comment** — clarifies which directories are
  harness-authored (refreshed on `--update`) vs. user-owned (`cp_user`).
- **Hook settings factored** — `templates/hooks/settings-fragment-bash.json`
  and `-pwsh.json` are now the canonical source both installers read,
  mitigating JSON drift between the two.

### Fixed

- **PowerShell `ConvertTo-Json` array unwrap bug** — `install.ps1` now
  uses `ConvertFrom-Json -AsHashtable` throughout and stores hook-event
  arrays as `List[object]`, preventing single-element array unwrap that
  would have broken Claude Code's hook loader schema on Windows.

### Internal

- Research notes for Codex CLI conventions (`harness/agents/codex-adapter-research.md`)
  and Gemini CLI conventions (`harness/agents/gemini-adapter-research.md`) —
  both answer the research questions + open questions that informed the
  final adapter layouts.
- Installer-boundary assertion is now load-bearing in CI — break-each-invariant
  reproducers verified: rogue file → parity fails, corrupt TOML → validate
  fails, renamed subagent → parity fails, broken `install.sh` → smoke fails.

[v0.8.0]: https://github.com/alexherrero/agentic-harness/releases/tag/v0.8.0
[v0.5.1]: https://github.com/alexherrero/agentic-harness/releases/tag/v0.5.1
[v0.5.0]: https://github.com/alexherrero/agentic-harness/releases/tag/v0.5.0
[v0.4.0]: https://github.com/alexherrero/agentic-harness/releases/tag/v0.4.0
[v0.3.0]: https://github.com/alexherrero/agentic-harness/releases/tag/v0.3.0
[v0.2.0]: https://github.com/alexherrero/agentic-harness/releases/tag/v0.2.0
[v0.1.0]: https://github.com/alexherrero/agentic-harness/releases/tag/v0.1.0
