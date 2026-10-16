---
name: swarmlock
description: Use ONLY when the user explicitly invokes /swarmlock. Do NOT auto-trigger, suggest, or load during standard single-chat file editing.
---

# SwarmLock Skill

Multi-agent concurrency and file locking coordinator. Prevents conflicting edits, stale reads, and overwritten code when multiple AI assistants or sub-agents work concurrently on the same codebase.

---

## 🆔 Conversation & Sub-Agent Identity Protocol

Every conversation and sub-agent must identify itself using its session context so locks belong exclusively to that session:

- **Flag format:** `--agent "Antigravity" --session "<conversation_or_subagent_id>"`
- **Composite format:** `--agent "Antigravity:<conversation_or_subagent_id>"`

---

## 🔒 The Four Golden Rules

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

### 2. Opportunistic Pivot Rule (Never Wait Upfront)
If a batch lock request reveals that some files are locked while others are acquired:
- **Never wait upfront:** Immediately proceed to edit all files you successfully acquired.
- Do NOT loop, poll, or block while there are unblocked files ready to work on.

### 3. Contested Files at the End (CLI-Level Blocking Wait)
Once all unblocked files have been edited, return to the remaining contested file(s) at the very end of your turn:
- Use the `--wait 15m` flag (or simply `--wait`, which defaults to 15 minutes) on the contested file(s).
- The CLI process blocks at the OS level until the other session releases the lock, costing ZERO LLM reasoning tokens and requiring no active polling:
```bash
swarmlock acquire <contested_path> --wait 15m --agent "Antigravity" --session "<session_id>"
```
- If acquired within the timeout: complete the remaining edits.
- If it times out after 15 minutes: report partial completion and current blockage to the user without further turn-spinning.

### 4. Release-On-Complete (Batch Release)
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
| **Wait for Contested Lock** | `swarmlock acquire <path> --wait 15m --agent "Antigravity" --session "<id>"` *(Blocks at OS level)* |
| **Check Status** | `swarmlock check <path1> [<path2> ...] [--wait 15m]` *(Exit 0: FREE, Exit 1: LOCKED)* |
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
