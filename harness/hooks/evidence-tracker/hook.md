---
name: evidence-tracker
description: Default-FAIL evidence enforcement for /work. Fires on PreToolUse for Read/Write/Edit. Records reads of existing files; blocks Write/Edit operations that would flip a PLAN.md task's [ ] to [x] when no evidence has been recorded for that task. Per-task `**Evidence:** <patterns>` override; `**Evidence:** none` opt-out.
kind: hook
supported_hosts: [claude-code]
version: 0.1.0
install_scope: project
---

# evidence-tracker — default-FAIL evidence enforcement for `/work`

A `PreToolUse` hook that tightens `/work`'s verification gate. From [cwc-long-running-agents](https://github.com/anthropics/cwc-long-running-agents) (paraphrased): *"The only evidence that counts is a file matching the patterns."* Today's `/work` trusts the agent to verify before marking a task `[x]`; this hook makes that verification step *observable* + *enforced*.

## How it works

| Tool | Hook behavior |
|---|---|
| `Read` (file exists) | Record the path under `.harness/.evidence-reads` (key `__global__` = `"0"` — visible to all tasks) |
| `Read` (file missing) | No-op (prevents fictitious-path bypass: agent can't claim to have read `tests/fake.py`) |
| `Write` or `Edit` on `.harness/PLAN.md` that would flip `[ ]` → `[x]` for task N | Resolve task N's evidence requirement; check recorded reads; **block (exit 2)** if not met; **allow (exit 0)** if met |
| `Write` or `Edit` not flipping a checkbox | Pass-through (exit 0) |
| Any other tool | Pass-through (exit 0) |

Evidence requirement per task (HYBRID — locked in [ADR 0009](../../wiki/explanation/decisions/0009-evidence-tracker-hook.md)):

- **HEURISTIC** by default — files under `tests/` or `spec/`, matching `*.spec.*` / `*.test.*` / `*_test.py` / `test_*.py` with a code extension (markdown excluded to prevent `tests/README.md` false-positive), OR any path literally named in the task's `**Verification:**` text.
- **Per-task override** via `**Evidence:** <glob-or-paths>` task-body annotation (comma- or whitespace-separated; supports globs).
- **Explicit opt-out** via `**Evidence:** none — <one-line rationale>` (case-insensitive; rationale stripped after `—` or `-`).

## State file

`.harness/.evidence-reads` (JSON, gitignored, atomic write). Per-task buckets keyed by task ID; `"0"` is the global bucket. Reset on `/work` session start per the harness `/work` spec §5b (lands in plan #9 task 4).

## Operator usage

**To add an evidence override to a task** (PLAN.md):

```markdown
### 3. Audit the API client
- **What:** Walk the new pagination logic.
- **Verification:** Manual scan of the client.
- **Evidence:** src/api/client.py, src/api/pagination.py
- **Status:** [ ]
```

**To opt a task out of evidence-tracking** (genuinely no-test-evidence cases):

```markdown
### 7. Append CHANGELOG entry for v1.2.0
- **What:** Add user-visible changes under the v1.2.0 header.
- **Evidence:** none — pure documentation; no code paths to verify.
- **Status:** [ ]
```

**When the hook blocks you**, stderr explains exactly what's expected. To unblock:

1. Read a file that satisfies the requirement above (use the `Read` tool), OR
2. Add `**Evidence:** none — <rationale>` to the task body if genuinely docs-only, OR
3. Reset session state: `python3 .claude/hooks/evidence_tracker.py --mode reset`

## Graceful-skip conditions

The hook never blocks `/work` from running — only specific `[x]` flips. Silent no-op (exit 0) when:

- Python 3 not available on PATH.
- `.claude/hooks/evidence_tracker.py` helper not installed (shouldn't happen post-install, but defensive).
- Project root has no `.harness/` directory (hook isn't a no-op outside a harness install).
- Tool operation isn't `Read`/`Write`/`Edit` OR isn't touching PLAN.md OR doesn't flip a checkbox.
- Tool input JSON is malformed (fail-open per Claude Code's PreToolUse contract).

## Settings registration

The settings fragment registers the hook on `PreToolUse` with matcher `Read|Write|Edit`. Timeout: 10s (parsing PLAN.md + state-file I/O should complete in <100ms; 10s is the safety ceiling).

## Cross-references

- **Python helper:** [`evidence_tracker.py`](evidence_tracker.py) (~720 lines, stdlib-only) — the core resolver + state-file management + checkbox-flip detector. 61 unit tests covering all paths.
- **Sibling base hooks:** [`kill-switch`](../kill-switch/hook.md), [`steer`](../steer/hook.md), [`commit-on-stop`](../commit-on-stop/hook.md) — operator-control hooks landing in earlier plans (#4 + #5).
- **Harness `/work` spec amendment:** `harness/phases/03-work.md` §5b — documents the evidence-tracking contract from the harness side (lands in plan #9 task 4).
- **ADR 0009:** [Evidence-tracker hook design rationale](../../wiki/explanation/decisions/0009-evidence-tracker-hook.md) — 3 locked design calls Q1–Q3 + load-bearing assumptions (lands in plan #9 task 6).
- **How-to:** [Use The Evidence-Tracker Hook](../../wiki/how-to/Use-The-Evidence-Tracker-Hook.md) (lands in plan #9 task 5).
