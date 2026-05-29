---
name: harness-context-session-start
description: SessionStart hook that injects the project's vault-resident PLAN.md + progress.md paths into session context. Fires on every session boot in any cwd; resolves the active project's harness state via `harness_memory.py vault-state-path` and emits a short 4-line block only when both files exist. Silent no-op for non-harness cwds. Hard 500ms budget; degraded-graceful. V4 #39.
kind: hook
supported_hosts: [claude-code]
version: 0.1.0
install_scope: user
---

# harness-context-session-start — surface vault PLAN.md / progress.md on session boot

A `SessionStart` event hook (universal, `install_scope: user` — fires in every project the operator works in). Post-V4 #26, a project's harness state (`PLAN.md`, `progress.md`) lives in the MemoryVault at `<vault>/projects/<slug>/_harness/`, not in the repo's `.harness/`. Nothing told the agent that at session boot — it had to *think* to call the resolver, and sometimes didn't (the gap that motivated V4 #39). This hook closes it: on every SessionStart it reads the event's `cwd`, resolves the active project's vault state paths via `harness_memory.py vault-state-path`, and — **only when both `PLAN.md` and `progress.md` resolve and exist on disk** — injects a 4-line context block telling the agent where they live and to read `PLAN.md` before plan-status questions or phase commands.

## Behavior

- **Reads `cwd` from the SessionStart event JSON on stdin** (not the script's `pwd` — Claude Code's hook-firing cwd may differ from the project cwd; DC-6).
- **Resolves `harness_memory.py`** from `~/.claude/.agentm-config.json` → `source_clones.agentm`, falling back to `~/Antigravity/agentm/scripts/harness_memory.py`.
- **Injects only when both state files exist** — otherwise a silent `exit 0` with a one-line stderr reason. Non-harness cwds, an unreachable vault, or a missing resolver all degrade gracefully (DC-3).
- **Hard 500ms budget** via `gtimeout`/`timeout` when available (graceful if neither is installed).
- **Fires on matcher `.*`** (every SessionStart — startup / resume / clear / compact). Idempotent: re-injecting the same block on resume is harmless (DC-8).
- **Output block** (4 lines, locked DC-7):

  ```
  [agentm] Project state for this repo lives in the vault, not in .harness/:
    PLAN.md:     <resolved path>
    progress.md: <resolved path>
  Read PLAN.md before answering plan-status questions or running /work, /review, /release.
  ```

## Install

Universal — installs to `~/.claude/hooks/harness-context-session-start/` under `--scope user`; the installer merges `settings-fragment-bash.json` into `~/.claude/settings.json` and absolutizes the command to `bash ~/.claude/hooks/harness-context-session-start/harness-context-session-start.sh` (V4 #39 task 1). Never blocks session boot.
