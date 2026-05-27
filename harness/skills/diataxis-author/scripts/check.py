#!/usr/bin/env python3
# check.py — /diataxis check drift detection (plan #13 part 3 task 1).
#
# Wraps `scripts/check-wiki.py` (harness-side) as a subprocess for the
# strict-validator rules + adds 4 skill-side drift heuristics that
# operate beyond what check-wiki.py catches:
#
#   1. mode-mixed: page has both how-to-shape + explanation-shape signals
#      (call classify.py + check `mode_mixed: true`).
#   2. stale-cross-ref: link target file no longer exists at that path.
#   3. template-shape-drift: page authored with template X but body has
#      evolved toward template Y (requires comparison against template
#      signatures — heuristic for v1; tunable as patterns emerge).
#   4. convention-drift: page violates an operator convention stored in
#      AgentMemory but not yet codified in check-wiki.py rules
#      (read-side wires in part 5; v1 stubs the check).
#
# Outputs structured JSON report grouped by mode. Non-zero exit on findings.
# Graceful-skip on check-wiki.py subprocess failure → in-skill-heuristic-
# only mode + clear stderr warning + log a version-mismatch / absent /
# error line.

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

# Reuse classify.py for mode-mixed detection.
import classify  # type: ignore

# Minimum check-wiki.py version we know how to consume (matches contract).
_MIN_CHECK_WIKI_VERSION = "0.1.0"

_MODE_DIRS = ("tutorials", "how-to", "reference", "explanation")


@dataclass
class Finding:
    file: str
    rule: str
    severity: str      # info | warning | error
    msg: str
    suggested_fix: str | None = None


@dataclass
class CheckReport:
    wiki_root: str
    check_wiki_status: str       # ran | skipped-absent | skipped-error | skipped-version-mismatch
    check_wiki_findings: int
    skill_heuristic_findings: int
    findings_by_rule: dict[str, int] = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)


def _resolve_wiki_root(arg_path: str | None) -> Path:
    if arg_path:
        return Path(arg_path).expanduser()
    candidate = Path.cwd() / "wiki"
    if candidate.is_dir():
        return candidate
    raise ValueError(
        "wiki root not found: pass --wiki-root or cd into a project with a wiki/ dir"
    )


