---
name: SwarmLockSkill
description: Standalone, engine-agnostic multi-agent file locking protocol for concurrent AI assistants and sub-agents. Enforces Lock-Before-Edit, Opportunistic Pivot, and Release-On-Complete.
---

# SwarmLockSkill — Multi-Agent Coordination Protocol

> **CRITICAL SYSTEM INSTRUCTION FOR ALL AI CODING ASSISTANTS & SUB-AGENTS**  
> Multiple AI agents (Claude Code, Cursor, Antigravity, etc.), sub-agents, and human developers work concurrently across separate chats on this codebase. To prevent race conditions, overwritten code, and corrupted assets, you **MUST** strictly follow the locking protocol below.

---

## 🆔 Conversation & Sub-Agent Identity Protocol

Each conversation, chat session, and sub-agent owns its own exclusive locks. **Never share generic IDs across multiple chats.**

Always identify yourself using one of these two formats:
1. **Flag Format:** `--agent "<ToolName>" --session "<TaskOrChatId>"`
2. **Composite Format:** `--agent "<ToolName>:<TaskOrChatId>"`

### Identity Examples:
- **Claude Chat 1 (Combat):** `--agent "Claude" --session "Combat"`
- **Claude Chat 2 (Inventory):** `--agent "Claude" --session "Inventory"`
- **Cursor Composer (UI):** `--agent "Cursor" --session "UI-Menu"`
- **Antigravity Primary:** `--agent "Antigravity" --session "Main"`
- **Antigravity Sub-Agent:** `--agent "Antigravity" --session "SubAgent-Worker"`

---

## 🔒 The Four Golden Rules

### 1. Lock-All-Upfront in One Go (Mandatory)
Before modifying, creating, renaming, or deleting ANY file:
- **Determine all files** you plan to touch during your task turn.
- **Lock everything in one go upfront** before writing any code.
- **NEVER** do incremental "lock file A -> edit -> unlock file A -> lock file B -> edit -> unlock file B" 10 times. Incremental locking causes race conditions, lock stomping, and wasted tool turns.

Lock all planned files in a single batch command:
```bash
swarmlock acquire <path1> <path2> <path3> --agent "<tool>" --session "<chat_id>" --reason "<short_task_description>"
```
*Example:*
```bash
swarmlock acquire Assets/Scripts/Combat/PlayerCombat.cs Assets/Scripts/Combat/CombatStats.cs Assets/Scripts/UI/CombatHUD.cs --agent "Claude" --session "Combat" --reason "Refactoring attack combos and HUD"
```
- If all succeed (exit code `0`): All locks secured. Proceed with edits.
- If any path fails (exit code `1`): The path is locked by another conversation or agent. Apply Rule 2 (Opportunistic Pivot).

---

### 2. The Opportunistic Pivot Rule (Never Wait Upfront)
If a batch lock request reveals that some files are locked while others are successfully acquired:
- **Never wait upfront:** Immediately proceed to edit all files you successfully acquired.
- **DO NOT** sleep, poll, or loop waiting while there are unblocked files ready to work on.
- **DO NOT** halt your turn or ask the user to intervene immediately.
- **IMMEDIATELY PIVOT** to work on the unblocked files, tests, documentation, or subtasks in your plan.

*Pivot Example:*
> *If `Assets/Scripts/UI/Menu.cs` is locked by Cursor:UI, immediately pivot to work on acquired `Assets/Scripts/Audio/SoundManager.cs` or independent unit tests instead.*

---

### 3. Contested Files at the End (CLI-Level Blocking Wait)
Once all unblocked files have been edited, return to the remaining contested file(s) at the very end of your turn:
- Use the `--wait <seconds>` flag (e.g. `--wait 30` or `--wait 60`) on the contested file(s).
- The CLI process blocks at the OS level until the other session releases the lock, costing ZERO LLM reasoning tokens and requiring no polling loop:
```bash
swarmlock acquire <contested_path> --wait 30 --agent "<tool>" --session "<chat_id>"
```
- If acquired within the timeout: complete the remaining edits.
- If it times out: report partial completion and current blockage to the user without further turn-spinning.

