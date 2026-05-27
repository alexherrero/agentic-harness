#!/usr/bin/env python3
# migrate.py — /diataxis migrate (plan #13 part 4 task 1).
#
# Ports the harness's `migrate-to-diataxis` predecessor (one-shot legacy
# wiki → Diátaxis four-mode migration). Preview-first, deterministic
# classification by heading shape per ADR 0004, `git mv` for blame
# preservation, mode-mixed pages flagged for human split (delegates to
# `/diataxis repair` from part 3), link rewrites across all wiki/**/*.md,
# single-commit safety net via leaving migration staged-but-not-committed
# (operator stages + commits manually after reviewing diff — same
# convention as predecessor).
#
# Preconditions (matches predecessor):
#   1. Working tree clean (git status --porcelain empty).
#   2. wiki/ dir exists at repo root.
#   3. wiki/.diataxis marker does NOT exist (else: already migrated).
#   4. At least one legacy mode-dir exists: development/operational/
#      design/architecture.
#
# Classification rules (matches predecessor's table verbatim):
#   - ADR: H1 matches `^# ADR \d{4}:` → explanation/decisions/<basename>.
#   - Status page: body has `> [!NOTE]` block with `**Status:**` + `**Plan:**`
#     → explanation/<basename>.
#   - How-to: `## Steps` H2 with numbered list OR ≥3 numbered imperative
#     steps in first 40 lines, AND no `## Rationale|Why|Background|Context`.
#   - Tutorial: `## Step N —` heading AND `## What you learned` AND `## Next`.
#   - Reference: `## ⚡ Quick Reference` or `## Quick Reference` in first
#     20 lines OR ≥60% table lines.
#   - Explanation (default): anything else.
#   - Mode-mixed (flag for human split): meets ≥2 of {how-to, reference,
#     explanation} with competing strength.

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

# Force UTF-8 stdout so Unicode in the preview report (e.g. `→` arrow in
# the MOVES section) doesn't crash on Windows Python's default cp1252
# encoding. Python 3.7+ supports reconfigure; toolkit minimum is 3.9+.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


# Legacy audience-based dirs (predecessor convention).
_LEGACY_DIRS = ("development", "operational", "design", "architecture")

# Diátaxis four-mode dirs (matches ADR 0004 + classify.py convention —
# only tutorials is plural).
_MODE_DIRS = {
    "tutorial": "tutorials",
    "how-to": "how-to",
    "reference": "reference",
    "explanation": "explanation",
}


# ── Classification (deterministic; matches predecessor's table) ────────────


_ADR_HEADING_RE = re.compile(r"^#\s+ADR\s+\d{4}:", re.IGNORECASE)
_STATUS_NOTE_BLOCK_RE = re.compile(r">\s*\[!NOTE\]")
_STATUS_FIELD_RE = re.compile(r"\*\*Status:\*\*")
_PLAN_FIELD_RE = re.compile(r"\*\*Plan:\*\*")
_HOWTO_STEPS_RE = re.compile(r"^##\s+Steps\s*$", re.IGNORECASE)
_HOWTO_NUMBERED_STEP_RE = re.compile(r"^\d+\.\s+\S")
_HOWTO_FORBIDDEN_RE = re.compile(
    r"^##\s+(Rationale|Why|Background|Context)\s*$", re.IGNORECASE
)
_TUTORIAL_STEP_RE = re.compile(r"^##\s+Step\s+\d+\s*[—\-:]", re.IGNORECASE)
_TUTORIAL_LEARNED_RE = re.compile(r"^##\s+What\s+you\s+learned\s*$", re.IGNORECASE)
_TUTORIAL_NEXT_RE = re.compile(r"^##\s+Next\s*$", re.IGNORECASE)
_REFERENCE_QUICKREF_RE = re.compile(
    r"^##\s+⚡?\s*Quick\s+Reference\s*$", re.IGNORECASE
)
_REFERENCE_TABLE_LINE_RE = re.compile(r"^\s*\|")

_STRUCTURAL_FILES = {"Home.md", "_Sidebar.md", "README.md", ".diataxis"}


