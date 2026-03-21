"""
Source-code checker for log_format_linter.

:func:`check_file` scans a single source file for log calls that violate the
structured-log pattern (missing ``domain``, ``trace_id``, or other configured
required fields).

:func:`check_directory` walks a directory tree and aggregates all violations.

Detection strategy
------------------
The checker uses regex rather than a full AST parse so that it works across
Python, TypeScript, and Go without heavy dependencies.  The trade-off is that
it can produce false positives for log calls inside comments or string literals
and may miss calls split across many lines (> ``_BLOCK_LINES`` lines).
A tolerance window of up to 5 source lines is collected around each detected
call to handle the common case of multi-line log calls.

Per-framework check strategies (set by :func:`generate_rules`)
--------------------------------------------------------------
regex+extra-dict      (python_logging)  — look for ``extra={...}`` dict
regex+kwargs          (structlog)       — look for ``field=`` kwarg
regex+bind-or-kwargs  (loguru)          — accept ``.bind(field=...)`` OR kwargs
regex+object-keys     (winston, pino, bunyan) — look for ``"field":`` or ``field:``
regex+zap-fields      (zap)             — look for ``zap.String("field", ...)``
regex+with-fields     (logrus)          — look for ``WithFields({...})`` with keys
regex+zerolog-chain   (zerolog)         — look for ``.Str("field", ...)`` chain
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path

from .models import Language, LogFramework, LogLinterConfig, LogViolation

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BLOCK_LINES = 6  # max lines to collect for a multi-line log call

_EXT_TO_LANG: dict[str, Language] = {
    ".py": Language.PYTHON,
    ".ts": Language.TYPESCRIPT,
    ".tsx": Language.TYPESCRIPT,
    ".js": Language.TYPESCRIPT,
    ".jsx": Language.TYPESCRIPT,
    ".go": Language.GO,
}

# ---------------------------------------------------------------------------
# Log-call detection regexes (one per framework)
# ---------------------------------------------------------------------------

_LOG_CALL_PATTERNS: dict[LogFramework, re.Pattern[str]] = {
    LogFramework.PYTHON_LOGGING: re.compile(
        r"\b(?:logger|logging|log)\.(debug|info|warning|warn|error|critical|exception)\s*\("
    ),
    LogFramework.STRUCTLOG: re.compile(
        r"\b(?:log|logger)\.(debug|info|warning|warn|error|critical)\s*\("
    ),
    LogFramework.LOGURU: re.compile(
        r"\b(?:logger|log)\.(debug|info|warning|warn|error|critical|exception)\s*\("
    ),
    LogFramework.WINSTON: re.compile(
        r"\b(?:logger|log)\.(debug|info|warn|error)\s*\("
    ),
    LogFramework.PINO: re.compile(
        r"\b(?:logger|log)\.(debug|info|warn|error|fatal|trace)\s*\("
    ),
    LogFramework.BUNYAN: re.compile(
        r"\b(?:logger|log)\.(debug|info|warn|error|fatal|trace)\s*\("
    ),
    LogFramework.ZAP: re.compile(
        r"\blogger\.(Debug|Info|Warn|Error|Fatal|Panic|DPanic)\s*\("
    ),
    LogFramework.LOGRUS: re.compile(
        r"\b(?:logrus|log|logger)\.(Debug|Info|Warn|Warning|Error|Fatal|Panic|Print)\s*\("
    ),
    LogFramework.ZEROLOG: re.compile(
        r"\b(?:log|logger)\.(Debug|Info|Warn|Error|Fatal|Panic)\s*\(\)"
    ),
}

# Frameworks whose log calls may appear in non-log files (low specificity)
# — we skip files that don't contain the corresponding import.
_REQUIRE_IMPORT: dict[LogFramework, re.Pattern[str]] = {
    LogFramework.PYTHON_LOGGING: re.compile(r"\bimport\s+logging\b|from\s+logging\b"),
    LogFramework.STRUCTLOG: re.compile(r"\bimport\s+structlog\b|from\s+structlog\b"),
    LogFramework.LOGURU: re.compile(r"\bimport\s+loguru\b|from\s+loguru\b"),
    LogFramework.WINSTON: re.compile(r"""(require|import).*['"]winston['"]"""),
    LogFramework.PINO: re.compile(r"""(require|import).*['"]pino['"]"""),
    LogFramework.BUNYAN: re.compile(r"""(require|import).*['"]bunyan['"]"""),
    LogFramework.ZAP: re.compile(r'"go\.uber\.org/zap"'),
    LogFramework.LOGRUS: re.compile(r'"github\.com/sirupsen/logrus"'),
    LogFramework.ZEROLOG: re.compile(r'"github\.com/rs/zerolog"'),
}

