"""Backward-compatible entrypoint for the coordination dashboard."""
from __future__ import annotations

import asyncio

from harness_tools.coordinate import *  # noqa: F403
from harness_tools.coordinate import main

if __name__ == "__main__":
    asyncio.run(main())
