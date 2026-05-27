#!/usr/bin/env python3
# classify.py — Diátaxis mode classification engine (plan #13 part 2 task 2).
#
# Two-tier classification per the parent design:
#   Tier 1 (this script's pure-Python heuristic): regex + heading-shape rules
#     from ADR 0004 + frontmatter signals. Returns mode + confidence; if
#     confidence is high (>= threshold) → emit + skip sub-agent.
#   Tier 2 (diataxis-evaluator sub-agent, dispatched by this script when
#     Tier 1 confidence is below threshold): semantic judgment for the
#     ambiguous tail. Lands when caller dispatches; in --stub mode we
#     return the canned "needs_subagent: true" marker without invoking.
#
# Confidence threshold: 0.7 default (tunable via operator's
# AgentMemory `_always-load/diataxis-classify-threshold.md` entry; v1
# reads only at startup; part 5 wires that read fully).
#
# Locked design calls (parent §1 + §5):
#   - Heuristic rules mirror agentm/scripts/check-wiki.py:
#       Tutorial: ## Step N — heading + ## What you learned + ## Next.
#       How-to: ## Steps section OR ≥3 numbered imperative steps in
#               first 40 lines; NO ## Rationale / Why / Background.
#       Reference: ## ⚡ Quick Reference table near top OR
#                  ≥60% tables by line count.
#       Explanation: anything else (default; prose-heavy narrative).
#   - Mode-mixed = ≥2 modes scored with competing strength → flag for
#     sub-agent semantic split.
#   - Stdlib-only (no third-party deps); matches the established pattern.

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


# Default confidence threshold for Tier-1 emit (below → Tier 2 dispatch).
_DEFAULT_CONFIDENCE_THRESHOLD = 0.7


# ── Mode-shape regex catalog (mirrors check-wiki.py's machine rules) ───────

_TUTORIAL_STEP_RE = re.compile(r"^##\s+Step\s+\d+\s*[—\-:]", re.IGNORECASE)
_TUTORIAL_LEARNED_RE = re.compile(r"^##\s+What\s+you\s+learned\s*$", re.IGNORECASE)
_TUTORIAL_NEXT_RE = re.compile(r"^##\s+Next\s*$", re.IGNORECASE)

_HOWTO_STEPS_RE = re.compile(r"^##\s+Steps\s*$", re.IGNORECASE)
_HOWTO_NUMBERED_STEP_RE = re.compile(r"^\d+\.\s+\S")

_REFERENCE_QUICKREF_RE = re.compile(
    r"^##\s+⚡?\s*Quick\s+Reference\s*$", re.IGNORECASE
)
_REFERENCE_TABLE_LINE_RE = re.compile(r"^\s*\|")  # any line starting with |

_EXPLANATION_FORBIDDEN_IN_HOWTO_RE = re.compile(
    r"^##\s+(Rationale|Why|Background|Context)\s*$", re.IGNORECASE
)


@dataclass
class Classification:
    mode: str                       # tutorial | how-to | reference | explanation
    confidence: float               # 0.0 - 1.0
    rationale: str                  # one-line explanation
    mode_mixed: bool = False
    needs_subagent: bool = False
    scores: dict[str, float] = field(default_factory=dict)  # per-mode scores
    suggested_split: list[dict] | None = None  # only set when mode_mixed + dispatched


def _read_text(path: Path) -> str:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"page not found: {path}")
    return path.read_text(encoding="utf-8", errors="replace")


