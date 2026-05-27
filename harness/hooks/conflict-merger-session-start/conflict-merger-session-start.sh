#!/usr/bin/env bash
# conflict-merger-session-start — detect GDrive conflict files on session boot.
#
# Walks the MemoryVault for files containing the `(conflicted copy` substring;
# surfaces a one-paragraph operator-facing notice on stderr per pair found.
# Non-blocking: never freezes session boot waiting on operator input.
#
# Graceful-skip when MEMORY_VAULT_PATH unset or harness_memory.py unavailable.
#
# See hook.md in this directory for full documentation.

set -uo pipefail  # no -e — hook must never block session boot.

# Honor mode env var.
MODE="${HARNESS_CONFLICT_MERGER_MODE:-interactive}"
if [[ "$MODE" == "off" ]]; then
    exit 0
fi

# Graceful-skip if no vault.
if [[ -z "${MEMORY_VAULT_PATH:-}" ]]; then
    exit 0
fi
if [[ ! -d "$MEMORY_VAULT_PATH" ]]; then
    exit 0
fi

# Resolve harness_memory.py path. The hook script lives at
# .claude/hooks/<this>.sh post-install; the harness_memory.py lives at
# agentm/scripts/. Search the standard locations.
HM_PY=""
for candidate in \
    "$HOME/Antigravity/agentm/scripts/harness_memory.py" \
    "../agentm/scripts/harness_memory.py" \
    "../../agentm/scripts/harness_memory.py"; do
    if [[ -f "$candidate" ]]; then
        HM_PY="$candidate"
        break
    fi
done
if [[ -z "$HM_PY" ]]; then
    # No agentm install on this device — graceful-skip.
    exit 0
fi

# Invoke detect-conflict-files via a small inline Python that imports the helper.
# stderr is intentionally NOT redirected — the Python writes operator-facing
# findings there. Python-level errors (import / runtime) also surface — that's
# acceptable; the hook still exits 0 (never blocks session boot).
python3 - "$HM_PY" "$MEMORY_VAULT_PATH" <<'PY' || true
import importlib.util, sys
from pathlib import Path
hm_path, vault_root = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location("harness_memory", hm_path)
hm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hm)
conflicts = hm.detect_conflict_files(Path(vault_root))
if not conflicts:
    sys.exit(0)
import os
mode = os.environ.get("HARNESS_CONFLICT_MERGER_MODE", "interactive")
sys.stderr.write(f"\n[conflict-merger] {len(conflicts)} GDrive conflict file(s) detected in vault:\n")
for entry in conflicts:
    sys.stderr.write(f"    conflict: {entry['rel']}\n")
    sys.stderr.write(f"    base:     {entry['base'].relative_to(Path(vault_root))}\n")
if mode == "interactive":
    sys.stderr.write(
        "\n    To merge interactively: review each pair in Obsidian or via\n"
        "    `diff <base> <conflict>` and merge by hand. Run `/work` from the\n"
        "    affected repo if the conflict is in a vault-backed harness file\n"
        "    (PLAN.md / progress.md / etc.).\n\n"
        "    To suppress this notice for the current session, set\n"
        "    HARNESS_CONFLICT_MERGER_MODE=silent in the environment.\n\n"
    )
PY

exit 0