def _resolve_check_wiki_py(arg_path: str | None) -> Path | None:
    """Resolve path to check-wiki.py. Returns None if absent."""
    if arg_path:
        return Path(arg_path).expanduser()
    # Common sibling-clone locations: <toolkit>/../agentm/scripts/check-wiki.py
    me = Path(__file__).resolve()
    candidates = [
        me.parents[5] / "agentm" / "scripts" / "check-wiki.py",
        Path.home() / "Antigravity" / "agentm" / "scripts" / "check-wiki.py",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def _run_check_wiki(check_wiki_py: Path, wiki_root: Path, strict: bool) -> tuple[str, list[Finding]]:
    """Subprocess-invoke check-wiki.py + parse output.

    Returns (status, findings). status one of:
      ran / skipped-absent / skipped-error / skipped-version-mismatch.
    """
    if check_wiki_py is None or not check_wiki_py.exists():
        return "skipped-absent", []
    cmd = ["python3", str(check_wiki_py), "--root", str(wiki_root)]
    if strict:
        cmd.append("--strict")
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        print(
            f"[diataxis-check] check-wiki.py subprocess failed: {type(e).__name__}: {e}; "
            f"falling back to in-skill heuristics only",
            file=sys.stderr,
        )
        return "skipped-error", []
    # check-wiki.py prints findings to stdout as `path:line: rule: msg` lines on issues
    # OR a "no issues" line on clean. Exit 0 = clean; non-zero = findings.
    findings: list[Finding] = []
    # Parse simple line format: "<path>:<line>: <rule>: <msg>" (matches the
    # existing check-wiki.py emit() format).
    line_re = re.compile(r"^([^:]+):(\d+):\s+(\S+):\s+(.+)$")
    for line in (proc.stdout or "").splitlines():
        m = line_re.match(line.strip())
        if m:
            findings.append(
                Finding(
                    file=m.group(1),
                    rule=f"check-wiki/{m.group(3)}",
                    severity="error" if strict else "warning",
                    msg=m.group(4),
                    suggested_fix=None,
                )
            )
    return "ran", findings


# ── Skill-side heuristics (4 drift types per parent design §2) ─────────────


def _walk_wiki_pages(wiki_root: Path) -> list[Path]:
    """Find every .md page under wiki/ excluding structural files."""
    out: list[Path] = []
    if not wiki_root.exists():
        return out
    for p in wiki_root.rglob("*.md"):
        if not p.is_file():
            continue
        # Skip structural pages (Home.md, _Sidebar.md, READMEs).
        if p.name in {"Home.md", "_Sidebar.md", "README.md"}:
            continue
        out.append(p)
    return sorted(out)


def _heuristic_mode_mixed(p: Path) -> Finding | None:
    """Drift type 1: mode-mixed page (per classify.py).

    Catches two cases that both indicate "mode unclear":
      - mode_mixed: ≥1 other mode within 0.2 of winner AND above 0.5
      - needs_subagent: winner's confidence below threshold (0.7 default)
    The latter case catches pages where penalties (e.g. how-to with
    rationale section dropping its score below 0.5) mask the mix.
    """
    try:
        c = classify.classify_file(p)
    except FileNotFoundError:
        return None
    if c.mode_mixed or c.needs_subagent:
        # Differentiate the message so operators understand which signal
        # fired — guides their repair decision.
        label = "mode-mixed" if c.mode_mixed else "mode-ambiguous"
        return Finding(
            file=str(p),
            rule="diataxis/mode-mixed",
            severity="warning",
            msg=f"page is {label}: winner {c.mode} confidence {c.confidence}; scores {c.scores}",
            suggested_fix="run `/diataxis repair` to split into N pages or reclassify",
        )
    return None


_WIKI_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def _heuristic_stale_xref(p: Path, all_pages: set[str]) -> list[Finding]:
    """Drift type 2: stale cross-references — link target doesn't exist."""
    findings: list[Finding] = []
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    for m in _WIKI_LINK_RE.finditer(text):
        target = m.group(1).strip()
        # Skip external URLs + anchor-only links + relative-but-not-md links.
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        # Wiki-style internal links use the page basename (no extension).
        # Resolve target to a basename for comparison against known pages.
        base = target.split("#")[0]  # drop anchor
        if not base or base.startswith("."):
            continue
        # Strip .md if present + drop any directory prefix.
        stem = Path(base).stem
        if stem and stem not in all_pages:
            findings.append(
                Finding(
                    file=str(p),
                    rule="diataxis/stale-xref",
                    severity="warning",
                    msg=f"link target '{target}' (resolved stem: '{stem}') not found in wiki pages",
                    suggested_fix=f"update link to a current page or remove the reference",
                )
            )
    return findings


def _heuristic_template_drift(p: Path) -> Finding | None:
    """Drift type 3: template-shape drift.

    v1 heuristic: if the page lives in mode-dir X but classify.py says
    it's mode Y with high confidence (≥0.7), flag template-drift —
    body has evolved away from where it lives.
    """
    mode_dir = p.parent.name
    # Map directory name → expected mode.
    dir_to_mode = {
        "tutorials": "tutorial",
        "how-to": "how-to",
        "reference": "reference",
        "explanation": "explanation",
    }
    expected = dir_to_mode.get(mode_dir)
    if not expected:
        # Page in a non-mode dir (e.g. wiki/Home.md skipped earlier; nested
        # explanation/decisions/ → mode-dir is "decisions"). Skip.
        return None
    try:
        c = classify.classify_file(p)
    except FileNotFoundError:
        return None
    if c.mode_mixed:
        return None  # already covered by drift type 1
    if c.mode == expected:
        return None
    if c.confidence >= 0.7:
        return Finding(
            file=str(p),
            rule="diataxis/template-drift",
            severity="warning",
            msg=f"page lives in {mode_dir}/ but classifies as {c.mode} (confidence {c.confidence})",
            suggested_fix=f"move page to {c.mode}-mode dir OR rewrite body to match template",
        )
    return None


def _heuristic_convention_drift(p: Path) -> Finding | None:
    """Drift type 4: convention-drift against AgentMemory conventions.

    v1: stub. Always returns None. Part 5 wires AgentMemory read-side +
    operator-defined conventions to compare against.
    """
    return None


# ── Top-level orchestration ────────────────────────────────────────────────


def run_check(
    *,
    wiki_root: Path,
    strict: bool = False,
    check_wiki_py: Path | None = None,
) -> CheckReport:
    """Walk wiki/ + apply check-wiki.py + 4 skill heuristics. Returns CheckReport."""
    report = CheckReport(
        wiki_root=str(wiki_root),
        check_wiki_status="not-run",
        check_wiki_findings=0,
        skill_heuristic_findings=0,
    )
    # Step 1: check-wiki.py subprocess (if available).
    status, cw_findings = _run_check_wiki(check_wiki_py, wiki_root, strict)
    report.check_wiki_status = status
    report.check_wiki_findings = len(cw_findings)
    report.findings.extend(cw_findings)
    # Step 2: skill-side heuristics.
    pages = _walk_wiki_pages(wiki_root)
    all_stems = {p.stem for p in pages}
    for p in pages:
        f1 = _heuristic_mode_mixed(p)
        if f1:
            report.findings.append(f1)
        for f2 in _heuristic_stale_xref(p, all_stems):
            report.findings.append(f2)
        f3 = _heuristic_template_drift(p)
        if f3:
            report.findings.append(f3)
        f4 = _heuristic_convention_drift(p)
        if f4:
            report.findings.append(f4)
    skill_findings = len(report.findings) - report.check_wiki_findings
    report.skill_heuristic_findings = skill_findings
    # Group by rule for the summary.
    counts: dict[str, int] = {}
    for f in report.findings:
        counts[f.rule] = counts.get(f.rule, 0) + 1
    report.findings_by_rule = counts
    return report


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="diataxis-check",
        description=(
            "Diátaxis drift detection. Wraps check-wiki.py for the strict "
            "validator rules + adds 4 skill-side heuristics (mode-mixed / "
            "stale-cross-ref / template-shape-drift / convention-drift). "
            "Outputs structured JSON report. Non-zero exit on findings."
        ),
    )
    parser.add_argument("--wiki-root", default=None, help="wiki root path (default: ./wiki)")
    parser.add_argument(
        "--strict", action="store_true",
        help="pass --strict to check-wiki.py + escalate warnings to errors",
    )
    parser.add_argument(
        "--check-wiki-py", default=None,
        help="explicit path to check-wiki.py (default: auto-detect sibling clone)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    try:
        wiki_root = _resolve_wiki_root(args.wiki_root)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    check_wiki_py = _resolve_check_wiki_py(args.check_wiki_py)
    report = run_check(
        wiki_root=wiki_root,
        strict=args.strict,
        check_wiki_py=check_wiki_py,
    )
    print(json.dumps({
        "wiki_root": report.wiki_root,
        "check_wiki_status": report.check_wiki_status,
        "check_wiki_findings": report.check_wiki_findings,
        "skill_heuristic_findings": report.skill_heuristic_findings,
        "total_findings": len(report.findings),
        "findings_by_rule": report.findings_by_rule,
        "findings": [asdict(f) for f in report.findings],
    }, indent=2))
    # Exit code: 0 if no findings; 1 if findings (non-strict warnings included).
    # In strict mode any finding = exit 1.
    return 0 if not report.findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
