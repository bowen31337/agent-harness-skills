"""Backward-compatible entrypoint for ``checkpoint_agent`` harness demo."""
from __future__ import annotations

import sys

import anyio

from harness_tools.checkpoint_agent import main

if __name__ == "__main__":
    try:
        anyio.run(main)
    except KeyboardInterrupt:
        print("\n[harness] Interrupted.")
        sys.exit(1)
