#!/usr/bin/env bash
# install.sh — install agentic-harness into a target project.
#
# Usage:
#   /path/to/agentic-harness/install.sh /path/to/target-project
#
# Idempotent: safe to re-run. Existing files are preserved; templates are only
# copied if they don't already exist at the destination.

set -euo pipefail

HARNESS_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
TARGET="${1:-}"

if [[ -z "$TARGET" ]]; then
  echo "Usage: $0 <target-project-path>" >&2
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

# AGENTS.md — universal entry. Copy only if missing; otherwise print a hint.
if [[ ! -e AGENTS.md ]]; then
  cp "$HARNESS_ROOT/AGENTS.md" AGENTS.md
  echo "    created AGENTS.md"
else
  echo "    kept   AGENTS.md (exists — you may want to merge harness sections from $HARNESS_ROOT/AGENTS.md)"
fi

# CLAUDE.md — Claude Code pointer. Same pattern.
if [[ ! -e CLAUDE.md ]]; then
  cp "$HARNESS_ROOT/CLAUDE.md" CLAUDE.md
  echo "    created CLAUDE.md"
else
  echo "    kept   CLAUDE.md (exists)"
fi

echo ""
echo "==> done."
echo ""
echo "Next steps:"
echo "  1. Edit .harness/init.sh so it actually boots this project"
echo "  2. Run /setup (Claude Code) or prompt 'run the setup phase' (Antigravity)"
echo "  3. Then /plan <your first brief>"
