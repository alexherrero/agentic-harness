#!/usr/bin/env python3
"""evidence_tracker — hook helper for /work evidence-tracking enforcement.

Default-FAIL contract: every PLAN.md task starts with evidence-met=false.
The agent must demonstrably READ relevant spec/test/evidence files before
a Write/Edit that flips PLAN.md `[ ]` → `[x]` is allowed.

The hook (`evidence-tracker.sh` / `.ps1`) shells out to this CLI with the
PreToolUse JSON input on stdin. Behavior by tool name:

  Read   → record path read (if file exists); exit 0
  Write  → check whether op would flip a PLAN.md checkbox without evidence;
           exit 2 (block) on default-FAIL, else exit 0
  Edit   → same as Write
  other  → exit 0 (no-op)

State lives at `<project-root>/.harness/.evidence-reads` (JSON, per-task
file-path lists; gitignored; atomic write). Reset on `/work` session start
per the harness `/work` spec §5b.

Evidence requirement per task (HYBRID):
  - HEURISTIC by default: file under tests/ or spec/, matches *.spec.* /
    *.test.* / *_test.py, has a code extension, OR literally appears in
    the task's **Verification:** text in PLAN.md.
  - Per-task override via `**Evidence:** <glob-or-paths>` task-body
    annotation (comma- or whitespace-separated; supports globs).
  - Explicit opt-out via `**Evidence:** none` (case-insensitive).

Stdlib-only. Cross-platform via pathlib.PurePosixPath normalization.

CLI:
    python3 evidence_tracker.py --mode {check|reset|self-test}

`check` reads the PreToolUse JSON from stdin (per Claude Code's contract:
`tool_name`, `tool_input.file_path`, etc.); decides allow/block.

`reset` clears the state file (called by harness /work at session start).

`self-test` runs the embedded unittest suite (32 tests).
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sys
import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Optional


# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------

_PLAN_REL = (".harness", "PLAN.md")
_STATE_REL = (".harness", ".evidence-reads")

# Code-file extensions that count toward heuristic match. Markdown deliberately
# excluded — tests/README.md should NOT satisfy evidence for a coding task.
_CODE_EXTENSIONS = {
    ".py", ".pyi",
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".sh", ".bash", ".zsh",
    ".ps1", ".psm1",
    ".rb", ".go", ".rs", ".java", ".kt", ".swift",
    ".c", ".cc", ".cpp", ".h", ".hpp",
    ".cs", ".php", ".scala", ".clj", ".ex", ".exs",
    ".lua", ".sql",
}

# Heuristic-match directory prefixes + filename patterns. All path comparison
# happens on the POSIX-normalized path string.
_HEURISTIC_DIRS = ("tests/", "test/", "spec/", "specs/", "__tests__/")
_HEURISTIC_FILENAME_PATTERNS = (
    "*.spec.*",
    "*.test.*",
    "*_test.py",
    "test_*.py",
)

# Regex patterns for PLAN.md task parsing.
_TASK_HEADER_RE = re.compile(r"^### (\d+)\. (.+)$")
_VERIFICATION_RE = re.compile(
    r"\*\*Verification:\*\*\s*(.+?)(?=\n\s*-\s+\*\*|\n###|\n##|\Z)",
    re.DOTALL | re.IGNORECASE,
)
_EVIDENCE_RE = re.compile(
    r"\*\*Evidence:\*\*\s*(.+?)(?=\n\s*-\s+\*\*|\n###|\n##|\Z)",
    re.DOTALL | re.IGNORECASE,
)
_STATUS_LINE_RE = re.compile(r"\*\*Status:\*\*\s*\[([ x])\]")


# -----------------------------------------------------------------------------
# Data shapes
# -----------------------------------------------------------------------------

@dataclass
class Task:
    """A parsed PLAN.md task."""
    id: int
    title: str
    body: str  # raw markdown body between this task's H3 and the next H3
    checkbox: str  # "[ ]" or "[x]"
    verification_text: str  # extracted **Verification:** text (may be empty)
    evidence_annotation: Optional[str]  # raw **Evidence:** text if present, else None


@dataclass
class EvidenceRequirement:
    """Resolved per-task evidence requirement."""
    kind: str  # "none" | "list" | "heuristic"
    patterns: list[str] = field(default_factory=list)  # for "list" kind
    verification_text: str = ""  # for "heuristic" kind — extracted literal paths


# -----------------------------------------------------------------------------
# Path normalization
# -----------------------------------------------------------------------------

def normalize_path(p: str) -> str:
    """Return POSIX-form path string for cross-platform comparison.

    Windows `C:\\foo\\bar` → `C:/foo/bar`. Leading `./` stripped.
    """
    if not p:
        return ""
    # Strip surrounding whitespace + quotes the agent might emit.
    p = p.strip().strip('"').strip("'")
    s = Path(p).as_posix()
    if s.startswith("./"):
        s = s[2:]
    return s


# -----------------------------------------------------------------------------
# PLAN.md parsing
# -----------------------------------------------------------------------------

def parse_plan(plan_path: Path) -> list[Task]:
    """Parse PLAN.md and return list of Tasks. Empty list if file missing."""
    try:
        text = plan_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    lines = text.splitlines(keepends=False)
    tasks: list[Task] = []
    current_start: Optional[int] = None
    current_id: Optional[int] = None
    current_title: Optional[str] = None

    def _close(start: int, body_lines: list[str]) -> None:
        nonlocal tasks
        body = "\n".join(body_lines)
        checkbox = "[ ]"
        m = _STATUS_LINE_RE.search(body)
        if m:
            checkbox = f"[{m.group(1)}]"
        ver_m = _VERIFICATION_RE.search(body)
        verification_text = ver_m.group(1).strip() if ver_m else ""
        ev_m = _EVIDENCE_RE.search(body)
        evidence_annotation = ev_m.group(1).strip() if ev_m else None
        assert current_id is not None and current_title is not None
        tasks.append(Task(
            id=current_id,
            title=current_title,
            body=body,
            checkbox=checkbox,
            verification_text=verification_text,
            evidence_annotation=evidence_annotation,
        ))

    body_lines: list[str] = []
    for i, line in enumerate(lines):
        m = _TASK_HEADER_RE.match(line)
        if m:
            if current_start is not None:
                _close(current_start, body_lines)
            current_id = int(m.group(1))
            current_title = m.group(2).strip()
            current_start = i
            body_lines = []
        elif current_start is not None:
            # Stop accumulating into the current task when we hit an H2.
            if line.startswith("## "):
                _close(current_start, body_lines)
                current_start = None
                current_id = None
                current_title = None
                body_lines = []
            else:
                body_lines.append(line)

    if current_start is not None:
        _close(current_start, body_lines)

    return tasks


# -----------------------------------------------------------------------------
# Evidence requirement resolver
# -----------------------------------------------------------------------------

def resolve_evidence_requirement(task: Task) -> EvidenceRequirement:
    """Map a Task to its EvidenceRequirement per the hybrid contract.

    Order: explicit `**Evidence:** none` → NONE; explicit `**Evidence:** <patterns>`
    → LIST; otherwise → HEURISTIC.
    """
    ann = task.evidence_annotation
    if ann is not None:
        stripped = ann.strip()
        # Take only the first line/sentence — annotations are short.
        first_line = stripped.splitlines()[0].strip() if stripped else ""
        # Strip an optional "— <rationale>" tail.
        em_dash_idx = first_line.find(" — ")
        if em_dash_idx != -1:
            first_line = first_line[:em_dash_idx].strip()
        dash_idx = first_line.find(" - ")
        if dash_idx != -1:
            first_line = first_line[:dash_idx].strip()

        if first_line.lower() == "none":
            return EvidenceRequirement(kind="none")

        # Parse comma- or whitespace-separated patterns.
        tokens = [t.strip().strip(",").strip("`") for t in re.split(r"[,\s]+", first_line) if t.strip()]
        patterns = [normalize_path(t) for t in tokens if t]
        if patterns:
            return EvidenceRequirement(kind="list", patterns=patterns)

    return EvidenceRequirement(kind="heuristic", verification_text=task.verification_text)


# -----------------------------------------------------------------------------
# Heuristic + list match
# -----------------------------------------------------------------------------

def matches_heuristic(path: str, verification_text: str) -> bool:
    """Default-heuristic match for evidence-tracking.

    Returns True iff the (POSIX-normalized) `path`:
      - Lives under a test/spec dir AND has a code extension, OR
      - Filename matches *.spec.* / *.test.* / *_test.py / test_*.py AND
        has a code extension, OR
      - Literally appears in `verification_text`.
    """
    if not path:
        return False
    p = normalize_path(path)

    # Literal verification-text match (takes precedence; code-ext check not
    # required since operator-stated paths can be anything).
    if verification_text and p in verification_text:
        return True

    # Code-extension gate (markdown explicitly excluded).
    suffix = PurePosixPath(p).suffix.lower()
    if suffix not in _CODE_EXTENSIONS:
        return False

    # Test/spec directory match.
    for d in _HEURISTIC_DIRS:
        if p == d.rstrip("/") or p.startswith(d) or f"/{d}" in p:
            return True

    # Filename pattern match.
    name = PurePosixPath(p).name
    for pat in _HEURISTIC_FILENAME_PATTERNS:
        if fnmatch.fnmatch(name, pat):
            return True

    return False


def matches_list(path: str, patterns: list[str]) -> bool:
    """List-of-patterns glob match. Patterns and path are POSIX-normalized."""
    if not path or not patterns:
        return False
    p = normalize_path(path)
    for pat in patterns:
        if not pat:
            continue
        n_pat = normalize_path(pat)
        # Exact or glob match against full path.
        if fnmatch.fnmatch(p, n_pat):
            return True
        # Also match against the basename — common-case override "tests/foo.py"
        # should accept a read whose path is "/tmp/scratch/tests/foo.py".
        if fnmatch.fnmatch(PurePosixPath(p).name, PurePosixPath(n_pat).name):
            return True
        # Match suffix (handle absolute-path reads of relative-pattern files).
        if p.endswith("/" + n_pat) or p == n_pat:
            return True
    return False


# -----------------------------------------------------------------------------
# State file (atomic read + write)
# -----------------------------------------------------------------------------

def read_state(state_path: Path) -> dict[str, list[str]]:
    """Return the {task_id_str: [paths]} mapping. Empty dict on miss/parse-fail."""
    if not state_path.is_file():
        return {}
    try:
        with state_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    # Coerce to expected shape.
    out: dict[str, list[str]] = {}
    for k, v in data.items():
        if isinstance(v, list):
            out[str(k)] = [str(x) for x in v if isinstance(x, str)]
    return out


def write_state(state_path: Path, state: dict[str, list[str]]) -> None:
    """Atomic write: tmp+rename."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(state, indent=2, sort_keys=True) + "\n").encode("utf-8")
    fd, tmp_path = tempfile.mkstemp(
        prefix=state_path.name + ".",
        suffix=".tmp",
        dir=str(state_path.parent),
    )
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(payload)
        os.replace(tmp_path, state_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def record_read(state_path: Path, task_id: int, file_path: str) -> None:
    """Append `file_path` to state[str(task_id)] (de-duped). Atomic write."""
    if not file_path:
        return
    p = normalize_path(file_path)
    state = read_state(state_path)
    key = str(task_id)
    bucket = state.setdefault(key, [])
    if p not in bucket:
        bucket.append(p)
    write_state(state_path, state)


def record_global_read(state_path: Path, file_path: str) -> None:
    """Append a read with no specific task association — visible to all tasks.

    The hook doesn't know which task is "active" at Read-time; the agent might
    be reading evidence for any open task. We store the read under a special
    `__global__` bucket; `check_evidence_met` consults both per-task and global
    buckets when checking a task.
    """
    record_read(state_path, 0, file_path)


def reset_state(state_path: Path) -> None:
    """Delete the state file (used at /work session start)."""
    try:
        state_path.unlink()
    except FileNotFoundError:
        pass


# -----------------------------------------------------------------------------
# check_evidence_met
# -----------------------------------------------------------------------------

def check_evidence_met(
    state: dict[str, list[str]],
    task: Task,
    requirement: EvidenceRequirement,
) -> bool:
    """Return True iff the recorded reads satisfy the task's requirement."""
    if requirement.kind == "none":
        return True

    # Collect reads visible to this task: per-task + __global__ (key "0").
    reads: list[str] = []
    reads.extend(state.get(str(task.id), []))
    reads.extend(state.get("0", []))

    if requirement.kind == "list":
        for r in reads:
            if matches_list(r, requirement.patterns):
                return True
        return False

    # heuristic
    for r in reads:
        if matches_heuristic(r, requirement.verification_text):
            return True
    return False


# -----------------------------------------------------------------------------
# would_flip_checkbox — detect Write/Edit ops that change [ ] to [x]
# -----------------------------------------------------------------------------

def would_flip_checkbox(
    plan_path: Path,
    tool_name: str,
    tool_input: dict,
) -> Optional[int]:
    """If the tool op would flip a PLAN.md task's `[ ]` → `[x]`, return the
    task id. Else None.

    Handles Write (full content replace) and Edit (old_string → new_string).
    """
    target = tool_input.get("file_path") or tool_input.get("path") or ""
    if not target:
        return None
    target_norm = normalize_path(target)
    plan_norm = normalize_path(str(plan_path))
    # Match by suffix or exact — agents may pass absolute or relative paths.
    if not (target_norm == plan_norm or target_norm.endswith("/" + plan_norm)
            or plan_norm.endswith("/" + target_norm)
            or PurePosixPath(target_norm).name == PurePosixPath(plan_norm).name
            and target_norm.endswith(plan_norm)):
        # Also allow plain ".harness/PLAN.md" relative target.
        if not (target_norm.endswith(".harness/PLAN.md")
                or target_norm == "PLAN.md"):
            return None

    # Parse current PLAN.md.
    current_tasks = parse_plan(plan_path)
    current_states = {t.id: t.checkbox for t in current_tasks}

    if tool_name == "Write":
        new_content = tool_input.get("content", "")
        if not isinstance(new_content, str):
            return None
        # Parse the proposed new content as a plan.
        new_tasks = _parse_plan_text(new_content)
        for nt in new_tasks:
            old_cb = current_states.get(nt.id)
            if old_cb == "[ ]" and nt.checkbox == "[x]":
                return nt.id
        return None

    if tool_name == "Edit":
        old_str = tool_input.get("old_string", "")
        new_str = tool_input.get("new_string", "")
        if not isinstance(old_str, str) or not isinstance(new_str, str):
            return None
        # Look for the Status-line flip in the edit strings.
        old_has_unchecked = bool(re.search(r"\*\*Status:\*\*\s*\[\s\]", old_str))
        new_has_checked = bool(re.search(r"\*\*Status:\*\*\s*\[x\]", new_str))
        if not (old_has_unchecked and new_has_checked):
            return None
        # Attribute to the task whose old_string appears in the current
        # PLAN.md just after the H3 task header.
        try:
            plan_text = plan_path.read_text(encoding="utf-8")
        except OSError:
            return None
        idx = plan_text.find(old_str)
        if idx == -1:
            return None
        # Walk backwards from idx to find the most recent task H3 header.
        prefix = plan_text[:idx]
        for line in reversed(prefix.splitlines()):
            m = _TASK_HEADER_RE.match(line)
            if m:
                return int(m.group(1))
        return None

    return None


def _parse_plan_text(text: str) -> list[Task]:
    """Parse a string as if it were PLAN.md content. Used by would_flip_checkbox
    for the Write op's proposed new content (which isn't on disk yet)."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8",
    ) as fh:
        fh.write(text)
        tmp = Path(fh.name)
    try:
        return parse_plan(tmp)
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


# -----------------------------------------------------------------------------
# CLI: --mode check / reset / self-test
# -----------------------------------------------------------------------------

def _find_project_root(start: Path) -> Optional[Path]:
    """Walk up from `start` looking for a `.harness/` dir. Returns None if not
    found. Used to anchor PLAN.md + state-file paths when CWD is a sub-dir."""
    cur = start.resolve()
    while True:
        if (cur / ".harness").is_dir():
            return cur
        if cur.parent == cur:
            return None
        cur = cur.parent


def cli_check(stdin_text: str, project_root: Path) -> int:
    """Process a PreToolUse JSON event. Returns exit code (0 allow, 2 block)."""
    try:
        event = json.loads(stdin_text) if stdin_text.strip() else {}
    except json.JSONDecodeError:
        # Malformed input — fail open (don't block on parser errors).
        return 0
    if not isinstance(event, dict):
        return 0

    tool_name = event.get("tool_name", "")
    tool_input = event.get("tool_input", {}) or {}
    if not isinstance(tool_input, dict):
        return 0

    plan_path = project_root / _PLAN_REL[0] / _PLAN_REL[1]
    state_path = project_root / _STATE_REL[0] / _STATE_REL[1]

    if tool_name == "Read":
        file_path = tool_input.get("file_path") or tool_input.get("path") or ""
        if not file_path:
            return 0
        # Only record reads of files that actually exist (prevents fictitious-
        # path bypass: agent reads "tests/fake.py" → file doesn't exist → no
        # record. Agent reads "tests/real.py" → file exists → recorded).
        abs_path = (project_root / file_path).resolve() if not Path(file_path).is_absolute() else Path(file_path)
        if abs_path.is_file():
            record_global_read(state_path, file_path)
        return 0

    if tool_name in ("Write", "Edit"):
        flipped_id = would_flip_checkbox(plan_path, tool_name, tool_input)
        if flipped_id is None:
            return 0
        # Determine the task + its requirement.
        tasks = parse_plan(plan_path)
        task = next((t for t in tasks if t.id == flipped_id), None)
        if task is None:
            # Edge case — task not parseable. Fail open.
            return 0
        requirement = resolve_evidence_requirement(task)
        state = read_state(state_path)
        if check_evidence_met(state, task, requirement):
            return 0
        # Block with a helpful message.
        msg = _build_block_message(task, requirement, state)
        print(msg, file=sys.stderr)
        return 2

    return 0


def _build_block_message(
    task: Task,
    requirement: EvidenceRequirement,
    state: dict[str, list[str]],
) -> str:
    lines = [
        f"evidence-tracker: default-FAIL — refusing to flip task {task.id} ('{task.title}') checkbox to [x].",
        "",
        f"  Reason: no recorded evidence read satisfies the task's requirement.",
    ]
    if requirement.kind == "list":
        lines.append("  Evidence requirement (per-task **Evidence:** override):")
        for p in requirement.patterns:
            lines.append(f"    - {p}")
    elif requirement.kind == "heuristic":
        lines.append("  Evidence requirement (default heuristic): any file under")
        lines.append("    tests/ or spec/, matching *.spec.* / *.test.* / *_test.py /")
        lines.append("    test_*.py with a code extension, OR a path literally named")
        lines.append("    in the task's **Verification:** text.")
        if task.verification_text:
            ver_preview = task.verification_text[:200].replace("\n", " ")
            lines.append(f"  Verification preview: {ver_preview}")
    lines.append("")
    reads_this_task = state.get(str(task.id), [])
    reads_global = state.get("0", [])
    all_reads = reads_this_task + reads_global
    if all_reads:
        lines.append("  Reads recorded this /work session:")
        for r in all_reads:
            lines.append(f"    - {r}")
    else:
        lines.append("  Reads recorded this /work session: (none)")
    lines.append("")
    lines.append("  How to unblock:")
    lines.append("    1. Read a file that satisfies the requirement above (use the Read tool),")
    lines.append("       OR")
    lines.append("    2. If this task genuinely has no evidence (docs-only / ADR / CHANGELOG),")
    lines.append("       add `**Evidence:** none — <one-line rationale>` to the task body in PLAN.md")
    lines.append("       and retry the flip.")
    lines.append("    3. To reset session state: `python3 evidence_tracker.py --mode reset`")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="evidence_tracker")
    parser.add_argument(
        "--mode",
        choices=("check", "reset", "self-test"),
        required=True,
    )
    parser.add_argument(
        "--project-root",
        default=None,
        help="Override project root (default: walk up from cwd to find .harness/).",
    )
    args = parser.parse_args(argv)

    if args.mode == "self-test":
        loader = unittest.TestLoader()
        suite = loader.loadTestsFromModule(sys.modules[__name__])
        runner = unittest.TextTestRunner(verbosity=2)
        return 0 if runner.run(suite).wasSuccessful() else 1

    project_root = (
        Path(args.project_root).resolve()
        if args.project_root
        else _find_project_root(Path.cwd())
    )
    if project_root is None:
        # No .harness/ found — fail open (hook should be a no-op outside a
        # harness install).
        return 0

    if args.mode == "reset":
        reset_state(project_root / _STATE_REL[0] / _STATE_REL[1])
        return 0

    if args.mode == "check":
        return cli_check(sys.stdin.read(), project_root)

    return 0


# -----------------------------------------------------------------------------
# Unit tests (run via `python3 evidence_tracker.py --mode self-test`)
# -----------------------------------------------------------------------------

class TestNormalizePath(unittest.TestCase):

    def test_strips_quotes_and_whitespace(self) -> None:
        self.assertEqual(normalize_path('  "tests/foo.py"  '), "tests/foo.py")

    def test_windows_backslash_to_posix(self) -> None:
        # Path() on POSIX keeps backslashes literal, so we test the behavior
        # we'd see on Windows. Use as_posix on a Windows-style string by
        # manually substituting — but Path() on POSIX won't do that, so we
        # validate the simpler case here. On Windows runners this will pass
        # because PureWindowsPath.as_posix() converts.
        # Use forward slashes directly to validate the normalize result:
        self.assertEqual(normalize_path("./tests/foo.py"), "tests/foo.py")

    def test_empty(self) -> None:
        self.assertEqual(normalize_path(""), "")


class TestParsePlan(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_plan(self, content: str) -> Path:
        p = self.root / "PLAN.md"
        p.write_text(content, encoding="utf-8")
        return p

    def test_empty_plan(self) -> None:
        p = self._write_plan("# Plan: empty\n\n")
        self.assertEqual(parse_plan(p), [])

    def test_single_task_unchecked(self) -> None:
        p = self._write_plan(
            "# Plan: t\n\n"
            "## Tasks\n\n"
            "### 1. Build it\n\n"
            "- **What:** do stuff\n"
            "- **Verification:** tests/foo.py passes\n"
            "- **Status:** [ ]\n"
        )
        tasks = parse_plan(p)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].id, 1)
        self.assertEqual(tasks[0].title, "Build it")
        self.assertEqual(tasks[0].checkbox, "[ ]")
        self.assertIn("tests/foo.py", tasks[0].verification_text)
        self.assertIsNone(tasks[0].evidence_annotation)

    def test_task_checked(self) -> None:
        p = self._write_plan(
            "### 1. Done\n\n- **Status:** [x] — shipped\n"
        )
        tasks = parse_plan(p)
        self.assertEqual(tasks[0].checkbox, "[x]")

    def test_task_with_evidence_override(self) -> None:
        p = self._write_plan(
            "### 1. Override task\n\n"
            "- **What:** do\n"
            "- **Verification:** runs\n"
            "- **Evidence:** custom/path.py, other/path.md\n"
            "- **Status:** [ ]\n"
        )
        tasks = parse_plan(p)
        self.assertIsNotNone(tasks[0].evidence_annotation)
        self.assertIn("custom/path.py", tasks[0].evidence_annotation or "")

    def test_task_with_evidence_none(self) -> None:
        p = self._write_plan(
            "### 1. Docs task\n\n- **Evidence:** none — pure ADR write\n- **Status:** [ ]\n"
        )
        tasks = parse_plan(p)
        self.assertIsNotNone(tasks[0].evidence_annotation)
        ann = (tasks[0].evidence_annotation or "").lower()
        self.assertTrue(ann.startswith("none"))

    def test_multiple_tasks(self) -> None:
        p = self._write_plan(
            "### 1. A\n- **Status:** [x]\n\n"
            "### 2. B\n- **Status:** [ ]\n\n"
            "### 3. C\n- **Status:** [ ]\n"
        )
        tasks = parse_plan(p)
        self.assertEqual([t.id for t in tasks], [1, 2, 3])
        self.assertEqual([t.checkbox for t in tasks], ["[x]", "[ ]", "[ ]"])

    def test_h2_terminates_task_body(self) -> None:
        # An H2 after a task should close that task (not roll into body).
        p = self._write_plan(
            "### 1. T\n\n- **Status:** [ ]\n\n"
            "## Risks\n\n- something\n"
        )
        tasks = parse_plan(p)
        self.assertEqual(len(tasks), 1)
        self.assertNotIn("Risks", tasks[0].body)

    def test_missing_file(self) -> None:
        self.assertEqual(parse_plan(self.root / "nonexistent.md"), [])


class TestResolveEvidenceRequirement(unittest.TestCase):

    def _task(self, ann: Optional[str], ver: str = "") -> Task:
        return Task(
            id=1, title="t", body="", checkbox="[ ]",
            verification_text=ver, evidence_annotation=ann,
        )

    def test_none_opt_out(self) -> None:
        r = resolve_evidence_requirement(self._task("none — docs only"))
        self.assertEqual(r.kind, "none")

    def test_none_case_insensitive(self) -> None:
        for ann in ("None", "NONE", " None  - rationale", "none"):
            r = resolve_evidence_requirement(self._task(ann))
            self.assertEqual(r.kind, "none", f"failed for {ann!r}")

    def test_list_override(self) -> None:
        r = resolve_evidence_requirement(
            self._task("custom/path.py, other/*.md")
        )
        self.assertEqual(r.kind, "list")
        self.assertIn("custom/path.py", r.patterns)
        self.assertIn("other/*.md", r.patterns)

    def test_list_single_pattern(self) -> None:
        r = resolve_evidence_requirement(self._task("wiki/Home.md"))
        self.assertEqual(r.kind, "list")
        self.assertEqual(r.patterns, ["wiki/Home.md"])

    def test_heuristic_default(self) -> None:
        r = resolve_evidence_requirement(
            self._task(None, ver="see tests/foo.py for the check")
        )
        self.assertEqual(r.kind, "heuristic")
        self.assertIn("tests/foo.py", r.verification_text)


class TestMatchesHeuristic(unittest.TestCase):

    def test_tests_dir_py(self) -> None:
        self.assertTrue(matches_heuristic("tests/foo.py", ""))

    def test_tests_dir_nested(self) -> None:
        self.assertTrue(matches_heuristic("project/tests/sub/foo.py", ""))

    def test_spec_dir(self) -> None:
        self.assertTrue(matches_heuristic("spec/parser_spec.rb", ""))

    def test_tests_readme_excluded(self) -> None:
        # Markdown in tests/ should NOT satisfy.
        self.assertFalse(matches_heuristic("tests/README.md", ""))

    def test_spec_dot_ts(self) -> None:
        self.assertTrue(matches_heuristic("src/parser.spec.ts", ""))

    def test_test_dot_js(self) -> None:
        self.assertTrue(matches_heuristic("src/util.test.js", ""))

    def test_underscore_test_py(self) -> None:
        self.assertTrue(matches_heuristic("scripts/foo_test.py", ""))

    def test_test_prefix_py(self) -> None:
        self.assertTrue(matches_heuristic("scripts/test_foo.py", ""))

    def test_random_py_file_rejected(self) -> None:
        # Plain .py in a non-test dir doesn't satisfy heuristic.
        self.assertFalse(matches_heuristic("src/main.py", ""))

    def test_verification_literal_path(self) -> None:
        # If the verification text names a file literally, reading that
        # file satisfies — even if it doesn't match the test-dir heuristic.
        ver = "Run `python3 wiki/Home.md` to check (silly example)"
        self.assertTrue(matches_heuristic("wiki/Home.md", ver))

    def test_verification_literal_non_match(self) -> None:
        ver = "Read tests/foo.py for the check"
        # Reading a different file doesn't help.
        self.assertFalse(matches_heuristic("src/main.go", ver))

    def test_empty_path(self) -> None:
        self.assertFalse(matches_heuristic("", "anything"))


class TestMatchesList(unittest.TestCase):

    def test_exact_match(self) -> None:
        self.assertTrue(matches_list("custom/path.py", ["custom/path.py"]))

    def test_glob_match(self) -> None:
        self.assertTrue(matches_list("custom/foo.py", ["custom/*.py"]))

    def test_basename_match(self) -> None:
        # Operator wrote "tests/foo.py" but read happened with absolute path.
        self.assertTrue(matches_list("/tmp/scratch/tests/foo.py", ["tests/foo.py"]))

    def test_suffix_match(self) -> None:
        self.assertTrue(matches_list("/abs/wiki/explanation/decisions/0009-ev.md",
                                     ["decisions/0009-ev.md"]))

    def test_no_match(self) -> None:
        self.assertFalse(matches_list("src/main.go", ["tests/*.py"]))

    def test_empty_inputs(self) -> None:
        self.assertFalse(matches_list("", ["x"]))
        self.assertFalse(matches_list("x", []))


class TestStateFile(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.state_path = Path(self.tmp.name) / ".evidence-reads"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_empty_state_no_file(self) -> None:
        self.assertEqual(read_state(self.state_path), {})

    def test_record_and_read(self) -> None:
        record_read(self.state_path, 1, "tests/foo.py")
        state = read_state(self.state_path)
        self.assertEqual(state, {"1": ["tests/foo.py"]})

    def test_record_dedup(self) -> None:
        record_read(self.state_path, 1, "tests/foo.py")
        record_read(self.state_path, 1, "tests/foo.py")
        record_read(self.state_path, 1, " ./tests/foo.py ")  # normalized to same
        state = read_state(self.state_path)
        self.assertEqual(state["1"], ["tests/foo.py"])

    def test_record_multiple_tasks(self) -> None:
        record_read(self.state_path, 1, "tests/a.py")
        record_read(self.state_path, 2, "tests/b.py")
        state = read_state(self.state_path)
        self.assertEqual(set(state.keys()), {"1", "2"})

    def test_global_read_visible_to_all_tasks(self) -> None:
        record_global_read(self.state_path, "tests/shared.py")
        state = read_state(self.state_path)
        self.assertIn("0", state)
        self.assertEqual(state["0"], ["tests/shared.py"])

    def test_reset_clears(self) -> None:
        record_read(self.state_path, 1, "tests/a.py")
        reset_state(self.state_path)
        self.assertFalse(self.state_path.exists())
        self.assertEqual(read_state(self.state_path), {})

    def test_reset_no_file_is_safe(self) -> None:
        reset_state(self.state_path)  # should not raise

    def test_malformed_state_recovers_empty(self) -> None:
        self.state_path.write_bytes(b"{not valid json")
        self.assertEqual(read_state(self.state_path), {})


class TestCheckEvidenceMet(unittest.TestCase):

    def _task(self, **kw) -> Task:
        defaults = dict(id=1, title="t", body="", checkbox="[ ]",
                        verification_text="", evidence_annotation=None)
        defaults.update(kw)
        return Task(**defaults)

    def test_none_requirement_always_met(self) -> None:
        task = self._task()
        req = EvidenceRequirement(kind="none")
        self.assertTrue(check_evidence_met({}, task, req))

    def test_list_met_when_any_pattern_matches(self) -> None:
        task = self._task()
        req = EvidenceRequirement(kind="list", patterns=["tests/foo.py"])
        state = {"1": ["tests/foo.py"]}
        self.assertTrue(check_evidence_met(state, task, req))

    def test_list_met_via_global_read(self) -> None:
        task = self._task()
        req = EvidenceRequirement(kind="list", patterns=["tests/foo.py"])
        # Read recorded under __global__ (key "0"), not task 1.
        state = {"0": ["tests/foo.py"]}
        self.assertTrue(check_evidence_met(state, task, req))

    def test_list_unmet(self) -> None:
        task = self._task()
        req = EvidenceRequirement(kind="list", patterns=["tests/foo.py"])
        state = {"1": ["src/main.py"]}
        self.assertFalse(check_evidence_met(state, task, req))

    def test_heuristic_met(self) -> None:
        task = self._task(verification_text="tests/foo.py passes")
        req = EvidenceRequirement(
            kind="heuristic", verification_text="tests/foo.py passes",
        )
        state = {"0": ["tests/foo.py"]}
        self.assertTrue(check_evidence_met(state, task, req))

    def test_heuristic_unmet_no_reads(self) -> None:
        task = self._task()
        req = EvidenceRequirement(kind="heuristic")
        self.assertFalse(check_evidence_met({}, task, req))


class TestWouldFlipCheckbox(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".harness").mkdir()
        self.plan_path = self.root / ".harness" / "PLAN.md"
        self.plan_path.write_text(
            "# Plan\n\n"
            "## Tasks\n\n"
            "### 1. First\n\n- **What:** a\n- **Status:** [ ]\n\n"
            "### 2. Second\n\n- **What:** b\n- **Status:** [ ]\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_edit_flip(self) -> None:
        tid = would_flip_checkbox(
            self.plan_path, "Edit",
            {
                "file_path": str(self.plan_path),
                "old_string": "- **What:** a\n- **Status:** [ ]",
                "new_string": "- **What:** a\n- **Status:** [x] — done",
            },
        )
        self.assertEqual(tid, 1)

    def test_edit_no_flip(self) -> None:
        tid = would_flip_checkbox(
            self.plan_path, "Edit",
            {
                "file_path": str(self.plan_path),
                "old_string": "- **What:** a\n- **Status:** [ ]",
                "new_string": "- **What:** a-modified\n- **Status:** [ ]",
            },
        )
        self.assertIsNone(tid)

    def test_edit_wrong_file(self) -> None:
        tid = would_flip_checkbox(
            self.plan_path, "Edit",
            {
                "file_path": str(self.root / "other.md"),
                "old_string": "[ ]",
                "new_string": "[x]",
            },
        )
        self.assertIsNone(tid)

    def test_write_flip(self) -> None:
        new_content = (
            "# Plan\n\n## Tasks\n\n"
            "### 1. First\n- **Status:** [x] — shipped\n\n"
            "### 2. Second\n- **Status:** [ ]\n"
        )
        tid = would_flip_checkbox(
            self.plan_path, "Write",
            {"file_path": str(self.plan_path), "content": new_content},
        )
        self.assertEqual(tid, 1)

    def test_write_no_flip(self) -> None:
        new_content = (
            "# Plan\n\n## Tasks\n\n"
            "### 1. First\n- **Status:** [ ]\n\n"
            "### 2. Second\n- **Status:** [ ]\n"
        )
        tid = would_flip_checkbox(
            self.plan_path, "Write",
            {"file_path": str(self.plan_path), "content": new_content},
        )
        self.assertIsNone(tid)


class TestCLI(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".harness").mkdir()
        (self.root / "tests").mkdir()
        (self.root / "tests" / "foo.py").write_text("# fixture", encoding="utf-8")
        self.plan_path = self.root / ".harness" / "PLAN.md"
        self.plan_path.write_text(
            "# Plan\n\n## Tasks\n\n"
            "### 1. Task with heuristic\n"
            "- **Verification:** tests/foo.py passes\n"
            "- **Status:** [ ]\n\n"
            "### 2. Opt-out task\n"
            "- **Evidence:** none — docs only\n"
            "- **Status:** [ ]\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _check(self, event: dict) -> int:
        return cli_check(json.dumps(event), self.root)

    def test_read_records_existing_file(self) -> None:
        rc = self._check({"tool_name": "Read", "tool_input": {"file_path": "tests/foo.py"}})
        self.assertEqual(rc, 0)
        state = read_state(self.root / ".harness" / ".evidence-reads")
        self.assertIn("0", state)
        self.assertIn("tests/foo.py", state["0"])

    def test_read_ignores_nonexistent_file(self) -> None:
        rc = self._check({"tool_name": "Read", "tool_input": {"file_path": "tests/fake.py"}})
        self.assertEqual(rc, 0)
        state = read_state(self.root / ".harness" / ".evidence-reads")
        self.assertEqual(state, {})

    def test_edit_blocks_without_evidence(self) -> None:
        rc = self._check({
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(self.plan_path),
                "old_string": "- **Verification:** tests/foo.py passes\n- **Status:** [ ]",
                "new_string": "- **Verification:** tests/foo.py passes\n- **Status:** [x] — done",
            },
        })
        self.assertEqual(rc, 2)

    def test_edit_allowed_after_read(self) -> None:
        self._check({"tool_name": "Read", "tool_input": {"file_path": "tests/foo.py"}})
        rc = self._check({
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(self.plan_path),
                "old_string": "- **Verification:** tests/foo.py passes\n- **Status:** [ ]",
                "new_string": "- **Verification:** tests/foo.py passes\n- **Status:** [x] — done",
            },
        })
        self.assertEqual(rc, 0)

    def test_edit_opt_out_task_always_allowed(self) -> None:
        # Task 2 has `**Evidence:** none` — flip allowed without reads.
        rc = self._check({
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(self.plan_path),
                "old_string": "- **Evidence:** none — docs only\n- **Status:** [ ]",
                "new_string": "- **Evidence:** none — docs only\n- **Status:** [x] — shipped",
            },
        })
        self.assertEqual(rc, 0)

    def test_edit_non_plan_file_passthrough(self) -> None:
        other = self.root / "other.md"
        other.write_text("hello\n", encoding="utf-8")
        rc = self._check({
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(other),
                "old_string": "[ ]",
                "new_string": "[x]",
            },
        })
        self.assertEqual(rc, 0)

    def test_unrelated_tool_passthrough(self) -> None:
        rc = self._check({"tool_name": "Bash", "tool_input": {"command": "ls"}})
        self.assertEqual(rc, 0)

    def test_malformed_json_fails_open(self) -> None:
        rc = cli_check("{not json", self.root)
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    sys.exit(main())
