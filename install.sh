#!/usr/bin/env bash
set -e
echo "========================================================"
echo "  Installing SwarmLock Multi-Agent Coordinator Globally"
echo "========================================================"
echo ""
python3 -m pip install -e .
echo ""
echo "[SUCCESS] SwarmLock installed! You can now run 'swarmlock' anywhere."
echo "Try: swarmlock --help"
