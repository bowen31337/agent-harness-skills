"""Backward-compatible entrypoint for harness context CLI."""
from harness_tools.harness_context import *  # noqa: F403
from harness_tools.harness_context import main

if __name__ == "__main__":
    main()