# ---------------------------------------------------------------------------
# Block extraction
# ---------------------------------------------------------------------------


def _extract_block(lines: list[str], start: int) -> str:
    """Return up to ``_BLOCK_LINES`` source lines beginning at *start*.

    Stops early once open parentheses are balanced (depth returns to 0 or
    below after the opening line).
    """
    block_lines: list[str] = []
    depth = 0
    for i in range(start, min(start + _BLOCK_LINES, len(lines))):
        line = lines[i]
        block_lines.append(line)
        depth += line.count("(") - line.count(")")
        # Stop as soon as parentheses balance — this handles both single-line
        # calls (depth hits 0 on the first line) and multi-line calls.
        if depth <= 0:
            break
    return "\n".join(block_lines)


# ---------------------------------------------------------------------------
# Per-strategy field checks
# ---------------------------------------------------------------------------


def _missing_from_extra_dict(block: str, fields: list[str]) -> list[str]:
    """python_logging: fields must appear as string keys in extra={...}."""
    if not re.search(r"\bextra\s*=\s*\{", block):
        return list(fields)  # extra kwarg absent entirely
    missing = []
    for f in fields:
        if not re.search(rf"""['"]{re.escape(f)}['"]\s*:""", block):
            missing.append(f)
    return missing


def _missing_from_kwargs(block: str, fields: list[str]) -> list[str]:
    """structlog: fields must appear as ``field=`` keyword arguments."""
    return [f for f in fields if not re.search(rf"\b{re.escape(f)}\s*=", block)]


def _missing_from_bind_or_kwargs(block: str, fields: list[str]) -> list[str]:
    """loguru: accept .bind(field=...) anywhere on the line, or plain kwargs."""
    # Extend the search window to the whole source context (bind may precede call)
    return [f for f in fields if not re.search(rf"\b{re.escape(f)}\s*=", block)]


def _missing_from_object_keys(block: str, fields: list[str]) -> list[str]:
    """winston / pino / bunyan: fields as object literal keys ``field:`` or ``"field":``."""
    missing = []
    for f in fields:
        # Matches: field: ...  OR  "field": ...  OR  'field': ...
        if not re.search(rf"""(?:^|[\s{{,])['"]?{re.escape(f)}['"]?\s*:""", block):
            missing.append(f)
    return missing


def _missing_from_zap_fields(block: str, fields: list[str]) -> list[str]:
    """zap: fields must appear as ``zap.String("field", ...)`` etc."""
    missing = []
    for f in fields:
        pattern = rf"""zap\.(?:String|Int|Bool|Float64|Any|Field)\s*\(\s*['"{re.escape(f)}['"]"""
        # Simplified: just look for the field name as a quoted string near zap.*
        if not re.search(rf"""['"]{re.escape(f)}['"]""", block):
            missing.append(f)
    return missing


def _missing_from_with_fields(block: str, fields: list[str]) -> list[str]:
    """logrus: fields must appear as string keys inside logrus.Fields{...}."""
    if not re.search(r"\.WithFields\s*\(", block):
        # Bare logrus.Info("...") without WithFields → all fields missing
        return list(fields)
    missing = []
    for f in fields:
        if not re.search(rf"""['"]{re.escape(f)}['"]\s*:""", block):
            missing.append(f)
    return missing


def _missing_from_zerolog_chain(block: str, fields: list[str]) -> list[str]:
    """zerolog: fields must appear as .Str("field", ...) chain calls."""
    missing = []
    for f in fields:
        if not re.search(rf"""\.(?:Str|Interface)\s*\(\s*['"]?{re.escape(f)}['"]?""", block):
            missing.append(f)
    return missing


