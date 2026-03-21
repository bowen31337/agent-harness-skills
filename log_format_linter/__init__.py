"""
log_format_linter — structured-log linter rules generator and source checker.

Every log statement must carry: domain, trace_id (plus timestamp, level, message
which are framework-managed). This package generates per-framework linter rules
and scans Python / TypeScript / Go source files for violations.

Public API
----------
generate_rules(framework, config)  → GeneratorResult
detect_framework(path)             → LogFramework
check_file(path, config)           → list[LogViolation]
check_directory(path, config)      → list[LogViolation]
"""

from .checker import check_directory, check_file
from .detector import detect_framework
from .generator import generate_rules
from .models import (
    GeneratorResult,
    Language,
    LogFramework,
    LogLinterConfig,
    LogViolation,
    ViolationSeverity,
)

__all__ = [
    "Language",
    "LogFramework",
    "ViolationSeverity",
    "LogLinterConfig",
    "LogViolation",
    "GeneratorResult",
    "generate_rules",
    "detect_framework",
    "check_file",
    "check_directory",
]
