"""
harness_skills/models/gate_configs.py
=======================================
Dataclass configuration models for all evaluation gates.

Each gate configuration class is a plain Python dataclass — intentionally
lightweight so gate modules can be imported without pulling in Pydantic.
``BaseGateConfig`` adds ``model_dump()`` / ``model_validate()`` shims so the
:class:`~harness_skills.gates.runner.HarnessConfigLoader` can merge YAML
overrides into typed config objects without a hard Pydantic dependency.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# BaseGateConfig — compatibility shim for HarnessConfigLoader
# ---------------------------------------------------------------------------


class BaseGateConfig:
    """Mixin providing ``model_dump()`` / ``model_validate()`` for gate configs.

    All concrete gate config *dataclasses* inherit from this class so that
    :class:`~harness_skills.gates.runner.HarnessConfigLoader` can serialize
    and deserialize them using the same Pydantic-style API it would use if
    the configs were Pydantic models.
    """

    # ------------------------------------------------------------------
    # Pydantic-compatible API
    # ------------------------------------------------------------------

    def model_dump(self) -> dict[str, Any]:
        """Return a dict of all dataclass fields and their current values."""
        return dataclasses.asdict(self)  # type: ignore[arg-type]

    @classmethod
    def model_validate(cls, data: dict[str, Any]) -> "BaseGateConfig":
        """Construct an instance from *data*, ignoring unknown keys."""
        known = {f.name for f in dataclasses.fields(cls)}  # type: ignore[arg-type]
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)  # type: ignore[call-arg]


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

    enabled: bool = True
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

    enabled: bool = True
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
    """Configuration for the performance-benchmark gate."""

    enabled: bool = False
    fail_on_error: bool = True
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
    """Configuration for the golden-principles compliance gate.

    Attributes
    ----------
    enabled:
        When ``False`` the gate is skipped entirely.
    fail_on_error:
        When ``True``, *any* violation at severity ``"error"`` causes the
        gate to fail.  ``False`` downgrades all errors to warnings (advisory).
    fail_on_critical:
        When ``True`` (the default), violations from principles whose YAML
        ``severity`` is ``"blocking"`` are reported as ``"error"`` and fail
        the gate even in ``fail_on_error=False`` mode.  Set to ``False`` to
        treat blocking violations as warnings.
    principles_file:
        Path (relative to project root) to the YAML principles store.
        Defaults to ``".claude/principles.yaml"``.
    rules:
        List of rule IDs to enable.  ``["all"]`` (the default) activates
        every built-in scanner.  Pass specific rule names such as
        ``["no_magic_numbers", "function_naming"]`` to run a subset.
    """

    enabled: bool = True
    fail_on_error: bool = False        # advisory by default
    fail_on_critical: bool = True      # blocking-severity violations always fail
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
# Registry mapping gate_id → config class.  Consumed by HarnessConfigLoader
# to enumerate all built-in gates and resolve per-gate configurations.
# Order matters: gates run in this order during evaluation.
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
        "principles":    PrinciplesGateConfig(enabled=True, fail_on_error=False, fail_on_critical=True),
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
        "principles":    PrinciplesGateConfig(enabled=True, fail_on_error=True, fail_on_critical=True),
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
        "principles":    PrinciplesGateConfig(
            enabled=True, fail_on_error=True, fail_on_critical=True,
        ),
        "docs_freshness": DocsFreshnessGateConfig(max_staleness_days=14),
        "types":         TypesGateConfig(enabled=True, fail_on_error=True, strict=True),
        "lint":          LintGateConfig(enabled=True, fail_on_error=True, autofix=False),
    },
}
