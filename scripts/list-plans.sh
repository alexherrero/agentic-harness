#!/usr/bin/env bash
# list-plans.sh — cross-repo "show me all in-flight plans" surface.
#
# Walks `<vault>/projects/*/_harness/PLAN.md` (and legacy
# `personal-projects/*/_harness/` if vault rename hasn't run yet),
# parses each plan's title + Status + last-update mtime, and prints a
# one-row-per-project summary table.
#
# Built as part of plan #20 task 10 — surfaced as a watchlist item
# during the V4 #26 design conversation: "Cross-repo 'show me all
# in-flight plans' UX becomes trivial once state is centralized."
#
# Usage:
#   bash agentm/scripts/list-plans.sh [OPTIONS]
#
# Options:
#   --vault-path <path>   Override vault root. Default: $MEMORY_VAULT_PATH env.
#   --all                 Show plans with Status: done too (default: only
#                         planning + in-progress + (no-status)).
#   --help, -h            Print this help and exit.

set -euo pipefail

# ── argument parsing ──────────────────────────────────────────────────────
VAULT_PATH="${MEMORY_VAULT_PATH:-}"
SHOW_ALL=0

print_help() {
    sed -n '/^# list-plans.sh/,/^[^#]/p' "$0" | sed 's|^# \?||' | sed '$d'
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --vault-path)
            VAULT_PATH="${2:-}"
            [[ -z "$VAULT_PATH" ]] && { echo "--vault-path requires a value" >&2; exit 2; }
            shift 2
            ;;
        --all) SHOW_ALL=1; shift ;;
        --help|-h) print_help; exit 0 ;;
        *) echo "Unknown option: $1" >&2; echo "" >&2; print_help >&2; exit 2 ;;
    esac
done

# ── vault resolution ──────────────────────────────────────────────────────
if [[ -z "$VAULT_PATH" ]]; then
    echo "Error: vault path not provided. Set MEMORY_VAULT_PATH or pass --vault-path." >&2
    exit 1
fi
if [[ ! -d "$VAULT_PATH" ]]; then
    echo "Error: vault path is not a directory: $VAULT_PATH" >&2
    exit 1
fi
VAULT_PATH="$(cd "$VAULT_PATH" && pwd)"

# Resolve projects dir (post-V4 #26 `projects/` preferred; legacy fallback).
if [[ -d "$VAULT_PATH/projects" ]]; then
    PROJECTS_DIR="$VAULT_PATH/projects"
elif [[ -d "$VAULT_PATH/personal-projects" ]]; then
    PROJECTS_DIR="$VAULT_PATH/personal-projects"
else
    echo "Error: no projects/ or personal-projects/ dir found under $VAULT_PATH" >&2
    exit 1
fi

# ── parse + render via Python (deterministic + portable) ──────────────────
python3 - "$PROJECTS_DIR" "$SHOW_ALL" <<'PY'
import sys, re
from pathlib import Path
from datetime import datetime

projects_dir = Path(sys.argv[1])
show_all = sys.argv[2] == "1"

rows = []
for project_dir in sorted(projects_dir.iterdir()):
    if not project_dir.is_dir():
        continue
    plan = project_dir / "_harness" / "PLAN.md"
    slug = project_dir.name
    if not plan.is_file():
        rows.append({"slug": slug, "title": "(no in-flight plan)", "status": "-", "updated": "-"})
        continue
    try:
        text = plan.read_text(encoding="utf-8")
    except OSError:
        rows.append({"slug": slug, "title": "(unreadable)", "status": "?", "updated": "?"})
        continue
    # Title: first `# Plan:` line, stripped.
    title = "(no title)"
    for line in text.splitlines()[:10]:
        m = re.match(r"^# Plan:\s*(.+)$", line)
        if m:
            title = m.group(1).strip()
            break
    # Status: first `**Status:** <word>` line.
    status = "?"
    for line in text.splitlines()[:30]:
        m = re.match(r"^\*\*Status:\*\*\s*(.+)$", line)
        if m:
            status = m.group(1).strip().split()[0].lower()
            break
    # mtime → date.
    updated = datetime.fromtimestamp(plan.stat().st_mtime).strftime("%Y-%m-%d")
    rows.append({"slug": slug, "title": title, "status": status, "updated": updated})

# Filter by status unless --all.
if not show_all:
    rows = [r for r in rows if r["status"] in ("planning", "in-progress", "?", "-")]

if not rows:
    print("(no in-flight plans across vault projects)")
    sys.exit(0)

# Render table.
max_slug = max(len(r["slug"]) for r in rows)
max_title = max(len(r["title"]) for r in rows)
max_status = max(len(r["status"]) for r in rows)

# Cap title width for readability.
title_width = min(max_title, 80)

header = f"{'PROJECT':<{max_slug}}  {'PLAN':<{title_width}}  {'STATUS':<{max_status}}  UPDATED"
print(header)
print("-" * len(header))
for r in rows:
    title_trimmed = r["title"][:title_width]
    print(f"{r['slug']:<{max_slug}}  {title_trimmed:<{title_width}}  {r['status']:<{max_status}}  {r['updated']}")
PY
