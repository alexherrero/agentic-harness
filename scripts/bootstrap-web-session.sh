#!/usr/bin/env bash
# bootstrap-web-session.sh — make a Claude Code (web) container boot as a fully
# configured agentm "home" workstation with read/write access to the
# AgentMemory Google Drive vault.
#
# Designed to be the (or part of the) web environment SETUP SCRIPT. It is
# idempotent: safe to run at the start of every session.
#
# SECRETS: the rclone Drive OAuth token is read from the env var
#   AGENTM_RCLONE_TOKEN   (a JSON blob from `rclone authorize "drive"`)
# set in the environment's secret/variable config — NEVER committed to the repo.
# Without it, everything installs but the vault stays unmounted (read-only via
# whatever MCP is present).
set -euo pipefail

log() { printf '  [bootstrap] %s\n' "$*"; }

AGENTM_SRC="${AGENTM_SRC:-/home/user/agentm}"     # this checkout
CRICKETS_SRC="${CRICKETS_SRC:-$HOME/Antigravity/crickets}"
BIN="$HOME/.local/bin"
export PATH="$BIN:$PATH"
mkdir -p "$BIN"

# 1) Lay out the home-style sibling tree -------------------------------------
mkdir -p "$HOME/Antigravity"
[ -e "$HOME/Antigravity/agentm" ] || ln -s "$AGENTM_SRC" "$HOME/Antigravity/agentm"
if [ ! -d "$CRICKETS_SRC" ]; then
  log "cloning crickets (personal customizations)"
  git clone --quiet --depth 1 https://github.com/alexherrero/crickets.git "$CRICKETS_SRC" || \
    log "WARN: crickets clone failed (continuing without personalizations)"
fi

# 2) Install the full harness in user scope (~/.claude) -----------------------
log "installing agentm --scope user"
bash "$AGENTM_SRC/install.sh" --scope user >/dev/null

# 3) rclone (pinned; CDN is blocked here, GitHub releases are allowed) --------
if ! command -v rclone >/dev/null 2>&1; then
  log "installing rclone"
  ver="v1.69.1"
  tmp="$(mktemp -d)"
  curl -fsSL -o "$tmp/r.zip" \
    "https://github.com/rclone/rclone/releases/download/$ver/rclone-$ver-linux-amd64.zip"
  unzip -qo "$tmp/r.zip" -d "$tmp"
  install -m755 "$tmp/rclone-$ver-linux-amd64/rclone" "$BIN/rclone"
  rm -rf "$tmp"
fi
log "rclone $(rclone version | head -1 | awk '{print $2}')"

# 4) Reconstruct the Drive remote from the secret token -----------------------
if rclone listremotes 2>/dev/null | grep -qx "gdrive:"; then
  log "rclone remote 'gdrive' already configured"
elif [ -n "${AGENTM_RCLONE_TOKEN:-}" ]; then
  log "creating rclone remote 'gdrive' from AGENTM_RCLONE_TOKEN"
  rclone config create gdrive drive scope=drive token="$AGENTM_RCLONE_TOKEN" >/dev/null
else
  log "AGENTM_RCLONE_TOKEN not set — vault will NOT be mounted (read-only mode)."
  log "Set it in the environment's secrets to enable read/write parity."
fi

# 5) Pull the vault so the harness operates on real files ----------------------
export MEMORY_VAULT_PATH="${MEMORY_VAULT_PATH:-$HOME/vault/AgentMemory}"
if rclone listremotes 2>/dev/null | grep -qx "gdrive:"; then
  log "pulling AgentMemory vault -> $MEMORY_VAULT_PATH"
  mkdir -p "$MEMORY_VAULT_PATH"
  rclone sync "gdrive:AgentMemory" "$MEMORY_VAULT_PATH" || log "WARN: vault pull failed"
  # Point the harness at it (persist for this user)
  python3 "$AGENTM_SRC/scripts/agentm_config.py" --vault-path "$MEMORY_VAULT_PATH" >/dev/null 2>&1 || true
  log "vault ready: $(find "$MEMORY_VAULT_PATH" -type f 2>/dev/null | wc -l) files"
fi

log "done. 'agentm-vault push' to sync changes back to Drive."
