"""Structured logging configuration for agent-harness-skills.

Framework detected: **python_logging** (stdlib ``logging`` module).

Convention
----------
Every log entry MUST carry five required fields:

+------------+-----------------------------------+----------------------------+
| Field      | Format                            | Source                     |
+============+===================================+============================+
| timestamp  | ISO-8601 UTC, millisecond prec.   | auto — formatter           |
| level      | DEBUG/INFO/WARN/ERROR/FATAL       | auto — logging level       |
| domain     | dot-separated string              | caller — ``get_logger()``  |
| trace_id   | 32-char lowercase hex (W3C)       | context var / auto-gen     |
| message    | non-empty UTF-8 string            | caller — log call          |
+------------+-----------------------------------+----------------------------+

Extra key/value pairs are accepted via ``extra={"key": value}`` and are
serialised under the ``"extra"`` object in the JSON output.  Extra keys must
not shadow the five required field names.

Quick start
-----------
::

    from harness_skills.logging_config import configure, get_logger, set_trace_id

    configure()                       # stdout NDJSON, INFO level
    log = get_logger("harness.auth")

    with set_trace_id("4bf92f3577b34da6a3ce929d0e0e4736"):
        log.info("user signed in", extra={"user_id": "u-42"})
    # → {"timestamp":"2026-03-13T14:22:05.123Z","level":"INFO",
    #    "domain":"harness.auth","trace_id":"4bf92f3577b34da6a3ce929d0e0e4736",
    #    "message":"user signed in","extra":{"user_id":"u-42"}}
"""

from __future__ import annotations

import contextvars
import json
import logging
import logging.handlers
import os
import re
import secrets
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TRACE_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_RESERVED_FIELDS = frozenset({"timestamp", "level", "domain", "trace_id", "message"})

# Canonical level names (stdlib WARNING → convention WARN, CRITICAL → FATAL)
_LEVEL_MAP: dict[int, str] = {
    logging.DEBUG: "DEBUG",
    logging.INFO: "INFO",
    logging.WARNING: "WARN",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "FATAL",
}

# ---------------------------------------------------------------------------
# Trace-ID context (asyncio + thread-safe via ContextVar)
# ---------------------------------------------------------------------------

_trace_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "trace_id", default=None
)


def _generate_trace_id() -> str:
    """Return a fresh W3C-compatible 32-character lowercase hex trace ID."""
    return secrets.token_hex(16)  # 16 bytes → 32 hex chars


def get_current_trace_id() -> str:
    """Return the active trace ID, generating a fresh one if none is set."""
    tid = _trace_id_var.get()
    if tid is None:
        tid = _generate_trace_id()
    return tid


@contextmanager
def set_trace_id(trace_id: str) -> Generator[None, None, None]:
    """Context manager that pushes *trace_id* into the current context.

    Works correctly across both threads (via ``ContextVar`` copy-on-write
    semantics) and asyncio tasks.

    Parameters
    ----------
    trace_id:
        A 32-character lowercase hex string (W3C Trace Context compatible).

    Raises
    ------
    ValueError
        If *trace_id* is not exactly 32 lowercase hex characters.

    Example
    -------
    ::

        with set_trace_id("4bf92f3577b34da6a3ce929d0e0e4736"):
            logger.info("processing request")
    """
    if not _TRACE_ID_RE.match(trace_id):
        raise ValueError(
            f"trace_id must be exactly 32 lowercase hex characters; got {trace_id!r}"
        )
    token = _trace_id_var.set(trace_id)
    try:
        yield
    finally:
        _trace_id_var.reset(token)


# ---------------------------------------------------------------------------
# JSON Formatter
# ---------------------------------------------------------------------------

_FORBIDDEN_IN_EXTRA = _RESERVED_FIELDS


