"""Desktop GUI Launcher for SwarmLock.

Opens a native desktop dashboard window using pywebview with clean shutdown hooks.
Supports graceful browser fallback and headless background mode.
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Optional

from .core import find_workspace_root
from .server import DEFAULT_PORT, SwarmLockServer


def is_port_in_use(port: int, host: str = "127.0.0.1", timeout: float = 0.05) -> bool:
    """Checks whether the specified port is already actively listening."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        try:
            return s.connect_ex((host, port)) == 0
        except OSError:
            return False


def launch_gui(
    port: int = DEFAULT_PORT,
    workspace_root: Optional[Path] = None,
    minimized: bool = False,
    no_focus: bool = False,
    browser_only: bool = False,
    headless: bool = False,
) -> None:
    """
    Starts the SwarmLock backend (if not already running) and opens
    the desktop GUI window or browser.
    """
    root = (workspace_root or find_workspace_root()).resolve()
    url = f"http://127.0.0.1:{port}"

    # 1. Start background server if port is not yet active
    server_instance: Optional[SwarmLockServer] = None
    if not is_port_in_use(port):
        server_instance = SwarmLockServer(workspace_root=root, port=port)
        server_instance.start(block=False)

        # Wait up to 3 seconds for port to open
        t0 = time.time()
        while time.time() - t0 < 3.0:
            if is_port_in_use(port):
                break
            time.sleep(0.05)

    if headless:
        print(f"[SwarmLock] Server running in headless mode on {url}. Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1.0)
        except KeyboardInterrupt:
            if server_instance:
                server_instance.stop()
        return

    # 2. Browser fallback mode
    if browser_only:
        print(f"[SwarmLock] Opening browser dashboard at {url}...")
        webbrowser.open(url)
        if server_instance:
            try:
                while True:
                    time.sleep(1.0)
            except KeyboardInterrupt:
                server_instance.stop()
        return

    # 3. Native desktop window using pywebview
    try:
        import webview

        def on_closed():
            """Clean exit handler: stop server when desktop window closes."""
            if server_instance:
                server_instance.stop()
            # Terminate python process cleanly
            os._exit(0)

        window = webview.create_window(
            title="SwarmLock — Multi-Agent File Lock Coordinator",
            url=url,
            width=1160,
            height=720,
            min_size=(760, 480),
            background_color="#090d16",
            focus=not no_focus,
            minimized=minimized,
            resizable=True,
        )

        window.events.closed += on_closed

        # Start webview GUI loop
        webview.start()

    except ImportError:
        # Fallback to browser if pywebview is not installed
        print(f"[SwarmLock] 'pywebview' not available. Opening system browser at {url}...")
        webbrowser.open(url)
        if server_instance:
            try:
                while True:
                    time.sleep(1.0)
            except KeyboardInterrupt:
                server_instance.stop()
    except Exception as e:
        print(f"[SwarmLock] Error launching desktop window: {e}. Opening browser fallback...")
        webbrowser.open(url)
        if server_instance:
            try:
                while True:
                    time.sleep(1.0)
            except KeyboardInterrupt:
                server_instance.stop()


def main():
    parser = argparse.ArgumentParser(description="SwarmLock Desktop GUI & Server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to run/connect (default: 7890)")
    parser.add_argument("--minimized", action="store_true", help="Start the desktop window minimized")
    parser.add_argument("--no-focus", action="store_true", help="Do not steal active keyboard focus on boot")
    parser.add_argument("--browser", action="store_true", help="Open in default web browser instead of desktop window")
    parser.add_argument("--headless", action="store_true", help="Run background server without any UI window")
    parser.add_argument("--workspace", type=str, default=None, help="Custom workspace root directory")

    args = parser.parse_args()
    root_path = Path(args.workspace) if args.workspace else None
    launch_gui(
        port=args.port,
        workspace_root=root_path,
        minimized=args.minimized,
        no_focus=args.no_focus,
        browser_only=args.browser,
        headless=args.headless,
    )


if __name__ == "__main__":
    main()
