"""CLI command group for harness-skills."""

from harness_skills.cli.verbosity import VerbosityLevel, get_verbosity, vecho


def __getattr__(name: str):
    """Lazy imports to break circular dependency with telemetry_reporter."""
    if name == "cli":
        from harness_skills.cli.main import cli
        return cli
    if name == "PipelineGroup":
        from harness_skills.cli.main import PipelineGroup
        return PipelineGroup
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "cli",            # Click group — registered as the `harness` entry-point
    "PipelineGroup",  # re-exported so external tooling can subclass it
    "VerbosityLevel", # level constants: quiet, normal, verbose, debug
    "get_verbosity",  # retrieve active level from a Click context
    "vecho",          # verbosity-aware click.echo wrapper
]
