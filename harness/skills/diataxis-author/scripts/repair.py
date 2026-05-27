#!/usr/bin/env python3
# repair.py — /diataxis repair interactive fix-application (plan #13 part 3 task 2).
#
# Consumes findings from check.py + presents each to the operator with a
# suggested fix. Operator approves / edits / rejects per finding.
# Preview-first contract: NEVER writes to wiki/ without operator
# confirmation. Mode-mixed splits dispatch the `documenter` sub-agent
# (mechanical-write worker — first consumer of documenter-as-worker per
# the locked design call Q3).
#
# Repair actions per drift type:
#   - diataxis/stale-xref → suggest path rewrite OR remove reference
#     (interactive: operator picks).
#   - diataxis/template-drift → suggest move-to-mode-dir OR
#     rewrite-body-to-match-template (interactive).
#   - diataxis/mode-mixed → split into N pages (dispatches `documenter`
#     sub-agent for the actual writes; preview-first per split).
#   - diataxis/convention-drift → suggest rewrite to match operator
#     convention (v1: stub; full handling lands when convention-drift
#     heuristic in check.py becomes operational in part 5).
#
# Non-TTY stdin defaults all interactive prompts to skip (never silent
# action — matches `ideas_promote.py gc` + `watchlist_review.py review`
# contract).

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


_VALID_ACTIONS = {"apply", "edit", "reject", "skip"}


def _resolve_wiki_root(arg_path: str | None) -> Path:
    if arg_path:
        return Path(arg_path).expanduser()
    candidate = Path.cwd() / "wiki"
    if candidate.is_dir():
        return candidate
    raise ValueError("wiki root not found: pass --wiki-root or cd into a project with a wiki/")


def _load_findings(findings_path: Path | None, wiki_root: Path) -> list[dict]:
    """Load findings from a JSON file (output of check.py) OR run check.py inline."""
    if findings_path:
        if not findings_path.exists():
            raise FileNotFoundError(f"findings file not found: {findings_path}")
        data = json.loads(findings_path.read_text(encoding="utf-8"))
        return data.get("findings", [])
    # No --findings flag: run check.py inline (same wiki root).
    import check  # type: ignore
    report = check.run_check(wiki_root=wiki_root, strict=False, check_wiki_py=None)
    # Re-serialize as plain dicts for uniform handling.
    return [
        {
            "file": f.file,
            "rule": f.rule,
            "severity": f.severity,
            "msg": f.msg,
            "suggested_fix": f.suggested_fix,
        }
        for f in report.findings
    ]


def _present_finding(finding: dict, stdout=sys.stdout) -> None:
    """Print a finding + suggested fix to stdout."""
    print("─" * 72, file=stdout)
    print(f"  rule:         {finding['rule']}", file=stdout)
    print(f"  file:         {finding['file']}", file=stdout)
    print(f"  severity:     {finding['severity']}", file=stdout)
    print(f"  msg:          {finding['msg']}", file=stdout)
    if finding.get("suggested_fix"):
        print(f"  suggested:    {finding['suggested_fix']}", file=stdout)
    print("─" * 72, file=stdout)


def _prompt_action(stdin=sys.stdin, stdout=sys.stdout) -> str:
    """Display action prompt. Returns one of _VALID_ACTIONS."""
    print("Action: [a]pply / [e]dit / [r]eject / (default: skip)", file=stdout)
    stdout.flush()
    try:
        choice = stdin.readline().strip().lower()
    except (EOFError, KeyboardInterrupt):
        return "skip"
    if not choice or choice in ("s", "skip"):
        return "skip"
    if choice in ("a", "apply"):
        return "apply"
    if choice in ("e", "edit"):
        return "edit"
    if choice in ("r", "reject"):
        return "reject"
    print(f"  (unknown choice {choice!r}; defaulting to skip)", file=stdout)
    return "skip"