@dataclass
class Page:
    old_path: Path
    new_path: Path | None = None      # None when flagged for human split
    target_mode: str | None = None    # tutorial / how-to / reference / explanation
    mixed_modes: list[str] = field(default_factory=list)  # populated on human-split flag
    rationale: str = ""


def _read_lines(p: Path) -> list[str]:
    try:
        return p.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def _is_adr(p: Path, lines: list[str]) -> bool:
    if not lines:
        return False
    # H1-shape OR path-shape per predecessor.
    if _ADR_HEADING_RE.match(lines[0]):
        return True
    if "decisions" in p.parts and re.match(r"\d{4}-.*\.md$", p.name):
        return True
    return False


def _is_status_page(lines: list[str]) -> bool:
    # NOTE-block within first 25 lines containing Status: + Plan:.
    text_window = "\n".join(lines[:25])
    return bool(
        _STATUS_NOTE_BLOCK_RE.search(text_window)
        and _STATUS_FIELD_RE.search(text_window)
        and _PLAN_FIELD_RE.search(text_window)
    )


def _looks_howto(lines: list[str]) -> bool:
    """Pure how-to: has primary how-to signal AND no forbidden sections."""
    has_steps_section = any(_HOWTO_STEPS_RE.match(l) for l in lines)
    numbered_in_first40 = sum(
        1 for l in lines[:40] if _HOWTO_NUMBERED_STEP_RE.match(l.strip())
    )
    has_forbidden = any(_HOWTO_FORBIDDEN_RE.match(l) for l in lines)
    primary_signal = has_steps_section or numbered_in_first40 >= 3
    return primary_signal and not has_forbidden


def _has_howto_signal_with_forbidden(lines: list[str]) -> bool:
    """How-to-shaped page with explanation-style forbidden sections.

    Per predecessor's table: a how-to with `## Rationale` H2 is the
    canonical mode-mixed example. This catches it: the primary how-to
    signal fires AND a forbidden section also fires — both signals
    real, competing strength → mode-mixed.
    """
    has_steps_section = any(_HOWTO_STEPS_RE.match(l) for l in lines)
    numbered_in_first40 = sum(
        1 for l in lines[:40] if _HOWTO_NUMBERED_STEP_RE.match(l.strip())
    )
    has_forbidden = any(_HOWTO_FORBIDDEN_RE.match(l) for l in lines)
    primary_signal = has_steps_section or numbered_in_first40 >= 3
    return primary_signal and has_forbidden


def _looks_tutorial(lines: list[str]) -> bool:
    has_step = any(_TUTORIAL_STEP_RE.match(l) for l in lines)
    has_learned = any(_TUTORIAL_LEARNED_RE.match(l) for l in lines)
    has_next = any(_TUTORIAL_NEXT_RE.match(l) for l in lines)
    return has_step and has_learned and has_next


def _looks_reference(lines: list[str]) -> bool:
    quickref_early = any(_REFERENCE_QUICKREF_RE.match(l) for l in lines[:20])
    if quickref_early:
        return True
    non_empty = [l for l in lines if l.strip()]
    if not non_empty:
        return False
    table_ratio = sum(1 for l in non_empty if _REFERENCE_TABLE_LINE_RE.match(l)) / len(non_empty)
    return table_ratio >= 0.6


def _looks_explanation(lines: list[str]) -> bool:
    # Explanation is the default; this returns True if at least some prose
    # signal is present (not strict — predecessor uses it as fallback).
    text = "\n".join(lines)
    if "## Rationale" in text or "## Why" in text or "## Background" in text or "## Context" in text:
        return True
    # Pages with substantial prose + few tables qualify as explanation-shaped.
    non_empty = [l for l in lines if l.strip()]
    if not non_empty:
        return False
    table_lines = sum(1 for l in non_empty if _REFERENCE_TABLE_LINE_RE.match(l))
    return (table_lines / len(non_empty)) < 0.4


