#!/usr/bin/env bash
# install.sh — install agentic-harness into a target project.
#
# Usage:
#   /path/to/agentic-harness/install.sh [--hooks] <target-project-path>
#
# Options:
#   --hooks   Also install a PostToolUse verification hook that runs
#             .harness/verify.sh after every Write|Edit. You'll edit
#             verify.sh to uncomment the typecheck/lint for your stack.
#
# Idempotent: safe to re-run. Existing files are preserved; templates are only
# copied if they don't already exist at the destination. Hooks are merged into
# any existing .claude/settings.json.

set -euo pipefail

HARNESS_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
INSTALL_HOOKS=0
TARGET=""

for arg in "$@"; do
  case "$arg" in
    --hooks) INSTALL_HOOKS=1 ;;
    -h|--help)
      sed -n 's/^# //p' "$0" | head -20
      exit 0
      ;;
    -*)
      echo "Error: unknown flag: $arg" >&2
      exit 1
      ;;
    *)
      if [[ -n "$TARGET" ]]; then
        echo "Error: multiple target paths given" >&2
        exit 1
      fi
      TARGET="$arg"
      ;;
  esac
done

if [[ -z "$TARGET" ]]; then
  echo "Usage: $0 [--hooks] <target-project-path>" >&2
  exit 1
fi

if [[ ! -d "$TARGET" ]]; then
  echo "Error: target directory does not exist: $TARGET" >&2
  exit 1
fi

cd "$TARGET"

echo "==> installing agentic-harness into: $TARGET"

# .harness/ — per-project state
mkdir -p .harness
for f in PLAN.md features.json progress.md init.sh; do
  if [[ ! -e ".harness/$f" ]]; then
    cp "$HARNESS_ROOT/templates/$f" ".harness/$f"
    echo "    created .harness/$f"
  else
    echo "    kept   .harness/$f (exists)"
  fi
done
chmod +x .harness/init.sh

# .claude/ — Claude Code config
mkdir -p .claude/commands .claude/agents
for f in "$HARNESS_ROOT"/adapters/claude-code/commands/*.md; do
  name="$(basename "$f")"
  if [[ ! -e ".claude/commands/$name" ]]; then
    cp "$f" ".claude/commands/$name"
    echo "    created .claude/commands/$name"
  else
    echo "    kept   .claude/commands/$name (exists)"
  fi
done
for f in "$HARNESS_ROOT"/adapters/claude-code/agents/*.md; do
  name="$(basename "$f")"
  if [[ ! -e ".claude/agents/$name" ]]; then
    cp "$f" ".claude/agents/$name"
    echo "    created .claude/agents/$name"
  else
    echo "    kept   .claude/agents/$name (exists)"
  fi
done

# AGENTS.md — universal entry. Copy only if missing.
if [[ ! -e AGENTS.md ]]; then
  cp "$HARNESS_ROOT/AGENTS.md" AGENTS.md
  echo "    created AGENTS.md"
else
  echo "    kept   AGENTS.md (exists — you may want to merge harness sections from $HARNESS_ROOT/AGENTS.md)"
fi

# CLAUDE.md — Claude Code pointer.
if [[ ! -e CLAUDE.md ]]; then
  cp "$HARNESS_ROOT/CLAUDE.md" CLAUDE.md
  echo "    created CLAUDE.md"
else
  echo "    kept   CLAUDE.md (exists)"
fi

# --hooks: verification hook setup
if [[ $INSTALL_HOOKS -eq 1 ]]; then
  if ! command -v jq >/dev/null 2>&1; then
    echo "Error: --hooks requires jq (for merging settings.json). Install jq and re-run." >&2
    exit 1
  fi

  # verify.sh template — only copy if missing (it's the per-project part)
  if [[ ! -e .harness/verify.sh ]]; then
    cp "$HARNESS_ROOT/templates/verify.sh" .harness/verify.sh
    chmod +x .harness/verify.sh
    echo "    created .harness/verify.sh (edit this to enable typecheck/lint per language)"
  else
    echo "    kept   .harness/verify.sh (exists)"
  fi

  # Hook config — merge into .claude/settings.json
  HOOK_FRAGMENT=$(cat <<'JSON'
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "jq -r '.tool_input.file_path // .tool_response.filePath // empty' | { read -r f; [[ -n \"$f\" && -x .harness/verify.sh ]] && bash .harness/verify.sh \"$f\" || true; }",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
JSON
)

  if [[ ! -e .claude/settings.json ]]; then
    echo "$HOOK_FRAGMENT" > .claude/settings.json
    echo "    created .claude/settings.json with verification hook"
  else
    # Merge: preserve existing settings, add the hook if not already present
    existing=$(cat .claude/settings.json)
    already_present=$(echo "$existing" | jq '[.hooks.PostToolUse // [] | .[] | select(.matcher == "Write|Edit") | .hooks[] | .command | strings | contains(".harness/verify.sh")] | any' 2>/dev/null || echo "false")

    if [[ "$already_present" == "true" ]]; then
      echo "    kept   .claude/settings.json (verification hook already present)"
    else
      merged=$(echo "$existing" "$HOOK_FRAGMENT" | jq -s '
        .[0] as $a | .[1] as $b |
        $a * ($b | {hooks: ((($a.hooks // {}) | .PostToolUse //= []) as $h | $h | .PostToolUse += $b.hooks.PostToolUse)})
      ' 2>/dev/null)
      if [[ -z "$merged" ]]; then
        # jq merge failed — fall back to simple concatenation if there's no existing hooks key
        has_hooks=$(echo "$existing" | jq 'has("hooks")')
        if [[ "$has_hooks" == "false" ]]; then
          merged=$(echo "$existing" "$HOOK_FRAGMENT" | jq -s '.[0] + .[1]')
        else
          echo "    WARNING: .claude/settings.json already has a 'hooks' key. Merge skipped." >&2
          echo "    Add this PostToolUse entry manually:" >&2
          echo "$HOOK_FRAGMENT" | sed 's/^/      /' >&2
          merged=""
        fi
      fi
      if [[ -n "$merged" ]]; then
        echo "$merged" > .claude/settings.json
        echo "    updated .claude/settings.json (added verification hook)"
      fi
    fi
  fi

  echo ""
  echo "==> hooks installed. Edit .harness/verify.sh to enable checks for your stack."
fi

echo ""
echo "==> done."
echo ""
echo "Next steps:"
echo "  1. Edit .harness/init.sh so it actually boots this project"
if [[ $INSTALL_HOOKS -eq 1 ]]; then
  echo "  2. Edit .harness/verify.sh — uncomment the language case for your stack"
  echo "  3. Run /setup (Claude Code) or prompt 'run the setup phase' (Antigravity)"
  echo "  4. Then /plan <your first brief>"
else
  echo "  2. Run /setup (Claude Code) or prompt 'run the setup phase' (Antigravity)"
  echo "  3. Then /plan <your first brief>"
fi