class ConventionFormatter(logging.Formatter):
    """JSON formatter that enforces the five-field logging convention.

    Emits one compact NDJSON line per record::

        {"timestamp": "...", "level": "...", "domain": "...",
         "trace_id": "...", "message": "...", "extra": {...}}

    The ``extra`` object is omitted when empty.

    Parameters
    ----------
    pretty:
        If *True* emit indented JSON (4 spaces) for human-readable output
        instead of compact NDJSON.  Intended for local development only.
    """

    def __init__(self, *, pretty: bool = False) -> None:
        super().__init__()
        self._pretty = pretty

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _iso_timestamp(record: logging.LogRecord) -> str:
        dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
        # Format with millisecond precision and explicit Z suffix
        return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"

    @staticmethod
    def _extract_extra(record: logging.LogRecord) -> dict[str, Any]:
        """Pull caller-supplied extra keys from the LogRecord."""
        skip = {
            # stdlib LogRecord built-ins
            "name", "msg", "args", "levelname", "levelno", "pathname",
            "filename", "module", "exc_info", "exc_text", "stack_info",
            "lineno", "funcName", "created", "msecs", "relativeCreated",
            "thread", "threadName", "processName", "process", "taskName",
            "message",
        }
        extra: dict[str, Any] = {}
        for key, value in record.__dict__.items():
            if key.startswith("_") or key in skip:
                continue
            if key in _FORBIDDEN_IN_EXTRA:
                # Silently drop keys that would shadow required fields
                continue
            extra[key] = value
        return extra

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        # ── Required fields ───────────────────────────────────────────
        entry: dict[str, Any] = {
            "timestamp": self._iso_timestamp(record),
            "level": _LEVEL_MAP.get(record.levelno, record.levelname),
            "domain": record.name,  # set by get_logger(domain)
            "trace_id": get_current_trace_id(),
            "message": record.getMessage(),
        }

        # ── Exception information (appended to message) ────────────────
        if record.exc_info:
            exc_text = self.formatException(record.exc_info)
            entry["message"] = f"{entry['message']}\n{exc_text}"

        # ── Optional extra fields ─────────────────────────────────────
        extra = self._extract_extra(record)
        if extra:
            entry["extra"] = extra

        indent = 4 if self._pretty else None
        return json.dumps(entry, default=str, ensure_ascii=False, indent=indent)


# ---------------------------------------------------------------------------
# Pretty (dev) formatter with ANSI colours
# ---------------------------------------------------------------------------

_ANSI_RESET = "\033[0m"
_LEVEL_COLOURS: dict[str, str] = {
    "DEBUG": "\033[36m",   # cyan
    "INFO": "\033[32m",    # green
    "WARN": "\033[33m",    # yellow
    "ERROR": "\033[31m",   # red
    "FATAL": "\033[1;31m", # bright red + bold
}


class PrettyConventionFormatter(logging.Formatter):
    """Human-readable formatter for interactive / TTY use.

    Output format::

        2026-03-13T14:22:05.123Z  INFO  harness.auth  [4bf92f35]  user signed in  {extra}
    """

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
        ts = dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"
        level_str = _LEVEL_MAP.get(record.levelno, record.levelname)
        colour = _LEVEL_COLOURS.get(level_str, "")
        trace_id = get_current_trace_id()
        short_tid = trace_id[:8]  # abbreviated for readability
        message = record.getMessage()

        parts = [
            ts,
            f"{colour}{level_str:<5}{_ANSI_RESET}",
            f"\033[34m{record.name}\033[0m",
            f"[{short_tid}]",
            message,
        ]

        if record.exc_info:
            parts.append("\n" + self.formatException(record.exc_info))

        return "  ".join(parts)


# ---------------------------------------------------------------------------
# DomainLogger — thin wrapper that stores the domain name
# ---------------------------------------------------------------------------


class DomainLogger:
    """A ``logging.Logger`` bound to a *domain* string.

    Provides the five severity methods defined by the convention:
    :meth:`debug`, :meth:`info`, :meth:`warn`, :meth:`error`, :meth:`fatal`.

    Use :func:`get_logger` to obtain an instance.
    """

    def __init__(self, logger: logging.Logger, *, bound: dict[str, Any] | None = None) -> None:
        self._logger = logger
        self._bound: dict[str, Any] = bound or {}

    # ------------------------------------------------------------------
    # Log-level methods
    # ------------------------------------------------------------------

    def _log(self, level: int, msg: str, **extra: Any) -> None:
        merged = {**self._bound, **extra}
        # Silently drop keys that would shadow required fields
        safe_extra = {k: v for k, v in merged.items() if k not in _FORBIDDEN_IN_EXTRA}
        self._logger.log(level, msg, extra=safe_extra, stacklevel=2)

    def debug(self, msg: str, **extra: Any) -> None:
        """Emit a DEBUG-level log entry."""
        self._log(logging.DEBUG, msg, **extra)

    def info(self, msg: str, **extra: Any) -> None:
        """Emit an INFO-level log entry."""
        self._log(logging.INFO, msg, **extra)

    def warn(self, msg: str, **extra: Any) -> None:
        """Emit a WARN-level log entry (convention alias for WARNING)."""
        self._log(logging.WARNING, msg, **extra)

    def error(self, msg: str, **extra: Any) -> None:
        """Emit an ERROR-level log entry."""
        self._log(logging.ERROR, msg, **extra)

    def fatal(self, msg: str, **extra: Any) -> None:
        """Emit a FATAL-level log entry (convention alias for CRITICAL)."""
        self._log(logging.CRITICAL, msg, **extra)

    # ------------------------------------------------------------------
    # Field binding
    # ------------------------------------------------------------------

    def bind(self, **fields: Any) -> "DomainLogger":
        """Return a child logger with *fields* pre-attached to every entry.

        Supports unlimited nesting — fields accumulate across :meth:`bind` calls::

            base = get_logger("payments")
            ctx  = base.bind(request_id="r-99", user_id="u-42")
            ctx.info("charge processed", amount=1999)
            # → extra: {request_id: "r-99", user_id: "u-42", amount: 1999}
        """
        merged = {**self._bound, **fields}
        return DomainLogger(self._logger, bound=merged)

    # ------------------------------------------------------------------
    # Passthrough helpers
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        """The domain string this logger is bound to."""
        return self._logger.name

    def setLevel(self, level: int | str) -> None:  # noqa: N802
        """Delegate level changes to the underlying stdlib logger."""
        self._logger.setLevel(level)


