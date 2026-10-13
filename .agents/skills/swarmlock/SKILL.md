---
name: swarmlock
description: Standalone, engine-agnostic multi-agent file locking coordinator for concurrent AI coding assistants (Claude Code, Cursor, Antigravity) and sub-agents. Use this skill whenever acquiring or releasing file locks, checking lock status, or resolving edit conflicts before modifying codebase files.
---

# SwarmLock Skill

Multi-agent concurrency and file locking coordinator. Prevents conflicting edits, stale reads, and overwritten code when multiple AI assistants or sub-agents work concurrently on the same codebase.

---

## 🆔 Conversation & Sub-Agent Identity Protocol

Every conversation and sub-agent must identify itself using its session context so locks belong exclusively to that session:

- **Flag format:** `--agent "Antigravity" --session "<conversation_or_subagent_id>"`
- **Composite format:** `--agent "Antigravity:<conversation_or_subagent_id>"`

---

## 🔒 The Three Golden Rules

### 1. Lock-Before-Edit
Before modifying, creating, or deleting any file:
```bash
python agent_lock.py acquire <path> --agent "Antigravity" --session "<session_id>" --reason "<task_summary>"
```
- If exit code `0`: Lock acquired. Proceed with edits.
- If exit code `1`: File or parent directory is locked by another agent. **Do NOT touch the file.**

### 2. Opportunistic Pivot Rule (Never Wait Idle)
If your lock request is rejected because another agent or conversation holds it:
- **Never sleep or loop waiting.**
- **Immediately pivot** to other unblocked files or independent tasks in your plan.
- Only re-check the locked file at the end of your turn before reporting progress.

### 3. Release-On-Complete
Once edits are finished and verified:
```bash
python agent_lock.py release <path> --agent "Antigravity" --session "<session_id>"
```

---

## 🛠️ CLI Quick Reference

| Action | Command |
|---|---|
| **Acquire Lock** | `python agent_lock.py acquire <path> --agent "Antigravity" --session "<id>" [--reason "<text>"] [--ttl <minutes>]` |
| **Check Status** | `python agent_lock.py check <path>` *(Exit 0: FREE, Exit 1: LOCKED)* |
| **Release Lock** | `python agent_lock.py release <path> --agent "Antigravity" --session "<id>"` |
| **Force Release** | `python agent_lock.py release <path> --agent "Antigravity" --force` |
| **List Locks** | `python agent_lock.py list` |
| **Open GUI Dashboard** | `python agent_lock.py gui` |

---

## 📁 Hierarchical Locking Rules
- Locking a folder (e.g. `src/components/`) automatically blocks child files (e.g. `src/components/Button.tsx`).
- Locking a child file automatically blocks parent folder locks.
- Default TTL is 30 minutes; stale locks auto-expire if a chat session is abandoned.
