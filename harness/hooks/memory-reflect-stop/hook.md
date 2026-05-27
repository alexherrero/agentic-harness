---
name: memory-reflect-stop
description: "Stop-event hook that mines the just-ended session's transcript for durable candidate entries. Parallel passes: 3-category MemoryVault mine + idea-candidate mine. Emits a transparency line listing candidate counts per confidence tier. Tri-modal routing (HIGH→auto / MEDIUM→interactive / LOW→inbox) lands in plan #7a part 3 task 5; this hook ships the scaffold + mining call. Plan #7a part 3 task 3."
kind: hook
supported_hosts: [claude-code]
version: 0.1.0
install_scope: project
---

# memory-reflect-stop — mine the just-ended session's transcript on Stop

A `Stop` event hook that runs reflection mining (via `skills/memory/scripts/reflect.py`) against the just-ended session's transcript + emits a transparency line summarizing what got mined. The same mining logic also runs via the manual `/memory reflect` skill (plan #7a part 3 task 2) + the idle-time hook (task 4 — covers crashed sessions where this Stop hook didn't fire).

## How it works

- **Trigger:** Claude Code's `Stop` event (matcher `.*` — fires at the end of every agent turn that ends a session).
- **Session-id resolution:** parses the Stop event's stdin JSON payload + extracts `session_id`. The transcript path is computed as `~/.claude/projects/<cwd-slug>/<session_id>.jsonl` where `<cwd-slug>` is `cwd` with `/` → `-` + leading `-`.
- **Mining call:** invokes `python3 .claude/skills/memory/scripts/reflect.py <transcript-path> --summary`. The script emits one JSON record per candidate on stdout.
- **Output:**
  - **stdout** — passed through from reflect.py (one JSON record per line). Claude Code shows this in hook logs; future task 5 routing logic will parse + act on these records.
  - **stderr** — one transparency line: `[memory-reflect-stop] Mined N memory candidates + M idea candidates from <transcript-path>`. Truncated to slug list if any candidates surface.
- **Exit 0 always** — even on missing transcript, mining errors, missing python3 (graceful-skip pattern across the layered failure modes).

## Implementation status (task 3 of plan #7a part 3)

This task ships the hook scaffold + transcript-path resolution + reflect.py invocation. **Tri-modal routing** (HIGH→auto-save via `/memory save`, MEDIUM→interactive review, LOW→`_inbox/` write) lands in task 5 of this part. Until then, this hook **emits candidates but does NOT save them** — the operator can inspect the hook logs to see what would have been routed.

## What it never does

- **Never blocks session end.** If anything fails (transcript missing, reflect.py missing, python3 missing, mining error), the hook exits 0 silently.
- **Never writes to MemoryVault.** Task 3 only mines + reports. Writing happens in task 5.
- **Never modifies the transcript.** Pure read-only.
- **Never invokes reflect.py with a non-existent transcript.** If the path doesn't resolve, hook exits 0 with a "transcript not found" stderr note.

## Failure modes (all soft)

- **`MEMORY_VAULT_PATH` unset** — hook still mines + reports candidates, but the future task-5 routing won't know where to save. Stop-event hook itself doesn't need vault access — that's task 5's wiring.
- **Stdin payload missing `session_id`** — hook reports "no session_id on stdin" + exit 0.
- **Transcript path doesn't exist** — stderr "transcript not found: <path>" + exit 0.
- **reflect.py not installed** — exit 0 silently (graceful-skip; matches the recall hooks' pattern).
- **python3 not on PATH** — shell wrapper exits 0 silently.

## Antigravity equivalent

Antigravity has no first-class Stop-event surface (per v0.7.0+ installer reality). The equivalent pattern for Antigravity is a per-conversation-end skill auto-invocation; tracked under MemoryVault's discovery-mining part as a future companion customization.

## See also

- [`memory-reflect-idle`](../memory-reflect-idle/hook.md) — companion idle-time hook (lands in plan #7a part 3 task 4) that catches sessions where Stop didn't fire (crashed Claude Code).
- [`memory` skill — `/memory reflect`](../../skills/memory/SKILL.md) — manual trigger using the same mining logic.
- [`reflect.py`](../../skills/memory/scripts/reflect.py) — canonical Python implementation invoked by this hook.
- [MemoryVault reflection-and-recovery part](../../wiki/explanation/designs/memoryvault/parts/reflection-and-recovery.md) — full architectural context.
