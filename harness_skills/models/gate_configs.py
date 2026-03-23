"""
harness_skills/models/gate_configs.py
=======================================
Pydantic configuration models for all evaluation gates.

Each gate configuration class inherits from :class:`BaseGateConfig` — a
Pydantic ``BaseModel`` that provides ``model_dump()`` and ``model_validate()``
used by :class:`~harness_skills.gates.runner.HarnessConfigLoader` to merge
profile defaults with YAML overrides.

Unknown YAML keys are silently ignored (``model_config = {"extra": "ignore"}``),
so future harness.config.yaml additions never break older installations.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# BaseGateConfig
# ---------------------------------------------------------------------------


class BaseGateConfig(BaseModel):
    """Shared base for every gate configuration.

    Attributes
    ----------
    enabled:
        When ``False`` the gate is skipped entirely during ``harness evaluate``.
        Defaults to ``True``; individual subclasses may override.
    fail_on_error:
        When ``True`` (the default), *error*-severity violations cause the
        gate to return a non-zero exit code and block merges.
        Set to ``False`` to downgrade all violations to *warnings* (advisory
        mode) without blocking CI.
    """

    model_config: Any = {"extra": "ignore"}

    enabled: bool = True
    fail_on_error: bool = True


# ---------------------------------------------------------------------------
# DocsFreshnessGate
# ---------------------------------------------------------------------------


class DocsFreshnessGateConfig(BaseGateConfig):
    """Configuration for the documentation-freshness gate.

    Attributes
    ----------
    max_staleness_days:
        Maximum number of days between the ``generated_at`` timestamp and
        today before the content is considered stale.  Defaults to 30.
    tracked_files:
        File names (basenames only) to scan for freshness timestamps.
        ``AGENTS.md`` is always included; additional names may be appended.
    """

    max_staleness_days: int = 30
    tracked_files: list[str] = Field(default_factory=lambda: ["AGENTS.md"])


# ---------------------------------------------------------------------------
# CoverageGate
# ---------------------------------------------------------------------------


class CoverageGateConfig(BaseGateConfig):
    """Configuration for the code-coverage gate.

    Attributes
    ----------
    threshold:
        Minimum required line-coverage percentage expressed as a value
        between 0 and 100 (default: **90.0**).  PRs whose overall coverage
        falls below this bar are blocked when ``fail_on_error=True``.
    coverage_file:
        Path to the coverage report, either absolute or relative to the
        repository root passed to :meth:`~CoverageGate.run`.
        Defaults to ``"coverage.xml"`` (the pytest-cov default).
    report_format:
        Hint for the report parser.  ``"auto"`` (default) detects the
        format from the file extension: ``.xml`` → xml, ``.json`` → json,
        ``.info`` / ``.out`` / ``.lcov`` → lcov.  Pass ``"xml"``,
        ``"json"``, or ``"lcov"`` to override auto-detection.
    branch_coverage:
        When ``True``, branch coverage is enforced in addition to line
        coverage.  Defaults to ``False``.
    exclude_patterns:
        File-path glob patterns to exclude from coverage measurement
        (passed as ``--omit`` to pytest-cov).
    """

    threshold: float = 90.0
    coverage_file: str = "coverage.xml"
    report_format: str = "auto"
    branch_coverage: bool = False
    exclude_patterns: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# RegressionGate
# ---------------------------------------------------------------------------


class RegressionGateConfig(BaseGateConfig):
    """Configuration for the regression (test-suite) gate."""

    timeout_seconds: int = 300
    extra_args: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# SecurityGate
# ---------------------------------------------------------------------------


class SecurityGateConfig(BaseGateConfig):
    """Configuration for the security-scan gate (pip-audit / npm audit / bandit)."""

    enabled: bool = True
    severity_threshold: str = "HIGH"   # CRITICAL | HIGH | MEDIUM | LOW
    scan_dependencies: bool = True
    scan_secrets: bool = False
    ignore_ids: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# PerformanceGate
# ---------------------------------------------------------------------------


class PerformanceGateConfig(BaseGateConfig):
    """Configuration for the performance-benchmark gate."""

    enabled: bool = False
    budget_ms: int = 200
    regression_threshold_pct: float = 10.0


# ---------------------------------------------------------------------------
# ArchitectureGate
# ---------------------------------------------------------------------------


class ArchitectureGateConfig(BaseGateConfig):
    """Configuration for the architecture (import-layer) gate."""

    rules: list[str] = Field(default_factory=lambda: [
        "no_circular_dependencies",
        "enforce_layer_boundaries",
    ])
    layer_order: list[str] = Field(default_factory=lambda: [
        "models", "repositories", "services", "api",
    ])
    report_only: bool = False


# ---------------------------------------------------------------------------
# PrinciplesGate
# ---------------------------------------------------------------------------


class PrinciplesGateConfig(BaseGateConfig):
    """Configuration for the golden-principles gate."""

    fail_on_error: bool = False   # advisory by default
    principles_file: str = ".claude/principles.yaml"
    rules: list[str] = Field(default_factory=lambda: ["all"])


# ---------------------------------------------------------------------------
# TypesGate
# ---------------------------------------------------------------------------


class TypesGateConfig(BaseGateConfig):
    """Configuration for the static type-checking gate (mypy / tsc / pyright).

    Attributes
    ----------
    strict:
        When ``True``, passes ``--strict`` to mypy (enables all optional
        error codes: ``disallow_untyped_defs``, ``disallow_any_generics``,
        ``warn_return_any``, etc.).  For tsc, enables
        ``"strict": true`` in the compiler options.  Defaults to ``False``.
    ignore_errors:
        List of mypy error codes (e.g. ``["import", "attr-defined"]``) or
        TypeScript diagnostic codes (e.g. ``["TS2304"]``) to suppress.
        Suppressed errors are excluded from the violation list and never
        cause the gate to fail.
    checker:
        Explicitly select the type checker: ``"mypy"``, ``"pyright"``, or
        ``"tsc"``.  ``"auto"`` (the default) detects the checker from the
        project layout:
        - ``pyproject.toml`` / ``setup.py`` present → mypy
        - ``tsconfig.json`` present → tsc
    paths:
        Paths to pass to the type checker (relative to the repository root).
        Defaults to ``["."]`` (the whole project).
    """

    strict: bool = False
    ignore_errors: list[str] = Field(default_factory=list)
    checker: str = "auto"          # "auto" | "mypy" | "pyright" | "tsc"
    paths: list[str] = Field(default_factory=lambda: ["."])


# ---------------------------------------------------------------------------
# LintGate
# ---------------------------------------------------------------------------


class LintGateConfig(BaseGateConfig):
    """Configuration for the linting gate (ruff / eslint / golangci-lint)."""

    autofix: bool = False
    select: list[str] = Field(default_factory=list)
    ignore: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# GATE_CONFIG_CLASSES
# Registry consumed by HarnessConfigLoader.gate_configs() to resolve per-gate
# config from harness.config.yaml.
# ---------------------------------------------------------------------------

#: Maps gate_id → config class.  Order determines execution priority.
GATE_CONFIG_CLASSES: dict[str, type[BaseGateConfig]] = {
    "regression":     RegressionGateConfig,
    "coverage":       CoverageGateConfig,
    "security":       SecurityGateConfig,
    "performance":    PerformanceGateConfig,
    "architecture":   ArchitectureGateConfig,
    "principles":     PrinciplesGateConfig,
    "docs_freshness": DocsFreshnessGateConfig,
    "types":          TypesGateConfig,
    "lint":           LintGateConfig,
}


# ---------------------------------------------------------------------------
# PROFILE_GATE_DEFAULTS
# Canonical per-profile default configurations consumed by config_generator.
# ---------------------------------------------------------------------------

PROFILE_GATE_DEFAULTS: dict[str, dict[str, BaseGateConfig]] = {
    "starter": {
        "regression":    RegressionGateConfig(enabled=True, fail_on_error=True),
        "coverage":      CoverageGateConfig(threshold=60.0, fail_on_error=True),
        "security":      SecurityGateConfig(enabled=False),
        "performance":   PerformanceGateConfig(enabled=False),
        "architecture":  ArchitectureGateConfig(enabled=False, fail_on_error=False, report_only=True),
        "principles":    PrinciplesGateConfig(enabled=True, fail_on_error=False),
        "docs_freshness": DocsFreshnessGateConfig(max_staleness_days=30),
        "types":         TypesGateConfig(enabled=False),
        "lint":          LintGateConfig(enabled=True, fail_on_error=True),
    },
    "standard": {
        "regression":    RegressionGateConfig(enabled=True, fail_on_error=True),
        "coverage":      CoverageGateConfig(threshold=80.0, fail_on_error=True),
        "security":      SecurityGateConfig(enabled=True, severity_threshold="HIGH"),
        "performance":   PerformanceGateConfig(enabled=False),
        "architecture":  ArchitectureGateConfig(enabled=True, fail_on_error=True),
        "principles":    PrinciplesGateConfig(enabled=True, fail_on_error=True),
        "docs_freshness": DocsFreshnessGateConfig(max_staleness_days=30),
        "types":         TypesGateConfig(enabled=True, fail_on_error=True),
        "lint":          LintGateConfig(enabled=True, fail_on_error=True),
    },
    "advanced": {
        "regression":    RegressionGateConfig(enabled=True, fail_on_error=True),
        "coverage":      CoverageGateConfig(threshold=90.0, fail_on_error=True),
        "security":      SecurityGateConfig(
            enabled=True, severity_threshold="MEDIUM",
            scan_dependencies=True, scan_secrets=True,
        ),
        "performance":   PerformanceGateConfig(enabled=True, regression_threshold_pct=10.0),
        "architecture":  ArchitectureGateConfig(
            enabled=True, fail_on_error=True,
            rules=[
                "no_circular_dependencies",
                "enforce_layer_boundaries",
                "require_interface_contracts",
                "enforce_naming_conventions",
            ],
        ),
        "principles":    PrinciplesGateConfig(enabled=True, fail_on_error=True),
        "docs_freshness": DocsFreshnessGateConfig(max_staleness_days=14),
        "types":         TypesGateConfig(enabled=True, fail_on_error=True, strict=True),
        "lint":          LintGateConfig(enabled=True, fail_on_error=True, autofix=False),
    },
}
