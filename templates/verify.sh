#!/usr/bin/env bash
# verify.sh — per-project verification hook.
# Called by the Claude Code PostToolUse hook after every Write|Edit with the
# path of the file that was just written or edited as $1.
#
# Customize the case statement below to match your project's typecheck/lint.
# Leave commands commented until you know you want them — a noisy hook is
# worse than no hook.
#
# RULES:
# - This runs on EVERY Write/Edit. Keep it FAST (<2s total). Full-suite tests
#   belong in /review or CI, not here.
# - Prefer single-file operations (lint one file, not the whole project).
# - Exit 0 on success (silent), non-zero on failure (shown as system message).
# - Stdout/stderr are shown to the user, so keep output minimal on success.

set -uo pipefail

FILE="${1:-}"
[[ -z "$FILE" ]] && exit 0
[[ ! -f "$FILE" ]] && exit 0

case "$FILE" in
  # TypeScript — typecheck single file
  # *.ts|*.tsx)
  #   npx tsc --noEmit "$FILE" 2>&1 || exit 1
  #   ;;

  # JavaScript — lint single file
  # *.js|*.jsx|*.mjs|*.cjs)
  #   npx eslint --no-error-on-unmatched-pattern "$FILE" 2>&1 || exit 1
  #   ;;

  # Python — lint with ruff (fast) or flake8
  # *.py)
  #   ruff check "$FILE" 2>&1 || exit 1
  #   ;;

  # Go — vet the containing package
  # *.go)
  #   go vet "./$(dirname "$FILE")/..." 2>&1 || exit 1
  #   ;;

  # Rust — check (fast; no codegen)
  # *.rs)
  #   cargo check --quiet 2>&1 || exit 1
  #   ;;
esac

exit 0
