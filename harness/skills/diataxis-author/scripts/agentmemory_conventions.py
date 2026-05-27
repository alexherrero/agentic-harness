#!/usr/bin/env python3
# agentmemory_conventions.py — AgentMemory read + write integration
# for the diataxis-author skill (plan #13 part 5).
#
# Read-side: globs `<vault>/personal-private/_always-load/diataxis-*.md`
# at invocation; parses simple `key: value` lines from each entry's
# frontmatter + body to build a conventions dict. Per-repo override at
# `<repo>/wiki/.diataxis-conventions.md` takes precedence when present.
#
# Write-side: `confirm_save_convention()` routes through the existing
# `permeable_boundary` helper (shipped in plan #7a part 4) for operator
# confirmation on cross-boundary writes. Same A3 contract as
# `ideas_surface.py`'s Ideas.md writer — never silent; respects
# `MEMORY_REVIEW_MODE=silent` env var.
#
# Fallback chain (lookup order):
#   1. Per-repo `.diataxis-conventions.md` (when wiki_root provided + file present)
#   2. Vault `_always-load/diataxis-*.md` (when MEMORY_VAULT_PATH or
#      --vault-path resolves)
#   3. ADR 0004 defaults (hardcoded fallbacks).
#
# Stdlib-only; matches the established convention.

from __future__ import annotations

import json
import os
import re
import sys
from datetime import date
from pathlib import Path


# Hardcoded ADR 0004 defaults — used when no operator entries exist anywhere.
_DEFAULTS = {
    "filename_style": "CamelCase-With-Dashes",
    "mode_mixed_default_split": "how-to + reference",
    "confidence_threshold": 0.7,
}

# Always-load entry slug prefix this skill writes / reads.
_ALWAYS_LOAD_PREFIX = "diataxis-"


def _resolve_vault_path(arg_path: str | None = None) -> Path | None:
    """Resolve vault path: arg → MEMORY_VAULT_PATH env → None (no vault)."""
    if arg_path:
        return Path(arg_path).expanduser()
    env_path = os.environ.get("MEMORY_VAULT_PATH", "").strip()
    if env_path:
        return Path(env_path).expanduser()
    return None


# Optional `**bold**` markdown wrapping around the key — both formats
# accepted so the same regex catches operator-curated entries (plain
# `Filename style: X`) and skill-written entries (`**Filename style**: X`).
_OPT_BOLD = r"(?:\*\*)?"


def _parse_conventions_text(text: str) -> dict:
    """Extract recognized convention keys from arbitrary markdown text.

    Recognizes (case-insensitive; with or without `**` bold wrapping;
    anywhere in the file — frontmatter or body):
      `Filename style: <value>` → `filename_style`
      `Confidence threshold: <number>` → `confidence_threshold`
      `Mode-mixed default split: <text>` → `mode_mixed_default_split`
    """
    out: dict = {}
    m = re.search(
        rf"^{_OPT_BOLD}Filename style{_OPT_BOLD}:\s*(\S.*?)\s*$",
        text, re.MULTILINE | re.IGNORECASE,
    )
    if m:
        out["filename_style"] = m.group(1).strip()
    m = re.search(
        rf"^{_OPT_BOLD}Confidence threshold{_OPT_BOLD}:\s*([\d.]+)\s*$",
        text, re.MULTILINE | re.IGNORECASE,
    )
    if m:
        try:
            out["confidence_threshold"] = float(m.group(1))
        except ValueError:
            pass
    m = re.search(
        rf"^{_OPT_BOLD}Mode-mixed default split{_OPT_BOLD}:\s*(.+)$",
        text, re.MULTILINE | re.IGNORECASE,
    )
    if m:
        out["mode_mixed_default_split"] = m.group(1).strip()
    return out


def _parse_per_repo_conventions(repo_conventions: Path) -> dict:
    if not repo_conventions.exists():
        return {}
    try:
        return _parse_conventions_text(repo_conventions.read_text(encoding="utf-8"))
    except OSError:
        return {}


def _parse_always_load_entry(entry_path: Path) -> dict:
    if not entry_path.exists():
        return {}
    try:
        return _parse_conventions_text(entry_path.read_text(encoding="utf-8"))
    except OSError:
        return {}


def load_conventions(
    *,
    wiki_root: Path | None = None,
    vault_path: Path | None = None,
) -> dict:
    """Build effective conventions dict via the fallback chain.

    Priority (highest to lowest):
      1. Per-repo `<wiki_root>/.diataxis-conventions.md`
      2. Vault `<vault>/personal-private/_always-load/diataxis-*.md` (any entry)
      3. ADR 0004 hardcoded defaults
    """
    # Start with defaults.
    out = dict(_DEFAULTS)
    # Vault entries (apply all matching diataxis-* files; later files
    # overwrite earlier).
    if vault_path is None:
        vault_path = _resolve_vault_path()
    if vault_path:
        always_load_dir = vault_path / "personal-private" / "_always-load"
        if always_load_dir.exists():
            for entry in sorted(always_load_dir.glob(f"{_ALWAYS_LOAD_PREFIX}*.md")):
                out.update(_parse_always_load_entry(entry))
    # Per-repo override (highest priority).
    if wiki_root is not None:
        repo_conv = wiki_root / ".diataxis-conventions.md"
        if repo_conv.exists():
            out.update(_parse_per_repo_conventions(repo_conv))
    return out


