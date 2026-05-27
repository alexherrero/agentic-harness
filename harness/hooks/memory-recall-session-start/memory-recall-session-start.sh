#!/usr/bin/env bash
# memory-recall-session-start — load MemoryVault always-load entries on session boot.
#
# Fires on Claude Code's SessionStart event. Calls the memory skill's recall.py
# helper to glob _always-load/*.md entries + emit their bodies on stdout (which
# Claude Code injects as additional session context). Transparency line on
# stderr. Hard 500ms time budget; degraded-graceful on overrun.
#
# See hook.md in this directory for full documentation.

set -uo pipefail  # NOTE: no -e — graceful-skip pattern; hook must never block session boot.

# ── Crash-recovery marker (plan #7a part 3 task 6) ─────────────────────────
# Parse the SessionStart event's stdin JSON for session_id + cwd, then write
# a `.harness/session-id-<sid>.start` marker. The marker enables the idle
# hook's orphan-recovery sweep — if Stop never fires (Claude Code crashed,
# OS killed it, force quit), the marker stays as .start past the idle
# threshold and the idle hook reflects retroactively on next SessionStart.
#
# Marker writes are best-effort: failure here doesn't block recall (which is
# the primary purpose of this hook). If .harness/ doesn't exist or session_id
# can't be parsed, we skip the marker + continue to recall.
PAYLOAD="$(cat 2>/dev/null || true)"
if [[ -n "$PAYLOAD" ]] && [[ -d .harness || -w . ]]; then
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
    if [[ -n "$PARSED" ]]; then
        SESSION_ID="$(printf '%s' "$PARSED" | cut -f1)"
        SESSION_CWD="$(printf '%s' "$PARSED" | cut -f2)"
        if [[ -z "$SESSION_CWD" ]]; then
            SESSION_CWD="$(pwd)"
        fi
        # Transcript path (same formula as memory-reflect-stop.sh).
        CWD_SLUG="-$(printf '%s' "$SESSION_CWD" | tr '/' '-')"
        TRANSCRIPT_PATH="$HOME/.claude/projects/${CWD_SLUG}/${SESSION_ID}.jsonl"
        # Ensure .harness/ exists; if not, create it (operator may not have
        # initialized the harness in this project yet — marker is still useful
        # to write, even if it gets ignored by other tooling).
        mkdir -p .harness 2>/dev/null
        MARKER=".harness/session-id-${SESSION_ID}.start"
        # Write only if not present already (idempotent; SessionStart fires
        # multiple times per session in resume/clear/compact scenarios).
        if [[ ! -f "$MARKER" ]]; then
            cat > "$MARKER" 2>/dev/null << MARKER_EOF || true
session_id: ${SESSION_ID}
started_at: $(date -u +%Y-%m-%dT%H:%M:%SZ)
transcript: ${TRANSCRIPT_PATH}
MARKER_EOF
        fi
    fi
fi

# ── Recall pass ────────────────────────────────────────────────────────────
# Resolve recall.py location. The installer drops the memory skill at
# .claude/skills/memory/scripts/recall.py; this hook script runs from the
# target project root (Claude Code's cwd convention), so the path is fixed.
RECALL_PY=".claude/skills/memory/scripts/recall.py"
if [[ ! -f "$RECALL_PY" ]]; then
    # Memory skill not installed; nothing to do. Exit 0 (graceful-skip).
    exit 0
fi

# Require python3 — exit 0 if missing (graceful-skip; no blocking).
if ! command -v python3 >/dev/null 2>&1; then
    exit 0
fi

# Invoke. recall.py handles MEMORY_VAULT_PATH resolution, glob, frontmatter
# parse, filter, output, and the 500ms time budget internally.
exec python3 "$RECALL_PY" session-start
