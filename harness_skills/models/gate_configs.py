"""
harness_skills/models/gate_configs.py
=======================================
Pydantic configuration models for all evaluation gates.

Each gate configuration class extends :class:`BaseGateConfig` and exposes
only the fields relevant to that gate.  Pydantic's ``model_dump()`` /
``model_validate()`` methods are used by :class:`HarnessConfigLoader` to
merge YAML overrides onto profile defaults at runtime.

All classes can be instantiated with keyword arguments just like dataclasses:

    cfg = CoverageGateConfig(threshold=85.0, fail_on_error=False)
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class BaseGateConfig(BaseModel):
    """Shared gate fields.  All built-in gate configs extend this."""

    model_config = ConfigDict(extra="allow")

    enabled: bool = True
    fail_on_error: bool = True


# ---------------------------------------------------------------------------
# RegressionGate
# ---------------------------------------------------------------------------


class RegressionGateConfig(BaseGateConfig):
    """Configuration for the regression (test-suite) gate."""

    timeout_seconds: int = 120
    extra_args: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# CoverageGate
# ---------------------------------------------------------------------------


class CoverageGateConfig(BaseGateConfig):
    """Configuration for the code-coverage gate."""

    threshold: float = 90.0
    branch_coverage: bool = False
    exclude_patterns: list[str] = Field(default_factory=list)
    coverage_file: str = "coverage.xml"
    report_format: str = "auto"


# ---------------------------------------------------------------------------
# SecurityGate
# ---------------------------------------------------------------------------


class SecurityGateConfig(BaseGateConfig):
    """Configuration for the security-scanning gate."""

    severity_threshold: str = "HIGH"
    scan_dependencies: bool = True
    scan_secrets: bool = False
    ignore_ids: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# PerformanceGate
# ---------------------------------------------------------------------------


class PerformanceGateConfig(BaseGateConfig):
    """Configuration for the performance-benchmark gate."""

    budget_ms: int = 500
    regression_threshold_pct: int = 20


# ---------------------------------------------------------------------------
# ArchitectureGate
# ---------------------------------------------------------------------------


class ArchitectureGateConfig(BaseGateConfig):
    """Configuration for the import-layer-violation gate."""

    layer_order: list[str] = Field(
        default_factory=lambda: ["domain", "application", "infrastructure", "presentation"]
    )
    rules: list[str] = Field(
        default_factory=lambda: ["no_circular_dependencies", "enforce_layer_boundaries"]
    )
    report_only: bool = False


# ---------------------------------------------------------------------------
# PrinciplesGate
# ---------------------------------------------------------------------------


class PrinciplesGateConfig(BaseGateConfig):
    """Configuration for the coding-principles scanner."""

    principles_file: str = ".harness-principles.md"
    rules: list[str] = Field(
        default_factory=lambda: ["no_magic_numbers", "no_hardcoded_urls"]
    )


# ---------------------------------------------------------------------------
# DocsFreshnessGate
# ---------------------------------------------------------------------------


class DocsFreshnessGateConfig(BaseGateConfig):
    """Configuration for the documentation-freshness gate."""

    max_staleness_days: int = 30
    tracked_files: list[str] = Field(default_factory=lambda: ["AGENTS.md"])


# ---------------------------------------------------------------------------
# TypesGate
# ---------------------------------------------------------------------------


class TypesGateConfig(BaseGateConfig):
    """Configuration for the static type-checking gate."""

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
# Registry: gate_id -> config class
# ---------------------------------------------------------------------------

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
# Profile defaults
# ---------------------------------------------------------------------------

PROFILE_GATE_DEFAULTS: dict[str, dict[str, BaseGateConfig]] = {
    "starter": {
        "regression":     RegressionGateConfig(enabled=True, timeout_seconds=120),
        "coverage":       CoverageGateConfig(enabled=True, threshold=60.0, fail_on_error=True),
        "security":       SecurityGateConfig(enabled=False),
        "performance":    PerformanceGateConfig(enabled=False),
        "architecture":   ArchitectureGateConfig(enabled=False),
        "principles":     PrinciplesGateConfig(enabled=False),
        "docs_freshness": DocsFreshnessGateConfig(enabled=True, max_staleness_days=30),
        "types":          TypesGateConfig(enabled=False),
        "lint":           LintGateConfig(enabled=True, fail_on_error=False),
    },
    "standard": {
        "regression":     RegressionGateConfig(enabled=True, timeout_seconds=300),
        "coverage":       CoverageGateConfig(enabled=True, threshold=80.0, branch_coverage=True),
        "security":       SecurityGateConfig(enabled=True, severity_threshold="HIGH"),
        "performance":    PerformanceGateConfig(enabled=False),
        "architecture":   ArchitectureGateConfig(enabled=True),
        "principles":     PrinciplesGateConfig(enabled=True, fail_on_error=False),
        "docs_freshness": DocsFreshnessGateConfig(enabled=True, max_staleness_days=14),
        "types":          TypesGateConfig(enabled=True),
        "lint":           LintGateConfig(enabled=True),
    },
    "advanced": {
        "regression":     RegressionGateConfig(enabled=True, timeout_seconds=600),
        "coverage":       CoverageGateConfig(enabled=True, threshold=90.0, branch_coverage=True),
        "security":       SecurityGateConfig(
            enabled=True, severity_threshold="MEDIUM", scan_secrets=True
        ),
        "performance":    PerformanceGateConfig(
            enabled=True, budget_ms=200, regression_threshold_pct=10
        ),
        "architecture":   ArchitectureGateConfig(enabled=True),
        "principles":     PrinciplesGateConfig(enabled=True),
        "docs_freshness": DocsFreshnessGateConfig(enabled=True, max_staleness_days=7),
        "types":          TypesGateConfig(enabled=True, strict=True),
        "lint":           LintGateConfig(enabled=True),
    },
}