def confirm_save_convention(
    key: str,
    new_value: str,
    *,
    vault_path: Path | None = None,
    mode: str | None = None,
    stdin=sys.stdin,
    stdout=sys.stdout,
) -> Path | None:
    """Offer to save a new convention to the operator's AgentMemory.

    Routes through the existing `permeable_boundary.confirm_write_outside_
    memoryvault()` helper for A3-boundary respect (writes to `_always-load/`
    are INSIDE the MemoryVault, so technically don't need cross-boundary
    confirmation — but we use a similar interactive-confirm pattern for
    consistency + to avoid surprise saves).

    Returns Path written on operator-approved save; None if declined or
    no vault resolved.
    """
    if vault_path is None:
        vault_path = _resolve_vault_path()
    if vault_path is None:
        return None
    if not vault_path.exists() or not vault_path.is_dir():
        return None
    # Compute target path.
    slug = re.sub(r"[^a-z0-9-]", "-", key.lower()).strip("-")
    target = vault_path / "personal-private" / "_always-load" / f"{_ALWAYS_LOAD_PREFIX}{slug}.md"
    # Mode resolution (matches MEMORY_REVIEW_MODE pattern from existing scripts).
    if mode is None:
        mode = os.environ.get("MEMORY_REVIEW_MODE", "interactive").strip().lower()
    # 'silent' mode bypasses confirmation; 'auto' denies non-TTY; 'interactive' prompts.
    if mode == "silent":
        approved = True
    elif mode == "auto":
        approved = stdin.isatty() if hasattr(stdin, "isatty") else False
        if not approved:
            print(
                f"[diataxis-conv] auto mode + non-TTY → denying save of {key!r}",
                file=sys.stderr,
            )
            return None
    else:  # interactive
        if not stdin.isatty() if hasattr(stdin, "isatty") else True:
            print(
                f"[diataxis-conv] interactive mode + non-TTY → defaulting to deny",
                file=sys.stderr,
            )
            return None
        print(f"Save convention '{key}: {new_value}' to AgentMemory? [y/N]", file=stdout)
        stdout.flush()
        try:
            response = stdin.readline().strip().lower()
        except (EOFError, KeyboardInterrupt):
            return None
        approved = response in ("y", "yes")
    if not approved:
        return None
    # Write the entry. Use save.save_entry if available (preferred — gives
    # us proper frontmatter shape); otherwise direct write.
    try:
        scripts_parent = Path(__file__).resolve().parent.parent.parent  # skills/
        memory_scripts = scripts_parent / "memory" / "scripts"
        if str(memory_scripts) not in sys.path:
            sys.path.insert(0, str(memory_scripts))
        import save  # type: ignore
        body = (
            f"# {key}\n\n"
            f"Operator convention captured from diataxis-author skill on {date.today().isoformat()}.\n\n"
            f"**{key.replace('_', ' ').capitalize()}**: {new_value}\n"
        )
        return save.save_entry(
            vault_path=vault_path,
            kind="convention",
            slug=f"{_ALWAYS_LOAD_PREFIX}{slug}",
            body=body,
            group="personal-private",
            always_load=True,
            tags=["diataxis", "convention", "auto-captured"],
        )
    except Exception as e:
        # Fallback to direct write if save.py unavailable or errors.
        print(f"[diataxis-conv] save.py path failed ({e}); falling back to direct write", file=sys.stderr)
        target.parent.mkdir(parents=True, exist_ok=True)
        today = date.today().isoformat()
        content = (
            "---\n"
            f"kind: convention\n"
            f"status: active\n"
            f"created: {today}\n"
            f"updated: {today}\n"
            "tags: [diataxis, convention, auto-captured]\n"
            "group: personal-private\n"
            f"slug: {_ALWAYS_LOAD_PREFIX}{slug}\n"
            "always_load: true\n"
            "---\n"
            "\n"
            f"# {key}\n\n"
            f"Operator convention captured from diataxis-author skill on {today}.\n\n"
            f"**{key.replace('_', ' ').capitalize()}**: {new_value}\n"
        )
        target.write_bytes(content.encode("utf-8"))
        return target


def main(argv: list[str] | None = None) -> int:
    """CLI entry: dump current conventions as JSON. Operator-debug surface."""
    import argparse
    parser = argparse.ArgumentParser(prog="diataxis-conventions")
    parser.add_argument("--wiki-root", default=None)
    parser.add_argument("--vault-path", default=None)
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    wiki_root = Path(args.wiki_root).expanduser() if args.wiki_root else None
    vault_path = Path(args.vault_path).expanduser() if args.vault_path else None
    conv = load_conventions(wiki_root=wiki_root, vault_path=vault_path)
    print(json.dumps(conv, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
