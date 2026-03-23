"""
Environment-variable pattern detector.

Scans a project directory for environment variable declarations and references
across three source types:

1. ``.env`` template files (``.env.example``, ``.env.sample``, etc.)
2. YAML / TOML / JSON / INI configuration files (``${VAR}`` and ``$VAR`` syntax)
3. Source code files (Python, JavaScript/TypeScript, Go, Ruby, Shell)

Public API
----------
- :func:`detect_env_vars` — scan a path and return a
  :class:`~harness_skills.models.env_vars.EnvVarDetectionResult`.
- :func:`scan_dotenv_file` — parse a single ``.env.example``-style file.
- :func:`scan_config_file` — extract ``${VAR}`` references from a config file.
- :func:`scan_source_file` — find ``os.environ`` / ``process.env`` references.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from harness_skills.models.base import Status
from harness_skills.models.env_vars import (
    EnvVarDetectionResult,
    EnvVarEntry,
    EnvVarSource,
)

# ---------------------------------------------------------------------------
# File-name patterns
# ---------------------------------------------------------------------------

#: Glob patterns for .env template files.
_DOTENV_GLOBS: Sequence[str] = (
    ".env.example",
    ".env.sample",
    ".env.template",
    ".env.example.local",
    ".env.dist",
    "*.env.example",
    "*.env.sample",
)

#: Extensions recognised as configuration files.
_CONFIG_EXTENSIONS: frozenset[str] = frozenset(
    {".yaml", ".yml", ".toml", ".json", ".ini", ".cfg", ".conf"}
)

#: Extensions recognised as source-code files, mapped to a language tag.
_SOURCE_EXTENSIONS: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".go": "go",
    ".rb": "ruby",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".fish": "shell",
}

#: Directory names to skip during recursive scan.
_SKIP_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "dist",
        "build",
        ".claw-forge",
        ".tox",
    }
)

# ---------------------------------------------------------------------------
# Regex patterns — .env file format
# ---------------------------------------------------------------------------

# KEY=value  (required — not commented out)
_DOTENV_REQUIRED = re.compile(
    r"^(?P<key>[A-Z_][A-Z0-9_]*)=(?P<value>.*)$"
)

# # KEY=value  (commented out — optional variable documented as example)
_DOTENV_OPTIONAL = re.compile(
    r"^#\s*(?P<key>[A-Z_][A-Z0-9_]*)=(?P<value>.*)$"
)

# Standalone comment line (no KEY= form)
_DOTENV_COMMENT = re.compile(r"^#\s*(?P<text>.+)$")

# ---------------------------------------------------------------------------
# Regex patterns — config files (YAML/TOML/JSON/INI)
# ---------------------------------------------------------------------------

# Matches ${VAR_NAME} or $VAR_NAME (shell-style expansion)
_CONFIG_SHELL_VAR = re.compile(r"\$\{(?P<key>[A-Z_][A-Z0-9_]*)\}|\$(?P<bare>[A-Z_][A-Z0-9_]{2,})")

# ---------------------------------------------------------------------------
# Regex patterns — source code
# ---------------------------------------------------------------------------

# Python: os.environ['KEY'] / os.environ.get('KEY') / os.getenv('KEY')
_PY_ENVIRON = re.compile(
    r"""os\.environ(?:\.get)?\(\s*['"](?P<key>[A-Z_][A-Z0-9_]*)['"]"""
    r"""|os\.getenv\(\s*['"](?P<key2>[A-Z_][A-Z0-9_]*)['"]""",
    re.VERBOSE,
)

# Python: environ['KEY'] (when `from os import environ` / `from os.environ import ...`)
_PY_ENVIRON_BARE = re.compile(
    r"""(?<!\w)environ\[['"](?P<key>[A-Z_][A-Z0-9_]*)['"]"""
)

# Python dotenv: config('KEY') / env('KEY') / settings.KEY pattern
_PY_DOTENV_CONFIG = re.compile(
    r"""(?:config|env|get_env)\(\s*['"](?P<key>[A-Z_][A-Z0-9_]*)['"]"""
)

# JavaScript/TypeScript: process.env.KEY / process.env['KEY']
_JS_PROCESS_ENV = re.compile(
    r"""process\.env\.(?P<key>[A-Za-z_][A-Za-z0-9_]*)|"""
    r"""process\.env\[['"](?P<key2>[A-Za-z_][A-Za-z0-9_]*)['"]"""
)

# Go: os.Getenv("KEY") / os.LookupEnv("KEY")
_GO_GETENV = re.compile(
    r"""os\.(?:Getenv|LookupEnv)\(\s*"(?P<key>[A-Z_][A-Z0-9_]*)"\s*\)"""
)

# Ruby: ENV['KEY'] / ENV["KEY"] / ENV.fetch('KEY') / ENV.fetch("KEY")
_RUBY_ENV = re.compile(
    r"""ENV\[['"](?P<key>[A-Z_][A-Z0-9_]*)['"]"""
    r"""|ENV\.fetch\(['"](?P<key2>[A-Z_][A-Z0-9_]*)['"]"""
)

# Shell: $KEY / ${KEY} used in assignments or exports
_SHELL_ENV = re.compile(
    r"""(?:export\s+)?(?P<key>[A-Z_][A-Z0-9_]*)=|\$\{?(?P<ref>[A-Z_][A-Z0-9_]*)\}?"""
)


def _relative(path: Path, root: Path) -> str:
    """Return *path* relative to *root*, or the string form if not possible."""
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


# ---------------------------------------------------------------------------
# .env file scanner
# ---------------------------------------------------------------------------


def scan_dotenv_file(path: Path, root: Path) -> list[EnvVarEntry]:
    """Parse a ``.env.example``-style file and return one entry per variable.

    Rules:
    - ``KEY=value`` lines → required=True
    - ``# KEY=value`` lines → required=False (documented as optional)
    - Pure comment lines accumulate as context for the *next* variable found.
    - Blank lines reset the accumulated comment context.
    """
    entries: list[EnvVarEntry] = []
    pending_comment: list[str] = []

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    rel_path = _relative(path, root)

    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()

        if not line:
            pending_comment.clear()
            continue

        # Required variable (KEY=value)
        m = _DOTENV_REQUIRED.match(line)
        if m:
            comment = " ".join(pending_comment) if pending_comment else None
            entries.append(
                EnvVarEntry(
                    name=m.group("key"),
                    source=EnvVarSource.DOTENV_EXAMPLE,
                    file_path=rel_path,
                    line_number=lineno,
                    default_value=m.group("value") or None,
                    comment=comment,
                    required=True,
                )
            )
            pending_comment.clear()
            continue

        # Optional variable (# KEY=value)
        m = _DOTENV_OPTIONAL.match(line)
        if m:
            comment = " ".join(pending_comment) if pending_comment else None
            entries.append(
                EnvVarEntry(
                    name=m.group("key"),
                    source=EnvVarSource.DOTENV_EXAMPLE,
                    file_path=rel_path,
                    line_number=lineno,
                    default_value=m.group("value") or None,
                    comment=comment,
                    required=False,
                )
            )
            pending_comment.clear()
            continue

        # Standalone comment — accumulate for context
        m = _DOTENV_COMMENT.match(line)
        if m:
            pending_comment.append(m.group("text").strip())

    return entries


# ---------------------------------------------------------------------------
# Config-file scanner
# ---------------------------------------------------------------------------


def scan_config_file(path: Path, root: Path) -> list[EnvVarEntry]:
    """Extract ``${VAR}`` or ``$VAR`` references from a configuration file."""
    entries: list[EnvVarEntry] = []

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    rel_path = _relative(path, root)

    for lineno, line in enumerate(text.splitlines(), start=1):
        for m in _CONFIG_SHELL_VAR.finditer(line):
            key = m.group("key") or m.group("bare")
            if key:
                entries.append(
                    EnvVarEntry(
                        name=key,
                        source=EnvVarSource.CONFIG_FILE,
                        file_path=rel_path,
                        line_number=lineno,
                        required=True,
                    )
                )

    return entries


# ---------------------------------------------------------------------------
# Source-file scanner
# ---------------------------------------------------------------------------

_SOURCE_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "python": [_PY_ENVIRON, _PY_ENVIRON_BARE, _PY_DOTENV_CONFIG],
    "javascript": [_JS_PROCESS_ENV],
    "typescript": [_JS_PROCESS_ENV],
    "go": [_GO_GETENV],
    "ruby": [_RUBY_ENV],
    "shell": [_SHELL_ENV],
}