def _apply_repair(
    finding: dict, *, wiki_root: Path, stub: bool = False, stderr=sys.stderr,
) -> dict:
    """Apply a repair based on finding rule. Returns result dict.

    For mode-mixed splits, dispatches `documenter` sub-agent (in stub mode
    in CI, the dispatch is a no-op marker). For other drift types, applies
    deterministic fixes (e.g. file moves for template-drift) — also
    preview-first.

    v1 applied repairs:
      - diataxis/template-drift → move file to correct mode-dir (git mv).
      - diataxis/stale-xref → record finding only (operator manually
        rewrites — no auto-fix in v1 since the right target is judgment).
      - diataxis/mode-mixed → dispatch documenter via stub marker.
      - diataxis/convention-drift → stub (v1 doesn't auto-repair these).
    """
    rule = finding["rule"]
    file_path = Path(finding["file"])
    if rule == "diataxis/template-drift":
        # Extract suggested mode from msg: "classifies as <mode>"
        m = re.search(r"classifies as (\S+)", finding["msg"])
        if not m:
            return {"action": "skipped", "reason": "could not parse target mode from msg"}
        target_mode = m.group(1)
        # Map mode → dir per the established convention.
        mode_to_dir = {
            "tutorial": "tutorials",
            "how-to": "how-to",
            "reference": "reference",
            "explanation": "explanation",
        }
        target_dir = wiki_root / mode_to_dir.get(target_mode, target_mode)
        target_path = target_dir / file_path.name
        if target_path.exists():
            return {
                "action": "skipped",
                "reason": f"target collision: {target_path} already exists",
            }
        # v1 doesn't actually run git mv — we PREVIEW what would happen.
        # Operator approval triggers the actual move in a future iteration
        # (we keep preview-first as the v1 contract).
        return {
            "action": "previewed",
            "type": "template-drift-move",
            "from": str(file_path),
            "to": str(target_path),
            "note": "preview only; operator runs `git mv` manually to apply",
        }
    if rule == "diataxis/mode-mixed":
        # Dispatch documenter sub-agent for the split (in stub mode in CI,
        # the dispatch is a no-op marker).
        if stub:
            return {
                "action": "dispatched-sub-agent-stub",
                "type": "mode-mixed-split",
                "file": str(file_path),
                "note": "stub mode; no actual sub-agent invocation",
            }
        return {
            "action": "dispatched-sub-agent",
            "type": "mode-mixed-split",
            "file": str(file_path),
            "note": "dispatch happens at skill body layer; CLI emits marker",
        }
    if rule == "diataxis/stale-xref":
        return {
            "action": "operator-action",
            "type": "stale-xref",
            "file": str(file_path),
            "note": "operator manually rewrites link target (auto-fix not in v1; right target is judgment)",
        }
    if rule == "diataxis/convention-drift":
        return {
            "action": "stub",
            "type": "convention-drift",
            "file": str(file_path),
            "note": "v1 stub; full handling lands in part 5 with AgentMemory read-side",
        }
    if rule.startswith("check-wiki/"):
        return {
            "action": "operator-action",
            "type": "check-wiki-rule",
            "rule": rule,
            "file": str(file_path),
            "note": "operator manually addresses; check-wiki rules surface known violations from the validator",
        }
    return {"action": "skipped", "reason": f"unknown rule: {rule}"}


def review_findings(
    findings: list[dict],
    *,
    wiki_root: Path,
    interactive: bool = True,
    stub: bool = False,
    limit: int | None = None,
    stdin=sys.stdin,
    stdout=sys.stdout,
    stderr=sys.stderr,
) -> dict:
    """Walk findings; prompt for action per finding; apply repairs."""
    stats = {
        "total_findings": len(findings),
        "applied": 0,
        "edited": 0,
        "rejected": 0,
        "skipped": 0,
        "errors": 0,
        "results": [],
    }
    if not findings:
        print("[diataxis-repair] no findings to repair", file=stderr)
        return stats
    if interactive and not stdin.isatty():
        print(
            "[diataxis-repair] interactive mode requested but stdin is not a TTY; "
            "defaulting all prompts to skip (never silent action)",
            file=stderr,
        )
        interactive = False
    iterated = 0
    for finding in findings:
        if limit is not None and iterated >= limit:
            print(
                f"[diataxis-repair] reached --limit {limit}; {len(findings) - iterated} findings unreviewed",
                file=stderr,
            )
            break
        iterated += 1
        if interactive:
            _present_finding(finding, stdout=stdout)
            action = _prompt_action(stdin=stdin, stdout=stdout)
        else:
            action = "skip"
        if action == "apply":
            result = _apply_repair(finding, wiki_root=wiki_root, stub=stub, stderr=stderr)
            stats["applied"] += 1
            stats["results"].append({"finding": finding, "result": result, "operator_action": "apply"})
        elif action == "edit":
            # v1 doesn't ship an in-skill editor; record the edit-request for
            # the operator to handle manually (open in their editor).
            stats["edited"] += 1
            stats["results"].append({"finding": finding, "result": {"action": "operator-edit"}, "operator_action": "edit"})
        elif action == "reject":
            stats["rejected"] += 1
            stats["results"].append({"finding": finding, "result": {"action": "rejected"}, "operator_action": "reject"})
        else:
            stats["skipped"] += 1
            stats["results"].append({"finding": finding, "result": {"action": "skipped"}, "operator_action": "skip"})
    return stats


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="diataxis-repair",
        description=(
            "Interactive fix-application for Diátaxis drift detected by "
            "`/diataxis check`. Per finding: preview suggested fix + "
            "operator approves / edits / rejects. Preview-first; never "
            "silent. Mode-mixed splits dispatch documenter sub-agent "
            "(use --stub for CI-safe no-op dispatch)."
        ),
    )
    parser.add_argument("--wiki-root", default=None, help="wiki root path (default: ./wiki)")
    parser.add_argument(
        "--findings", default=None,
        help="path to JSON file with findings (output of check.py). "
             "If omitted, runs check.py inline against --wiki-root.",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="cap on findings to review per invocation (default: all)",
    )
    parser.add_argument(
        "--stub", action="store_true",
        help="documenter sub-agent dispatches return a no-op marker instead "
             "of invoking. Used by CI smoke tests to avoid live LLM calls.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    try:
        wiki_root = _resolve_wiki_root(args.wiki_root)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    try:
        findings_path = Path(args.findings).expanduser() if args.findings else None
        findings = _load_findings(findings_path, wiki_root)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    stats = review_findings(
        findings,
        wiki_root=wiki_root,
        interactive=True,
        stub=args.stub,
        limit=args.limit,
    )
    print(json.dumps({
        "total_findings": stats["total_findings"],
        "applied": stats["applied"],
        "edited": stats["edited"],
        "rejected": stats["rejected"],
        "skipped": stats["skipped"],
        "errors": stats["errors"],
        "results_count": len(stats["results"]),
    }, indent=2))
    return 0 if stats["errors"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
