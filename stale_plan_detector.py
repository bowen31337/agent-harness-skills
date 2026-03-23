"""Backward-compatible entrypoint for the SDK stale-plan demo runner."""
import anyio

from harness_tools.stale_plan_detector import *  # noqa: F403
from harness_tools.stale_plan_detector import demo

if __name__ == "__main__":
    anyio.run(demo)
