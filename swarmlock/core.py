"""Core locking engine for SwarmLock.

Handles hierarchical path resolution, conflict detection, TTL tracking,
persistence to .swarmlock/locks.json, and audit logging.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl


@dataclass
class Lock:
    """Represents an active lock record."""
    path: str              # Normalized display path relative to workspace root
    norm_path: str         # Lowercase normalized POSIX path for conflict checks
    is_dir: bool           # True if target is a directory
    agent: str             # Name/ID of agent holding the lock
    reason: str            # Purpose of lock (e.g. "Refactoring UI")
    acquired_at: float     # Unix timestamp of acquisition
    ttl_seconds: int       # Time-to-live in seconds
    pid: int = 0           # Process ID of acquiring process
    workspace: str = ""    # Project / repository name (e.g. "SwarmLock", "MyGame")
    workspace_root: str = "" # Canonical workspace root directory path

    @property
    def expires_at(self) -> float:
        return self.acquired_at + self.ttl_seconds

    def is_expired(self, now: Optional[float] = None) -> bool:
        t = now if now is not None else time.time()
        return t >= self.expires_at

    def time_left(self, now: Optional[float] = None) -> float:
        t = now if now is not None else time.time()
        return max(0.0, self.expires_at - t)

    def time_elapsed(self, now: Optional[float] = None) -> float:
        t = now if now is not None else time.time()
        return max(0.0, t - self.acquired_at)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["expires_at"] = self.expires_at
        d["time_left"] = self.time_left()
        d["time_elapsed"] = self.time_elapsed()
        d["is_expired"] = self.is_expired()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Lock":
        return cls(
            path=data.get("path", ""),
            norm_path=data.get("norm_path", ""),
            is_dir=bool(data.get("is_dir", False)),
            agent=data.get("agent", "unknown"),
            reason=data.get("reason", ""),
            acquired_at=float(data.get("acquired_at", time.time())),
            ttl_seconds=int(data.get("ttl_seconds", 1800)),
            pid=int(data.get("pid", 0)),
            workspace=data.get("workspace", ""),
            workspace_root=data.get("workspace_root", ""),
        )


class InterProcessLock:
    """Cross-platform inter-process file lock context manager."""

    def __init__(self, lockfile_path: Path, timeout: float = 5.0):
        self.lockfile_path = lockfile_path
        self.timeout = timeout
        self.file_handle = None

    def __enter__(self):
        self.lockfile_path.parent.mkdir(parents=True, exist_ok=True)
        self.file_handle = open(self.lockfile_path, "a+")
        start_time = time.time()
        while True:
            try:
                if sys.platform == "win32":
                    msvcrt.locking(self.file_handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(self.file_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except (BlockingIOError, OSError, PermissionError):
                if time.time() - start_time > self.timeout:
                    # Timeout reached; continue with best-effort to avoid total deadlocks
                    return self
                time.sleep(0.01)

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.file_handle:
            try:
                if sys.platform == "win32":
                    try:
                        self.file_handle.seek(0)
                        msvcrt.locking(self.file_handle.fileno(), msvcrt.LK_UNLCK, 1)
                    except OSError:
                        pass
                else:
                    try:
                        fcntl.flock(self.file_handle.fileno(), fcntl.LOCK_UN)
                    except OSError:
                        pass
            finally:
                self.file_handle.close()
                self.file_handle = None


def find_workspace_root(start_dir: Optional[Path] = None) -> Path:
    """Finds the root directory of the workspace or git repository."""
    current = (start_dir or Path.cwd()).resolve()
    home = Path.home().resolve()
    for parent in [current] + list(current.parents):
        if (parent / ".git").exists():
            return parent
        # Only treat local .swarmlock as workspace root if it is NOT the global ~/.swarmlock hub
        if (parent / ".swarmlock").is_dir() and parent.resolve() != home:
            return parent
    return current


def normalize_target_path(
    raw_path: str,
    workspace_root: Optional[Path] = None
) -> tuple[str, str, bool]:
    """
    Normalizes a path relative to workspace root.
    Returns:
        (display_path, norm_path, is_dir)
        - display_path: Clean POSIX-style relative path with original case
        - norm_path: Lowercased POSIX path for conflict checks
        - is_dir: Boolean indicating directory status
    """
    if not raw_path or raw_path.strip() in (".", "./", ".\\"):
        return ("", "", True)

    clean_raw = raw_path.strip().replace("\\", "/")
    is_dir_hint = clean_raw.endswith("/")

    root = (workspace_root or find_workspace_root()).resolve()
    target = Path(clean_raw)

    if not target.is_absolute():
        target = (root / target).resolve()
    else:
        target = target.resolve()

    # Determine if target is a directory on disk or ends with /
    is_directory = is_dir_hint or target.is_dir()

    # Compute path relative to workspace root if possible
    try:
        rel_path = target.relative_to(root)
        display_path = rel_path.as_posix()
    except ValueError:
        # Outside workspace root; use target POSIX path
        display_path = target.as_posix()

    if display_path == ".":
        display_path = ""

    norm_path = display_path.lower()
    return (display_path, norm_path, is_directory)


def paths_conflict(path_a: str, path_b: str) -> bool:
    """
    Evaluates whether two normalized paths conflict hierarchically.
    Conflict occurs if:
    1. Paths are identical
    2. Either path is the root ("")
    3. path_a is an ancestor of path_b (path_b inside path_a)
    4. path_b is an ancestor of path_a (path_a inside path_b)
    """
    if path_a == path_b:
        return True
    if path_a == "" or path_b == "":
        return True
    return path_a.startswith(path_b + "/") or path_b.startswith(path_a + "/")


def format_duration(seconds: float) -> str:
    """Formats seconds into human readable duration e.g. '12m 30s' or '45s'."""
    s = int(round(seconds))
    if s < 60:
        return f"{s}s"
    m = s // 60
    rem_s = s % 60
    if m < 60:
        return f"{m}m {rem_s}s" if rem_s > 0 else f"{m}m"
    h = m // 60
    rem_m = m % 60
    return f"{h}h {rem_m}m"


GLOBAL_SWARMLOCK_DIR = (Path.home() / ".swarmlock").resolve()


class LockManager:
    """
    Thread-safe & process-safe manager for file and directory locks.
    Defaults to global machine-wide registry at ~/.swarmlock/locks.json.
    """

    def __init__(
        self,
        workspace_root: Optional[Path] = None,
        data_dir: Optional[Path] = None,
        use_global: bool = True
    ):
        self.workspace_root = (workspace_root or find_workspace_root()).resolve()
        self.workspace_name = self.workspace_root.name or "Default"
        if data_dir is not None:
            self.data_dir = data_dir.resolve()
        elif os.environ.get("SWARMLOCK_DATA_DIR"):
            self.data_dir = Path(os.environ["SWARMLOCK_DATA_DIR"]).resolve()
        elif use_global:
            self.data_dir = GLOBAL_SWARMLOCK_DIR
        else:
            self.data_dir = self.workspace_root / ".swarmlock"

        self.state_file = self.data_dir / "locks.json"
        self.lock_file = self.data_dir / "locks.lock"
        self.log_file = self.data_dir / "events.log"
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _same_workspace(self, ws1: Optional[str], ws2: Optional[str]) -> bool:
        if not ws1 or not ws2:
            return True
        try:
            return Path(ws1).resolve().as_posix().lower() == Path(ws2).resolve().as_posix().lower()
        except Exception:
            return ws1.lower() == ws2.lower()

    def _make_key(self, norm_path: str, ws_root: Optional[str] = None) -> str:
        ws = (ws_root or self.workspace_root.as_posix()).lower()
        return f"{ws}::{norm_path}"

    def _log_event(self, action: str, path: str, agent: str, reason: str = "", extra: str = "") -> None:
        """Appends an event to the audit log."""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        ws_tag = f"[{self.workspace_name}] "
        entry = f"[{timestamp}] {action.upper():<12} ws='{self.workspace_name}' path='{path}' agent='{agent}' reason='{reason}' {extra}\n"
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(entry)
        except Exception:
            pass

    def _load_locks(self) -> dict[str, Lock]:
        """Loads locks from disk, automatically purging expired ones."""
        if not self.state_file.exists():
            return {}

        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            now = time.time()
            locks = {}
            for k, v in data.items():
                lock = Lock.from_dict(v)
                if not lock.is_expired(now):
                    key = k if "::" in k else f"{(lock.workspace_root or self.workspace_root.as_posix()).lower()}::{lock.norm_path}"
                    locks[key] = lock
                else:
                    self._log_event("EXPIRED", lock.path, lock.agent, lock.reason, f"elapsed={format_duration(lock.time_elapsed(now))}")
            return locks
        except Exception:
            return {}

    def _save_locks(self, locks: dict[str, Lock]) -> None:
        """Atomically saves locks to disk."""
        data = {k: lock.to_dict() for k, lock in locks.items()}
        temp_file = self.data_dir / f"locks.tmp.{os.getpid()}.{time.time_ns()}"
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(temp_file, self.state_file)
        finally:
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except OSError:
                    pass

    def _acquire_once(
        self,
        raw_path: str,
        agent: str,
        reason: str = "",
        ttl_minutes: int = 30,
    ) -> tuple[bool, Optional[Lock], str]:
        display_path, norm_path, is_dir = normalize_target_path(raw_path, self.workspace_root)
        ttl_seconds = max(60, int(ttl_minutes * 60))
        my_ws = self.workspace_root.as_posix().lower()
        lock_key = self._make_key(norm_path)

        with InterProcessLock(self.lock_file):
            locks = self._load_locks()
            now = time.time()

            # Check for conflict with existing active locks in the same workspace
            for key, existing in list(locks.items()):
                # Cross-project isolation: only check conflict if within the same workspace!
                if not self._same_workspace(existing.workspace_root, my_ws):
                    continue

                if paths_conflict(norm_path, existing.norm_path):
                    # Check if exact lock held by the same agent -> lease renewal
                    if norm_path == existing.norm_path and existing.agent.strip().lower() == agent.strip().lower():
                        existing.acquired_at = now
                        existing.ttl_seconds = ttl_seconds
                        if reason:
                            existing.reason = reason
                        self._save_locks(locks)
                        self._log_event("RENEWED", display_path, agent, reason, f"ttl={ttl_minutes}m")
                        return True, existing, f"Lease renewed for '[{self.workspace_name}] {display_path}' by '{agent}' (expires in {format_duration(existing.time_left(now))})"

                    # Otherwise, true conflict!
                    left_str = format_duration(existing.time_left(now))
                    rel_type = "same file" if norm_path == existing.norm_path else ("parent directory" if norm_path.startswith(existing.norm_path + "/") else "child item")
                    msg = (
                        f"LOCKED: '[{self.workspace_name}] {display_path}' conflicts with {rel_type} '{existing.path}' "
                        f"held by agent '{existing.agent}' "
                        f"(Reason: '{existing.reason or 'None'}'; Expires in {left_str})"
                    )
                    return False, existing, msg

            # No conflicts found - grant lock
            new_lock = Lock(
                path=display_path,
                norm_path=norm_path,
                is_dir=is_dir,
                agent=agent,
                reason=reason,
                acquired_at=now,
                ttl_seconds=ttl_seconds,
                pid=os.getpid(),
                workspace=self.workspace_name,
                workspace_root=self.workspace_root.as_posix(),
            )
            locks[lock_key] = new_lock
            self._save_locks(locks)
            self._log_event("ACQUIRED", display_path, agent, reason, f"ttl={ttl_minutes}m")
            return True, new_lock, f"ACQUIRED: '[{self.workspace_name}] {display_path}' locked by '{agent}' (TTL: {ttl_minutes}m)"

    def acquire(
        self,
        raw_path: str,
        agent: str,
        reason: str = "",
        ttl_minutes: int = 30,
        timeout: float = 0.0,
        poll_interval: float = 0.25,
    ) -> tuple[bool, Optional[Lock], str]:
        """
        Attempts to acquire a lock on raw_path.
        If timeout > 0, waits up to timeout seconds for conflicting locks to clear.
        Returns:
            (success: bool, lock: Optional[Lock], message: str)
        """
        start_time = time.time()
        while True:
            success, lock, msg = self._acquire_once(
                raw_path=raw_path,
                agent=agent,
                reason=reason,
                ttl_minutes=ttl_minutes,
            )
            if success or timeout <= 0.0:
                return success, lock, msg

            elapsed = time.time() - start_time
            if elapsed >= timeout:
                return False, lock, f"{msg} (Timed out after {timeout:.1f}s waiting for release)"

            sleep_time = min(poll_interval, timeout - elapsed)
            time.sleep(max(0.01, sleep_time))

    def release(
        self,
        raw_path: str,
        agent: str,
        force: bool = False
    ) -> tuple[bool, str]:
        """
        Releases a lock on raw_path.
        Returns:
            (success: bool, message: str)
        """
        display_path, norm_path, _ = normalize_target_path(raw_path, self.workspace_root)
        my_ws = self.workspace_root.as_posix().lower()
        lock_key = self._make_key(norm_path)

        with InterProcessLock(self.lock_file):
            locks = self._load_locks()

            # Find matching lock in current workspace
            existing = locks.get(lock_key)
            if not existing:
                for k, lk in list(locks.items()):
                    if self._same_workspace(lk.workspace_root, my_ws) and (lk.path == display_path or lk.norm_path == norm_path):
                        existing = lk
                        lock_key = k
                        break

            if not existing:
                return True, f"RELEASED: '{display_path}' was not locked."

            # Check agent ownership
            existing_agent = existing.agent.strip().lower()
            candidate_agent = agent.strip().lower()
            is_owner = (existing_agent == candidate_agent)

            if not is_owner and not force:
                if existing_agent.startswith(candidate_agent + ":"):
                    session_name = existing.agent.split(":", 1)[1]
                    return (
                        False,
                        f"PERMISSION DENIED: '{display_path}' is held by session '{existing.agent}'. "
                        f"Pass --session '{session_name}' or use --force."
                    )
                return (
                    False,
                    f"PERMISSION DENIED: '{display_path}' is held by agent '{existing.agent}'. "
                    f"Use --force to override."
                )

            # Remove lock
            del locks[lock_key]
            self._save_locks(locks)
            action_type = "FORCE_RELEASE" if force and not is_owner else "RELEASE"
            self._log_event(action_type, existing.path, agent, existing.reason)
            return True, f"RELEASED: Lock on '[{self.workspace_name}] {existing.path}' has been released."

    def force_release(self, raw_path: str, operator: str = "Admin") -> tuple[bool, str]:
        """Forcefully releases a lock regardless of holder."""
        return self.release(raw_path, agent=operator, force=True)

    def _check_once(self, raw_path: str) -> tuple[bool, Optional[Lock], str]:
        display_path, norm_path, _ = normalize_target_path(raw_path, self.workspace_root)
        my_ws = self.workspace_root.as_posix().lower()

        with InterProcessLock(self.lock_file):
            locks = self._load_locks()
            now = time.time()

            for existing in locks.values():
                if not self._same_workspace(existing.workspace_root, my_ws):
                    continue

                if paths_conflict(norm_path, existing.norm_path):
                    left_str = format_duration(existing.time_left(now))
                    return (
                        False,
                        existing,
                        f"LOCKED by '{existing.agent}' (Target: '[{existing.workspace}] {existing.path}', Reason: '{existing.reason or 'None'}', Expires in {left_str})"
                    )

            return True, None, "FREE"

    def check(
        self,
        raw_path: str,
        timeout: float = 0.0,
        poll_interval: float = 0.25,
    ) -> tuple[bool, Optional[Lock], str]:
        """
        Checks whether raw_path is free to lock or currently blocked in current workspace.
        If timeout > 0, waits up to timeout seconds for path to become free.
        Returns:
            (is_free: bool, conflicting_lock: Optional[Lock], message: str)
        """
        start_time = time.time()
        while True:
            is_free, conf, msg = self._check_once(raw_path)
            if is_free or timeout <= 0.0:
                return is_free, conf, msg

            elapsed = time.time() - start_time
            if elapsed >= timeout:
                return False, conf, f"{msg} (Timed out after {timeout:.1f}s waiting for path to be free)"

            sleep_time = min(poll_interval, timeout - elapsed)
            time.sleep(max(0.01, sleep_time))

    def list_locks(self, workspace_filter: Optional[str] = None) -> list[Lock]:
        """Returns active locks. If workspace_filter is None, returns ALL locks across all projects."""
        with InterProcessLock(self.lock_file):
            locks = self._load_locks()
            self._save_locks(locks)  # Persist purge of any expired locks
            result = []
            for lk in locks.values():
                if workspace_filter:
                    if not self._same_workspace(lk.workspace_root, workspace_filter):
                        continue
                result.append(lk)
            return sorted(result, key=lambda l: l.acquired_at)

    def clear(self, agent: Optional[str] = None, current_workspace_only: bool = False) -> int:
        """Clears locks. If agent is provided, clears locks held by that agent or agent session."""
        my_ws = self.workspace_root.as_posix().lower()
        with InterProcessLock(self.lock_file):
            locks = self._load_locks()
            count = 0
            remaining = {}
            for k, lk in locks.items():
                if current_workspace_only and not self._same_workspace(lk.workspace_root, my_ws):
                    remaining[k] = lk
                    continue

                if agent is None:
                    match = True
                else:
                    la = lk.agent.strip().lower()
                    qa = agent.strip().lower()
                    match = (la == qa or la.startswith(qa + ":") or la.startswith(qa + "-"))

                if match:
                    count += 1
                    self._log_event("CLEARED", lk.path, agent or "all", lk.reason)
                else:
                    remaining[k] = lk
            self._save_locks(remaining)
            return count
