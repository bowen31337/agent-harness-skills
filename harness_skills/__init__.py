"""harness-skills: Agent harness engineering toolkit."""

__version__ = "0.1.0"

# Each sub-package (models, generators, plugins, gates, cli) declares its own
# __all__.  The root package intentionally re-exports nothing — import from the
# relevant sub-package directly (e.g. `from harness_skills.models import Status`).
__all__: list[str] = []
