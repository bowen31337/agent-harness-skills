"""
Data models for log_format_linter.

Structured log pattern (required fields per log entry)
-------------------------------------------------------
    timestamp  -- ISO-8601 datetime  (framework-managed)
    level      -- Severity string    (framework-managed)
    domain     -- Logical subsystem / bounded-context label
    trace_id   -- Request / operation trace identifier
    message    -- Human-readable description of the event
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class Language(str, Enum):
    """Source language of the scanned codebase."""
    PYTHON = "python"
    TYPESCRIPT = "typescript"
    GO = "go"
    UNKNOWN = "unknown"


class LogFramework(str, Enum):
    """Logging framework / library detected in (or configured for) the codebase."""
    # Python
    PYTHON_LOGGING = "python_logging"
    STRUCTLOG = "structlog"
    LOGURU = "loguru"
    # TypeScript / JavaScript
    WINSTON = "winston"
    PINO = "pino"
    BUNYAN = "bunyan"
    # Go
    ZAP = "zap"
    LOGRUS = "logrus"
    ZEROLOG = "zerolog"
    # Fallback
    UNKNOWN = "unknown"


class ViolationSeverity(str, Enum):
    """Severity level attached to a linting violation."""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class LogLinterConfig(BaseModel):
    """Runtime configuration for the log-format linter."""

    required_fields: list[str] = Field(
        default=["domain", "trace_id"],
        description=(
            "Structured fields that must appear on every log call. "
            "'timestamp' and 'level' are managed by the framework itself; "
            "'message' is the log string. Only extra context fields need listing here."
        ),
    )
    severity: ViolationSeverity = Field(
        default=ViolationSeverity.ERROR,
        description="Default severity applied to violations.",
    )
    ignore_patterns: list[str] = Field(
        default_factory=list,
        description="Glob patterns for files or directories to skip during checking.",
    )
    framework: LogFramework | None = Field(
        default=None,
        description="Override framework; auto-detected when None.",
    )
    language: Language | None = Field(
        default=None,
        description="Override language; auto-detected when None.",
    )


class LogViolation(BaseModel):
    """A single linting violation found in a source file."""

    file: Path
    line: int = Field(..., ge=1, description="1-based line number of the violation.")
    column: int = Field(default=0, ge=0, description="0-based column offset.")
    message: str
    severity: ViolationSeverity = ViolationSeverity.ERROR
    rule: str = Field(default="structured-log-fields", description="Rule identifier.")
    snippet: str = Field(default="", description="Source line excerpt.")

    def __str__(self) -> str:
        return f"{self.file}:{self.line}: [{self.severity.value}] {self.message}"


class GeneratorResult(BaseModel):
    """Output of generate_rules()."""

    framework: LogFramework
    language: Language
    config: LogLinterConfig
    rules: dict[str, Any] = Field(
        default_factory=dict,
        description="Generated lint rules. Shape varies by framework/language.",
    )
    description: str = ""
    examples: list[dict[str, str]] = Field(
        default_factory=list,
        description="Good / bad code examples as {'type': 'good'|'bad', 'code': '...'}.",
    )
