#!/usr/bin/env python3
"""Unit tests for scripts/merge-settings-fragment.py.

Focus: the V4 #39 `--command` flag (absolutize a hook fragment's command at
user-scope merge time) + the pre-existing idempotent deep-merge behavior.

The script has a hyphenated filename (not importable), so these drive it as a
subprocess — which also exercises the real CLI contract install.sh relies on.

Run: python3 scripts/test_merge_settings_fragment.py
Discovered by CI via `(cd scripts && python3 -m unittest discover -p 'test_*.py')`.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_MERGE = _HERE / "merge-settings-fragment.py"


def _frag(command: str, event: str = "SessionStart") -> dict:
    return {
        "hooks": {
            event: [
                {"matcher": ".*", "hooks": [
                    {"type": "command", "command": command, "timeout": 5}
                ]}
            ]
        }
    }


def _run(settings: Path, fragment: Path, *extra: str):
    return subprocess.run(
        [sys.executable, str(_MERGE), str(settings), str(fragment), *extra],
        capture_output=True, text=True,
    )


class TestMergeSettingsFragment(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.settings = self.dir / "settings.json"
        self.fragment = self.dir / "frag.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_frag(self, command: str, event: str = "SessionStart") -> None:
        self.fragment.write_text(json.dumps(_frag(command, event)), encoding="utf-8")

    def test_merge_into_absent_settings_creates_hooks_block(self) -> None:
        self._write_frag("bash .claude/hooks/x.sh")
        rc = _run(self.settings, self.fragment).returncode
        self.assertEqual(rc, 0)
        d = json.loads(self.settings.read_text())
        cmds = [h["command"] for e in d["hooks"]["SessionStart"] for h in e["hooks"]]
        self.assertIn("bash .claude/hooks/x.sh", cmds)

    def test_idempotent_no_duplicate(self) -> None:
        self._write_frag("bash .claude/hooks/x.sh")
        _run(self.settings, self.fragment)
        _run(self.settings, self.fragment)
        d = json.loads(self.settings.read_text())
        self.assertEqual(len(d["hooks"]["SessionStart"]), 1)

    def test_preserves_other_top_level_keys(self) -> None:
        self.settings.write_text(json.dumps({"permissions": {"allow": ["x"]}}), encoding="utf-8")
        self._write_frag("bash .claude/hooks/x.sh")
        _run(self.settings, self.fragment)
        d = json.loads(self.settings.read_text())
        self.assertEqual(d["permissions"], {"allow": ["x"]})
        self.assertIn("hooks", d)

    # --- V4 #39: --command rewrite ---

    def test_command_override_rewrites_command(self) -> None:
        self._write_frag("bash .claude/hooks/memory-recall-session-start.sh")
        abs_cmd = "bash /home/u/.claude/hooks/memory-recall-session-start/memory-recall-session-start.sh"
        rc = _run(self.settings, self.fragment, "--command", abs_cmd).returncode
        self.assertEqual(rc, 0)
        d = json.loads(self.settings.read_text())
        cmds = [h["command"] for e in d["hooks"]["SessionStart"] for h in e["hooks"]]
        self.assertEqual(cmds, [abs_cmd])
        self.assertNotIn("bash .claude/hooks/memory-recall-session-start.sh", cmds)

    def test_command_override_idempotent(self) -> None:
        self._write_frag("bash .claude/hooks/x.sh")
        abs_cmd = "bash /home/u/.claude/hooks/x/x.sh"
        _run(self.settings, self.fragment, "--command", abs_cmd)
        _run(self.settings, self.fragment, "--command", abs_cmd)
        d = json.loads(self.settings.read_text())
        self.assertEqual(len(d["hooks"]["SessionStart"]), 1)
        cmds = [h["command"] for e in d["hooks"]["SessionStart"] for h in e["hooks"]]
        self.assertEqual(cmds, [abs_cmd])

    def test_command_override_dedups_against_prior_absolutized(self) -> None:
        # Merge with override, then merge the raw fragment WITH the same override
        # again — must still dedup (the stored command is the absolutized one).
        self._write_frag("bash .claude/hooks/x.sh", event="Stop")
        abs_cmd = "bash /home/u/.claude/hooks/x/x.sh"
        _run(self.settings, self.fragment, "--command", abs_cmd)
        r = _run(self.settings, self.fragment, "--command", abs_cmd)
        self.assertIn("already present", r.stdout)
        d = json.loads(self.settings.read_text())
        self.assertEqual(len(d["hooks"]["Stop"]), 1)

    def test_bad_args_exit_2(self) -> None:
        r = subprocess.run([sys.executable, str(_MERGE)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)

    def test_missing_fragment_exit_1(self) -> None:
        r = _run(self.settings, self.dir / "nope.json")
        self.assertEqual(r.returncode, 1)


if __name__ == "__main__":
    unittest.main()
