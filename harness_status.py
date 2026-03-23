"""Backward-compatible entrypoint for ``harness_status`` CLI."""
from __future__ import annotations

import sys

from harness_tools.harness_status import *  # noqa: F403
from harness_tools.harness_status import main

if __name__ == "__main__":
    sys.exit(main() or 0)
