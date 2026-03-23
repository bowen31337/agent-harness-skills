"""
harness_skills/models/gate_configs.py
=======================================
Dataclass configuration models for all evaluation gates.

Each gate configuration class is a plain Python dataclass that inherits from
:class:`BaseGateConfig`.  The base class provides :meth:`~BaseGateConfig.model_dump`
and :meth:`~BaseGateConfig.model_validate` helpers — a lightweight, Pydantic-compatible
interface — so the gate runner can merge YAML overrides with profile defaults
without pulling in Pydantic as a hard dependency for gate modules themselves.

:data:`GATE_CONFIG_CLASSES` maps the canonical gate ID (as used in
``harness.config.yaml``) to the corresponding config class, enabling the
runner to iterate all built-in gates and apply profile defaults automatically.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# BaseGateConfig — common interface for all gate config dataclasses
# ---------------------------------------------------------------------------


class BaseGateConfig:
    """Common interface for all gate configuration dataclasses.

    Provides :meth:`model_dump` / :meth:`model_validate` helpers so that
    :class:`~harness_skills.gates.runner.HarnessConfigLoader` can merge
    YAML overrides with profile defaults without knowing the concrete type.

    All built-in gate config dataclasses inherit from this class.  The class
    itself is intentionally **not** a dataclass so it does not add any fields
    to its subclasses.
    """

    def model_dump(self) -> dict[str, object]:
        """Return a plain-dict snapshot of this config (all fields and values)."""
        return dataclasses.asdict(self)  # type: ignore[arg-type]

    @classmethod
    def model_validate(cls, data: dict[str, object]) -> "BaseGateConfig":
        """Construct an instance from *data*, ignoring any unknown keys.

        This mirrors the Pydantic v2 ``model_validate`` signature so the
        runner can treat dataclass configs and Pydantic models uniformly.
        Unknown keys (e.g. YAML-only metadata) are silently dropped.
        """
        known = {f.name for f in dataclasses.fields(cls)}  # type: ignore[arg-type]
        return cls(**{k: v for k, v in data.items() if k in known})  # type: ignore[return-value]


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
    """Configuration for the security-scan gate (pip-audit / npm audit / bandit).

    Attributes
    ----------
    enabled:
        Whether this gate is active.  Set ``False`` to skip entirely.
    fail_on_error:
        When ``True`` (the default), *error*-severity violations cause the gate
        to return ``passed=False`` and exit with a non-zero code.  ``False``
        downgrades all violations to *warnings*.
    severity_threshold:
        Minimum CVE/advisory severity to report for dependency vulnerabilities.
        One of ``CRITICAL``, ``HIGH``, ``MEDIUM``, or ``LOW`` (default: ``HIGH``).
    scan_dependencies:
        Parse a pre-generated pip-audit / npm audit JSON report and flag
        packages with known CVEs at or above *severity_threshold*.
    scan_secrets:
        Regex-scan all source files for hardcoded credentials, private keys,
        and API tokens.  Off by default to avoid noise on first run.
    scan_input_validation:
        Regex-scan Python/JS/TS source files for dangerous patterns that
        indicate missing input sanitisation (e.g. ``eval(request.data)``,
        raw SQL string formatting with request objects, pickle deserialisation
        of user-supplied bytes).  On by default.
    ignore_ids:
        Vulnerability IDs (CVE, GHSA, PYSEC) or secret-scanner rule IDs to
        suppress.  Violations whose ``rule_id`` appears in this list are
        silently skipped.
    """

    enabled: bool = True
    fail_on_error: bool = True
    severity_threshold: str = "HIGH"   # CRITICAL | HIGH | MEDIUM | LOW
    scan_dependencies: bool = True
    scan_secrets: bool = False
    scan_input_validation: bool = True
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
# Maps canonical gate IDs (as used in harness.config.yaml) to config classes.
# Consumed by HarnessConfigLoader to iterate all built-in gates and apply
# profile defaults + YAML overrides per gate.
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
