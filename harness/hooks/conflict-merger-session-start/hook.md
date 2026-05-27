---
name: conflict-merger-session-start
description: SessionStart hook that detects GDrive-induced conflict files (`<file> (conflicted copy YYYY-MM-DD).md`) anywhere under the MemoryVault and surfaces an operator-confirm dialog per pair. Operator approves merge per-file or defers. Detection is heuristic substring match; safe to graceful-skip when MEMORY_VAULT_PATH is unset (no vault → nothing to scan).
kind: hook
supported_hosts: [claude-code]
version: 0.1.0
install_scope: project
---

# conflict-merger-session-start — GDrive conflict-file detection at SessionStart

When the operator works against the MemoryVault from multiple devices (desktop + phone via Obsidian, multiple workstations, etc.), GDrive sync occasionally produces conflict files: `PLAN (conflicted copy 2026-05-27) - Mac.md` alongside the canonical `PLAN.md`. Without explicit detection, these conflict files accumulate silently — operator discovers them weeks later in Obsidian's file browser, by which time merging is painful.

This hook walks the vault at SessionStart, surfaces any conflict files found, and lets the operator decide per-pair: merge now, defer, or ignore.

## What it does

1. Reads `MEMORY_VAULT_PATH` env. Graceful-skip if unset or directory missing.
2. Calls `harness_memory.detect_conflict_files(vault_root)` which walks the vault for files containing the `(conflicted copy` substring.
3. For each conflict pair, prints a one-line summary:
   ```
   ⚠ GDrive conflict detected:
       conflict: projects/agentm/_harness/PLAN (conflicted copy 2026-05-27) - Mac.md
       base:     projects/agentm/_harness/PLAN.md
   ```
4. Then surfaces a single operator-confirm prompt:
   ```
   Found N GDrive conflict file(s). Options:
     (a) show diffs + merge interactively per pair
     (b) defer — leave them for now (will re-prompt next session)
     (c) silent for this session — don't re-prompt
   ```
5. The hook itself is non-blocking. It surfaces information; the actual merge interaction happens via `/work` or operator-direct in Obsidian. SessionStart never freezes on operator decision — defaults to (b) defer in non-TTY contexts.

## Why SessionStart (not idle)

Conflict-file accumulation correlates with operator-active-multi-device work. SessionStart fires at the moment operator is about to start a new session — they can decide right then whether to deal with conflicts or defer. The `memory-reflect-idle` hook already does idle-time scans; this hook covers the start-of-session detection.

## Graceful-skip conditions (silent)

- `MEMORY_VAULT_PATH` env unset.
- Vault directory missing.
- `harness_memory.py` not importable (Python-stdlib-only resolver missing for some reason).
- No conflict files found (output empty; no operator prompt).

## Configuration

- `HARNESS_CONFLICT_MERGER_MODE` env var:
  - `interactive` (default) — surface prompt at SessionStart.
  - `silent` — log to stderr but skip prompt (CI / scripted-session use).
  - `off` — full no-op.

## Settings fragment

Registered via the same `merge-settings-fragment.py` flow as the memory-recall hooks. Settings entry:

```json
"SessionStart": [
  {
    "matcher": ".*",
    "hooks": [
      {"type": "command", "command": "bash .claude/hooks/conflict-merger-session-start.sh", "timeout": 5}
    ]
  }
]
```

## Related

- `scripts/harness_memory.py` `detect_conflict_files()` — the underlying helper.
- Plan #18 task 8 — `.harness/designs/v4-device-wide/08-concurrency.md` § "Pattern 1: GDrive-managed conflict files" — design rationale.
- V4 #26 plan #20 task 4 — this hook ships as part of the concurrency primitives wave.
