#!/usr/bin/env bash
# migrate-to-user-scope.sh — V4 #30 plan 3 per-project → user-scope migration.
#
# Walks a target project's <target>/.claude/{skills,hooks,agents,commands}/
# tree, classifies each entry via SHA256 compare against the agentm + crickets
# source clones, then (with --apply) moves byte-identical content out of the
# per-project install so the user-scope install at ~/.claude/ becomes the
# single source of truth. Idempotent + reversible via --rollback.
#
# Usage:
#   bash agentm/scripts/migrate-to-user-scope.sh [OPTIONS] [TARGET]
#
# Options:
#   --apply               Execute the migration (default is preview).
#   --rollback            Reverse a prior migration via .agentm-migrate-record.json.
#   --cleanup             Opt-in destructive removal of empty .claude/{...}/
#                         install subdirs after byte-identical verification.
#   --force               Migrate operator-edited files anyway (with backup).
#                         Only applies with --apply.
#   --no-register         Skip auto-registering the repo in repo_registry.
#                         Default: auto-register on successful --apply.
#   --registry-slug NAME  Slug to use when auto-registering. Default: inferred
#                         from <target>/.harness/project.json or basename.
#   --agentm PATH         Override agentm source clone path.
#   --crickets PATH       Override crickets source clone path.
#   --yes, -y             Skip interactive confirms (CI / scripted use).
#   --ci-override         Allow run when $CI=true env detected (default refuses).
#   --help, -h            Print this help and exit.
#
# Positional argument:
#   TARGET                Project path (default: $PWD).
#
# State matrix (per plan #24 task 5):
#   (1) No <target>/.claude/ at all                → graceful no-op exit 0.
#   (2) .claude/ with content + no install-state   → pre-V4.3; primary migrate path.
#   (3) .claude/ + install-state mode=project      → V4.3+ explicit per-project;
#                                                    requires --yes confirmation.
#   (4) install-state mode=user OR no .claude/     → already user-scope; exit 0.
#
# Per V4 #30 plan 3 of 3 task 4. Pattern mirrors V4 #26 migrate-harness-to-vault.sh.

set -euo pipefail

# ── argument parsing ──────────────────────────────────────────────────────
APPLY=0
ROLLBACK=0
CLEANUP=0
FORCE=0
NO_REGISTER=0
REGISTRY_SLUG=""
AGENTM_PATH=""
CRICKETS_PATH=""
ASSUME_YES=0
CI_OVERRIDE=0
TARGET=""

print_help() {
    sed -n '/^# migrate-to-user-scope.sh/,/^[^#]/p' "$0" | sed 's|^# \?||' | sed '$d'
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --apply) APPLY=1; shift ;;
        --rollback) ROLLBACK=1; shift ;;
        --cleanup) CLEANUP=1; shift ;;
        --force) FORCE=1; shift ;;
        --no-register) NO_REGISTER=1; shift ;;
        --registry-slug)
            REGISTRY_SLUG="${2:-}"
            [[ -z "$REGISTRY_SLUG" ]] && { echo "--registry-slug requires a value" >&2; exit 2; }
            shift 2
            ;;
        --agentm)
            AGENTM_PATH="${2:-}"
            [[ -z "$AGENTM_PATH" ]] && { echo "--agentm requires a value" >&2; exit 2; }
            shift 2
            ;;
        --crickets)
            CRICKETS_PATH="${2:-}"
            [[ -z "$CRICKETS_PATH" ]] && { echo "--crickets requires a value" >&2; exit 2; }
            shift 2
            ;;
        --yes|-y) ASSUME_YES=1; shift ;;
        --ci-override) CI_OVERRIDE=1; shift ;;
        --help|-h) print_help; exit 0 ;;
        --*)
            echo "Unknown option: $1" >&2
            echo "" >&2
            print_help >&2
            exit 2
            ;;
        *)
            if [[ -z "$TARGET" ]]; then
                TARGET="$1"; shift
            else
                echo "Unexpected positional argument: $1 (target already set to: $TARGET)" >&2
                exit 2
            fi
            ;;
    esac
done

# Mutually exclusive sanity
modes_set=0
[[ $APPLY -eq 1 ]] && modes_set=$((modes_set+1))
[[ $ROLLBACK -eq 1 ]] && modes_set=$((modes_set+1))
[[ $CLEANUP -eq 1 ]] && modes_set=$((modes_set+1))
if [[ $modes_set -gt 1 ]]; then
    echo "Error: --apply / --rollback / --cleanup are mutually exclusive." >&2
    exit 2
