#!/usr/bin/env python3
"""Unit tests for harness/hooks/harness-context-session-start/harness-context-session-start.sh (V4 #39).

Drives the bash hook as a subprocess with a synthetic SessionStart event JSON on
stdin + a fixture vault, asserting the inject/skip/graceful-skip behaviors.

The hook resolves the active project's vault PLAN.md/progress.md via the real
`harness_memory.py vault-state-path` (found through ~/.claude/.agentm-config.json
or the ~/Antigravity/agentm fallback) — so we point MEMORY_VAULT_PATH at a
fixture vault and pre-resolve the expected paths via the same resolver, keeping
the test self-consistent regardless of how the slug is derived.

Run: python3 scripts/test_harness_context_hook.py
Skipped on non-POSIX (bash hook).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent
_HOOK = _REPO / "harness" / "hooks" / "harness-context-session-start" / "harness-context-session-start.sh"
_RESOLVER = _REPO / "scripts" / "harness_memory.py"


@unittest.skipIf(os.name == "nt", "bash hook — POSIX only")
class TestHarnessContextHook(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.vault = self.root / "vault"
        (self.vault / "projects").mkdir(parents=True)  # mark as the projects layout
        self.proj = self.root / "myfixtureproj"
        self.proj.mkdir()
        # Give the fixture project a resolvable slug (tier-1: .harness/project.json
        # vault_project field) so vault-state-path resolves a concrete path.
        (self.proj / ".harness").mkdir()
        (self.proj / ".harness" / "project.json").write_text(
            json.dumps({"vault_project": "myfixtureproj"}), encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _resolve(self, name: str, env: dict) -> str:
        """Pre-resolve a state path via the same resolver the hook uses."""
        r = subprocess.run(
            [sys.executable, str(_RESOLVER), "vault-state-path", name],
            cwd=str(self.proj), env=env, capture_output=True, text=True,
        )
        return r.stdout.strip()

    def _run_hook(self, cwd: str, env: dict):
        payload = json.dumps({"session_id": "doctor-probe", "cwd": cwd})
        return subprocess.run(
            ["bash", str(_HOOK)], input=payload, env=env, capture_output=True, text=True,
        )

    def test_injects_block_when_both_state_files_exist(self) -> None:
        env = {**os.environ, "MEMORY_VAULT_PATH": str(self.vault)}
        plan = self._resolve("PLAN.md", env)
        prog = self._resolve("progress.md", env)
        self.assertTrue(plan and prog, f"resolver returned empty: plan={plan!r} prog={prog!r}")
        # Create both state files at the resolved paths.
        for p in (plan, prog):
            Path(p).parent.mkdir(parents=True, exist_ok=True)
            Path(p).write_text("# fixture\n", encoding="utf-8")

        r = self._run_hook(str(self.proj), env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("[agentm] Project state for this repo lives in the vault", r.stdout)
        self.assertIn(plan, r.stdout)
        self.assertIn(prog, r.stdout)
        self.assertIn("Read PLAN.md before", r.stdout)
        self.assertIn("injected vault paths", r.stderr)

    def test_skips_when_state_files_absent(self) -> None:
        # Vault reachable but no PLAN.md/progress.md for this cwd's slug → skip.
        env = {**os.environ, "MEMORY_VAULT_PATH": str(self.vault)}
        r = self._run_hook(str(self.proj), env)
        self.assertEqual(r.returncode, 0)
        self.assertNotIn("[agentm] Project state", r.stdout)
        self.assertIn("skipped", r.stderr)

    def test_skips_when_event_cwd_missing(self) -> None:
        env = {**os.environ, "MEMORY_VAULT_PATH": str(self.vault)}
        r = self._run_hook(str(self.root / "does-not-exist"), env)
        self.assertEqual(r.returncode, 0)
        self.assertNotIn("[agentm] Project state", r.stdout)
        self.assertIn("skipped", r.stderr)

    def test_graceful_skip_when_resolver_unavailable(self) -> None:
        # Fake HOME with no .agentm-config.json + no ~/Antigravity/agentm fallback
        # → resolver cannot be located → graceful skip, never blocks.
        fake_home = self.root / "fakehome"
        fake_home.mkdir()
        env = {**os.environ, "HOME": str(fake_home), "MEMORY_VAULT_PATH": str(self.vault)}
        env.pop("AGENTM_INSTALL_PREFIX", None)
        r = self._run_hook(str(self.proj), env)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "")
        self.assertIn("resolver unavailable", r.stderr)


if __name__ == "__main__":
    unittest.main()
