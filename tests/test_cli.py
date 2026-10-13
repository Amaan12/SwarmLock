"""Integration tests for SwarmLock CLI."""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest


class TestAgentLockCLI(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="swarmlock_cli_test_"))
        self.cli_script = Path(__file__).parent.parent / "agent_lock.py"

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def run_cli(self, *args) -> tuple[int, str, str]:
        cmd = [sys.executable, str(self.cli_script), "--no-auto-boot"] + list(args)
        proc = subprocess.run(
            cmd,
            cwd=str(self.test_dir),
            capture_output=True,
            text=True,
        )
        return proc.returncode, proc.stdout, proc.stderr

    def test_cli_acquire_and_check(self):
        # 1. Acquire
        rc, out, err = self.run_cli("acquire", "Assets/Scripts/Player.cs", "--agent", "Claude", "--reason", "Fix health bug")
        self.assertEqual(rc, 0)
        self.assertIn("ACQUIRED", out)

        # 2. Check locked
        rc, out, err = self.run_cli("check", "Assets/Scripts/Player.cs")
        self.assertEqual(rc, 1)
        self.assertIn("LOCKED by 'Claude'", out)

        # 3. Check free
        rc, out, err = self.run_cli("check", "Assets/Scripts/Enemy.cs")
        self.assertEqual(rc, 0)
        self.assertIn("FREE", out)

    def test_cli_conflict_blocks_other_agent(self):
        # Claude locks folder
        rc, out, err = self.run_cli("acquire", "Assets/Scripts/UI/", "--agent", "Claude")
        self.assertEqual(rc, 0)

        # Cursor tries to lock child file
        rc, out, err = self.run_cli("acquire", "Assets/Scripts/UI/Button.cs", "--agent", "Cursor")
        self.assertEqual(rc, 1)
        self.assertIn("LOCKED", err)
        self.assertIn("conflicts with", err)

    def test_cli_release_and_force(self):
        self.run_cli("acquire", "Source/Main.cpp", "--agent", "Cursor")

        # Claude tries release without force -> fails
        rc, out, err = self.run_cli("release", "Source/Main.cpp", "--agent", "Claude")
        self.assertEqual(rc, 1)
        self.assertIn("PERMISSION DENIED", err)

        # Claude uses --force -> succeeds
        rc, out, err = self.run_cli("release", "Source/Main.cpp", "--agent", "Claude", "--force")
        self.assertEqual(rc, 0)
        self.assertIn("RELEASED", out)

    def test_cli_list_table(self):
        self.run_cli("acquire", "Assets/Level1.unity", "--agent", "Antigravity", "--reason", "Bake lightmaps")
        rc, out, err = self.run_cli("list")
        self.assertEqual(rc, 0)
        self.assertIn("TARGET PATH", out)
        self.assertIn("Level1.unity", out)
        self.assertIn("Antigravity", out)

    def test_cli_clear(self):
        self.run_cli("acquire", "File1.txt", "--agent", "AgentA")
        self.run_cli("acquire", "File2.txt", "--agent", "AgentB")

        # Clear AgentA
        rc, out, _ = self.run_cli("clear", "--agent", "AgentA")
        self.assertEqual(rc, 0)
        self.assertIn("Cleared 1 active lock", out)

        # File1 is now free, File2 still locked
        rc, _, _ = self.run_cli("check", "File1.txt")
        self.assertEqual(rc, 0)
        rc, _, _ = self.run_cli("check", "File2.txt")
        self.assertEqual(rc, 1)

    def test_cli_sessions_isolation(self):
        # Claude Chat1 acquires file
        rc, out, _ = self.run_cli("acquire", "Assets/Combat.cs", "--agent", "Claude", "--session", "Chat1")
        self.assertEqual(rc, 0)
        self.assertIn("Claude:Chat1", out)

        # Claude Chat2 (different chat session) tries to acquire same file -> blocked!
        rc, out, err = self.run_cli("acquire", "Assets/Combat.cs", "--agent", "Claude", "--session", "Chat2")
        self.assertEqual(rc, 1)
        self.assertIn("Claude:Chat1", err)

        # Claude Chat2 tries to release Chat1's file -> permission denied!
        rc, out, err = self.run_cli("release", "Assets/Combat.cs", "--agent", "Claude", "--session", "Chat2")
        self.assertEqual(rc, 1)
        self.assertIn("PERMISSION DENIED", err)

        # Claude Chat1 releases its own file -> succeeds
        rc, out, _ = self.run_cli("release", "Assets/Combat.cs", "--agent", "Claude", "--session", "Chat1")
        self.assertEqual(rc, 0)

        # Claude Chat2 can now acquire it
        rc, out, _ = self.run_cli("acquire", "Assets/Combat.cs", "--agent", "Claude", "--session", "Chat2")
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
