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

## 🔒 The Three Golden Rules

### 1. Lock-Before-Edit (Mandatory)
Before creating, editing, renaming, or deleting any file or directory, you **MUST** acquire an exclusive lock:
```bash
swarmlock acquire <path> --agent "<tool>" --session "<chat_id>" --reason "<short_task_description>"
```
*Example:*
```bash
swarmlock acquire Assets/Scripts/Combat/PlayerCombat.cs --agent "Claude" --session "Combat" --reason "Refactoring attack combos"
```
- If the command succeeds (exit code `0`), proceed with your edits.
- If the command fails (exit code `1`), the path (or its parent directory/child files) is currently locked by another conversation or agent. **Do NOT modify the file.**

---

### 2. The Opportunistic Pivot Rule (Never Wait Idle)
If your lock request for a file is rejected because another conversation or agent holds it:
- **DO NOT** sleep, poll, or loop waiting for the lock to become free.
- **DO NOT** halt your turn or ask the user to intervene immediately.
- **IMMEDIATELY PIVOT** to other independent files, tests, documentation, or subtasks in your plan.
- Only re-check the locked file at the very end of your turn before reporting your progress to the user.

*Pivot Example:*
> *If `Assets/Scripts/UI/Menu.cs` is locked by Cursor:UI, immediately pivot to work on `Assets/Scripts/Audio/SoundManager.cs` or independent unit tests instead.*

---

### 3. Release-On-Complete (Mandatory)
As soon as you finish editing and verifying a file (or before completing your response turn), you **MUST** release all locks you acquired:
```bash
swarmlock release <path> --agent "<tool>" --session "<chat_id>"
```
*Example:*
```bash
swarmlock release Assets/Scripts/Combat/PlayerCombat.cs --agent "Claude" --session "Combat"
```

---

## 🛠️ CLI Quick Reference

| Action | Command |
|---|---|
| **Acquire Lock** | `swarmlock acquire <path> --agent "<name>" [--session "<id>"] [--reason "<text>"] [--ttl <min>]` |
| **Check Lock** | `swarmlock check <path>` *(Exits 0 if FREE, 1 if LOCKED)* |
| **Release Lock** | `swarmlock release <path> --agent "<name>" [--session "<id>"]` |
| **Force Release** | `swarmlock release <path> --agent "<name>" --force` *(Emergency only)* |
| **List Locks** | `swarmlock list` |
| **Clear My Locks** | `swarmlock clear --agent "<name>" [--session "<id>"]` |

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
1. Run `swarmlock acquire <path> --agent "Cursor" --session "<current_task_or_chat>" --reason "<task>"`
2. If locked (exit 1), do NOT wait idle. Opportunistically pivot to other independent files in your plan.
3. When finished editing, run `swarmlock release <path> --agent "Cursor" --session "<current_task_or_chat>"`.
```

### For Claude Code (`CLAUDE.md`)
```markdown
# Multi-Agent File Locking
Before modifying files, always acquire a lock with your session id:
`swarmlock acquire <path> --agent "Claude" --session "<task_or_session>" --reason "<description>"`
If locked by another agent or session, pivot to unblocked files immediately without waiting.
Release locks upon task completion:
`swarmlock release <path> --agent "Claude" --session "<task_or_session>"`
```

### For Antigravity (`.gemini/rules.md` or System Instructions)
```markdown
# Multi-Agent Coordination
- Lock-Before-Edit: Acquire locks with `swarmlock acquire <path> --agent "Antigravity" --session "<conversation_or_subagent_role>" --reason "<reason>"` before modifying files.
- Opportunistic Pivot: If blocked, pivot immediately to independent files without idle polling.
- Release-On-Complete: Always release locks with `swarmlock release <path> --agent "Antigravity" --session "<conversation_or_subagent_role>"`.
```