def _split_frontmatter_body(text: str) -> tuple[dict[str, str], list[str]]:
    """Split optional YAML frontmatter from body. Returns (frontmatter_dict, body_lines).

    Tolerant: if no frontmatter, returns ({}, lines_of_full_text).
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, lines
    end_idx = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return {}, lines
    fm: dict[str, str] = {}
    for line in lines[1:end_idx]:
        if not line.strip() or line.strip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        fm[key.strip()] = val.strip()
    return fm, lines[end_idx + 1:]


def _score_tutorial(body_lines: list[str]) -> float:
    """Score how strongly the body matches tutorial-shape (0.0-1.0)."""
    has_step = any(_TUTORIAL_STEP_RE.match(line) for line in body_lines)
    has_learned = any(_TUTORIAL_LEARNED_RE.match(line) for line in body_lines)
    has_next = any(_TUTORIAL_NEXT_RE.match(line) for line in body_lines)
    # All three signals = strong (0.95). Step alone = moderate (0.5).
    if has_step and has_learned and has_next:
        return 0.95
    if has_step and (has_learned or has_next):
        return 0.75
    if has_step:
        return 0.5
    return 0.0


def _score_howto(body_lines: list[str]) -> float:
    """Score how strongly the body matches how-to-shape (0.0-1.0)."""
    has_steps_section = any(_HOWTO_STEPS_RE.match(line) for line in body_lines)
    # Count numbered-step lines in first 40 lines.
    numbered_count = sum(
        1 for line in body_lines[:40]
        if _HOWTO_NUMBERED_STEP_RE.match(line.strip())
    )
    # Negative signal: explanation-style sections push toward NOT-how-to.
    has_explanation_section = any(
        _EXPLANATION_FORBIDDEN_IN_HOWTO_RE.match(line) for line in body_lines
    )
    score = 0.0
    if has_steps_section:
        score = 0.85
    elif numbered_count >= 3:
        score = 0.65
    elif numbered_count >= 1:
        score = 0.3
    if has_explanation_section:
        score *= 0.5  # mode-mixed penalty
    return score


def _score_reference(body_lines: list[str], first_n: int = 20) -> float:
    """Score how strongly the body matches reference-shape (0.0-1.0)."""
    # Signal 1: ⚡ Quick Reference heading in first N lines.
    quickref_early = any(
        _REFERENCE_QUICKREF_RE.match(line)
        for line in body_lines[:first_n]
    )
    # Signal 2: ≥60% table lines.
    if not body_lines:
        table_ratio = 0.0
    else:
        non_empty = [l for l in body_lines if l.strip()]
        if not non_empty:
            table_ratio = 0.0
        else:
            table_lines = sum(
                1 for line in non_empty if _REFERENCE_TABLE_LINE_RE.match(line)
            )
            table_ratio = table_lines / len(non_empty)
    score = 0.0
    if quickref_early:
        score = 0.8
    if table_ratio >= 0.6:
        score = max(score, 0.9)
    elif table_ratio >= 0.4:
        score = max(score, 0.55)
    return score


def _score_explanation(body_lines: list[str], other_scores: dict[str, float]) -> float:
    """Score how strongly the body matches explanation-shape.

    Explanation is the DEFAULT — it wins when other modes don't score.
    Computed as `1.0 - max(other modes)` with a small floor so high-prose
    pages with no positive signal still classify as explanation rather
    than 'undecided'.
    """
    others = max(other_scores.get(m, 0.0) for m in ("tutorial", "how-to", "reference"))
    # If no other mode scored well, default to explanation with mild confidence.
    base = 1.0 - others
    # Explanation has explicit signals: ADR-shape (`> [!NOTE]` block with
    # Status:) is a strong explanation signal.
    if any("> [!NOTE]" in line and "Status:" in (body_lines[i+1] if i+1 < len(body_lines) else "")
           for i, line in enumerate(body_lines[:25])):
        base = max(base, 0.85)  # ADR-shape almost always explanation
    return base


def classify_text(text: str, *, confidence_threshold: float = _DEFAULT_CONFIDENCE_THRESHOLD) -> Classification:
    """Pure-text classification (no filesystem). Returns a Classification."""
    _fm, body_lines = _split_frontmatter_body(text)
    scores: dict[str, float] = {
        "tutorial": _score_tutorial(body_lines),
        "how-to": _score_howto(body_lines),
        "reference": _score_reference(body_lines),
    }
    scores["explanation"] = _score_explanation(body_lines, scores)
    # Pick the winning mode.
    winning_mode = max(scores, key=lambda m: scores[m])
    winning_score = scores[winning_mode]
    # Mode-mixed detection: ≥2 modes score above 0.5 AND competing within 0.2.
    above_half = [(m, s) for m, s in scores.items() if s >= 0.5 and m != winning_mode]
    competing = [
        (m, s) for m, s in above_half
        if winning_score - s < 0.2
    ]
    mode_mixed = len(competing) >= 1
    # Rationale string.
    parts = [f"{m}={s:.2f}" for m, s in sorted(scores.items(), key=lambda x: -x[1])]
    rationale = f"scores {{ {', '.join(parts)} }}"
    if mode_mixed:
        rationale += f"; mode-mixed (competing within 0.2)"

    needs_subagent = mode_mixed or winning_score < confidence_threshold
    return Classification(
        mode=winning_mode,
        confidence=round(winning_score, 3),
        rationale=rationale,
        mode_mixed=mode_mixed,
        needs_subagent=needs_subagent,
        scores={k: round(v, 3) for k, v in scores.items()},
    )


def classify_file(
    file_path: Path,
    *,
    confidence_threshold: float = _DEFAULT_CONFIDENCE_THRESHOLD,
) -> Classification:
    """File-level classification. Reads the file then calls classify_text."""
    text = _read_text(file_path)
    return classify_text(text, confidence_threshold=confidence_threshold)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="diataxis-classify",
        description=(
            "Classify a wiki page's Diátaxis mode (tutorial / how-to / "
            "reference / explanation). Tier-1 heuristic returns mode + "
            "confidence + needs_subagent flag; ambiguous cases would "
            "dispatch the diataxis-evaluator sub-agent (operational from "
            "this part — see --stub for CI-safe no-op-dispatch)."
        ),
    )
    parser.add_argument("file", help="path to wiki page to classify")
    parser.add_argument(
        "--threshold", type=float, default=None,
        help=f"confidence threshold for Tier-1 emit (default {_DEFAULT_CONFIDENCE_THRESHOLD})",
    )
    parser.add_argument(
        "--no-subagent", action="store_true",
        help="never dispatch sub-agent; return Tier-1 result even if ambiguous",
    )
    parser.add_argument(
        "--stub", action="store_true",
        help="when sub-agent dispatch would fire, emit canned 'needs_subagent: true' "
             "marker without invoking. Used by CI smoke tests to avoid live LLM calls.",
    )
    return parser.parse_args(argv)


def _resolve_threshold(arg_threshold: float | None, file_path: Path) -> float:
    """Resolve confidence threshold: explicit arg → AgentMemory conventions → default."""
    if arg_threshold is not None:
        return arg_threshold
    # Try AgentMemory conventions; per-repo wiki override takes precedence.
    try:
        import agentmemory_conventions  # type: ignore
        # Walk up from the file path to find a wiki/ ancestor for per-repo conventions.
        wiki_root = None
        cur = file_path.resolve().parent
        while cur != cur.parent:
            if cur.name == "wiki":
                wiki_root = cur
                break
            cur = cur.parent
        conv = agentmemory_conventions.load_conventions(wiki_root=wiki_root)
        return float(conv.get("confidence_threshold", _DEFAULT_CONFIDENCE_THRESHOLD))
    except Exception:
        return _DEFAULT_CONFIDENCE_THRESHOLD


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    threshold = _resolve_threshold(args.threshold, Path(args.file).expanduser())
    try:
        result = classify_file(Path(args.file).expanduser(), confidence_threshold=threshold)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    # If sub-agent dispatch is warranted, behavior depends on flags.
    payload = asdict(result)
    if args.no_subagent:
        payload["dispatched_subagent"] = False
        payload["needs_subagent"] = False  # caller wants Tier-1 only
    elif args.stub:
        payload["dispatched_subagent"] = False
        # needs_subagent stays as-is — caller sees the flag without actual dispatch.
    else:
        # In a real invocation, this is where the caller (skill body) would
        # spawn the diataxis-evaluator sub-agent. Pure-Python CLI here can't
        # do that — it returns the marker, and the caller-side skill does
        # the dispatch. Same pattern as adapt_skills.py from plan #7b task 4.
        payload["dispatched_subagent"] = False
        payload["sub_agent_note"] = "dispatch happens at the skill body layer (CLI emits marker)"
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
