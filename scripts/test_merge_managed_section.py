#!/usr/bin/env python3
"""Unit tests for scripts/merge-managed-section.py.

Focus: idempotent insert/replace of a marker-delimited managed section in a
markdown file (the ~/.gemini/GEMINI.md merge for V4 #22 Task 4b), with hard
no-clobber guarantees for the operator's surrounding content.

The script has a hyphenated filename (not importable), so these drive it as a
subprocess — which also exercises the real CLI contract install.sh relies on.

Run: python3 scripts/test_merge_managed_section.py
Discovered by CI via `(cd scripts && python3 -m unittest discover -p 'test_*.py')`.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_MERGE = _HERE / "merge-managed-section.py"

_BEGIN = "<!-- AGENTMEMORY:BEGIN"
_END = "<!-- AGENTMEMORY:END -->"


def _run(target: Path, content: Path, *extra: str):
    return subprocess.run(
        [sys.executable, str(_MERGE), str(target), str(content), *extra],
        capture_output=True, text=True,
    )


class TestMergeManagedSection(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.target = self.dir / "GEMINI.md"
        self.content = self.dir / "payload.md"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_content(self, body: str) -> None:
        self.content.write_text(body, encoding="utf-8")

    # ── create ────────────────────────────────────────────────────────────
    def test_create_when_target_absent(self) -> None:
        self._write_content("# Vault\n\nRead it first.\n")
        r = _run(self.target, self.content)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.target.exists())
        out = self.target.read_text(encoding="utf-8")
        self.assertIn(_BEGIN, out)
        self.assertIn(_END, out)
        self.assertIn("# Vault", out)
        self.assertIn("created", r.stdout)

    # ── append, preserving existing content ───────────────────────────────
    def test_append_preserves_existing(self) -> None:
        self.target.write_text("# My own global rules\n\nAlways use TypeScript.\n", encoding="utf-8")
        self._write_content("# Vault\n\nRead it first.\n")
        r = _run(self.target, self.content)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = self.target.read_text(encoding="utf-8")
        self.assertIn("Always use TypeScript.", out)   # operator content kept
        self.assertIn(_BEGIN, out)
        self.assertIn("# Vault", out)
        # operator content comes before the managed block (appended)
        self.assertLess(out.index("Always use TypeScript."), out.index(_BEGIN))
        self.assertIn("appended", r.stdout)

    # ── idempotency: second run is a no-op ────────────────────────────────
    def test_idempotent_second_run_noop(self) -> None:
        self._write_content("# Vault\n\nRead it first.\n")
        r1 = _run(self.target, self.content)
        self.assertEqual(r1.returncode, 0, r1.stderr)
        first = self.target.read_text(encoding="utf-8")
        r2 = _run(self.target, self.content)
        self.assertEqual(r2.returncode, 0, r2.stderr)
        second = self.target.read_text(encoding="utf-8")
        self.assertEqual(first, second)            # byte-identical
        self.assertIn("kept", r2.stdout)

    # ── replace in place, preserving content on BOTH sides ────────────────
    def test_replace_in_place_no_clobber(self) -> None:
        self._write_content("# Vault\n\nOLD body.\n")
        _run(self.target, self.content)
        # operator edits the file around the managed block
        text = self.target.read_text(encoding="utf-8")
        text = "# Header the operator added\n\n" + text + "\n## Footer the operator added\n"
        self.target.write_text(text, encoding="utf-8")
        # now the payload content changes and we re-merge
        self._write_content("# Vault\n\nNEW body.\n")
        r = _run(self.target, self.content)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = self.target.read_text(encoding="utf-8")
        self.assertIn("NEW body.", out)
        self.assertNotIn("OLD body.", out)                 # section replaced
        self.assertIn("# Header the operator added", out)  # before preserved
        self.assertIn("## Footer the operator added", out) # after preserved
        # position preserved: managed block still between header and footer
        self.assertLess(out.index("# Header the operator added"), out.index(_BEGIN))
        self.assertLess(out.index(_END), out.index("## Footer the operator added"))
        self.assertEqual(out.count(_BEGIN), 1)             # exactly one block
        self.assertEqual(out.count(_END), 1)

    # ── strip-frontmatter ─────────────────────────────────────────────────
    def test_strip_frontmatter(self) -> None:
        self._write_content("---\ntrigger: always_on\n---\n\n# Vault\n\nBody.\n")
        r = _run(self.target, self.content, "--strip-frontmatter")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = self.target.read_text(encoding="utf-8")
        self.assertNotIn("trigger: always_on", out)        # frontmatter dropped
        self.assertIn("# Vault", out)

    def test_frontmatter_kept_without_flag(self) -> None:
        self._write_content("---\ntrigger: always_on\n---\n\n# Vault\n")
        r = _run(self.target, self.content)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = self.target.read_text(encoding="utf-8")
        self.assertIn("trigger: always_on", out)           # not stripped by default

    # ── custom marker ─────────────────────────────────────────────────────
    def test_custom_marker(self) -> None:
        self._write_content("# X\n")
        r = _run(self.target, self.content, "--marker", "FOO")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = self.target.read_text(encoding="utf-8")
        self.assertIn("<!-- FOO:BEGIN", out)
        self.assertIn("<!-- FOO:END -->", out)

    # ── error: content file missing ───────────────────────────────────────
    def test_missing_content_file_exits_1(self) -> None:
        r = _run(self.target, self.dir / "nope.md")
        self.assertEqual(r.returncode, 1)
        self.assertIn("not found", r.stderr)

    # ── trailing-newline variants don't break append spacing ──────────────
    def test_append_when_existing_lacks_trailing_newline(self) -> None:
        self.target.write_text("no trailing newline", encoding="utf-8")
        self._write_content("# Vault\n")
        r = _run(self.target, self.content)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = self.target.read_text(encoding="utf-8")
        self.assertIn("no trailing newline", out)
        self.assertIn(_BEGIN, out)
        # blank line separates operator content from the block
        self.assertIn("no trailing newline\n\n<!-- AGENTMEMORY:BEGIN", out)


if __name__ == "__main__":
    unittest.main()
