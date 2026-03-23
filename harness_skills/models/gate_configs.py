"""
harness_skills/models/gate_configs.py
=======================================
Pydantic configuration models for all evaluation gates.

Each gate configuration class extends ``BaseGateConfig``, which carries the two
universal control knobs every gate honours:

* ``enabled`` — set ``false`` to skip the gate entirely
* ``fail_on_error`` — set ``false`` to downgrade violations to warnings
  (advisory / non-blocking mode)

Gate-specific threshold fields live on the subclasses and are documented inline.

``PROFILE_GATE_DEFAULTS`` maps each profile name → a dict of gate_id → default
config instance, consumed by ``config_generator.generate_gate_config()`` and
``HarnessConfigLoader.gate_configs()``.

``GATE_CONFIG_CLASSES`` maps gate_id → config class, used by ``HarnessConfigLoader``
to instantiate and validate per-gate configs from YAML overrides.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class BaseGateConfig(BaseModel):
    """Universal control knobs present on every gate.

    Attributes
    ----------
    enabled:
        When ``False`` the gate is skipped entirely and counted as *skipped*
        in the evaluation summary.  Default is ``True``.
    fail_on_error:
        When ``True`` (default), *error*-severity violations cause the gate
        to return ``passed=False`` and exit with a non-zero code.
        Setting this to ``False`` downgrades all violations to *warnings*
        and lets the evaluation continue regardless of the gate outcome.
    """

    enabled: bool = True
    fail_on_error: bool = True

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# DocsFreshnessGate
# ---------------------------------------------------------------------------


class DocsFreshnessGateConfig(BaseGateConfig):
    """Configuration for the documentation-freshness gate.

    Attributes
    ----------
    enabled:
        Inherited from :class:`BaseGateConfig`.  Defaults to ``True``.
    fail_on_error:
        Inherited from :class:`BaseGateConfig`.  Defaults to ``True``.
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
    enabled:
        Inherited from :class:`BaseGateConfig`.  Defaults to ``True``.
    fail_on_error:
        Inherited from :class:`BaseGateConfig`.  Defaults to ``True``.
        Setting this to ``False`` emits a *warning* violation but still
        allows the build to continue.
    threshold:
        Minimum required line-coverage percentage expressed as a value
        between 0 and 100 (default: **90.0**).  PRs whose overall coverage
        falls below this bar are blocked when ``fail_on_error=True``.
    branch_coverage:
        When ``True``, also enforce branch/condition coverage in addition to
        line coverage.  Requires ``pytest-cov >= 4``.  Default: ``False``.
    coverage_file:
        Path to the coverage report, either absolute or relative to the
        repository root passed to :meth:`~CoverageGate.run`.
        Defaults to ``"coverage.xml"`` (the pytest-cov default).
    report_format:
        Hint for the report parser.  ``"auto"`` (default) detects the
        format from the file extension: ``.xml`` → xml, ``.json`` → json,
        ``.info`` / ``.out`` / ``.lcov`` → lcov.  Pass ``"xml"``,
        ``"json"``, or ``"lcov"`` to override auto-detection.
    exclude_patterns:
        List of path patterns to exclude from coverage measurement.
        E.g. ``["tests/", "migrations/"]``.
    """

    threshold: float = 90.0
    branch_coverage: bool = False
    coverage_file: str = "coverage.xml"
    report_format: str = "auto"
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
    """Configuration for the static type-checking gate (mypy / tsc / pyright)."""

    strict: bool = False
    ignore_errors: list[str] = Field(default_factory=list)


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
# Maps gate_id → config class.  Used by HarnessConfigLoader to instantiate
# and validate per-gate configs from YAML overrides.
# ---------------------------------------------------------------------------

GATE_CONFIG_CLASSES: dict[str, type[BaseGateConfig]] = {
    "regression":    RegressionGateConfig,
    "coverage":      CoverageGateConfig,
    "security":      SecurityGateConfig,
    "performance":   PerformanceGateConfig,
    "architecture":  ArchitectureGateConfig,
    "principles":    PrinciplesGateConfig,
    "docs_freshness": DocsFreshnessGateConfig,
    "types":         TypesGateConfig,
    "lint":          LintGateConfig,
}


# ---------------------------------------------------------------------------
# PROFILE_GATE_DEFAULTS
# Canonical per-profile default configurations consumed by config_generator
# and HarnessConfigLoader.
# ---------------------------------------------------------------------------

PROFILE_GATE_DEFAULTS: dict[str, dict[str, Any]] = {
    "starter": {
        "regression":    RegressionGateConfig(
            enabled=True, fail_on_error=True, timeout_seconds=120,
        ),
        "coverage":      CoverageGateConfig(
            enabled=True, threshold=60.0, fail_on_error=True,
        ),
        "security":      SecurityGateConfig(enabled=False),
        "performance":   PerformanceGateConfig(enabled=False),
        "architecture":  ArchitectureGateConfig(
            enabled=False, fail_on_error=False, report_only=True,
        ),
        "principles":    PrinciplesGateConfig(enabled=True, fail_on_error=False),
        "docs_freshness": DocsFreshnessGateConfig(
            enabled=True, max_staleness_days=30,
        ),
        "types":         TypesGateConfig(enabled=False),
        "lint":          LintGateConfig(enabled=True, fail_on_error=True),
    },
    "standard": {
        "regression":    RegressionGateConfig(enabled=True, fail_on_error=True),
        "coverage":      CoverageGateConfig(
            enabled=True, threshold=80.0, fail_on_error=True, branch_coverage=True,
        ),
        "security":      SecurityGateConfig(
            enabled=True, severity_threshold="HIGH",
        ),
        "performance":   PerformanceGateConfig(enabled=False),
        "architecture":  ArchitectureGateConfig(enabled=True, fail_on_error=True),
        "principles":    PrinciplesGateConfig(enabled=True, fail_on_error=True),
        "docs_freshness": DocsFreshnessGateConfig(
            enabled=True, max_staleness_days=14,
        ),
        "types":         TypesGateConfig(enabled=True, fail_on_error=True),
        "lint":          LintGateConfig(enabled=True, fail_on_error=True),
    },
    "advanced": {
        "regression":    RegressionGateConfig(enabled=True, fail_on_error=True),
        "coverage":      CoverageGateConfig(
            enabled=True, threshold=90.0, fail_on_error=True, branch_coverage=True,
        ),
        "security":      SecurityGateConfig(
            enabled=True, severity_threshold="MEDIUM",
            scan_dependencies=True, scan_secrets=True,
        ),
        "performance":   PerformanceGateConfig(
            enabled=True, regression_threshold_pct=10.0,
        ),
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
        "docs_freshness": DocsFreshnessGateConfig(
            enabled=True, max_staleness_days=7,
        ),
        "types":         TypesGateConfig(
            enabled=True, fail_on_error=True, strict=True,
        ),
        "lint":          LintGateConfig(
            enabled=True, fail_on_error=True, autofix=False,
        ),
    },
}
