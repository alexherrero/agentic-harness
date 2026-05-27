#!/usr/bin/env python3
# author.py — /diataxis author <slug> live authoring guidance (plan #13 part 2 task 3).
#
# Invocation entry for `/diataxis author`. Steps:
#   1. Resolve mode (explicit --mode flag, or operator-input via stdin
#      prompt, or classify intent statement via classify.classify_text).
#   2. Load the corresponding template from templates/<mode>.md.
#   3. Apply filename style (--filename-style or default from AgentMemory
#      conventions or fall-through default 'CamelCase-With-Dashes').
#   4. Compute target path <wiki-root>/<mode>/<filename>.md.
#   5. Halt if target already exists (operator picks a different slug).
#   6. Write the template content to the target.
#   7. Emit operator-facing summary (path written + template fields to fill in).
#
# Stdlib-only. Filename style + mode default are operator-tunable via
# AgentMemory `_always-load/diataxis-*.md` (read-side wires in part 5;
# v1 uses constants).

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

# Templates ship alongside scripts/ at templates/<mode>.md.
_TEMPLATES_DIR = _SCRIPTS_DIR.parent / "templates"

_VALID_MODES = {"tutorial", "how-to", "reference", "explanation"}

# Per Diátaxis convention (matches harness's templates/wiki/ + check-wiki.py
# expectations): tutorials/ is plural, others are singular. Map mode names to
# their directory names here so author.py + classify.py share the convention.
_MODE_TO_DIR = {
    "tutorial": "tutorials",
    "how-to": "how-to",
    "reference": "reference",
    "explanation": "explanation",
}
_DEFAULT_FILENAME_STYLE = "CamelCase-With-Dashes"
_VALID_FILENAME_STYLES = {"CamelCase-With-Dashes", "snake_case", "kebab-case"}


def _resolve_wiki_root(arg_path: str | None) -> Path:
    """Resolve wiki root: arg → ./wiki → error."""
    if arg_path:
        return Path(arg_path).expanduser()
    candidate = Path.cwd() / "wiki"
    if candidate.is_dir():
        return candidate
    raise ValueError(
        "wiki root not found: pass --wiki-root or cd into a project with a wiki/ dir"
    )


def _apply_filename_style(slug: str, style: str) -> str:
    """Convert a slug to the chosen filename style. Returns base name (no extension)."""
    # Normalize input to lowercase words first.
    words = re.findall(r"[A-Za-z0-9]+", slug)
    if not words:
        return "Untitled"
    lower_words = [w.lower() for w in words]
    if style == "CamelCase-With-Dashes":
        return "-".join(w.capitalize() for w in lower_words)
    if style == "kebab-case":
        return "-".join(lower_words)
    if style == "snake_case":
        return "_".join(lower_words)
    raise ValueError(f"unknown filename style: {style}")


