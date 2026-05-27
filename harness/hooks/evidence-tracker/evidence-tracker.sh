#!/usr/bin/env bash
# evidence-tracker — default-FAIL evidence enforcement for /work.
#
# Fires on Claude Code's PreToolUse event (matcher Read|Write|Edit). Reads
# the PreToolUse JSON event from stdin and shells out to evidence_tracker.py
# which decides:
#   Read   → record the path (if file exists); exit 0
#   Write  → check whether op would flip a PLAN.md task [ ] → [x] without
#            evidence; exit 2 (block) if default-FAIL, else 0
#   Edit   → same as Write
#   other  → exit 0 (no-op)
#
# Graceful-skip: never blocks tool calls when Python3 is missing or the
# evidence_tracker.py helper isn't installed. The harness `/work` flow runs
# unchanged — only the specific [x] flips are gated.
#
# See hook.md in this directory for full documentation.

set -uo pipefail  # NOTE: no -e — graceful-skip; hook must never crash the session.

HELPER=".claude/hooks/evidence_tracker.py"

if [[ ! -f "$HELPER" ]]; then
    # Helper not installed — silently pass through.
    exit 0
fi

if ! command -v python3 >/dev/null 2>&1; then
    # Python3 not available — silently pass through.
    exit 0
fi

# Forward stdin (PreToolUse event JSON) to the Python helper and propagate
# its exit code. `exec` replaces the shell so stdin streams directly.
exec python3 "$HELPER" --mode check
