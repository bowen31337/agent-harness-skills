"""CLI command group for harness-skills."""

from harness_skills.cli.main import PipelineGroup, cli
from harness_skills.cli.verbosity import VerbosityLevel, get_verbosity, vecho

__all__ = [
    "cli",            # Click group — registered as the `harness` entry-point
    "PipelineGroup",  # re-exported so external tooling can subclass it
    "VerbosityLevel", # level constants: quiet, normal, verbose, debug
    "get_verbosity",  # retrieve active level from a Click context
    "vecho",          # verbosity-aware click.echo wrapper
]
