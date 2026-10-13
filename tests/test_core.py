"""Unit tests for SwarmLock core locking logic."""

import shutil
import tempfile
import time
from pathlib import Path
import unittest

from swarmlock.core import (
    LockManager,
    normalize_target_path,
    paths_conflict,
    format_duration,
)


class TestLockCore(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="swarmlock_test_"))
        self.manager = LockManager(workspace_root=self.test_dir, data_dir=self.test_dir / ".swarmlock", use_global=False)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_normalize_target_path(self):
        root = self.test_dir
        # Relative file
        disp, norm, is_dir = normalize_target_path("Assets/Scripts/Player.cs", root)
        self.assertEqual(disp, "Assets/Scripts/Player.cs")
        self.assertEqual(norm, "assets/scripts/player.cs")
        self.assertFalse(is_dir)

        # Trailing slash indicates directory
        disp, norm, is_dir = normalize_target_path("Assets/Scripts/UI/", root)
        self.assertEqual(disp, "Assets/Scripts/UI")
        self.assertEqual(norm, "assets/scripts/ui")
        self.assertTrue(is_dir)

        # Windows backslashes
        disp, norm, _ = normalize_target_path("Assets\\Scripts\\Player.cs", root)
        self.assertEqual(disp, "Assets/Scripts/Player.cs")
        self.assertEqual(norm, "assets/scripts/player.cs")

    def test_paths_conflict_logic(self):
        # Exact match
        self.assertTrue(paths_conflict("assets/scripts/player.cs", "assets/scripts/player.cs"))

        # Parent directory conflicts with child file
        self.assertTrue(paths_conflict("assets/scripts", "assets/scripts/player.cs"))
        self.assertTrue(paths_conflict("assets/scripts/player.cs", "assets/scripts"))

        # Deep nesting
        self.assertTrue(paths_conflict("assets", "assets/scripts/ui/menu.cs"))

        # Unrelated paths
        self.assertFalse(paths_conflict("assets/scripts/player.cs", "assets/scripts/enemy.cs"))
        self.assertFalse(paths_conflict("assets/scripts/player.cs", "assets/textures/player.png"))
        self.assertFalse(paths_conflict("assets/scripts", "assets/scripts_backup"))

    def test_acquire_and_check(self):
        success, lock, msg = self.manager.acquire(
            "Assets/Scripts/UI/Button.cs",
            agent="Claude",
            reason="Refactor button animation",
            ttl_minutes=15
        )
        self.assertTrue(success)
        self.assertIsNotNone(lock)
        self.assertEqual(lock.agent, "Claude")

        # Check path
        is_free, conf, chk_msg = self.manager.check("Assets/Scripts/UI/Button.cs")
        self.assertFalse(is_free)
        self.assertEqual(conf.agent, "Claude")

        # Check unrelated path
        is_free, _, _ = self.manager.check("Assets/Scripts/Audio/SoundManager.cs")
        self.assertTrue(is_free)

    def test_hierarchical_blocking(self):
        # Claude locks directory Assets/Scripts/UI/
        ok, _, _ = self.manager.acquire("Assets/Scripts/UI/", agent="Claude", reason="Overhaul UI")
        self.assertTrue(ok)

        # Cursor tries to acquire child file inside Assets/Scripts/UI/
        ok, conf, msg = self.manager.acquire("Assets/Scripts/UI/Button.cs", agent="Cursor", reason="Fix click bug")
        self.assertFalse(ok)
        self.assertIn("conflicts with", msg)
        self.assertEqual(conf.agent, "Claude")

        # Claude releases folder
        rel_ok, _ = self.manager.release("Assets/Scripts/UI/", agent="Claude")
        self.assertTrue(rel_ok)

        # Now Cursor can acquire child file
        ok, _, _ = self.manager.acquire("Assets/Scripts/UI/Button.cs", agent="Cursor", reason="Fix click bug")
        self.assertTrue(ok)

        # Antigravity tries to lock parent directory Assets/Scripts/
        ok, conf, msg = self.manager.acquire("Assets/Scripts/", agent="Antigravity", reason="Refactor all scripts")
        self.assertFalse(ok)
        self.assertEqual(conf.agent, "Cursor")

    def test_reentrant_lease_renewal(self):
        ok, lock1, _ = self.manager.acquire("Assets/Player.cs", agent="Claude", ttl_minutes=10)
        self.assertTrue(ok)
        initial_acq = lock1.acquired_at

        # Same agent acquires again with longer TTL
        time.sleep(0.05)
        ok, lock2, msg = self.manager.acquire("Assets/Player.cs", agent="Claude", ttl_minutes=30)
        self.assertTrue(ok)
        self.assertIn("Lease renewed", msg)
        self.assertGreaterEqual(lock2.acquired_at, initial_acq)
        self.assertEqual(lock2.ttl_seconds, 1800)

    def test_release_permissions_and_force(self):
        self.manager.acquire("Assets/Player.cs", agent="Claude")

        # Cursor tries to release without force -> fails
        ok, msg = self.manager.release("Assets/Player.cs", agent="Cursor", force=False)
        self.assertFalse(ok)
        self.assertIn("PERMISSION DENIED", msg)

        # Cursor uses --force -> succeeds
        ok, msg = self.manager.release("Assets/Player.cs", agent="Cursor", force=True)
        self.assertTrue(ok)
        self.assertIn("RELEASED", msg)

        # File is now free
        is_free, _, _ = self.manager.check("Assets/Player.cs")
        self.assertTrue(is_free)

    def test_ttl_auto_expiration(self):
        # Acquire with 60 second minimum TTL, but artificially set acquired_at in past
        ok, lock, _ = self.manager.acquire("Assets/Temp.cs", agent="Claude", ttl_minutes=1)
        self.assertTrue(ok)

        # Artificially expire the lock
        locks = self.manager._load_locks()
        norm_key = self.manager._make_key("assets/temp.cs")
        locks[norm_key].acquired_at = time.time() - 3600  # 1 hour ago
        self.manager._save_locks(locks)

        # Check should now report FREE
        is_free, _, msg = self.manager.check("Assets/Temp.cs")
        self.assertTrue(is_free)
        self.assertEqual(msg, "FREE")

        # Another agent can acquire without collision
        ok, _, _ = self.manager.acquire("Assets/Temp.cs", agent="Antigravity")
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
