#!/usr/bin/env python3
"""SwarmLock CLI - Multi-Agent File & Directory Lock Coordinator.

Usage:
  python agent_lock.py acquire <path> --agent <name> [--reason <text>] [--ttl <minutes>]
  python agent_lock.py release <path> --agent <name> [--force]
  python agent_lock.py check <path>
  python agent_lock.py list
  python agent_lock.py clear [--agent <name>] [--all]
  python agent_lock.py gui [--minimized] [--browser]
"""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

# Ensure swarmlock package is on path
_HERE = Path(__file__).parent.resolve()
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from swarmlock.core import (
    LockManager,
    find_workspace_root,
    format_duration,
    normalize_target_path,
)
from swarmlock.server import DEFAULT_PORT


def is_gui_server_running(port: int = DEFAULT_PORT, timeout: float = 0.02) -> bool:
    """Performs a fast non-blocking socket check to localhost:port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        try:
            return s.connect_ex(("127.0.0.1", port)) == 0
        except OSError:
            return False


def ensure_gui_running(
    port: int = DEFAULT_PORT,
    workspace_root: Optional[Path] = None,
    minimized: bool = False
) -> None:
    """
    Launches the SwarmLock server and opens the dashboard directly in the browser
    if the server is not already active on port 7890.
    """
    if is_gui_server_running(port):
        return

    root = (workspace_root or find_workspace_root()).resolve()

    cmd = [
        sys.executable,
        "-m",
        "swarmlock.gui",
        "--port",
        str(port),
        "--browser",
    ]

    try:
        if sys.platform == "win32":
            CREATE_NEW_CONSOLE = 0x00000010
            subprocess.Popen(
                cmd,
                creationflags=CREATE_NEW_CONSOLE,
                cwd=str(root),
            )
        else:
            subprocess.Popen(
                cmd,
                start_new_session=True,
                close_fds=True,
                cwd=str(root),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        # Give server up to 2.5s to bind port
        t0 = time.time()
        while time.time() - t0 < 2.5:
            if is_gui_server_running(port, timeout=0.05):
                break
            time.sleep(0.05)
    except Exception:
        pass


ensure_gui_running_silently = ensure_gui_running


def resolve_agent_identity(agent: str, session: Optional[str] = None) -> str:
    """
    Resolves canonical agent:session identity.
    Priority:
    1. Explicit --session flag
    2. Environment variables: SWARMLOCK_SESSION_ID, CONVERSATION_ID, CLAUDE_SESSION_ID
    3. If session is present and agent is not already suffixed, produces '{agent}:{session}'
    4. Otherwise returns agent as-is
    """
    clean_agent = (agent or "").strip()
    clean_session = (session or "").strip()

    if not clean_session:
        clean_session = (
            os.environ.get("SWARMLOCK_SESSION_ID", "").strip()
            or os.environ.get("CONVERSATION_ID", "").strip()
            or os.environ.get("CLAUDE_SESSION_ID", "").strip()
        )

    if clean_session:
        # Avoid duplicate suffix e.g. Claude:chat1:chat1
        if clean_agent.endswith(f":{clean_session}"):
            return clean_agent
        return f"{clean_agent}:{clean_session}"

    return clean_agent


def api_request(endpoint: str, data: Optional[dict] = None) -> Optional[dict]:
    """Attempts fast local HTTP API call to running SwarmLock server."""
    try:
        import json
        import urllib.request
        url = f"http://127.0.0.1:{DEFAULT_PORT}{endpoint}"
        body = json.dumps(data).encode("utf-8") if data is not None else None
        headers = {"Content-Type": "application/json"} if body else {}
        req = urllib.request.Request(url, data=body, headers=headers)
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def cmd_acquire(args: argparse.Namespace, manager: LockManager) -> int:
    agent_id = resolve_agent_identity(args.agent, getattr(args, "session", None))

    # Fast path: If server is running on 7890, call API for instant SSE update!
    if is_gui_server_running() and not os.environ.get("SWARMLOCK_DATA_DIR"):
        res = api_request("/api/acquire", {
            "path": args.path,
            "agent": agent_id,
            "reason": args.reason or "",
            "ttl": args.ttl or 30,
            "workspace_root": str(manager.workspace_root),
        })
        if res:
            if res.get("success"):
                print(res.get("message", "ACQUIRED"))
                return 0
            else:
                print(res.get("message", "LOCKED"), file=sys.stderr)
                return 1

    # Server not yet running: auto-boot if enabled and write to global store
    if not args.no_auto_boot:
        ensure_gui_running_silently(workspace_root=manager.workspace_root)

    success, lock, message = manager.acquire(
        raw_path=args.path,
        agent=agent_id,
        reason=args.reason or "",
        ttl_minutes=args.ttl or 30,
    )

    if success:
        print(message)
        return 0
    else:
        print(message, file=sys.stderr)
        return 1


def cmd_release(args: argparse.Namespace, manager: LockManager) -> int:
    agent_id = resolve_agent_identity(args.agent, getattr(args, "session", None))

    # Fast path: If server is running on 7890, call API for instant SSE update!
    if is_gui_server_running() and not os.environ.get("SWARMLOCK_DATA_DIR"):
        res = api_request("/api/release", {
            "path": args.path,
            "agent": agent_id,
            "force": args.force,
            "workspace_root": str(manager.workspace_root),
        })
        if res:
            if res.get("success"):
                print(res.get("message", "RELEASED"))
                return 0
            else:
                print(res.get("message", "PERMISSION DENIED"), file=sys.stderr)
                return 1

    if not args.no_auto_boot:
        ensure_gui_running_silently(workspace_root=manager.workspace_root)

    success, message = manager.release(
        raw_path=args.path,
        agent=agent_id,
        force=args.force,
    )

    if success:
        print(message)
        return 0
    else:
        print(message, file=sys.stderr)
        return 1


def cmd_check(args: argparse.Namespace, manager: LockManager) -> int:
    if not args.no_auto_boot:
        ensure_gui_running_silently(workspace_root=manager.workspace_root)

    is_free, conf, message = manager.check(args.path)
    if is_free:
        print("FREE")
        return 0
    else:
        print(message)
        return 1


def cmd_list(args: argparse.Namespace, manager: LockManager) -> int:
    if not args.no_auto_boot:
        ensure_gui_running_silently(workspace_root=manager.workspace_root)

    locks = manager.list_locks()
    if not locks:
        print("No active locks. All files and directories are free.")
        return 0

    now = time.time()
    # Print formatted ASCII table with Workspace column
    headers = ["WORKSPACE", "TARGET PATH", "HOLDING AGENT", "REASON", "ELAPSED", "TTL LEFT"]
    rows = []
    for lk in locks:
        elapsed = format_duration(lk.time_elapsed(now))
        left = format_duration(lk.time_left(now))
        rows.append([
            lk.workspace or "Default",
            lk.path or "(Root)",
            lk.agent,
            (lk.reason[:28] + "...") if len(lk.reason) > 31 else (lk.reason or "-"),
            elapsed,
            left,
        ])

    col_widths = [len(h) for h in headers]
    for row in rows:
        for idx, val in enumerate(row):
            col_widths[idx] = max(col_widths[idx], len(str(val)))

    # Format separator
    sep = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
    header_line = "| " + " | ".join(f"{headers[i]:<{col_widths[i]}}" for i in range(len(headers))) + " |"

    print(sep)
    print(header_line)
    print(sep)
    for row in rows:
        row_line = "| " + " | ".join(f"{row[i]:<{col_widths[i]}}" for i in range(len(row))) + " |"
        print(row_line)
    print(sep)
    return 0


def cmd_clear(args: argparse.Namespace, manager: LockManager) -> int:
    if not args.all and not args.agent:
        print("Error: Specify --agent <name> or --all to clear locks.", file=sys.stderr)
        return 1

    agent_id = resolve_agent_identity(args.agent, getattr(args, "session", None)) if args.agent else None
    cleared = manager.clear(agent=agent_id if not args.all else None)
    target_str = f"agent/session '{agent_id}'" if agent_id and not args.all else "all agents"
    print(f"Cleared {cleared} active lock(s) for {target_str}.")
    return 0


def cmd_gui(args: argparse.Namespace, manager: LockManager) -> int:
    from swarmlock.gui import launch_gui
    launch_gui(
        port=args.port or DEFAULT_PORT,
        workspace_root=manager.workspace_root,
        minimized=args.minimized,
        browser_only=args.browser,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent_lock",
        description="SwarmLock - Multi-Agent File & Directory Locking System",
    )
    parser.add_argument(
        "--no-auto-boot",
        action="store_true",
        help="Disable automatic silent spawning of GUI dashboard",
    )

    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # acquire
    p_acq = subparsers.add_parser("acquire", help="Acquire a lock on a file or directory")
    p_acq.add_argument("path", help="Path to target file or directory")
    p_acq.add_argument("--agent", "-a", required=True, help="Name of agent acquiring the lock")
    p_acq.add_argument("--session", "-s", default=None, help="Unique conversation, chat, or sub-agent session ID")
    p_acq.add_argument("--reason", "-r", default="", help="Reason / task description for lock")
    p_acq.add_argument("--ttl", "-t", type=int, default=30, help="TTL in minutes (default: 30)")

    # release
    p_rel = subparsers.add_parser("release", help="Release a lock on a file or directory")
    p_rel.add_argument("path", help="Path to target file or directory")
    p_rel.add_argument("--agent", "-a", required=True, help="Name of agent releasing the lock")
    p_rel.add_argument("--session", "-s", default=None, help="Unique conversation, chat, or sub-agent session ID")
    p_rel.add_argument("--force", "-f", action="store_true", help="Force release regardless of owner")

    # check
    p_chk = subparsers.add_parser("check", help="Check if a path is free or locked")
    p_chk.add_argument("path", help="Path to target file or directory")

    # list
    p_lst = subparsers.add_parser("list", help="List all active locks in terminal table")

    # clear
    p_clr = subparsers.add_parser("clear", help="Clear locks in batch")
    p_clr.add_argument("--agent", "-a", default=None, help="Clear locks only for specific agent")
    p_clr.add_argument("--session", "-s", default=None, help="Specific session ID to clear")
    p_clr.add_argument("--all", action="store_true", help="Clear all active locks")

    # gui
    p_gui = subparsers.add_parser("gui", help="Launch or view desktop GUI dashboard")
    p_gui.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to run/connect")
    p_gui.add_argument("--minimized", action="store_true", help="Launch window minimized")
    p_gui.add_argument("--browser", action="store_true", help="Open in web browser instead of desktop window")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    manager = LockManager()

    if args.subcommand == "acquire":
        return cmd_acquire(args, manager)
    elif args.subcommand == "release":
        return cmd_release(args, manager)
    elif args.subcommand == "check":
        return cmd_check(args, manager)
    elif args.subcommand == "list":
        return cmd_list(args, manager)
    elif args.subcommand == "clear":
        return cmd_clear(args, manager)
    elif args.subcommand == "gui":
        return cmd_gui(args, manager)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