def classify_for_migration(p: Path) -> tuple[str | None, list[str], str]:
    """Returns (target_mode, mixed_modes_if_human_split, rationale).

    target_mode is None if human-split flagged. mixed_modes lists the
    modes that competed for human-split. rationale is one line.
    """
    lines = _read_lines(p)
    # Rule 1: ADR
    if _is_adr(p, lines):
        return "explanation", [], "ADR (H1 matches ADR pattern or path under decisions/)"
    # Rule 2: Status page
    if _is_status_page(lines):
        return "explanation", [], "Status page (NOTE block with **Status:** + **Plan:**)"
    # Run mode-shape detectors.
    howto = _looks_howto(lines)
    howto_mixed = _has_howto_signal_with_forbidden(lines)
    tutorial = _looks_tutorial(lines)
    reference = _looks_reference(lines)
    explanation = _looks_explanation(lines)
    if tutorial:
        # Tutorial is a strong + rare signal; doesn't compete — it wins.
        return "tutorial", [], "Tutorial shape (## Step N + ## What you learned + ## Next)"
    # Mode-mixed checks (predecessor table; canonical example: how-to with
    # ## Rationale H2).
    if howto_mixed:
        return None, ["how-to", "explanation"], "Mode-mixed: how-to signals (## Steps or numbered steps) + explanation forbidden section (## Rationale/Why/Background/Context)"
    # ≥2 of {how-to, reference, explanation} with competing strength.
    competing = []
    if howto:
        competing.append("how-to")
    if reference:
        competing.append("reference")
    if explanation:
        competing.append("explanation")
    if len(competing) >= 2:
        return None, competing, f"Mode-mixed: signals fired for {', '.join(competing)}"
    if howto:
        return "how-to", [], "How-to (## Steps section OR ≥3 numbered imperative steps; no Rationale/Why/Background/Context)"
    if reference:
        return "reference", [], "Reference (## Quick Reference or ≥60% table lines)"
    return "explanation", [], "Explanation (default; no strong other-mode signals)"


# ── Filesystem operations ──────────────────────────────────────────────────


