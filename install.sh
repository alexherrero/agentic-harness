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
for f in PLAN.md features.json progress.md init.sh known-migrations.md; do
  if [[ ! -e ".harness/$f" ]]; then
    cp "$HARNESS_ROOT/templates/$f" ".harness/$f"
    echo "    created .harness/$f"
  else
    echo "    kept   .harness/$f (exists)"
  fi
done
chmod +x .harness/init.sh

# .claude/ — Claude Code config
mkdir -p .claude/commands .claude/agents .claude/skills
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
for d in "$HARNESS_ROOT"/adapters/claude-code/skills/*/; do
  [[ -d "$d" ]] || continue
  name="$(basename "$d")"
  if [[ ! -e ".claude/skills/$name" ]]; then
    cp -R "$d" ".claude/skills/$name"
    echo "    created .claude/skills/$name"
  else
    echo "    kept   .claude/skills/$name (exists)"
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

# --hooks: install all harness hooks (verify + precompact + session-start-compact)
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

  # Compaction-aware hook scripts — copy to .harness/hooks/
  mkdir -p .harness/hooks
  for f in precompact.sh session-start-compact.sh; do
    if [[ ! -e ".harness/hooks/$f" ]]; then
      cp "$HARNESS_ROOT/templates/hooks/$f" ".harness/hooks/$f"
      chmod +x ".harness/hooks/$f"
      echo "    created .harness/hooks/$f"
    else
      echo "    kept   .harness/hooks/$f (exists)"
    fi
  done

  # Hook registrations — merge into .claude/settings.json idempotently per event.
  # Each entry is keyed by a unique substring in its command so we can detect
  # whether it's already present without depending on field-by-field equality.
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
    ],
    "PreCompact": [
      {
        "matcher": "manual|auto",
        "hooks": [
          {
            "type": "command",
            "command": "bash .harness/hooks/precompact.sh",
            "timeout": 5
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "matcher": "compact",
        "hooks": [
          {
            "type": "command",
            "command": "bash .harness/hooks/session-start-compact.sh",
            "timeout": 5
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
    echo "    created .claude/settings.json with harness hooks (verify + precompact + session-start)"
  else
    # Merge per-event. For each event in the fragment, append entries that
    # aren't already present (detected by a unique substring of the command).
    merged=$(jq -s '
      def has_cmd($needle):
        [.. | objects | .command? // empty | strings | select(contains($needle))] | any;

      .[0] as $existing | .[1] as $fragment |
      reduce ($fragment.hooks | to_entries[]) as $e ($existing;
        . as $cur |
        ($e.value[0]) as $new_entry |
        ($new_entry.hooks[0].command) as $needle |
        if (($cur.hooks // {})[$e.key] // []) | has_cmd($needle)
        then $cur
        else
          .hooks //= {} |
          .hooks[$e.key] //= [] |
          .hooks[$e.key] += [$new_entry]
        end
      )
    ' .claude/settings.json <(echo "$HOOK_FRAGMENT") 2>/dev/null)

    if [[ -z "$merged" ]]; then
      echo "    WARNING: failed to merge hooks into .claude/settings.json. Add manually:" >&2
      echo "$HOOK_FRAGMENT" | sed 's/^/      /' >&2
    else
      # Compute what changed for the user-visible message
      added=$(diff <(jq -S . .claude/settings.json) <(echo "$merged" | jq -S .) | grep -c '^>' || true)
      echo "$merged" > .claude/settings.json
      if [[ "$added" -eq 0 ]]; then
        echo "    kept   .claude/settings.json (all harness hooks already present)"
      else
        echo "    updated .claude/settings.json (added missing harness hooks)"
      fi
    fi
  fi

  echo ""
  echo "==> hooks installed:"
  echo "    - PostToolUse  → .harness/verify.sh (per-file verification on Write/Edit)"
  echo "    - PreCompact   → .harness/hooks/precompact.sh (writes marker to progress.md)"
  echo "    - SessionStart → .harness/hooks/session-start-compact.sh (re-anchors after compact)"
  echo "    Edit .harness/verify.sh to enable checks for your stack."
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
