"""SwarmLock - Multi-Agent File Locking System.

Engine-agnostic, standalone file & directory locking coordination
for concurrent AI coding agents and human developers.
"""

__version__ = "1.0.0"

from .core import Lock, LockManager

__all__ = ["Lock", "LockManager"]