fi

# ── resolve target ────────────────────────────────────────────────────────
TARGET="${TARGET:-$PWD}"
if [[ ! -d "$TARGET" ]]; then
    echo "Error: target is not a directory: $TARGET" >&2
    exit 1
fi
TARGET="$(cd "$TARGET" && pwd)"

# ── CI guard ──────────────────────────────────────────────────────────────
if [[ "${CI:-}" == "true" && $CI_OVERRIDE -eq 0 ]]; then
    echo "Error: refusing to run inside CI (\$CI=true detected)." >&2
    echo "  CI runners typically use per-project installs by design." >&2
    echo "  Re-run with --ci-override if you really intend to migrate inside CI." >&2
    exit 4
fi

# ── locate helpers ────────────────────────────────────────────────────────
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"
LIB_PY="$REPO_ROOT/lib/install/python"
INSTALL_MIGRATE_PY="$LIB_PY/install_migrate.py"
INSTALL_STATE_PY="$LIB_PY/install_state.py"
REPO_REGISTRY_PY="$REPO_ROOT/scripts/repo_registry.py"
INSTALL_SH="$REPO_ROOT/install.sh"

for f in "$INSTALL_MIGRATE_PY" "$INSTALL_STATE_PY" "$REPO_REGISTRY_PY"; do
    if [[ ! -f "$f" ]]; then
        echo "Error: required helper not found: $f" >&2
        echo "  (Did you run this from a checked-out agentm clone?)" >&2
        exit 1
    fi
done

# ── 4-state detection ─────────────────────────────────────────────────────
# Determine which of the 4 starting states the target is in.
# v4.5.1: prefer .agentm-config.json; fall back to legacy .agentm-install-state.json
# on pre-v4.5.1 installs that haven't been touched by v4.5.1 install_state.py yet.
CLAUDE_DIR="$TARGET/.claude"
INSTALL_STATE_JSON="$CLAUDE_DIR/.agentm-config.json"
if [[ ! -f "$INSTALL_STATE_JSON" && -f "$CLAUDE_DIR/.agentm-install-state.json" ]]; then
    INSTALL_STATE_JSON="$CLAUDE_DIR/.agentm-install-state.json"
fi
HAS_CLAUDE_CONTENT=0
if [[ -d "$CLAUDE_DIR" ]]; then
    for sub in skills hooks agents commands; do
        if [[ -d "$CLAUDE_DIR/$sub" ]] && [[ -n "$(ls -A "$CLAUDE_DIR/$sub" 2>/dev/null)" ]]; then
            HAS_CLAUDE_CONTENT=1
            break
        fi
    done
fi
INSTALL_STATE_MODE=""
if [[ -f "$INSTALL_STATE_JSON" ]]; then
    INSTALL_STATE_MODE="$(python3 -c "import json,sys; print(json.load(open('$INSTALL_STATE_JSON')).get('mode',''))" 2>/dev/null || true)"
fi

state="unknown"
if [[ $HAS_CLAUDE_CONTENT -eq 0 ]]; then
    state="no-claude"
elif [[ -z "$INSTALL_STATE_MODE" ]]; then
    state="pre-v4.3"
elif [[ "$INSTALL_STATE_MODE" == "project" ]]; then
    state="explicit-project"
elif [[ "$INSTALL_STATE_MODE" == "user" ]]; then
    state="already-user"
else
    state="pre-v4.3"  # defensive default for unknown mode strings
fi

# ── handle "nothing to do" states up front ────────────────────────────────
# Exception: --rollback runs the rollback flow regardless (record file may
# exist even after .claude/ subdirs are empty mid-cycle); --cleanup also
# runs regardless because its purpose is to remove the empty subdirs.
if [[ "$state" == "no-claude" && $ROLLBACK -eq 0 && $CLEANUP -eq 0 ]]; then
    echo "No per-project install detected at $TARGET/.claude/."
    echo "If you want a user-scope install, run:"
    echo "    bash $INSTALL_SH --scope user $TARGET"
    exit 0
fi
if [[ "$state" == "already-user" && $ROLLBACK -eq 0 && $CLEANUP -eq 0 ]]; then
    echo "Already user-scope (mode=user in $INSTALL_STATE_JSON). Nothing to migrate."
    exit 0
fi

