"""Backward-compatible entrypoint for task lock CLI."""
from harness_tools.task_lock import *  # noqa: F403
from harness_tools.task_lock import main

if __name__ == "__main__":
    main()
