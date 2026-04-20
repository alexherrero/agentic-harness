# CLAUDE.md

This project uses [agentic-harness](https://github.com/alexherrero/agentic-harness). The universal instructions live in [AGENTS.md](AGENTS.md) — read that first.

## Claude Code specifics

- Slash commands (`/setup`, `/plan`, `/work`, `/review`, `/release`, `/bugfix`) are in [`.claude/commands/`](.claude/commands/). They point back to the canonical phase specs in [`harness/phases/`](harness/phases/).
- Verification hooks (typecheck / lint / test on Write|Edit) are configured in [`.claude/settings.json`](.claude/settings.json) when `install.sh --hooks` (POSIX) or `install.ps1 -Hooks` (Windows/PowerShell 7+) is run.
- Sub-agents live in [`.claude/agents/`](.claude/agents/) — `explorer` (read-only fan-out) and `adversarial-reviewer` (critic).

For anything not Claude-specific, [AGENTS.md](AGENTS.md) is authoritative.
