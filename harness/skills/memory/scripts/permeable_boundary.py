#!/usr/bin/env python3
# permeable_boundary.py — shared helper for the A3 permeable-write-boundary.
#
# Per locked design call A3 (from the parent MemoryVault design doc): the
# agent reads anywhere in the user vault but writes to MemoryVault/ by
# default. Writes OUTSIDE MemoryVault/ (e.g. to ~/Obsidian/Ideas.md) require
# either:
#   (a) **explicit user request** — operator typed `/memory idea` or similar
#       with full intent. Writes proceed without confirmation.
#   (b) **agent-initiated + user-confirmed** — reflection sidecar surfaced
#       an idea candidate, proposes the write, user confirms before it lands.
#
# Never silent writes outside MemoryVault/.
#
# This module is the SHARED PRIMITIVE for path (b). Callers invoke
# `confirm_write_outside_memoryvault(target_path, content_preview, rationale)`
# and only proceed with the write if the return value is True. Built once,
# reusable for every future cross-boundary writer (idea ledger ships first;
# discovery-mining + seed-pass + future skills will reuse this contract).
#
# Plan #7a part 4 task 1 (this commit) ships the helper + tests. Tasks 2-5
# wire it into the Ideas.md surface-tier writer + incubator deep-research
# writer + `/memory promote idea` + how-to documentation.
#
# Mode resolution (consistent with reflect.py's tri-modal routing):
#   1. Explicit `mode` arg → trumps everything.
#   2. MEMORY_REVIEW_MODE env var: 'silent' | 'interactive' | 'auto'.
#   3. Default: 'interactive' (the safer default — never auto-write outside
#      MemoryVault without user assent).
#
# Behavior per mode:
#   - 'silent': return True (operator pre-confirmed; e.g. set
#     MEMORY_REVIEW_MODE=silent in a long-running batch).
#   - 'interactive': render a prompt to stdout (target + preview + rationale)
#     + read y/n from stdin. Default action is NO (safer — empty input or
#     unknown input means deny).
#   - 'auto': **deny** (return False). The 'auto' mode is for non-TTY hook
#     contexts where we can't prompt; per the A3 design call, never silently
#     write outside MemoryVault, so deny rather than approve.
#   - Interactive mode with non-TTY stdin → fall back to 'auto' (deny). Same
#     reasoning — never silently approve a cross-boundary write.

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

MODE_SILENT = "silent"
MODE_INTERACTIVE = "interactive"
MODE_AUTO = "auto"
_VALID_MODES = {MODE_SILENT, MODE_INTERACTIVE, MODE_AUTO}

# Preview length cap for the prompt. Content previews are truncated to this
# many chars to keep prompts scannable; full content is what the caller will
# write if confirmed. Tune from real use.
_PREVIEW_CHAR_CAP = 400


def _resolve_mode(arg_mode: str | None) -> str:
    """Resolve mode: arg → env → default ('interactive')."""
    if arg_mode is not None:
        if arg_mode not in _VALID_MODES:
            raise ValueError(
                f"unknown mode {arg_mode!r}: expected one of {_VALID_MODES}"
            )
        return arg_mode
    env_mode = os.environ.get("MEMORY_REVIEW_MODE", "").strip().lower()
    if env_mode in _VALID_MODES:
        return env_mode
    return MODE_INTERACTIVE


def _truncate_preview(content: str, cap: int = _PREVIEW_CHAR_CAP) -> str:
    """Truncate content to first `cap` chars; append ellipsis if truncated."""
    if not content:
        return "(empty content)"
    content = content.replace("\r", "")
    if len(content) <= cap:
        return content
    return content[:cap].rstrip() + f"\n... ({len(content) - cap} more chars truncated)"