# ── banner ────────────────────────────────────────────────────────────────
[[ $APPLY -eq 0 && $ROLLBACK -eq 0 && $CLEANUP -eq 0 ]] && echo "==> [PREVIEW MODE — no changes will be made]"
echo "==> migrate-to-user-scope"
echo "    target:       $TARGET"
echo "    state:        $state"
if [[ $ROLLBACK -eq 1 ]]; then
    echo "    mode:         rollback"
elif [[ $CLEANUP -eq 1 ]]; then
    echo "    mode:         cleanup"
elif [[ $APPLY -eq 1 ]]; then
    echo "    mode:         apply"
else
    echo "    mode:         preview (default)"
fi
echo ""

# ── DC-10 confirmation for explicit-project state ─────────────────────────
if [[ "$state" == "explicit-project" && $APPLY -eq 1 && $ASSUME_YES -eq 0 ]]; then
    echo "Target's install-state.json explicitly sets mode=project."
    echo "Migration may be unwanted — see wiki/how-to/Use-Per-Project-Install.md"
    echo "for cases where --scope project is the right choice."
    echo ""
    read -r -p "Proceed with migration anyway? [y/N] " yn
    case "$yn" in
        [Yy]*) ;;
        *) echo "Aborted."; exit 0 ;;
    esac
fi

# ── shared Python invocation helper ───────────────────────────────────────
# Note: bash 3.2 (macOS default) errors on `"${arr[@]}"` expansion of empty
# arrays under `set -u`. Guard each optional flag with explicit conditionals
# so the python call only sees flags that are actually set.
run_migrate() {
    local mode="$1"
    shift
    local cmd=(python3 "$INSTALL_MIGRATE_PY" --mode "$mode")
    [[ -n "$AGENTM_PATH" ]] && cmd+=(--agentm "$AGENTM_PATH")
    [[ -n "$CRICKETS_PATH" ]] && cmd+=(--crickets "$CRICKETS_PATH")
    [[ -n "$REGISTRY_SLUG" ]] && cmd+=(--registry-slug "$REGISTRY_SLUG")
    [[ $FORCE -eq 1 ]] && cmd+=(--force)
    # Add any extra positional args from the caller, then target last.
    if [[ $# -gt 0 ]]; then
        cmd+=("$@")
    fi
    cmd+=("$TARGET")
    "${cmd[@]}"
}

# ── handle --rollback ─────────────────────────────────────────────────────
if [[ $ROLLBACK -eq 1 ]]; then
    echo "==> rolling back migration via .agentm-migrate-record.json"
    if ! run_migrate rollback > /tmp/migrate-rollback-$$.json 2>&1; then
        cat /tmp/migrate-rollback-$$.json >&2
        rm -f /tmp/migrate-rollback-$$.json
        exit 3
    fi
    restored=$(python3 -c "import json; d=json.load(open('/tmp/migrate-rollback-$$.json')); print(len(d.get('restored',[])))" 2>/dev/null || echo 0)
    skipped=$(python3 -c "import json; d=json.load(open('/tmp/migrate-rollback-$$.json')); print(len(d.get('skipped',[])))" 2>/dev/null || echo 0)
    cat /tmp/migrate-rollback-$$.json
    rm -f /tmp/migrate-rollback-$$.json
    echo ""
    echo "==> rollback complete: $restored restored, $skipped skipped"
    if [[ $NO_REGISTER -eq 0 ]]; then
        # Best-effort: unregister if we can determine a slug
        slug="$REGISTRY_SLUG"
        if [[ -z "$slug" ]]; then
            slug="$(basename "$TARGET")"
        fi
        echo "==> unregistering '$slug' from repo_registry (best-effort)"
        python3 "$REPO_REGISTRY_PY" unregister "$slug" 2>/dev/null || echo "  (slug not registered or registry unavailable; ignored)"
    fi
    exit 0
fi

# ── handle --cleanup ──────────────────────────────────────────────────────
if [[ $CLEANUP -eq 1 ]]; then
    echo "==> cleanup: verifying + removing empty install subdirs"
    if ! run_migrate cleanup > /tmp/migrate-cleanup-$$.json 2>&1; then
        cat /tmp/migrate-cleanup-$$.json >&2
        rm -f /tmp/migrate-cleanup-$$.json
        exit 3
    fi
    refused=$(python3 -c "import json; d=json.load(open('/tmp/migrate-cleanup-$$.json')); print('1' if d.get('refused') else '0')")
    cat /tmp/migrate-cleanup-$$.json
    rm -f /tmp/migrate-cleanup-$$.json
    if [[ "$refused" == "1" ]]; then
        echo ""
        echo "==> cleanup REFUSED — operator content remains under .claude/{...}/."
        echo "    Either move/remove that content, or accept the un-cleaned state."
        exit 5
    fi
    echo ""
    echo "==> cleanup complete."
    exit 0
fi

# ── preview OR apply ──────────────────────────────────────────────────────
# Always classify first; emit a preview table.
if ! run_migrate classify > /tmp/migrate-classify-$$.json 2>&1; then
    cat /tmp/migrate-classify-$$.json >&2
    rm -f /tmp/migrate-classify-$$.json
    echo "" >&2
    echo "Hint: source clones may be missing or path overrides may be wrong." >&2
    echo "Detected source clones:" >&2
    python3 "$INSTALL_STATE_PY" detect 2>&1 || true
    exit 1
fi

python3 - <<'PYEOF' "/tmp/migrate-classify-$$.json"
import json, os, sys
with open(sys.argv[1]) as f:
    data = json.load(f)
classified = data.get("classified", data) if isinstance(data, dict) else data
if not isinstance(classified, list):
    classified = data.get("classified", [])
if not classified:
    print("No per-project install entries to classify (empty .claude/).")
    sys.exit(0)
# Header
print(f"  {'CLASSIFICATION':<22} {'CLONE':<10} {'PATH'}")
print(f"  {'-'*22:<22} {'-'*10:<10} {'-'*40}")
counts = {}
for entry in classified:
    cls = entry.get("classification", "?")
    counts[cls] = counts.get(cls, 0) + 1
    clone = entry.get("source_clone") or "-"
    rel = entry.get("rel_path", "?")
    print(f"  {cls:<22} {clone:<10} {rel}")
print()
print("Summary:")
for k in sorted(counts):
    print(f"  {k:<22} {counts[k]}")
PYEOF

if [[ $APPLY -eq 0 ]]; then
    rm -f /tmp/migrate-classify-$$.json
    echo ""
    echo "Preview only. Re-run with --apply to execute the migration."
    exit 0
fi

# ── apply ─────────────────────────────────────────────────────────────────
rm -f /tmp/migrate-classify-$$.json
if [[ $ASSUME_YES -eq 0 ]]; then
    echo ""
    read -r -p "Apply this migration? [y/N] " yn
    case "$yn" in
        [Yy]*) ;;
        *) echo "Aborted."; exit 0 ;;
    esac
