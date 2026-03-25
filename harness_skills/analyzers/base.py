"""Abstract base class for language-specific codebase analyzers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from harness_skills.utils.import_graph import ImportEdge


@dataclass
class Symbol:
    """A code symbol (function, class, constant, etc.)."""

    name: str
    kind: str  # "function" | "class" | "constant" | "method"
    file_path: str
    line_number: int
    exported: bool = True


@dataclass
class AnalysisResult:
    """Unified output from any language analyzer."""

    language: str
    imports: list[ImportEdge] = field(default_factory=list)
    symbols: list[Symbol] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)


class BaseAnalyzer(ABC):
    """Abstract interface for language-specific codebase analyzers.

    Each analyzer:
    1. Detects whether it can analyze a given project root.
    2. Extracts imports and symbols from source files.
    3. Infers candidate domain boundaries from directory structure.
    """

    @abstractmethod
    def language(self) -> str:
        """Return the canonical language name (e.g. 'python', 'typescript')."""

    @abstractmethod
    def can_analyze(self, root: Path) -> bool:
        """Return True if this analyzer is applicable to the project at *root*."""

    @abstractmethod
    def analyze(
        self, root: Path, *, file_paths: list[Path] | None = None
    ) -> AnalysisResult:
        """Run full analysis on the project at *root*.

        If *file_paths* is given, only analyze those files (useful for incremental).
        """

    @abstractmethod
    def extract_imports(self, file_path: Path) -> list[ImportEdge]:
        """Extract import edges from a single file."""

    @abstractmethod
    def extract_symbols(self, file_path: Path) -> list[Symbol]:
        """Extract exported symbols from a single file."""

    def file_extensions(self) -> tuple[str, ...]:
        """Return file extensions this analyzer handles (e.g. ('.py',))."""
        return ()
