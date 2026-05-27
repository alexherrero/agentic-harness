#!/usr/bin/env bash
# memory-recall-prompt-submit — inject query-relevant MemoryVault entries on prompt submit.
#
# Fires on Claude Code's UserPromptSubmit event. Receives the user's prompt
# (and other session metadata) as JSON on stdin; passes it through to
# recall.py's prompt-submit subcommand, which calls the recall engine for
# top-K relevant entries and emits them on stdout for context injection.
# Transparency line on stderr. Hard 300ms time budget; degraded-graceful
# on overrun.
#
# See hook.md in this directory for full documentation.

set -uo pipefail  # NOTE: no -e — graceful-skip pattern; hook must never block the user prompt.

# Resolve recall.py location. The installer drops the memory skill at
# .claude/skills/memory/scripts/recall.py; this hook script runs from the
# target project root (Claude Code's cwd convention).
RECALL_PY=".claude/skills/memory/scripts/recall.py"
if [[ ! -f "$RECALL_PY" ]]; then
    # Memory skill not installed; nothing to do. Exit 0 (graceful-skip).
    exit 0
fi

# Require python3 — exit 0 if missing.
if ! command -v python3 >/dev/null 2>&1; then
    exit 0
fi

# Pipe stdin (the UserPromptSubmit JSON payload) through to recall.py.
# recall.py handles MEMORY_VAULT_PATH resolution, JSON parsing, prompt
# extraction, recall engine query (lands in task 3), dedup, output, and
# the 300ms time budget internally.
exec python3 "$RECALL_PY" prompt-submit