---

### 4. Release-On-Complete (Batch Release)
As soon as you finish editing and verifying all files in your task (or before completing your response turn), release all acquired locks in one batch:
```bash
swarmlock release <path1> <path2> <path3> --agent "<tool>" --session "<chat_id>"
```
*Example:*
```bash
swarmlock release Assets/Scripts/Combat/PlayerCombat.cs Assets/Scripts/Combat/CombatStats.cs Assets/Scripts/UI/CombatHUD.cs --agent "Claude" --session "Combat"
```
Or clear all locks owned by your session at once:
```bash
swarmlock clear --agent "<tool>" --session "<chat_id>"
```

---

## 🛠️ CLI Quick Reference

| Action | Command |
|---|---|
| **Batch Acquire Locks** | `swarmlock acquire <path1> [<path2> ...] --agent "<name>" [--session "<id>"] [--reason "<text>"] [--ttl <min>]` |
| **Wait for Contested Lock** | `swarmlock acquire <path> --wait <seconds> --agent "<name>" [--session "<id>"]` *(Blocks at OS level)* |
| **Check Locks** | `swarmlock check <path1> [<path2> ...] [--wait <sec>]` *(Exits 0 if ALL FREE, 1 if ANY LOCKED)* |
| **Batch Release Locks** | `swarmlock release <path1> [<path2> ...] --agent "<name>" [--session "<id>"]` |
| **Clear All My Locks** | `swarmlock clear --agent "<name>" [--session "<id>"]` |
| **Force Release** | `swarmlock release <path> --agent "<name>" --force` *(Emergency only)* |
| **List Locks** | `swarmlock list` |

---

## 📁 Hierarchical Directory Rules
- **Directory Locks Block Children**: Locking `Assets/Scripts/UI/` automatically prevents any other agent from locking `Assets/Scripts/UI/Button.cs`.
- **Child Locks Block Directories**: If `Assets/Scripts/UI/Button.cs` is locked, no agent can lock the parent `Assets/Scripts/UI/` directory until the child is released.
- **Stale Lock Auto-Expiration (TTL)**: Default TTL is 30 minutes. If an agent crashes or a chat closes, stale locks expire automatically without manual intervention.

---

## 📋 Copy-Paste Setup Snippets

### For Cursor (`.cursorrules` or `.cursor/rules/swarmlock.mdc`)
```markdown
# SwarmLock Multi-Agent Concurrency Protocol
Before editing any file:
1. Determine all files to edit and lock them in ONE GO upfront: `swarmlock acquire <path1> <path2> --agent "Cursor" --session "<current_task_or_chat>" --reason "<task>"`
2. If locked (exit 1), do NOT wait idle. Opportunistically pivot to other independent files in your plan.
3. When finished editing, batch release all locks: `swarmlock release <path1> <path2> --agent "Cursor" --session "<current_task_or_chat>"`.
```

### For Claude Code (`CLAUDE.md`)
```markdown
# Multi-Agent File Locking
Before modifying files, always acquire all planned locks upfront in one batch:
`swarmlock acquire <path1> <path2> --agent "Claude" --session "<task_or_session>" --reason "<description>"`
If locked by another agent or session, pivot to unblocked files immediately without waiting.
Release all locks upon task completion:
`swarmlock release <path1> <path2> --agent "Claude" --session "<task_or_session>"`
```

### For Antigravity (`.gemini/rules.md` or System Instructions)
```markdown
# Multi-Agent Coordination
- Lock-All-Upfront: Lock all planned files in one go with `swarmlock acquire <path1> <path2> --agent "Antigravity" --session "<conversation_or_subagent_role>" --reason "<reason>"` before editing. Do not lock/unlock incrementally.
- Opportunistic Pivot: If blocked, pivot immediately to independent files without idle polling.
- Release-On-Complete: Always batch release locks with `swarmlock release <path1> <path2> --agent "Antigravity" --session "<conversation_or_subagent_role>"`.
```
