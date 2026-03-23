"""Backward-compatible entrypoint for ``harness_telemetry`` CLI."""
from harness_tools.harness_telemetry import *  # noqa: F403
from harness_tools.harness_telemetry import (
    _cli,
    _identify_gate,
    _is_harness_artifact,
    _merge_counts,
    _output_indicates_failure,
)

if __name__ == "__main__":
    _cli()