def author_page(
    slug: str,
    mode: str,
    *,
    wiki_root: Path,
    filename_style: str = _DEFAULT_FILENAME_STYLE,
    overwrite: bool = False,
) -> dict:
    """Emit a pre-filled template skeleton to <wiki-root>/<mode>/<filename>.md.

    Returns: {action, target, mode, template, filename_style}.
    Raises FileExistsError if target exists + overwrite=False.
    """
    if mode not in _VALID_MODES:
        raise ValueError(f"mode must be one of {sorted(_VALID_MODES)}; got {mode!r}")
    if filename_style not in _VALID_FILENAME_STYLES:
        raise ValueError(
            f"filename style must be one of {sorted(_VALID_FILENAME_STYLES)}; got {filename_style!r}"
        )
    if not wiki_root.exists() or not wiki_root.is_dir():
        raise FileNotFoundError(f"wiki root not found: {wiki_root}")
    template_path = _TEMPLATES_DIR / f"{mode}.md"
    if not template_path.exists():
        raise FileNotFoundError(f"template missing: {template_path}")
    base = _apply_filename_style(slug, filename_style)
    target = wiki_root / _MODE_TO_DIR[mode] / f"{base}.md"
    if target.exists() and not overwrite:
        raise FileExistsError(
            f"target already exists: {target}; pick a different slug or pass --overwrite"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    # Read template + emit verbatim (operator edits in their editor).
    # write_bytes for LF-only line endings (Windows portability — same
    # pattern as save.py / ideas_surface.py / adapt_skills.py).
    content = template_path.read_text(encoding="utf-8")
    target.write_bytes(content.encode("utf-8"))
    return {
        "action": "authored",
        "target": str(target),
        "mode": mode,
        "template": str(template_path),
        "filename_style": filename_style,
        "filename": f"{base}.md",
    }


def _resolve_filename_style(arg_style: str | None, wiki_root: Path) -> str:
    """Filename style resolution: explicit arg → AgentMemory conventions → default."""
    if arg_style:
        return arg_style
    # Try AgentMemory conventions (per-repo wiki overrides; then vault entries).
    try:
        import agentmemory_conventions  # type: ignore
        conv = agentmemory_conventions.load_conventions(wiki_root=wiki_root)
        style = conv.get("filename_style", _DEFAULT_FILENAME_STYLE)
        if style in _VALID_FILENAME_STYLES:
            return style
    except Exception:
        pass
    return _DEFAULT_FILENAME_STYLE


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="diataxis-author",
        description=(
            "Emit a pre-filled Diátaxis template skeleton to <wiki-root>/<mode>/"
            "<filename>.md. Operator picks mode + filename style; skill loads "
            "the template + writes the skeleton; operator edits in their editor. "
            "Skill doesn't write further content after the skeleton."
        ),
    )
    parser.add_argument("slug", help="page slug (e.g. 'Install foo into a project')")
    parser.add_argument(
        "--mode", choices=sorted(_VALID_MODES), default=None,
        help="Diátaxis mode (default: prompt or infer from --intent via classify.py)",
    )
    parser.add_argument(
        "--intent", default=None,
        help="one-sentence intent statement for classify.py to derive mode "
             "(used when --mode not provided)",
    )
    parser.add_argument(
        "--filename-style", default=None,
        choices=sorted(_VALID_FILENAME_STYLES),
        help=f"filename style (default: AgentMemory conventions → {_DEFAULT_FILENAME_STYLE})",
    )
    parser.add_argument(
        "--wiki-root", default=None,
        help="wiki root path (default: ./wiki)",
    )
    parser.add_argument(
        "--overwrite", action="store_true",
        help="overwrite existing target (default: refuse + ask operator to pick a different slug)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    try:
        wiki_root = _resolve_wiki_root(args.wiki_root)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    # Mode resolution: --mode > --intent (classify) > stdin prompt.
    mode = args.mode
    if not mode and args.intent:
        # Treat the intent string as a classification input; build a
        # minimal "page" with the intent as body and classify.
        import classify  # type: ignore
        c = classify.classify_text(args.intent)
        mode = c.mode
        # If the classifier thinks it's ambiguous, prompt operator.
        if c.needs_subagent:
            print(
                f"INFO: intent '{args.intent}' classified as {c.mode} with confidence "
                f"{c.confidence}; rationale: {c.rationale}",
                file=sys.stderr,
            )
            print(
                "Confidence below threshold; specify --mode explicitly to disambiguate.",
                file=sys.stderr,
            )
            return 1
    if not mode:
        print(
            "ERROR: --mode or --intent required (cannot infer Diátaxis mode without input)",
            file=sys.stderr,
        )
        return 1
    # Resolve filename style via AgentMemory conventions fallback if not
    # explicitly passed.
    resolved_style = _resolve_filename_style(args.filename_style, wiki_root)
    try:
        result = author_page(
            slug=args.slug,
            mode=mode,
            wiki_root=wiki_root,
            filename_style=resolved_style,
            overwrite=args.overwrite,
        )
    except (FileNotFoundError, FileExistsError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
