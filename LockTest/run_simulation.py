"""Multi-Agent Simulation Runner for LockTest.

Spawns 3 concurrent sub-agents with unique IDs:
  - Agent 1: Claude:SubAgent-Auth
  - Agent 2: Cursor:SubAgent-Frontend
  - Agent 3: Antigravity:SubAgent-Database

Each agent:
1. Acquires a lock with a 1-minute TTL.
2. If blocked by another agent, immediately pivots to an unblocked file.
3. Appends placeholder edits with timestamps.
4. Holds locks during processing and times out / releases after 60 seconds.
"""

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

# Force UTF-8 stdout
if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT_DIR = Path(__file__).parent.parent.resolve()
CLI_SCRIPT = ROOT_DIR / "agent_lock.py"


def run_agent_task(agent_name: str, session_id: str, primary_file: str, fallback_file: str, edit_note: str):
    prefix = f"[{agent_name}:{session_id}]"
    print(f"{prefix} Starting task execution...", flush=True)

    # Step 1: Try acquiring primary file with 1 minute TTL
    cmd_acq = [
        sys.executable, str(CLI_SCRIPT), "acquire", primary_file,
        "--agent", agent_name, "--session", session_id,
        "--reason", edit_note, "--ttl", "1"
    ]
    proc = subprocess.run(cmd_acq, cwd=str(ROOT_DIR), capture_output=True, text=True)

    target_file = primary_file
    if proc.returncode != 0:
        # CONFLICT! Demonstrate Opportunistic Pivot Rule!
        print(f"{prefix} Primary target '{primary_file}' is LOCKED! Opportunistically pivoting to '{fallback_file}'...", flush=True)
        target_file = fallback_file
        cmd_pivot = [
            sys.executable, str(CLI_SCRIPT), "acquire", target_file,
            "--agent", agent_name, "--session", session_id,
            "--reason", f"Pivoted: {edit_note}", "--ttl", "1"
        ]
        proc_pivot = subprocess.run(cmd_pivot, cwd=str(ROOT_DIR), capture_output=True, text=True)
        if proc_pivot.returncode != 0:
            print(f"{prefix} Fallback target also locked. Standing by.", flush=True)
            return
        print(f"{prefix} Successfully acquired lock on fallback: '{target_file}'", flush=True)
    else:
        print(f"{prefix} Successfully acquired lock on '{target_file}' (TTL: 1m)", flush=True)

    # Step 2: Make placeholder random edit
    abs_path = ROOT_DIR / target_file
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    placeholder_text = f"\n# [{timestamp}] Placeholder edit by {agent_name}:{session_id} - Task: {edit_note}\n"
    try:
        with open(abs_path, "a", encoding="utf-8") as f:
            f.write(placeholder_text)
        print(f"{prefix} Wrote placeholder edit to '{target_file}'", flush=True)
    except Exception as e:
        print(f"{prefix} Error editing {target_file}: {e}", flush=True)

    # Step 3: Hold lock for 60 seconds (simulating work / TTL expiration)
    print(f"{prefix} Working with lock active on '{target_file}'... (Sleeping for 60s timeout)", flush=True)
    time.sleep(60)

    # Step 4: Release lock after 1 minute timeout
    print(f"{prefix} 1-minute timeout elapsed. Releasing lock on '{target_file}'...", flush=True)
    cmd_rel = [
        sys.executable, str(CLI_SCRIPT), "release", target_file,
        "--agent", agent_name, "--session", session_id
    ]
    subprocess.run(cmd_rel, cwd=str(ROOT_DIR), capture_output=True, text=True)
    print(f"{prefix} Released '{target_file}'. Task complete!", flush=True)


def main():
    print("=" * 70, flush=True)
    print("Launching 3 Concurrent Sub-Agents in LockTest (1-minute lifecycle)", flush=True)
    print("=" * 70, flush=True)

    t1 = threading.Thread(
        target=run_agent_task,
        args=("Claude", "SubAgent-Auth", "LockTest/backend/api/auth.py", "LockTest/config/settings.json", "Adding OAuth2 flow")
    )
    t2 = threading.Thread(
        target=run_agent_task,
        args=("Cursor", "SubAgent-Frontend", "LockTest/frontend/ui/Button.tsx", "LockTest/frontend/ui/Header.tsx", "Adding dark mode ripple effect")
    )
    t3 = threading.Thread(
        # Deliberately targets LockTest/backend/api/auth.py first to trigger Opportunistic Pivot!
        target=run_agent_task,
        args=("Antigravity", "SubAgent-Database", "LockTest/backend/api/auth.py", "LockTest/backend/database/schema.sql", "Adding audit log schema")
    )

    t1.start()
    t2.start()
    time.sleep(0.5)  # slight stagger so t3 encounters conflict on auth.py
    t3.start()

    t1.join()
    t2.join()
    t3.join()

    print("=" * 70, flush=True)
    print("All 3 Sub-Agents have completed their 1-minute lifecycle!", flush=True)
    print("=" * 70, flush=True)


if __name__ == "__main__":
    main()
