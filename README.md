# SwarmLock 🔒

A standalone, engine-agnostic **Multi-Agent File Locking System** with a real-time Python desktop GUI and a lightning-fast CLI tool.

Designed for teams running multiple AI coding agents (**Claude Code**, **Antigravity**, **Cursor**, **Windsurf**, **Codex**) working concurrently across different chats and IDE windows on the same codebase (Unity, Unreal Engine, Godot, or standard software).

---

## 🚀 Key Features

- **⚡ Lazy Initialization (Silent Auto-Boot)**: When an agent runs any lock command (e.g. `acquire`), the CLI performs an internal 1ms socket check to `localhost:7890`. If the dashboard is not running, it silently spawns the GUI in the background using Windows `SW_SHOWNOACTIVATE` so it **NEVER steals keyboard focus** from the user.
- **🛡️ Zero Token Overhead**: The agent only runs a single standard shell command (`python agent_lock.py acquire ...`). No extra status checks or MCP setup required.
- **📂 Hierarchical Directory Locking**: Locking a directory (e.g. `Assets/Scripts/UI/`) automatically blocks child file locks (e.g. `Assets/Scripts/UI/Button.cs`), and vice versa.
- **⏳ Stale Lock Auto-Expiration (TTL)**: Default 30 minutes. If an agent crashes or a chat closes, stale locks expire automatically.
- **🖥️ Standalone Desktop GUI**: A clean, dark-mode desktop window built with `pywebview` (backed by Edge WebView2 on Windows) with real-time live refresh via Server-Sent Events (SSE) and interactive Force Unlock controls.
- **🔄 Opportunistic Pivot Rule**: Pre-configured agent rules in `AGENT_RULES.md` directing AI agents to pivot to other unblocked files rather than waiting idle when a lock collision occurs.

---

## 📦 Installation & Setup

1. **Prerequisites**: Python 3.9+
2. **Install Dependencies**:
```bash
pip install -r requirements.txt
```
*(Only `pywebview` is required for the native desktop window. If `pywebview` is omitted, SwarmLock automatically falls back to your default web browser.)*

---

## 💻 CLI Quickstart

### 1. Acquire a Lock
```bash
python agent_lock.py acquire Assets/Scripts/UI/Button.cs --agent "Claude" --reason "Refactoring button states"
```
- If free: prints confirmation and exits with code `0`.
- If held: prints who holds it and exits with code `1`.

### 2. Check Lock Status
```bash
python agent_lock.py check Assets/Scripts/UI/Button.cs
```
- Returns `FREE` (exit `0`) or `LOCKED by <agent>` (exit `1`).

### 3. Release a Lock
```bash
python agent_lock.py release Assets/Scripts/UI/Button.cs --agent "Claude"
```

### 4. List Active Locks
```bash
python agent_lock.py list
```
Displays a clean terminal table:
```
+----------------------------+---------------+---------------------------+---------+----------+
| TARGET PATH                | HOLDING AGENT | REASON                    | ELAPSED | TTL LEFT |
+----------------------------+---------------+---------------------------+---------+----------+
| Assets/Scripts/UI/Button.cs| Claude        | Refactoring button states | 2m 14s  | 27m 46s  |
+----------------------------+---------------+---------------------------+---------+----------+
```

### 5. Launch Desktop Dashboard Directly
```bash
python agent_lock.py gui
```
Optional flags:
- `--minimized`: Launch minimized in system taskbar
- `--browser`: Open in default web browser instead of native desktop window

---

## 🤖 Agent Integration (`SwarmLockSkill.md`)

Add the rules from [SwarmLockSkill.md](file:///c:/Users/imama/Desktop/SwarmLock/SwarmLockSkill.md) into your project's agent instructions:
- **Cursor**: Paste into `.cursorrules` or `.cursor/rules/swarmlock.mdc`
- **Claude Code**: Paste into `CLAUDE.md`
- **Antigravity**: Paste into `.gemini/rules.md` or `.gemini/skills/SwarmLockSkill/SKILL.md`

### Core Rules:
1. **Lock-Before-Edit**: Always acquire lock before touching code (`--agent <tool> --session <id>`).
2. **Opportunistic Pivot**: If File A is locked by another agent, never wait idle. Immediately pivot to work on independent files in your task plan, and re-check File A at the end of the turn.
3. **Release-On-Complete**: Release all acquired locks once done.

---

## 🏗️ Architecture

```
SwarmLock/
├── agent_lock.py               # CLI tool & silent auto-boot launcher
├── SwarmLockSkill.md           # Standalone skill & prompt rules for AI assistants
├── SwarmLockSkill/             # Packaged skill folder (SKILL.md)
│   └── SKILL.md
├── requirements.txt            # Minimal dependencies (pywebview)
├── README.md                   # Documentation
├── swarmlock/
│   ├── __init__.py
│   ├── core.py                 # LockManager, hierarchical path logic, TTL, filelock
│   ├── server.py               # REST API & Server-Sent Events (SSE) server (Port 7890)
│   ├── gui.py                  # Pywebview native desktop window launcher
│   └── static/
│       ├── index.html          # Dark-mode dashboard HTML
│       ├── app.js              # Real-time SSE / countdown DOM updates
│       └── style.css           # Obsidian cyberpunk dark theme
└── tests/
    ├── test_core.py            # Unit tests for hierarchy, TTL, and permissions
    └── test_cli.py             # Integration tests for CLI commands
```

---

## 🧪 Testing

Run all unit and integration tests:
```bash
python -m unittest discover tests
```