fi

# Infer registry slug if not explicitly given
slug="$REGISTRY_SLUG"
if [[ -z "$slug" ]]; then
    if [[ -f "$TARGET/.harness/project.json" ]]; then
        slug="$(python3 -c "import json; d=json.load(open('$TARGET/.harness/project.json')); print(d.get('vault_project') or d.get('slug') or '')" 2>/dev/null || true)"
    fi
    if [[ -z "$slug" ]]; then
        slug="$(basename "$TARGET")"
    fi
fi

echo "==> applying migration (slug=$slug)"
if ! run_migrate apply > /tmp/migrate-apply-$$.json 2>&1; then
    cat /tmp/migrate-apply-$$.json >&2
    rm -f /tmp/migrate-apply-$$.json
    exit 3
fi
cat /tmp/migrate-apply-$$.json
skipped_force=$(python3 -c "import json; print(json.load(open('/tmp/migrate-apply-$$.json')).get('skipped_force_needed',0))" 2>/dev/null || echo 0)
rm -f /tmp/migrate-apply-$$.json

# Populate ~/.claude/ via install.sh --scope user (idempotent)
if [[ -f "$INSTALL_SH" ]]; then
    echo ""
    echo "==> ensuring ~/.claude/ is populated via 'bash install.sh --scope user'"
    bash "$INSTALL_SH" --scope user >/dev/null 2>&1 || echo "  (install.sh exited non-zero; ~/.claude/ may already be in place)"
fi

# Auto-register unless opted out
if [[ $NO_REGISTER -eq 0 ]]; then
    echo ""
    echo "==> auto-registering '$slug' in repo_registry (root=$TARGET)"
    if python3 "$REPO_REGISTRY_PY" register "$slug" --root "$TARGET" 2>/dev/null; then
        echo "  registered."
    else
        echo "  (registration skipped — vault unavailable or already registered)"
    fi
fi

echo ""
echo "==> apply complete."
[[ $skipped_force -gt 0 ]] && echo "    $skipped_force operator-edited file(s) skipped — re-run with --force to migrate."
echo "    Run with --cleanup once verified to remove .claude/{...}/ install subdirs."
echo "    Run with --rollback to reverse this migration."
exit 0