# Group names tried in order for each pattern.
_KEY_GROUPS = ("key", "key2", "ref")


def scan_source_file(path: Path, root: Path, language: str) -> list[EnvVarEntry]:
    """Scan a source file for environment-variable read calls.

    Returns one :class:`EnvVarEntry` per match, with ``source=SOURCE_CODE``
    and ``required=True`` (reading a var at runtime is always a hard
    dependency unless the caller provides a default — we conservatively
    mark it required).
    """
    entries: list[EnvVarEntry] = []
    patterns = _SOURCE_PATTERNS.get(language, [])

    if not patterns:
        return []

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    rel_path = _relative(path, root)

    for lineno, line in enumerate(text.splitlines(), start=1):
        for pattern in patterns:
            for m in pattern.finditer(line):
                key: str | None = None
                for group in _KEY_GROUPS:
                    try:
                        key = m.group(group)
                    except IndexError:
                        continue
                    if key:
                        break

                if not key:
                    continue

                # Skip obvious false-positives that are too short or all-lowercase
                if len(key) < 2 or key.islower():
                    continue

                entries.append(
                    EnvVarEntry(
                        name=key,
                        source=EnvVarSource.SOURCE_CODE,
                        file_path=rel_path,
                        line_number=lineno,
                        required=True,
                    )
                )

    return entries


