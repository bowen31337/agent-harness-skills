"""Tree-sitter setup helpers with graceful degradation.

Provides lazy-loaded parsers and query helpers for multi-language AST analysis.
If tree-sitter or a language grammar is not installed, ``LanguageNotAvailable``
is raised rather than crashing.

Usage::

    from harness_skills.utils.tree_sitter import parse_file, query_matches

    tree = parse_file(Path("app.py"), "python")
    matches = query_matches(tree, "python", "(import_statement) @imp")
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class TreeSitterNotInstalled(ImportError):
    """Raised when the tree-sitter package is not installed."""


class LanguageNotAvailable(ImportError):
    """Raised when a specific tree-sitter language grammar is not installed."""

    def __init__(self, language: str) -> None:
        self.language = language
        super().__init__(
            f"tree-sitter grammar for '{language}' is not installed. "
            f"Install it with: uv add tree-sitter-{language}"
        )


# ---------------------------------------------------------------------------
# Grammar mapping
# ---------------------------------------------------------------------------

_GRAMMAR_PACKAGES: dict[str, str] = {
    "python": "tree_sitter_python",
    "typescript": "tree_sitter_typescript",
    "tsx": "tree_sitter_typescript",
    "go": "tree_sitter_go",
    "rust": "tree_sitter_rust",
    "java": "tree_sitter_java",
    "c_sharp": "tree_sitter_c_sharp",
}

# Caches
_PARSER_CACHE: dict[str, Any] = {}
_LANGUAGE_CACHE: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_available() -> bool:
    """Return True if the base tree-sitter package is importable."""
    try:
        import tree_sitter  # noqa: F401, PLC0415

        return True
    except ImportError:
        return False


def get_language(language: str) -> Any:
    """Load and cache a tree-sitter Language object.

    Raises ``LanguageNotAvailable`` if the grammar package is missing.
    Raises ``TreeSitterNotInstalled`` if tree-sitter itself is missing.
    """
    if language in _LANGUAGE_CACHE:
        return _LANGUAGE_CACHE[language]

    if not is_available():
        raise TreeSitterNotInstalled("tree-sitter is not installed. uv add tree-sitter")

    from tree_sitter import Language  # noqa: PLC0415

    pkg_name = _GRAMMAR_PACKAGES.get(language)
    if pkg_name is None:
        raise LanguageNotAvailable(language)

    try:
        mod = __import__(pkg_name)
        # Most tree-sitter grammar packages expose a language() function
        if language == "typescript":
            lang_fn = getattr(mod, "language_typescript", None) or getattr(mod, "language", None)
        elif language == "tsx":
            lang_fn = getattr(mod, "language_tsx", None) or getattr(mod, "language", None)
        else:
            lang_fn = getattr(mod, "language", None)

        if lang_fn is None:
            raise LanguageNotAvailable(language)

        lang_obj = Language(lang_fn())
        _LANGUAGE_CACHE[language] = lang_obj
        return lang_obj
    except (ImportError, ModuleNotFoundError) as exc:
        raise LanguageNotAvailable(language) from exc


def get_parser(language: str) -> Any:
    """Return a cached Parser instance for the given language.

    Raises ``LanguageNotAvailable`` or ``TreeSitterNotInstalled``.
    """
    if language in _PARSER_CACHE:
        return _PARSER_CACHE[language]

    if not is_available():
        raise TreeSitterNotInstalled("tree-sitter is not installed")

    from tree_sitter import Parser  # noqa: PLC0415

    lang = get_language(language)
    parser = Parser(lang)
    _PARSER_CACHE[language] = parser
    return parser


def parse_file(file_path: Path, language: str) -> Any:
    """Parse a file and return a tree-sitter Tree."""
    parser = get_parser(language)
    source = file_path.read_bytes()
    return parser.parse(source)


def parse_bytes(source: bytes, language: str) -> Any:
    """Parse raw bytes and return a tree-sitter Tree."""
    parser = get_parser(language)
    return parser.parse(source)


def query_matches(
    tree: Any, language: str, query_string: str
) -> list[dict[str, Any]]:
    """Run a tree-sitter query and return matches as dicts.

    Each match is ``{"pattern_index": int, "captures": {name: node}}``.
    """
    lang = get_language(language)
    from tree_sitter import Query  # noqa: PLC0415 (import only when tree_sitter is installed)

    # tree_sitter 0.23+ API
    q = lang.query(query_string) if hasattr(lang, "query") else Query(lang, query_string)
    raw_matches = q.matches(tree.root_node)

    results: list[dict[str, Any]] = []
    for match in raw_matches:
        if isinstance(match, tuple) and len(match) == 2:
            pattern_idx, captures = match
            results.append({
                "pattern_index": pattern_idx,
                "captures": captures,
            })
        else:
            results.append({"pattern_index": 0, "captures": match})
    return results


def clear_caches() -> None:
    """Clear parser and language caches (useful in tests)."""
    _PARSER_CACHE.clear()
    _LANGUAGE_CACHE.clear()