def confirm_write_outside_memoryvault(
    target_path: Path | str,
    content_preview: str,
    rationale: str,
    *,
    mode: str | None = None,
    stdin=None,
    stdout=None,
) -> bool:
    """Ask the user to confirm a write to a path OUTSIDE MemoryVault/.

    This is the shared primitive for the A3 permeable-write-boundary
    locked design call. Callers must invoke this BEFORE attempting any
    write to a path outside the MemoryVault root + only proceed if the
    return value is True.

    Args:
        target_path: absolute path that would be written (e.g.
            `~/Obsidian/Ideas.md`). Path display in the prompt is
            shortened via `~` if it's under $HOME.
        content_preview: what would be written. Truncated to first 400
            chars in the prompt; the caller still writes the full content
            on confirmation.
        rationale: 1-2 sentence explanation of WHY this write is being
            proposed. Shown verbatim in the prompt so the operator can
            decide intelligently.
        mode: explicit override; resolves from arg → MEMORY_REVIEW_MODE
            env → 'interactive' default.
        stdin: stream to read user response from (defaults to sys.stdin).
        stdout: stream to render prompt to (defaults to sys.stdout).

    Returns:
        True if the caller may proceed with the write; False otherwise.

    Never raises; never writes anything itself. Pure I/O on stdin+stdout.
    """
    resolved_mode = _resolve_mode(mode)
    stdin = stdin if stdin is not None else sys.stdin
    stdout = stdout if stdout is not None else sys.stdout

    if resolved_mode == MODE_SILENT:
        return True

    if resolved_mode == MODE_AUTO:
        # Non-prompt context (e.g. hook); per A3 never silently write
        # outside MemoryVault.
        return False

    # Interactive mode. If stdin isn't a TTY, treat as auto (deny).
    is_tty = False
    try:
        is_tty = stdin.isatty()
    except (AttributeError, OSError, ValueError):
        is_tty = False
    if not is_tty:
        return False

    # Render the prompt.
    target_path = Path(target_path)
    display_path = str(target_path)
    home = str(Path.home())
    if display_path.startswith(home):
        display_path = "~" + display_path[len(home):]

    preview = _truncate_preview(content_preview)

    print("", file=stdout)
    print("─" * 72, file=stdout)
    print("MemoryVault permeable-boundary confirmation (A3)", file=stdout)
    print("─" * 72, file=stdout)
    print(f"  Target:    {display_path}", file=stdout)
    print(f"  Rationale: {rationale}", file=stdout)
    print("", file=stdout)
    print("  Content preview:", file=stdout)
    for line in preview.split("\n"):
        print(f"    {line}", file=stdout)
    print("─" * 72, file=stdout)
    print(
        "Approve write to this path OUTSIDE MemoryVault? [y/N]: ",
        end="", file=stdout, flush=True,
    )
    try:
        answer = stdin.readline()
    except (EOFError, KeyboardInterrupt):
        return False
    answer = (answer or "").strip().lower()
    return answer in {"y", "yes"}


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="memory-permeable-boundary",
        description=(
            "A3 permeable-write-boundary confirmation helper. Operator-debug "
            "CLI: invoke directly to test prompt behavior in different "
            "modes. Production callers use confirm_write_outside_memoryvault() "
            "as a Python API, not via this CLI."
        ),
    )
    parser.add_argument(
        "target_path",
        help="absolute path that would be written (e.g. ~/Obsidian/Ideas.md)",
    )
    parser.add_argument(
        "--content-preview", default="",
        help="content that would be written (truncated to 400 chars in prompt)",
    )
    parser.add_argument(
        "--rationale", default="(no rationale provided)",
        help="why this write is being proposed",
    )
    parser.add_argument(
        "--mode", choices=sorted(_VALID_MODES), default=None,
        help="override mode resolution (default: MEMORY_REVIEW_MODE env or 'interactive')",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    try:
        approved = confirm_write_outside_memoryvault(
            target_path=args.target_path,
            content_preview=args.content_preview,
            rationale=args.rationale,
            mode=args.mode,
        )
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    # Exit 0 = approved (proceed with write); Exit 1 = denied (caller halts).
    # JSON-Lines on stdout so scripts can also parse the decision.
    import json
    print(json.dumps({"approved": approved, "target": args.target_path}))
    return 0 if approved else 1


if __name__ == "__main__":
    raise SystemExit(main())
