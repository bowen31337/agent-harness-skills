"""CLI command group for harness-skills."""

from harness_skills.cli.main import PipelineGroup, cli

__all__ = [
    "cli",           # Click group — registered as the `harness` entry-point
    "PipelineGroup", # re-exported so external tooling can subclass it
]
