"""
Framework detection for log_format_linter.

Scans source files for import / require statements to identify the logging
framework in use.  When multiple frameworks are found the most-used one wins.
"""

from __future__ import annotations

import re
from pathlib import Path

from .models import Language, LogFramework

# ---------------------------------------------------------------------------
# File-extension to language mapping
# ---------------------------------------------------------------------------

_EXT_TO_LANG: dict[str, Language] = {
    ".py": Language.PYTHON,
    ".ts": Language.TYPESCRIPT,
    ".tsx": Language.TYPESCRIPT,
    ".js": Language.TYPESCRIPT,
    ".jsx": Language.TYPESCRIPT,
    ".go": Language.GO,
}

# ---------------------------------------------------------------------------
# Per-language detection patterns
# Each entry is (compiled_regex, LogFramework).
# Patterns are tested in order; the first match wins for that file.
# ---------------------------------------------------------------------------

_PYTHON_PATTERNS: list[tuple[re.Pattern[str], LogFramework]] = [
    (re.compile(r"\bimport\s+structlog\b|from\s+structlog\b"), LogFramework.STRUCTLOG),
    (re.compile(r"\bimport\s+loguru\b|from\s+loguru\b"), LogFramework.LOGURU),
    (re.compile(r"\bimport\s+logging\b|from\s+logging\b"), LogFramework.PYTHON_LOGGING),
]

_TYPESCRIPT_PATTERNS: list[tuple[re.Pattern[str], LogFramework]] = [
    (re.compile(r"""(require|import).*['"]winston['"]"""), LogFramework.WINSTON),
    (re.compile(r"""(require|import).*['"]pino['"]"""), LogFramework.PINO),
    (re.compile(r"""(require|import).*['"]bunyan['"]"""), LogFramework.BUNYAN),
]

_GO_PATTERNS: list[tuple[re.Pattern[str], LogFramework]] = [
    (re.compile(r'"go\.uber\.org/zap"'), LogFramework.ZAP),
    (re.compile(r'"github\.com/rs/zerolog"'), LogFramework.ZEROLOG),
    (re.compile(r'"github\.com/sirupsen/logrus"'), LogFramework.LOGRUS),
]

_LANG_PATTERNS: dict[Language, list[tuple[re.Pattern[str], LogFramework]]] = {
    Language.PYTHON: _PYTHON_PATTERNS,
    Language.TYPESCRIPT: _TYPESCRIPT_PATTERNS,
    Language.GO: _GO_PATTERNS,
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_framework(path: str | Path) -> LogFramework:
    """Detect the dominant logging framework used under *path*.

    *path* may be a single source file or a directory.  When a directory is
    given every source file is scanned and the framework with the highest
    occurrence count is returned.

    Returns LogFramework.UNKNOWN when no framework can be determined.
    """
    path = Path(path)
    files: list[Path] = list(path.rglob("*")) if path.is_dir() else [path]

    counts: dict[LogFramework, int] = {}

    for f in files:
        if not f.is_file():
            continue
        lang = _EXT_TO_LANG.get(f.suffix)
        if lang is None:
            continue

        try:
            src = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        patterns = _LANG_PATTERNS.get(lang, [])
        for regex, framework in patterns:
            if regex.search(src):
                counts[framework] = counts.get(framework, 0) + 1
                break  # first match wins per file

    if not counts:
        return LogFramework.UNKNOWN

    return max(counts, key=lambda fw: counts[fw])
