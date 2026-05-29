#!/usr/bin/env python3
"""Unit tests for scripts/detect_project.py — stdlib unittest, cross-platform.

Run directly:

    python3 scripts/test_detect_project.py

Or via discovery:

    python3 -m unittest scripts.test_detect_project

Covers V4 #32 task 1: per-rule detection against fixture dirs, the
default-all-enabled baseline, the R-harness bypass verdict, multi-rule
composition, and the text/json renderers.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import detect_project as dp  # noqa: E402


class _TmpRepo:
    """Context manager yielding a fresh empty tmpdir Path."""

    def __enter__(self) -> Path:
        self._td = tempfile.TemporaryDirectory()
        return Path(self._td.name)

    def __exit__(self, *exc) -> None:
        self._td.cleanup()


class TestSingleRules(unittest.TestCase):
    def test_wiki_enables_diataxis(self):
        with _TmpRepo() as root:
            (root / "wiki").mkdir()
            p = dp.detect(root)
            self.assertEqual(p.verdict, "propose")
            self.assertIn("R-wiki", p.matched_rules)
            self.assertTrue(p.skills["diataxis-author"].auto_detected)
            self.assertEqual(p.skills["diataxis-author"].rule_id, "R-wiki")

    def test_changelog_requires_manifest(self):
        with _TmpRepo() as root:
            (root / "CHANGELOG.md").write_text("# changelog\n", encoding="utf-8")
            # No language manifest -> no match.
            p = dp.detect(root)
            self.assertNotIn("R-changelog", p.matched_rules)
            self.assertFalse(p.skills["ship-release"].auto_detected)

    def test_changelog_with_manifest_enables_ship_release(self):
        with _TmpRepo() as root:
            (root / "CHANGELOG.md").write_text("# changelog\n", encoding="utf-8")
            (root / "package.json").write_text("{}", encoding="utf-8")
            p = dp.detect(root)
            self.assertIn("R-changelog", p.matched_rules)
            self.assertTrue(p.skills["ship-release"].auto_detected)

    def test_dependabot_enables_fixer(self):
        with _TmpRepo() as root:
            (root / ".github").mkdir()
            (root / ".github" / "dependabot.yml").write_text("version: 2\n", encoding="utf-8")
            p = dp.detect(root)
            self.assertIn("R-dependabot", p.matched_rules)
            self.assertTrue(p.skills["dependabot-fixer"].auto_detected)

    def test_pii_env_file(self):
        with _TmpRepo() as root:
            (root / ".env").write_text("SECRET=x\n", encoding="utf-8")
            p = dp.detect(root)
            self.assertIn("R-pii", p.matched_rules)
            self.assertTrue(p.skills["pii-scrubber"].auto_detected)

    def test_pii_envrc_is_known_false_positive(self):
        # .envrc (direnv) matches the .env* signal — documented false positive
        # the operator declines at approval. The engine still flags it.
        with _TmpRepo() as root:
            (root / ".envrc").write_text("export FOO=bar\n", encoding="utf-8")
            p = dp.detect(root)
            self.assertIn("R-pii", p.matched_rules)

    def test_tests_dir(self):
        with _TmpRepo() as root:
            (root / "tests").mkdir()
            p = dp.detect(root)
            self.assertIn("R-tests", p.matched_rules)
            self.assertTrue(p.hooks["evidence-tracker"].auto_detected)

    def test_tests_glob(self):
        with _TmpRepo() as root:
            (root / "foo_test.py").write_text("# test\n", encoding="utf-8")
            p = dp.detect(root)
            self.assertIn("R-tests", p.matched_rules)
            self.assertTrue(p.hooks["evidence-tracker"].auto_detected)

    def test_pkg_scripts_via_package_json(self):
        with _TmpRepo() as root:
            (root / "package.json").write_text(json.dumps({"scripts": {"test": "x"}}), encoding="utf-8")
            p = dp.detect(root)
            self.assertIn("R-pkg-scripts", p.matched_rules)
            self.assertTrue(p.hooks["kill-switch"].auto_detected)
            self.assertTrue(p.hooks["steer"].auto_detected)

    def test_pkg_scripts_package_json_without_scripts_no_match(self):
        with _TmpRepo() as root:
            (root / "package.json").write_text("{}", encoding="utf-8")
            p = dp.detect(root)
            self.assertNotIn("R-pkg-scripts", p.matched_rules)

    def test_pkg_scripts_via_makefile(self):
        with _TmpRepo() as root:
            (root / "Makefile").write_text("test:\n\techo hi\n", encoding="utf-8")
            p = dp.detect(root)
            self.assertIn("R-pkg-scripts", p.matched_rules)

    def test_vault_content_index(self):
        with _TmpRepo() as root:
            (root / "_index.md").write_text("# index\n", encoding="utf-8")
            p = dp.detect(root)
            self.assertIn("R-vault-content", p.matched_rules)
            self.assertTrue(p.skills["memory"].auto_detected)
            for h in ("memory-recall-session-start", "memory-reflect-idle"):
                self.assertTrue(p.hooks[h].auto_detected)

    def test_design_via_docs_dir(self):
        with _TmpRepo() as root:
            (root / "docs" / "design").mkdir(parents=True)
            p = dp.detect(root)
            self.assertIn("R-design", p.matched_rules)
            self.assertTrue(p.skills["design"].auto_detected)

    def test_non_coding_is_stub(self):
        with _TmpRepo() as root:
            (root / "_index.md").write_text("---\ntype: vacation\n---\n", encoding="utf-8")
            p = dp.detect(root)
            self.assertNotIn("R-non-coding", p.matched_rules)
            self.assertEqual(p.type, "coding")


class TestBypass(unittest.TestCase):
    def test_harness_source_bypasses(self):
        with _TmpRepo() as root:
            (root / "harness" / "phases").mkdir(parents=True)
            p = dp.detect(root)
            self.assertEqual(p.verdict, "bypass")
            self.assertFalse(p.legacy_harness_present)

    def test_harness_with_legacy_state(self):
        with _TmpRepo() as root:
            (root / "harness" / "phases").mkdir(parents=True)
            (root / ".harness").mkdir()
            p = dp.detect(root)
            self.assertEqual(p.verdict, "bypass")
            self.assertTrue(p.legacy_harness_present)

    def test_real_agentm_repo_bypasses(self):
        # The agentm repo root carries harness/phases/ -> bypass.
        agentm_root = _HERE.parent
        p = dp.detect(agentm_root)
        self.assertEqual(p.verdict, "bypass")


class TestComposition(unittest.TestCase):
    def test_empty_dir_default_all_enabled(self):
        with _TmpRepo() as root:
            p = dp.detect(root)
            self.assertEqual(p.verdict, "propose")
            self.assertEqual(p.matched_rules, ())
            # Every enableable skill/hook enabled, none auto_detected.
            for name in dp.ENABLEABLE_SKILLS:
                self.assertTrue(p.skills[name].enabled)
                self.assertFalse(p.skills[name].auto_detected)
            for name in dp.ENABLEABLE_HOOKS:
                self.assertTrue(p.hooks[name].enabled)
                self.assertFalse(p.hooks[name].auto_detected)

    def test_multi_rule_overlay(self):
        with _TmpRepo() as root:
            (root / "wiki").mkdir()
            (root / "tests").mkdir()
            (root / "CHANGELOG.md").write_text("# c\n", encoding="utf-8")
            (root / "go.mod").write_text("module x\n", encoding="utf-8")
            p = dp.detect(root)
            self.assertEqual(p.verdict, "propose")
            for rid in ("R-wiki", "R-tests", "R-changelog"):
                self.assertIn(rid, p.matched_rules)
            self.assertTrue(p.skills["diataxis-author"].auto_detected)
            self.assertTrue(p.skills["ship-release"].auto_detected)
            self.assertTrue(p.hooks["evidence-tracker"].auto_detected)
            # Untouched targets keep their default rationale.
            self.assertFalse(p.skills["dependabot-fixer"].auto_detected)


class TestRendering(unittest.TestCase):
    def test_text_propose_block(self):
        with _TmpRepo() as root:
            (root / "wiki").mkdir()
            p = dp.detect(root)
            txt = dp.render_text(p, repo_name="my-app", slug="my-app")
            self.assertIn("new project", txt)
            self.assertIn("Repo: my-app", txt)
            self.assertIn("(a) Register with all-enabled", txt)
            self.assertIn("diataxis-author", txt)

    def test_text_bypass_block(self):
        with _TmpRepo() as root:
            (root / "harness" / "phases").mkdir(parents=True)
            p = dp.detect(root)
            txt = dp.render_text(p, repo_name="agentm", slug="agentm")
            self.assertIn("harness project", txt)

    def test_json_shape(self):
        with _TmpRepo() as root:
            (root / "wiki").mkdir()
            d = dp.detect(root).to_dict()
            self.assertEqual(d["verdict"], "propose")
            self.assertEqual(d["type"], "coding")
            self.assertIn("skills", d)
            self.assertIn("hooks", d)
            self.assertIn("R-wiki", d["matched_rules"])
            self.assertEqual(d["skills"]["diataxis-author"]["rule_id"], "R-wiki")

    def test_json_bypass_shape(self):
        with _TmpRepo() as root:
            (root / "harness" / "phases").mkdir(parents=True)
            d = dp.detect(root).to_dict()
            self.assertEqual(d["verdict"], "bypass")
            self.assertIn("reason", d)
            self.assertIn("legacy_harness_present", d)


if __name__ == "__main__":
    unittest.main()
