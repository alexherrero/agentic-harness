#!/usr/bin/env bash
# memory-reflect-idle — orphan-recovery + idle reflection sweep.
#
# Fires on Claude Code's SessionStart event + invokable manually / via cron.
# Scans .harness/session-id-*.start markers for orphans (markers older than
# the idle threshold = crashed sessions where Stop didn't fire); runs
# reflection retroactively on each orphan's transcript; renames .start →
# .reflected on success. GCs .reflected markers older than 30 days.
#
# Plan #7a part 3 task 4 — new crickets primitive. Markers themselves
# are written by task 6 (SessionStart + Stop extensions).
#
# See hook.md in this directory for full documentation.

set -uo pipefail  # NOTE: no -e — graceful-skip pattern; hook must never block session start.

REFLECT_PY=".claude/skills/memory/scripts/reflect.py"
if [[ ! -f "$REFLECT_PY" ]]; then
    exit 0
fi
if ! command -v python3 >/dev/null 2>&1; then
    exit 0
fi

# Idle threshold: 1 hour (3600s) per locked design call B2.ii. Override via env.
IDLE_THRESHOLD_SEC="${MEMORY_IDLE_THRESHOLD_SEC:-3600}"
# GC threshold for .reflected markers: 30 days.
GC_THRESHOLD_SEC="${MEMORY_REFLECTED_GC_SEC:-2592000}"

# Glob session-id-*.start markers. shopt nullglob makes the array empty if
# no matches (vs. bash's default of leaving the literal pattern).
shopt -s nullglob
markers=(.harness/session-id-*.start)
shopt -u nullglob

# Also collect .reflected markers for the GC pass.
shopt -s nullglob
reflected_markers=(.harness/session-id-*.reflected)
shopt -u nullglob

if [[ ${#markers[@]} -eq 0 && ${#reflected_markers[@]} -eq 0 ]]; then
    # No orphan work to do — but the skill-discovery scan still runs.
    # Fall through to the bottom of the script (discover-skills block + exit).
    no_orphan_work=1
else
    no_orphan_work=0
fi

# Portable mtime via Python (we already require python3 above). Avoids the
# stat(1) GNU-vs-BSD `-c` / `-f` flag mismatch (the original implementation
# tried `stat -f %m` first → on Linux GNU stat treats `-f` as filesystem-info
# and silently returned the wrong value, breaking orphan detection).
get_mtime() {
    python3 -c "import os, sys; print(int(os.path.getmtime(sys.argv[1])))" "$1" 2>/dev/null || echo 0
}

now=$(date +%s)
processed_count=0

if (( no_orphan_work == 1 )); then
    # Skip the orphan + GC passes entirely; fall through to discover-skills.
    :
fi

for marker in "${markers[@]:-}"; do
    [[ -n "$marker" && -f "$marker" ]] || continue
    mtime=$(get_mtime "$marker")
    age_sec=$((now - mtime))
    if (( age_sec < IDLE_THRESHOLD_SEC )); then
        # Marker is fresh; session might still be active. Skip.
        continue
    fi

    # Parse marker for transcript path. Format (locked in task 6):
    #   session_id: <uuid>
    #   started_at: <iso-timestamp>
    #   transcript: <absolute-path>
    transcript="$(grep '^transcript:' "$marker" 2>/dev/null | head -1 | sed 's/^transcript:[[:space:]]*//')"
    if [[ -z "$transcript" ]]; then
        echo "[memory-reflect-idle] marker $marker missing 'transcript:' line (skipping)" >&2
        continue
    fi
    if [[ ! -f "$transcript" ]]; then
        echo "[memory-reflect-idle] marker $marker transcript not found: $transcript (skipping)" >&2
        continue
    fi

    # Run reflection with --route (HIGH → canonical / MEDIUM+LOW → _inbox/
    # via reflect.py's tri-modal routing). Requires MEMORY_VAULT_PATH; if
    # unset, --route fails non-zero + marker stays .start for next pass.
    if python3 "$REFLECT_PY" "$transcript" --summary --route 2>/dev/null; then
        # Rename .start → .reflected on success.
        mv "$marker" "${marker%.start}.reflected" 2>/dev/null && processed_count=$((processed_count + 1))
    fi
done

# GC pass: delete .reflected markers older than 30 days.
# Guard the array expansion with #count check so `set -u` doesn't error on
# an empty nullglob result (bash 4.x quirk).
gc_count=0
if (( ${#reflected_markers[@]} > 0 )); then
    for reflected in "${reflected_markers[@]}"; do
        [[ -f "$reflected" ]] || continue
        mtime=$(get_mtime "$reflected")
        age_sec=$((now - mtime))
        if (( age_sec > GC_THRESHOLD_SEC )); then
            rm -f "$reflected" && gc_count=$((gc_count + 1))
        fi
    done
fi

if (( ${#markers[@]} > 0 || gc_count > 0 )); then
    echo "[memory-reflect-idle] Scanned ${#markers[@]} .start + ${#reflected_markers[@]} .reflected markers; processed $processed_count orphans, GC'd $gc_count old markers (idle threshold: ${IDLE_THRESHOLD_SEC}s)" >&2
fi

# ── Skill-discovery cadence-checked scan (plan #7b task 3) ─────────────────
# Fire discover_skills.py with --cadence-check so it self-throttles to the
# configured cadence (default 7d). Requires MEMORY_VAULT_PATH; graceful-skip
# if unset / discover_skills.py absent / Python deps unavailable. Output
# routes to stderr so the hook's overall stdout stays clean for any
# downstream parsing.
DISCOVER_PY=".claude/skills/memory/scripts/discover_skills.py"
if [[ -f "$DISCOVER_PY" && -n "${MEMORY_VAULT_PATH:-}" ]]; then
    python3 "$DISCOVER_PY" --vault-path "$MEMORY_VAULT_PATH" --cadence-check >&2 2>&1 || true
fi

exit 0