def _has_clean_working_tree() -> bool:
    """git status --porcelain → empty (clean tree)."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, timeout=10,
        )
    except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
        return False
    return result.returncode == 0 and not result.stdout.strip()


def _walk_wiki(wiki_root: Path) -> list[Path]:
    """Return every .md under wiki/ excluding structural files."""
    out: list[Path] = []
    if not wiki_root.exists():
        return out
    for p in wiki_root.rglob("*.md"):
        if not p.is_file():
            continue
        if p.name in _STRUCTURAL_FILES:
            continue
        out.append(p)
    return sorted(out)


def _compute_new_path(p: Path, wiki_root: Path, target_mode: str) -> Path:
    """Compute new path for a page given target mode. Preserves basename;
    flattens out the old subdir."""
    mode_dir_name = _MODE_DIRS[target_mode]
    # ADRs stay under explanation/decisions/ subdir.
    if target_mode == "explanation" and (
        _ADR_HEADING_RE.match("".join(_read_lines(p)[:1]) or "")
        or "decisions" in p.parts
    ):
        return wiki_root / "explanation" / "decisions" / p.name
    return wiki_root / mode_dir_name / p.name


# ── Top-level orchestration ────────────────────────────────────────────────


def plan_migration(wiki_root: Path) -> list[Page]:
    """Walk wiki + classify + compute new paths. Returns list of Page."""
    pages: list[Page] = []
    for p in _walk_wiki(wiki_root):
        target_mode, mixed, rationale = classify_for_migration(p)
        page = Page(old_path=p, rationale=rationale)
        if target_mode is None:
            page.mixed_modes = mixed
            page.new_path = None
        else:
            page.target_mode = target_mode
            page.new_path = _compute_new_path(p, wiki_root, target_mode)
        pages.append(page)
    return pages


def render_preview(pages: list[Page], wiki_root: Path) -> str:
    """Render the preview report. Returns multiline string."""
    moves = [p for p in pages if p.new_path is not None and p.new_path != p.old_path]
    flagged = [p for p in pages if p.new_path is None]
    lines = ["migrate-to-diataxis: preview", ""]
    lines.append(f"MOVES ({len(moves)} pages):")
    for m in moves:
        lines.append(f"  {m.old_path.relative_to(wiki_root.parent)} → {m.new_path.relative_to(wiki_root.parent)}")
    lines.append("")
    lines.append(f"NEEDS HUMAN SPLIT ({len(flagged)} pages):")
    for f in flagged:
        lines.append(f"  {f.old_path.relative_to(wiki_root.parent)}")
        lines.append(f"    — {f.rationale}")
        lines.append(f"    — Suggested split: split into one page per mode in {{{', '.join(f.mixed_modes)}}}")
    lines.append("")
    lines.append("POST-MIGRATION:")
    lines.append("  - wiki/.diataxis marker will be created (enables strict-mode check-wiki lint).")
    lines.append("  - wiki/.diataxis-conventions.md will be auto-seeded with detected conventions.")
    lines.append("  - git log --follow on each moved page will show blame preserved.")
    return "\n".join(lines)


def _find_repo_root(start: Path) -> Path | None:
    """Walk up from start looking for a .git directory; return repo root or None."""
    cur = start.resolve()
    while cur != cur.parent:
        if (cur / ".git").exists():
            return cur
        cur = cur.parent
    return None


def execute_migration(pages: list[Page], wiki_root: Path, *, dry_run: bool = False) -> dict:
    """Execute the migration: git mv each page; create marker + conventions file.

    Operator stages + commits manually after reviewing diff. NEVER commits.
    """
    stats = {"moved": 0, "flagged": 0, "errors": 0, "marker_created": False, "conventions_seeded": False}
    # Find repo root so we can invoke `git -C <repo>` correctly regardless
    # of the caller's cwd. Falls back to wiki_root's parent if no .git
    # found (smoke tests + non-git scenarios).
    repo_root = _find_repo_root(wiki_root)
    git_base_args = ["git"]
    if repo_root is not None:
        git_base_args.extend(["-C", str(repo_root)])
    for p in pages:
        if p.new_path is None:
            stats["flagged"] += 1
            continue
        if p.new_path == p.old_path:
            continue  # no-op
        if dry_run:
            stats["moved"] += 1
            continue
        # Ensure target dir exists.
        p.new_path.parent.mkdir(parents=True, exist_ok=True)
        # git mv preserves blame; subprocess invocation with -C repo_root
        # so cwd-independence is guaranteed.
        try:
            subprocess.run(
                git_base_args + ["mv", str(p.old_path), str(p.new_path)],
                check=True, capture_output=True, text=True, timeout=30,
            )
            stats["moved"] += 1
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
            stats["errors"] += 1
            print(f"[migrate] git mv failed for {p.old_path}: {e}", file=sys.stderr)
    # Create marker.
    marker = wiki_root / ".diataxis"
    if not dry_run:
        marker.write_bytes(b"")
        stats["marker_created"] = True
        # Auto-seed conventions file (operator edits over time).
        conv_path = wiki_root / ".diataxis-conventions.md"
        conv_content = """# Diátaxis conventions for this repo

This file captures per-repo overrides + detected conventions discovered
during the initial `/diataxis migrate` run. The skill reads this file
on `/diataxis check`, `/diataxis author`, `/diataxis classify` invocations
when present in `<repo>/wiki/.diataxis-conventions.md`. Operator edits
over time as conventions evolve.

## Filename style

