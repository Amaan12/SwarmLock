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

### 1. Lock-All-Upfront in One Go (Mandatory)
Before modifying, creating, renaming, or deleting ANY file:
- **Determine all files** you plan to work on during your task turn.
- **Lock everything in one go upfront** before writing any code.
- **NEVER** do incremental "lock file A -> edit -> unlock file A -> lock file B -> edit -> unlock file B" 10 times. Incremental locking causes race conditions, lock stomping, and wasted tool turns.

Lock all planned files in a single batch command:
```bash
swarmlock acquire <path1> <path2> <path3> --agent "Antigravity" --session "<session_id>" --reason "<task_summary>"
```
- If all succeed (exit code `0`): All locks secured. Proceed with edits.
- If any file is locked (exit code `1`): Immediately apply Rule 2 (Opportunistic Pivot).

### 2. Opportunistic Pivot Rule (Never Wait Idle)
If a lock request is rejected because another agent or conversation holds it:
- **Never sleep, loop, or poll waiting.**
- **Immediately pivot** to other unblocked files or independent tasks in your plan.
- Only re-check the locked file at the end of your turn before reporting progress.

### 3. Release-On-Complete (Batch Release)
Once all edits across your task are finished and verified:
```bash
swarmlock release <path1> <path2> <path3> --agent "Antigravity" --session "<session_id>"
```
Or clear all locks owned by your session:
```bash
swarmlock clear --agent "Antigravity" --session "<session_id>"
```

---

## 🛠️ CLI Quick Reference

| Action | Command |
|---|---|
| **Batch Acquire Locks** | `swarmlock acquire <path1> [<path2> ...] --agent "Antigravity" --session "<id>" [--reason "<text>"] [--ttl <min>]` |
| **Check Status** | `swarmlock check <path1> [<path2> ...]` *(Exit 0: FREE, Exit 1: LOCKED)* |
| **Batch Release Locks** | `swarmlock release <path1> [<path2> ...] --agent "Antigravity" --session "<id>"` |
| **Clear All My Locks** | `swarmlock clear --agent "Antigravity" --session "<id>"` |
| **Force Release** | `swarmlock release <path> --agent "Antigravity" --force` |
| **List Locks** | `swarmlock list` |
| **Open GUI Dashboard** | `swarmlock gui` |

---

## 📁 Hierarchical Locking Rules
- Locking a folder (e.g. `src/components/`) automatically blocks child files (e.g. `src/components/Button.tsx`).
- Locking a child file automatically blocks parent folder locks.
- Default TTL is 30 minutes; stale locks auto-expire if a chat session is abandoned.
