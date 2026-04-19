# agentic-harness

A small, opinionated harness for doing production-quality engineering with AI coding agents (Claude Code, Antigravity, and tools that read `AGENTS.md`).

Not a 150-agent supermarket. Six phase-gated slash commands, two sub-agents, deterministic verification, on-disk state. Designed to be installed into any project in one command.

## Principles (the short version)

1. **Phase-gated workflow.** `setup → plan → work → review → release`. Hard boundaries.
2. **State lives on disk, not in context.** `.harness/PLAN.md`, `features.json`, `progress.md`, git.
3. **Single-threaded for coherence, fan-out only for read-only breadth.** Parallel implementers cause merge chaos; parallel readers are fine.
4. **Deterministic gates before LLM judgment.** Typecheck → lint → test → build, then optional critic.
5. **Adversarial review with "assume bugs" framing.** Neutral reviewers rubber-stamp; adversarial ones find things.
6. **Re-audit the harness on every model bump.** Scaffolding that was load-bearing last quarter often isn't anymore.

Full reasoning in [harness/principles.md](harness/principles.md).

## Install into a project

```bash
/path/to/agentic-harness/install.sh [--hooks] /path/to/your-project
```

This drops in:
- `.harness/` — per-project state (PLAN.md, features.json, progress.md, init.sh)
- `.claude/commands/` + `.claude/agents/` — slash commands and sub-agents for Claude Code
- `AGENTS.md` + `CLAUDE.md` — agent entry points (Antigravity, Cursor, Codex, Claude Code)

With `--hooks`:
- `.harness/verify.sh` — per-project verification script (edit to uncomment checks for your stack)
- `.claude/settings.json` — `PostToolUse` hook that runs `verify.sh` after every Write/Edit. Merges safely into existing settings.

Requires `jq` for `--hooks`. Idempotent — safe to re-run.

## Phases

| Command | Purpose |
|---|---|
| `/setup` | First-time project init: scaffold, `init.sh`, feature list |
| `/plan` | Turn a brief into `.harness/PLAN.md` — tasks with pass/fail criteria |
| `/work` | Execute one task from the plan; update progress; stop |
| `/review` | Adversarial critique of the change — must produce executable artifact |
| `/release` | Pre-merge gate: clean tree, verification passes, changelog |
| `/bugfix` | Report → Analyze → Fix → Verify pipeline (replaces `/work` for bugs) |

## Status

v0.1 — all six phases fully specified. No version tag yet; the harness is still expected to evolve rapidly as I use it on real projects. Re-audit the docs whenever you adopt a new model version ([principles §6](harness/principles.md)).

## License

MIT. See [LICENSE](LICENSE).
