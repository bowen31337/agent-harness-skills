"""
harness_skills/models/gate_configs.py
=======================================
Dataclass configuration models for all evaluation gates.

Each gate configuration class is a plain Python dataclass — intentionally
lightweight so gate modules can be imported without pulling in Pydantic.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# BaseGateConfig
# ---------------------------------------------------------------------------


class BaseGateConfig:
    """Base class for all gate configuration dataclasses.

    Provides :meth:`model_dump` so gate orchestration code can serialise
    any config to a plain ``dict`` without importing Pydantic.
    """

    def model_dump(self) -> dict[str, object]:
        """Return the config fields as a plain dictionary."""
        return dataclasses.asdict(self)  # type: ignore[call-overload]


# ---------------------------------------------------------------------------
# DocsFreshnessGate
# ---------------------------------------------------------------------------


@dataclass
class DocsFreshnessGateConfig(BaseGateConfig):
    """Configuration for the documentation-freshness gate.

    Attributes
    ----------
    max_staleness_days:
        Maximum number of days between the ``generated_at`` timestamp and
        today before the content is considered stale.  Defaults to 30.
    fail_on_error:
        When ``True`` (the default), *error*-severity violations cause the
        gate to return ``passed=False`` and exit with a non-zero code.
        Setting this to ``False`` downgrades all violations to *warnings*
        and lets the gate pass regardless.
    tracked_files:
        File names (basenames only) to scan for freshness timestamps.
        ``AGENTS.md`` is always included; additional names may be appended.
    """

    max_staleness_days: int = 30
    fail_on_error: bool = True
    tracked_files: list[str] = field(default_factory=lambda: ["AGENTS.md"])


# ---------------------------------------------------------------------------
# CoverageGate
# ---------------------------------------------------------------------------


@dataclass
class CoverageGateConfig(BaseGateConfig):
    """Configuration for the code-coverage gate.

    Attributes
    ----------
    threshold:
        Minimum required line-coverage percentage expressed as a value
        between 0 and 100 (default: **90.0**).  PRs whose overall coverage
        falls below this bar are blocked when ``fail_on_error=True``.
    fail_on_error:
        When ``True`` (the default), a below-threshold result causes the
        gate to return ``passed=False`` and exit with a non-zero code.
        Setting this to ``False`` emits a *warning* violation but still
        allows the build to continue.
    coverage_file:
        Path to the coverage report, either absolute or relative to the
        repository root passed to :meth:`~CoverageGate.run`.
        Defaults to ``"coverage.xml"`` (the pytest-cov default).
    report_format:
        Hint for the report parser.  ``"auto"`` (default) detects the
        format from the file extension: ``.xml`` → xml, ``.json`` → json,
        ``.info`` / ``.out`` / ``.lcov`` → lcov.  Pass ``"xml"``,
        ``"json"``, or ``"lcov"`` to override auto-detection.
    """

    threshold: float = 90.0
    fail_on_error: bool = True
    coverage_file: str = "coverage.xml"
    report_format: str = "auto"


# ---------------------------------------------------------------------------
# RegressionGate
# ---------------------------------------------------------------------------


@dataclass
class RegressionGateConfig(BaseGateConfig):
    """Configuration for the regression (test-suite) gate."""

    enabled: bool = True
    fail_on_error: bool = True
    timeout_seconds: int = 300
    extra_args: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# SecurityGate
# ---------------------------------------------------------------------------


@dataclass
class SecurityGateConfig(BaseGateConfig):
    """Configuration for the security-scan gate (pip-audit / npm audit / bandit)."""

    enabled: bool = True
    fail_on_error: bool = True
    severity_threshold: str = "HIGH"   # CRITICAL | HIGH | MEDIUM | LOW
    scan_dependencies: bool = True
    scan_secrets: bool = False
    ignore_ids: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# PerformanceGate
# ---------------------------------------------------------------------------


@dataclass
class PerformanceGateConfig(BaseGateConfig):
    """Configuration for the performance-benchmark gate.

    Attributes
    ----------
    enabled:
        Whether the gate is active (default ``True``).  Set to ``False``
        to skip the gate without removing its configuration.
    fail_on_error:
        When ``True`` (the default), *error*-severity violations cause the
        gate to return ``passed=False`` and exit with a non-zero code.
        Setting this to ``False`` downgrades all blocking violations to
        *warnings* and lets the gate pass regardless.
    thresholds_file:
        Path to the YAML rules file that defines per-rule thresholds and
        selectors (default: ``.harness/perf-thresholds.yml``).  Relative
        paths are resolved against the ``repo_root`` passed to
        :meth:`~harness_skills.gates.performance.PerformanceGate.run`.
    spans_file:
        Path to the JSON file containing span records collected by the
        benchmark harness (default: ``perf-spans.json``).  Used only when
        no ``spans`` argument is supplied directly to
        :meth:`~harness_skills.gates.performance.PerformanceGate.run`.
    baseline_file:
        Optional path to a baseline spans JSON for regression comparison.
        When empty (the default), regression checking is skipped even if
        the thresholds YAML has ``baseline.enabled: true``.
    output_file:
        Optional path to write the ``perf-report.json`` output.  When
        empty (the default), no file is written.
    budget_ms:
        Legacy single-threshold budget in milliseconds (retained for
        backward compatibility).  Prefer using ``thresholds_file`` rules.
    regression_threshold_pct:
        Maximum acceptable performance regression vs. baseline as a
        percentage (default: **10.0**).  Overridden by the
        ``baseline.regression_threshold_pct`` field in the YAML when that
        is present.
    """

    enabled: bool = True
    fail_on_error: bool = True
    thresholds_file: str = ".harness/perf-thresholds.yml"
    spans_file: str = "perf-spans.json"
    baseline_file: str = ""
    output_file: str = ""
    # Legacy / simple threshold support
    budget_ms: int = 200
    regression_threshold_pct: float = 10.0


# ---------------------------------------------------------------------------
# ArchitectureGate
# ---------------------------------------------------------------------------


@dataclass
class ArchitectureGateConfig(BaseGateConfig):
    """Configuration for the architecture (import-layer) gate."""

    enabled: bool = True
    fail_on_error: bool = True
    rules: list[str] = field(default_factory=lambda: [
        "no_circular_dependencies",
        "enforce_layer_boundaries",
    ])
    layer_order: list[str] = field(default_factory=lambda: [
        "models", "repositories", "services", "api",
    ])
    report_only: bool = False


# ---------------------------------------------------------------------------
# PrinciplesGate
# ---------------------------------------------------------------------------


@dataclass
class PrinciplesGateConfig(BaseGateConfig):
    """Configuration for the golden-principles gate."""

    enabled: bool = True
    fail_on_error: bool = False   # advisory by default
    principles_file: str = ".claude/principles.yaml"
    rules: list[str] = field(default_factory=lambda: ["all"])


# ---------------------------------------------------------------------------
# TypesGate
# ---------------------------------------------------------------------------


@dataclass
class TypesGateConfig(BaseGateConfig):
    """Configuration for the static type-checking gate (mypy / tsc / pyright)."""

    enabled: bool = True
    fail_on_error: bool = True
    strict: bool = False
    ignore_errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# LintGate
# ---------------------------------------------------------------------------


@dataclass
class LintGateConfig(BaseGateConfig):
    """Configuration for the linting gate (ruff / eslint / golangci-lint)."""

    enabled: bool = True
    fail_on_error: bool = True
    autofix: bool = False
    select: list[str] = field(default_factory=list)
    ignore: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# GATE_CONFIG_CLASSES
# Ordered mapping of gate IDs → config class, used by the runner to iterate
# built-in gates and by config_generator to produce YAML stanzas.
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
# Canonical per-profile default configurations consumed by config_generator.
# ---------------------------------------------------------------------------

PROFILE_GATE_DEFAULTS: dict[str, dict[str, object]] = {
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