# ---------------------------------------------------------------------------
# Public factory functions
# ---------------------------------------------------------------------------


def get_logger(domain: str) -> DomainLogger:
    """Return a :class:`DomainLogger` bound to *domain*.

    Parameters
    ----------
    domain:
        Dot-separated service scope string, e.g. ``"payments.stripe.webhook"``.
        Must be non-empty.

    Raises
    ------
    ValueError
        If *domain* is empty, whitespace-only, or contains consecutive dots.

    Example
    -------
    ::

        log = get_logger("harness.task_lock")
        log.info("lock acquired", lock_key="feature-42")
    """
    if not domain or not domain.strip():
        raise ValueError("domain must be a non-empty string.")
    if ".." in domain:
        raise ValueError(f"domain must not contain consecutive dots; got {domain!r}")
    return DomainLogger(logging.getLogger(domain))


def root_logger() -> DomainLogger:
    """Return a :class:`DomainLogger` with ``domain="root"`` for top-level use."""
    return get_logger("root")


# ---------------------------------------------------------------------------
# Global configure() — sets up handlers on the root stdlib logger
# ---------------------------------------------------------------------------


def configure(
    *,
    level: int | str = logging.INFO,
    pretty: bool | None = None,
    log_file: str | Path | None = None,
    max_bytes: int = 10 * 1024 * 1024,   # 10 MiB
    backup_count: int = 5,
    propagate: bool = True,
) -> None:
    """Configure the root ``logging`` handler for structured JSON output.

    Call this **once** at application startup before any :func:`get_logger`
    calls emit entries.

    Parameters
    ----------
    level:
        Minimum log level.  Defaults to ``INFO``.
    pretty:
        ``True``  → human-readable coloured TTY output.
        ``False`` → compact NDJSON (default in non-TTY environments).
        ``None``  → auto-detect: pretty when stdout is a TTY, NDJSON otherwise.
    log_file:
        Optional path to a rotating NDJSON log file.  When given, entries are
        written to *both* stdout and the file.
    max_bytes:
        Rotation threshold for the file handler.  Default 10 MiB.
    backup_count:
        Number of rotated files to keep.  Default 5.
    propagate:
        If *False*, suppress entries from propagating further up the hierarchy.

    Example
    -------
    ::

        # Production — compact NDJSON to stdout + rotating file
        configure(level=logging.INFO, log_file="/var/log/harness/app.log")

        # Development — pretty coloured TTY output
        configure(level=logging.DEBUG, pretty=True)
    """
    root = logging.getLogger()
    root.setLevel(level)

    # Clear any pre-existing handlers to avoid duplicate output
    root.handlers.clear()

    # Auto-detect pretty mode
    if pretty is None:
        pretty = sys.stdout.isatty()

    # ── stdout handler ────────────────────────────────────────────────────────
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(level)
    if pretty:
        stdout_handler.setFormatter(PrettyConventionFormatter())
    else:
        stdout_handler.setFormatter(ConventionFormatter())
    root.addHandler(stdout_handler)

    # ── rotating file handler (NDJSON, always compact) ────────────────────────
    if log_file is not None:
        file_path = Path(log_file)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            file_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(ConventionFormatter(pretty=False))
        root.addHandler(file_handler)

    root.propagate = propagate


# ---------------------------------------------------------------------------
# dictConfig-compatible configuration dict (for logging.config.dictConfig)
# ---------------------------------------------------------------------------

#: Pass to ``logging.config.dictConfig(LOGGING_CONFIG)`` as an alternative
#: to calling :func:`configure` directly.  Useful for Django / frameworks
#: that expect a logging configuration dict.
LOGGING_CONFIG: dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "convention_json": {
            "()": ConventionFormatter,
        },
        "convention_pretty": {
            "()": PrettyConventionFormatter,
        },
    },
    "handlers": {
        "stdout_json": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "convention_json",
            "level": "DEBUG",
        },
        "stdout_pretty": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "convention_pretty",
            "level": "DEBUG",
        },
    },
    "root": {
        "level": os.environ.get("LOG_LEVEL", "INFO").upper(),
        "handlers": ["stdout_json"],
    },
}