CamelCase-With-Dashes (matches the operator's canonical wikis).

## Mode-mixed split preferences

When a page is mode-mixed, prefer splitting in this order:
1. how-to + reference (extract lookup tables to reference; keep task in how-to)
2. tutorial + how-to (extract learning to tutorial; keep deep task in how-to)
3. how-to + explanation (extract rationale to explanation; keep task in how-to)

## Cross-reference policy

Wiki-internal links use page basenames only (no directory prefix).
External GitHub repo links use full URLs.

## See also

- [agentm ADR 0004 — Diátaxis Documentation Spec](../../../agentm/wiki/explanation/decisions/0004-diataxis-documentation-spec.md) — canonical spec
- [crickets diataxis-author design doc](../wiki/explanation/designs/diataxis-author.md) — skill design
"""
        conv_path.write_bytes(conv_content.encode("utf-8"))
        stats["conventions_seeded"] = True
    return stats


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="diataxis-migrate",
        description=(
            "One-shot legacy → Diátaxis four-mode migration. Subsumes the "
            "harness's `migrate-to-diataxis` predecessor. Preview-first; "
            "deterministic classification per ADR 0004; `git mv` for blame "
            "preservation; mode-mixed pages flagged for human split."
        ),
    )
    parser.add_argument("--wiki-root", default=None, help="wiki root (default: ./wiki)")
    parser.add_argument(
        "--preview", action="store_true",
        help="emit preview only; never touch filesystem",
    )
    parser.add_argument(
        "--execute", action="store_true",
        help="apply migration (default with no flag: preview + interactive prompt)",
    )
    parser.add_argument(
        "--yes", action="store_true",
        help="skip Apply? [y/N] prompt; preview still prints",
    )
    parser.add_argument(
        "--skip-precheck", action="store_true",
        help="skip clean-tree + already-migrated preconditions (testing fixture only)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    if args.wiki_root:
        wiki_root = Path(args.wiki_root).expanduser()
    else:
        candidate = Path.cwd() / "wiki"
        if not candidate.is_dir():
            print("ERROR: wiki/ not found at cwd; pass --wiki-root", file=sys.stderr)
            return 1
        wiki_root = candidate
    if not wiki_root.exists() or not wiki_root.is_dir():
        print(f"ERROR: wiki root not found or not a directory: {wiki_root}", file=sys.stderr)
        return 1
    # Preconditions (skip in testing).
    if not args.skip_precheck:
        if not _has_clean_working_tree():
            print("ERROR: working tree not clean (git status --porcelain non-empty); commit or stash first", file=sys.stderr)
            return 1
        if (wiki_root / ".diataxis").exists():
            print(f"ERROR: already migrated ({wiki_root / '.diataxis'} exists); remove to re-run", file=sys.stderr)
            return 1
        has_legacy_dir = any((wiki_root / d).is_dir() for d in _LEGACY_DIRS)
        if not has_legacy_dir:
            print(
                f"ERROR: no legacy mode-dirs found ({', '.join(_LEGACY_DIRS)}); "
                f"nothing to migrate. If this is a fresh project, run /diataxis author instead.",
                file=sys.stderr,
            )
            return 1
    # Plan + preview.
    pages = plan_migration(wiki_root)
    preview = render_preview(pages, wiki_root)
    print(preview)
    if args.preview:
        return 0
    if not args.execute and not args.yes:
        # Default: print preview + exit 0 with hint (no interactive prompt
        # in v1; operator re-runs with --execute or --yes to apply).
        print("\nRun with --execute (or --yes) to apply.", file=sys.stderr)
        return 0
    # Execute.
    stats = execute_migration(pages, wiki_root, dry_run=False)
    print(f"\nmigrate-to-diataxis: applied")
    print(f"  moved:    {stats['moved']} pages")
    print(f"  flagged:  {stats['flagged']} pages for human split")
    print(f"  errors:   {stats['errors']}")
    print(f"  marker:   {'created' if stats['marker_created'] else 'NOT created'}")
    print(f"  conventions: {'seeded' if stats['conventions_seeded'] else 'NOT seeded'}")
    print("\nNEXT:")
    print("  1. git status — review the diff.")
    print("  2. Spot-check git log --follow wiki/<new-path>/<Some-Page>.md to confirm blame preserved.")
    print(f"  3. Split the {stats['flagged']} flagged pages by hand via /diataxis repair.")
    print("  4. Run check-wiki.py --strict on the wiki/ root.")
    print("  5. Commit. Suggested message: refactor(wiki): migrate to Diátaxis four-mode layout (ADR 0004)")
    return 0 if stats["errors"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