# ---------------------------------------------------------------------------
# Strategy dispatch
# ---------------------------------------------------------------------------

_STRATEGY_FN = {
    "regex+extra-dict": _missing_from_extra_dict,
    "regex+kwargs": _missing_from_kwargs,
    "regex+bind-or-kwargs": _missing_from_bind_or_kwargs,
    "regex+object-keys": _missing_from_object_keys,
    "regex+zap-fields": _missing_from_zap_fields,
    "regex+with-fields": _missing_from_with_fields,
    "regex+zerolog-chain": _missing_from_zerolog_chain,
}

_FRAMEWORK_DEFAULT_STRATEGY: dict[LogFramework, str] = {
    LogFramework.PYTHON_LOGGING: "regex+extra-dict",
    LogFramework.STRUCTLOG: "regex+kwargs",
    LogFramework.LOGURU: "regex+bind-or-kwargs",
    LogFramework.WINSTON: "regex+object-keys",
    LogFramework.PINO: "regex+object-keys",
    LogFramework.BUNYAN: "regex+object-keys",
    LogFramework.ZAP: "regex+zap-fields",
    LogFramework.LOGRUS: "regex+with-fields",
    LogFramework.ZEROLOG: "regex+zerolog-chain",
}


def _find_missing(framework: LogFramework, block: str, fields: list[str]) -> list[str]:
    strategy = _FRAMEWORK_DEFAULT_STRATEGY.get(framework, "regex+kwargs")
    fn = _STRATEGY_FN.get(strategy, _missing_from_kwargs)
    return fn(block, fields)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_file(
    path: str | Path,
    config: LogLinterConfig | None = None,
) -> list[LogViolation]:
    """Check a single source file for structured-log violations.

    Parameters
    ----------
    path:
        Path to the source file.
    config:
        Linter configuration.  Auto-detects the framework when
        ``config.framework`` is ``None``.

    Returns
    -------
    list[LogViolation]
        All violations found in the file (empty list if clean).
    """
    if config is None:
        config = LogLinterConfig()

    path = Path(path)
    lang = _EXT_TO_LANG.get(path.suffix)
    if lang is None:
        return []

    try:
        src = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    # Determine framework
    framework = config.framework
    if framework is None:
        from .detector import detect_framework

        framework = detect_framework(path)

    # Skip files that don't import/use the framework at all
    import_guard = _REQUIRE_IMPORT.get(framework)
    if import_guard and not import_guard.search(src):
        return []

    call_pattern = _LOG_CALL_PATTERNS.get(framework)
    if call_pattern is None:
        return []

    lines = src.splitlines()
    violations: list[LogViolation] = []

    for i, line in enumerate(lines):
        m = call_pattern.search(line)
        if m is None:
            continue

        block = _extract_block(lines, i)
        missing = _find_missing(framework, block, config.required_fields)

        if missing:
            violations.append(
                LogViolation(
                    file=path,
                    line=i + 1,
                    column=m.start(),
                    message=f"Log call missing required structured fields: {missing}",
                    severity=config.severity,
                    rule="structured-log-fields",
                    snippet=line.rstrip(),
                )
            )

    return violations


def check_directory(
    path: str | Path,
    config: LogLinterConfig | None = None,
) -> list[LogViolation]:
    """Recursively check all source files under *path* for structured-log violations.

    Parameters
    ----------
    path:
        Root directory to scan.
    config:
        Linter configuration shared across all files.  When
        ``config.framework`` is ``None`` the framework is auto-detected
        per file.

    Returns
    -------
    list[LogViolation]
        All violations found across the directory tree, sorted by file path
        then line number.
    """
    if config is None:
        config = LogLinterConfig()

    path = Path(path)
    source_extensions = set(_EXT_TO_LANG.keys())
    violations: list[LogViolation] = []

    for f in sorted(path.rglob("*")):
        if not f.is_file():
            continue
        if f.suffix not in source_extensions:
            continue

        # Honour ignore_patterns
        rel = str(f.relative_to(path))
        if any(
            fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(f.name, pat)
            for pat in config.ignore_patterns
        ):
            continue

        violations.extend(check_file(f, config))

    return sorted(violations, key=lambda v: (v.file, v.line))
