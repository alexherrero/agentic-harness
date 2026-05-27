#!/usr/bin/env bash
# memory-reflect-stop — mine the just-ended session's transcript on Stop.
#
# Fires on Claude Code's Stop event. Parses the stdin JSON payload for
# session_id, computes the transcript path at
# ~/.claude/projects/<cwd-slug>/<session_id>.jsonl, and invokes reflect.py
# to mine durable candidates. Output on stdout (pass-through from reflect.py);
# transparency line on stderr.
#
# Tri-modal routing (HIGH→auto / MEDIUM→interactive / LOW→inbox) lands in
# plan #7a part 3 task 5; this hook ships the mining-only scaffold.
#
# See hook.md in this directory for full documentation.

set -uo pipefail  # NOTE: no -e — graceful-skip pattern; hook must never block session end.

# Resolve reflect.py location. Memory skill installs to:
#   .claude/skills/memory/scripts/reflect.py
# Hook runs from target project root (Claude Code's cwd convention).
REFLECT_PY=".claude/skills/memory/scripts/reflect.py"
if [[ ! -f "$REFLECT_PY" ]]; then
    # Memory skill not installed; nothing to do.
    exit 0
fi

if ! command -v python3 >/dev/null 2>&1; then
    exit 0
fi

# Stop hook stdin payload (per Claude Code hook spec): JSON with at minimum
# session_id (UUID) and cwd. We extract both to compute the transcript path.
# Read stdin into a variable so we can parse it WITHOUT requiring jq (not
# universally installed; Python json module is always present alongside python3).
PAYLOAD="$(cat 2>/dev/null || true)"
if [[ -z "$PAYLOAD" ]]; then
    echo "[memory-reflect-stop] no stdin payload (skipping)" >&2
    exit 0
fi

# Parse session_id + cwd via a one-liner Python invocation. Returns
# "<session_id>\t<cwd>" or empty on parse failure.
PARSED="$(printf '%s' "$PAYLOAD" | python3 -c '
import json, sys
try:
    d = json.loads(sys.stdin.read())
except Exception:
    sys.exit(0)
sid = d.get("session_id") or ""
cwd = d.get("cwd") or ""
if sid:
    print(f"{sid}\t{cwd}")
' 2>/dev/null)"

if [[ -z "$PARSED" ]]; then
    echo "[memory-reflect-stop] no session_id on stdin (skipping)" >&2
    exit 0
fi

SESSION_ID="$(printf '%s' "$PARSED" | cut -f1)"
CWD="$(printf '%s' "$PARSED" | cut -f2)"
if [[ -z "$CWD" ]]; then
    CWD="$(pwd)"
fi

# Compute transcript path: ~/.claude/projects/<cwd-slug>/<session_id>.jsonl
# where <cwd-slug> = CWD with '/' replaced by '-' and a leading '-'.
CWD_SLUG="-$(printf '%s' "$CWD" | tr '/' '-')"
TRANSCRIPT="$HOME/.claude/projects/${CWD_SLUG}/${SESSION_ID}.jsonl"

if [[ ! -f "$TRANSCRIPT" ]]; then
    echo "[memory-reflect-stop] transcript not found: $TRANSCRIPT (skipping)" >&2
    exit 0
fi

# Invoke reflect.py with --summary + --route. The routing pass auto-saves
# HIGH candidates to canonical paths + sends MEDIUM/LOW + ideas to _inbox/.
# Route-mode defaults to "auto" (hook-safe; never prompts; MEDIUM → _inbox/)
# unless operator sets MEMORY_REVIEW_MODE=silent (auto-save MEDIUM) or
# MEMORY_REVIEW_MODE=interactive (which falls back to auto here since hooks
# have no TTY).
#
# We capture output once + reuse for both the transparency line + stdout
# pass-through. Running reflect.py --route twice would error on slug
# collision (HIGH save would refuse the second time).
REFLECT_OUT="$(python3 "$REFLECT_PY" "$TRANSCRIPT" --summary --route 2>&1)"
REFLECT_EXIT=$?
if [[ $REFLECT_EXIT -ne 0 ]]; then
    # Most common cause: MEMORY_VAULT_PATH not set in hook env. Reflection
    # output is captured but routing failed; emit what we have + stderr note.
    echo "$REFLECT_OUT" >&2 | head -3
    echo "[memory-reflect-stop] reflect.py --route exited $REFLECT_EXIT (MEMORY_VAULT_PATH set?); transcript was $TRANSCRIPT" >&2
    exit 0
fi

# Extract counts from the summary + route records for the transparency line.
SUMMARY_LINE="$(printf '%s' "$REFLECT_OUT" | grep -m1 '"pass": "summary"')"
ROUTE_LINE="$(printf '%s' "$REFLECT_OUT" | grep -m1 '"pass": "route"')"

MEM_COUNT="$(printf '%s' "$SUMMARY_LINE" | python3 -c 'import json,sys;
try:
    d=json.loads(sys.stdin.read()); print(d.get("memory_candidate_count",0))
except: print(0)' 2>/dev/null || echo 0)"
IDEA_COUNT="$(printf '%s' "$SUMMARY_LINE" | python3 -c 'import json,sys;
try:
    d=json.loads(sys.stdin.read()); print(d.get("idea_candidate_count",0))
except: print(0)' 2>/dev/null || echo 0)"

if [[ -n "$ROUTE_LINE" ]]; then
    SAVED="$(printf '%s' "$ROUTE_LINE" | python3 -c 'import json,sys;
try:
    d=json.loads(sys.stdin.read()); print(d.get("auto_saved",0)+d.get("approved",0))
except: print(0)' 2>/dev/null || echo 0)"
    INBOXED="$(printf '%s' "$ROUTE_LINE" | python3 -c 'import json,sys;
try:
    d=json.loads(sys.stdin.read()); print(d.get("inboxed",0)+d.get("ideas_inboxed",0))
except: print(0)' 2>/dev/null || echo 0)"
    echo "[memory-reflect-stop] Mined ${MEM_COUNT} memory + ${IDEA_COUNT} idea candidates from $TRANSCRIPT; saved $SAVED, inboxed $INBOXED" >&2
else
    echo "[memory-reflect-stop] Mined ${MEM_COUNT} memory + ${IDEA_COUNT} idea candidates from $TRANSCRIPT (routing skipped)" >&2
fi

# Emit captured reflect.py output on stdout (one JSON record per line).
printf '%s\n' "$REFLECT_OUT"

# ── Crash-recovery marker rename (plan #7a part 3 task 6) ──────────────────
# Reflection succeeded → rename .harness/session-id-<sid>.start → .reflected.
# This marks the session as fully reflected; the idle hook's orphan scan
# (memory-reflect-idle) will GC the .reflected marker after 30 days.
# If the .start marker doesn't exist (operator never ran SessionStart, or
# .harness/ wasn't initialized), this is a no-op.
MARKER=".harness/session-id-${SESSION_ID}.start"
if [[ -f "$MARKER" ]]; then
    mv "$MARKER" "${MARKER%.start}.reflected" 2>/dev/null || true
fi

exit 0