# ---------------------------------------------------------------------------
# Top-level scanner
# ---------------------------------------------------------------------------


def detect_env_vars(
    path: str | Path = ".",
    *,
    skip_dirs: frozenset[str] | None = None,
    include_config: bool = True,
    include_source: bool = True,
) -> EnvVarDetectionResult:
    """Detect environment variable patterns under *path*.

    Parameters
    ----------
    path:
        Root directory to scan. Defaults to the current working directory.
    skip_dirs:
        Directory names to exclude (merged with the built-in skip list).
    include_config:
        Whether to scan YAML/TOML/JSON/INI config files for ``${VAR}`` refs.
    include_source:
        Whether to scan source files for ``os.environ`` / ``process.env`` refs.

    Returns
    -------
    EnvVarDetectionResult
        Structured result containing all discovered entries plus summary stats.
    """
    root = Path(path).resolve()
    effective_skip = _SKIP_DIRS | (skip_dirs or frozenset())

    all_entries: list[EnvVarEntry] = []
    dotenv_files: list[str] = []
    config_files: list[str] = []
    source_files_scanned = 0

    # ── Collect all files under root, skipping excluded directories ──────────
    candidates: list[Path] = []
    if root.is_file():
        candidates = [root]
    else:
        for item in root.rglob("*"):
            # Prune hidden / vendor directories
            if any(part in effective_skip for part in item.parts):
                continue
            if item.is_file():
                candidates.append(item)

    for file_path in candidates:
        name = file_path.name
        suffix = file_path.suffix.lower()

        # ── .env template files ───────────────────────────────────────────
        is_dotenv = any(
            file_path.match(g) or name == g or name.endswith(g)
            for g in _DOTENV_GLOBS
        )
        if is_dotenv:
            entries = scan_dotenv_file(file_path, root)
            if entries:
                dotenv_files.append(_relative(file_path, root))
                all_entries.extend(entries)
            continue

        # ── Config files ──────────────────────────────────────────────────
        if include_config and suffix in _CONFIG_EXTENSIONS:
            entries = scan_config_file(file_path, root)
            if entries:
                config_files.append(_relative(file_path, root))
                all_entries.extend(entries)
            continue

        # ── Source files ──────────────────────────────────────────────────
        if include_source:
            lang = _SOURCE_EXTENSIONS.get(suffix)
            if lang:
                source_files_scanned += 1
                entries = scan_source_file(file_path, root, lang)
                all_entries.extend(entries)

    unique_names = sorted({e.name for e in all_entries})

    return EnvVarDetectionResult(
        command="detect-env-vars",
        status=Status.PASSED,
        timestamp=datetime.now(tz=timezone.utc).isoformat(),
        scanned_path=str(path),
        env_vars=all_entries,
        unique_var_names=unique_names,
        dotenv_files_found=sorted(set(dotenv_files)),
        config_files_found=sorted(set(config_files)),
        source_files_scanned=source_files_scanned,
        total_vars_found=len(all_entries),
    )
