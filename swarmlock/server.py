"""HTTP & Server-Sent Events (SSE) server for SwarmLock.

Provides REST API endpoints for CLI & GUI interactions,
serves the dark-mode dashboard web app, and streams real-time updates.
"""

from __future__ import annotations

import json
import mimetypes
import os
import queue
import sys
import threading
import time
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from .core import LockManager, find_workspace_root

DEFAULT_PORT = 7890


class SwarmLockServer:
    """Threaded HTTP and SSE server managing the SwarmLock dashboard and API."""

    def __init__(self, workspace_root: Optional[Path] = None, port: int = DEFAULT_PORT):
        self.workspace_root = (workspace_root or find_workspace_root()).resolve()
        self.port = port
        self.lock_manager = LockManager(self.workspace_root)
        self.static_dir = Path(__file__).parent / "static"
        self.server: Optional[ThreadingHTTPServer] = None
        self.server_thread: Optional[threading.Thread] = None
        self.sweep_thread: Optional[threading.Thread] = None
        self.running = False
        self._sse_clients: list[queue.Queue] = []
        self._sse_lock = threading.Lock()
        self._last_lock_hash = ""

    def register_sse_client(self) -> queue.Queue:
        q = queue.Queue(maxsize=30)
        with self._sse_lock:
            self._sse_clients.append(q)
        return q

    def unregister_sse_client(self, q: queue.Queue) -> None:
        with self._sse_lock:
            if q in self._sse_clients:
                self._sse_clients.remove(q)

    def broadcast_update(self, event_type: str = "update") -> None:
        """Broadcasts current state to all connected SSE clients."""
        try:
            locks = [l.to_dict() for l in self.lock_manager.list_locks()]
            payload = json.dumps({"event": event_type, "locks": locks, "timestamp": time.time()})
            message = f"event: {event_type}\ndata: {payload}\n\n"
            with self._sse_lock:
                for q in list(self._sse_clients):
                    try:
                        q.put_nowait(message)
                    except queue.Full:
                        pass
        except Exception:
            pass

    def _sweep_loop(self) -> None:
        """Periodically sweeps expired locks and broadcasts changes."""
        while self.running:
            time.sleep(2.0)
            try:
                current_locks = self.lock_manager.list_locks()
                current_hash = ",".join(f"{l.norm_path}:{l.expires_at:.0f}" for l in current_locks)
                if current_hash != self._last_lock_hash:
                    self._last_lock_hash = current_hash
                    self.broadcast_update("sweep")
            except Exception:
                pass

    def start(self, block: bool = False) -> None:
        """Starts the HTTP server."""
        parent_self = self

        class Handler(SimpleHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                # Suppress noisy standard HTTP access logs
                pass

            def end_headers(self) -> None:
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                super().end_headers()

            def do_OPTIONS(self) -> None:
                self.send_response(HTTPStatus.OK)
                self.end_headers()

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                path = parsed.path

                if path in ("/", "/index.html"):
                    self._serve_file(parent_self.static_dir / "index.html", "text/html")
                elif path.startswith("/static/"):
                    rel = path[len("/static/"):]
                    self._serve_file(parent_self.static_dir / rel)
                elif path == "/api/locks":
                    self._handle_get_locks()
                elif path == "/api/status":
                    self._handle_get_status()
                elif path == "/api/events":
                    self._handle_sse_stream()
                else:
                    self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

            def do_POST(self) -> None:
                parsed = urlparse(self.path)
                path = parsed.path

                content_len = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
                try:
                    data = json.loads(body) if body else {}
                except json.JSONDecodeError:
                    data = {}

                if path == "/api/acquire":
                    self._handle_post_acquire(data)
                elif path == "/api/release":
                    self._handle_post_release(data)
                elif path == "/api/force-unlock":
                    self._handle_post_force_unlock(data)
                elif path == "/api/clear":
                    self._handle_post_clear(data)
                elif path == "/api/shutdown":
                    self._handle_post_shutdown()
                else:
                    self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

            def _serve_file(self, file_path: Path, forced_type: Optional[str] = None) -> None:
                if not file_path.exists() or not file_path.is_file():
                    self.send_error(HTTPStatus.NOT_FOUND, "File Not Found")
                    return
                content_type = forced_type or mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
                data = file_path.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", f"{content_type}; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(data)

            def _json_response(self, obj: Any, status: int = 200) -> None:
                payload = json.dumps(obj).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def _handle_get_locks(self) -> None:
                locks = [l.to_dict() for l in parent_self.lock_manager.list_locks()]
                self._json_response({"success": True, "locks": locks, "count": len(locks)})

            def _handle_get_status(self) -> None:
                locks = parent_self.lock_manager.list_locks()
                self._json_response({
                    "status": "online",
                    "port": parent_self.port,
                    "pid": os.getpid(),
                    "workspace": str(parent_self.workspace_root),
                    "active_locks": len(locks),
                    "timestamp": time.time(),
                })

            def _handle_post_acquire(self, data: dict[str, Any]) -> None:
                target_path = data.get("path", "")
                agent = data.get("agent", "Unknown")
                reason = data.get("reason", "")
                ttl_minutes = int(data.get("ttl", data.get("ttl_minutes", 30)))
                ws_root = data.get("workspace_root")
                mgr = LockManager(Path(ws_root) if ws_root else parent_self.workspace_root)

                success, lock, msg = mgr.acquire(
                    target_path, agent=agent, reason=reason, ttl_minutes=ttl_minutes
                )
                parent_self.broadcast_update("acquire")
                status_code = 200 if success else 409
                self._json_response({
                    "success": success,
                    "message": msg,
                    "lock": lock.to_dict() if lock else None,
                }, status=status_code)

            def _handle_post_release(self, data: dict[str, Any]) -> None:
                target_path = data.get("path", "")
                agent = data.get("agent", "")
                force = bool(data.get("force", False))
                ws_root = data.get("workspace_root")
                mgr = LockManager(Path(ws_root) if ws_root else parent_self.workspace_root)

                success, msg = mgr.release(target_path, agent=agent, force=force)
                parent_self.broadcast_update("release")
                status_code = 200 if success else 403
                self._json_response({"success": success, "message": msg}, status=status_code)

            def _handle_post_force_unlock(self, data: dict[str, Any]) -> None:
                target_path = data.get("path", "")
                operator = data.get("operator", "GUI-User")
                ws_root = data.get("workspace_root")
                mgr = LockManager(Path(ws_root) if ws_root else parent_self.workspace_root)

                success, msg = mgr.force_release(target_path, operator=operator)
                parent_self.broadcast_update("force-unlock")
                self._json_response({"success": success, "message": msg})

            def _handle_post_clear(self, data: dict[str, Any]) -> None:
                agent = data.get("agent")
                ws_root = data.get("workspace_root")
                mgr = LockManager(Path(ws_root) if ws_root else parent_self.workspace_root)
                cleared = mgr.clear(agent=agent)
                parent_self.broadcast_update("clear")
                self._json_response({"success": True, "cleared_count": cleared})

            def _handle_post_shutdown(self) -> None:
                self._json_response({"success": True, "message": "Server shutting down"})
                threading.Thread(target=parent_self.stop, daemon=True).start()

            def _handle_sse_stream(self) -> None:
                """Streams Server-Sent Events (SSE) to connected clients."""
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()

                client_q = parent_self.register_sse_client()

                # Send initial state
                initial_locks = [l.to_dict() for l in parent_self.lock_manager.list_locks()]
                initial_payload = json.dumps({"event": "initial", "locks": initial_locks, "timestamp": time.time()})
                try:
                    self.wfile.write(f"event: initial\ndata: {initial_payload}\n\n".encode("utf-8"))
                    self.wfile.flush()
                except Exception:
                    parent_self.unregister_sse_client(client_q)
                    return

                try:
                    while parent_self.running:
                        try:
                            msg = client_q.get(timeout=10.0)
                            self.wfile.write(msg.encode("utf-8"))
                            self.wfile.flush()
                        except queue.Empty:
                            # Send heartbeat comment to keep connection alive
                            self.wfile.write(b": heartbeat\n\n")
                            self.wfile.flush()
                except (ConnectionResetError, BrokenPipeError, OSError):
                    pass
                finally:
                    parent_self.unregister_sse_client(client_q)

        self.server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        self.running = True

        # Write server runtime metadata to global hub ~/.swarmlock/server.json
        meta_file = parent_self.lock_manager.data_dir / "server.json"
        meta_file.parent.mkdir(parents=True, exist_ok=True)
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump({
                "pid": os.getpid(),
                "port": self.port,
                "url": f"http://127.0.0.1:{self.port}",
                "started_at": time.time(),
                "workspace": str(self.workspace_root)
            }, f, indent=2)

        # Start sweep thread
        self.sweep_thread = threading.Thread(target=self._sweep_loop, daemon=True)
        self.sweep_thread.start()

        if block:
            try:
                self.server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                self.stop()
        else:
            self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.server_thread.start()

    def stop(self) -> None:
        """Stops the server cleanly."""
        self.running = False
        if self.server:
            try:
                self.server.shutdown()
                self.server.server_close()
            except Exception:
                pass
            self.server = None

        meta_file = self.workspace_root / ".swarmlock" / "server.json"
        if meta_file.exists():
            try:
                meta_file.unlink()
            except OSError:
                pass


def run_standalone_server(port: int = DEFAULT_PORT) -> None:
    """Entry point for running the server directly."""
    print(f"[SwarmLock] Starting server on http://127.0.0.1:{port} (PID: {os.getpid()})...")
    server = SwarmLockServer(port=port)
    server.start(block=True)


if __name__ == "__main__":
    port_arg = int(os.environ.get("SWARMLOCK_PORT", DEFAULT_PORT))
    run_standalone_server(port=port_arg)
