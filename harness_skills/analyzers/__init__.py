"""Language-specific codebase analyzers.

Each analyzer implements the ``BaseAnalyzer`` interface and provides
import extraction, symbol extraction, and domain boundary hints for
a specific programming language.
"""

from __future__ import annotations

from harness_skills.analyzers.base import AnalysisResult, BaseAnalyzer, Symbol
from harness_skills.utils.import_graph import ImportEdge

__all__ = ["AnalysisResult", "BaseAnalyzer", "ImportEdge", "Symbol", "get_analyzer"]

_REGISTRY: dict[str, type[BaseAnalyzer]] = {}


def register_analyzer(cls: type[BaseAnalyzer]) -> type[BaseAnalyzer]:
    """Decorator to register an analyzer class."""
    _REGISTRY[cls().language()] = cls
    return cls


def get_analyzer(language: str) -> BaseAnalyzer:
    """Return an analyzer instance for the given language.

    Raises ``KeyError`` if no analyzer is registered for the language.
    """
    if not _REGISTRY:
        _load_builtins()
    if language not in _REGISTRY:
        raise KeyError(f"No analyzer registered for language: {language}")
    return _REGISTRY[language]()


def available_languages() -> list[str]:
    """Return the list of languages with registered analyzers."""
    if not _REGISTRY:
        _load_builtins()
    return sorted(_REGISTRY.keys())


def _load_builtins() -> None:
    """Import built-in analyzer modules to trigger registration."""
    from harness_skills.analyzers import (  # noqa: PLC0415, F401
        csharp_analyzer,
        go_analyzer,
        java_analyzer,
        python_analyzer,
        rust_analyzer,
        typescript_analyzer,
    )
