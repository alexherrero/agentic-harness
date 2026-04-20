# Codex CLI adapter

Full-parity adapter for running agentic-harness in [OpenAI Codex CLI](https://codex.openai.com/). Every phase command, sub-agent, and skill that Claude Code users get as slash commands and sub-agents is available here as Codex skills and TOML subagents.

## Surface mapping

| Claude Code | Codex | Purpose |
|---|---|---|
| `.claude/commands/*.md` | `.agents/skills/harness-*/SKILL.md` | Phase entrypoints (setup/plan/work/review/release/bugfix) |
| `.claude/agents/*.md` | `.codex/agents/*.toml` | Sub-agents (explorer, adversarial-reviewer, adversarial-reviewer-cross, documenter) |
| `.claude/skills/*/SKILL.md` | `.agents/skills/*/SKILL.md` | Project skills (dependabot-fixer) |
| `CLAUDE.md` pointer | `AGENTS.md` at repo root | Operating contract (Codex loads `AGENTS.md` natively) |

## Why two directories

Codex has two distinct extensibility primitives:

- **Skills** (`.agents/skills/`, plural): markdown `SKILL.md` with `name` + `description` frontmatter. Can be invoked via `$skill-name` mention, the `/skills` command, or implicitly (if `allow_implicit_invocation: true`). Shared context with the caller.
- **Subagents** (`.codex/agents/`, singular): TOML files with `sandbox_mode`, `model`, `model_reasoning_effort`, and explicit-only dispatch. Inherited-but-separate context.

The harness uses **skills for phase entrypoints + the one project skill** (`dependabot-fixer`), and **TOML subagents for the four sub-agents** (`explorer`, `adversarial-reviewer`, `adversarial-reviewer-cross`, `documenter`). Rationale: sub-agents benefit from `sandbox_mode` enforcement (read-only for reviewers, workspace-write for documenter) that skills cannot provide.

## Phase name prefix

Codex has built-in `/plan` and `/review` slash commands with different semantics. To avoid collisions, **all six phase skills are prefixed `harness-`** — invoke them via `$harness-plan`, `$harness-work`, etc., not `/plan` / `/work`. The prefix is uniform across all six phases for consistency and future-proofing against new Codex built-ins.

## Layout

```
adapters/codex/
├── README.md                                   (this file)
├── skills/                                     (→ target's .agents/skills/)
│   ├── harness-setup/SKILL.md
│   ├── harness-plan/SKILL.md
│   ├── harness-work/SKILL.md
│   ├── harness-review/SKILL.md
│   ├── harness-release/SKILL.md
│   ├── harness-bugfix/SKILL.md
│   └── dependabot-fixer/SKILL.md
└── agents/                                     (→ target's .codex/agents/)
    ├── explorer.toml                           (sandbox_mode = read-only)
    ├── adversarial-reviewer.toml               (sandbox_mode = read-only)
    ├── adversarial-reviewer-cross.toml         (sandbox_mode = workspace-write)
    └── documenter.toml                         (sandbox_mode = workspace-write)
```

`install.sh` (POSIX) or `install.ps1` (Windows/PowerShell 7+) copies `skills/` to the target's `.agents/skills/` and `agents/` to the target's `.codex/agents/` with managed semantics: refreshed on `--update` / `-Update`, preserved on fresh install if already present.

## Invocation

From within Codex, invoke phases as skills:

- **Setup:** `$harness-setup`
- **Plan:** `$harness-plan <your brief>`
- **Work:** `$harness-work` (or `$harness-work task 3`)
- **Review:** `$harness-review`
- **Release:** `$harness-release`
- **Bugfix:** `$harness-bugfix <bug report>`

Subagents (`explorer`, `adversarial-reviewer`, `adversarial-reviewer-cross`, `documenter`) are dispatched automatically by the phase skills. You can also invoke them directly by name when you need a one-off.

## Known divergence: per-write verification

Claude Code's harness ships a `PostToolUse` hook with matcher `Write|Edit` that runs `verify.sh` after every file write. **Codex's `PostToolUse` hook supports only the `Bash` matcher** — the per-write verify pattern cannot port 1:1.

The `harness-work` skill instructs the agent to run `.harness/verify.sh` itself after implementing. This is the same discipline Antigravity uses (no hook surface at all).

**Opt-in Stop-based verification** (runs once per turn rather than per-write):

1. Enable the hooks feature in `<repo>/.codex/config.toml`:
   ```toml
   [features]
   codex_hooks = true
   ```
2. Create `<repo>/.codex/hooks.json`:
   ```json
   {
     "hooks": {
       "Stop": [
         {
           "matcher": "",
           "hooks": [
             {
               "type": "command",
               "command": "[[ -x .harness/verify.sh ]] && bash .harness/verify.sh || true",
               "timeout": 600
             }
           ]
         }
       ]
     }
   }
   ```

The harness does **not** ship these files — users opt in per-repo.

## Single source of truth

Every skill and subagent here points back to the canonical spec under [`harness/phases/`](../../harness/phases/), [`harness/pipelines/`](../../harness/pipelines/), or [`harness/agents/`](../../harness/agents/). If an adapter file drifts from the canonical spec, the canonical spec wins — file an issue or fix it.

## Re-audit hook

If Codex ships first-class PostToolUse matchers beyond `Bash` (e.g. `Write`, `Edit`), revisit the known-divergence note and consider shipping a `hooks.json` by default — per the re-audit principle ([principles.md §6](../../harness/principles.md)).
