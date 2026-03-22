"""
harness_skills/models/gate_configs.py
=======================================
Pydantic configuration models for all evaluation gates.

<<<<<<< HEAD
<<<<<<< HEAD
Each gate configuration class is a plain Python dataclass — intentionally
lightweight so gate modules can be imported without pulling in Pydantic.

The :class:`BaseGateConfig` base class provides two compatibility shims used
by :class:`~harness_skills.gates.runner.HarnessConfigLoader`:

* ``model_dump()``     — returns a ``dict`` of all dataclass fields (mirrors
  ``pydantic.BaseModel.model_dump``).
* ``model_validate()`` — constructs an instance from a dict, silently
  ignoring keys that are not declared fields (mirrors
  ``pydantic.BaseModel.model_validate``).

Engineers define **project-specific plugin gates** via ``harness.config.yaml``:

.. code-block:: yaml

    profiles:
      starter:
        gates:
          plugins:
            - gate_id: check_migrations
              gate_name: "DB Migration Safety"
              command: "python scripts/check_migrations.py"
              timeout_seconds: 30
              fail_on_error: true
              severity: error
              env:
                DATABASE_URL: "${DATABASE_URL}"

Plugin gates are validated and executed by
:mod:`harness_skills.plugins.gate_plugin`; this module only covers the
*built-in* gate configurations.
||||||| 0e893bd
Each gate configuration class is a plain Python dataclass — intentionally
lightweight so gate modules can be imported without pulling in Pydantic.
=======
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
>>>>>>> feat/evaluation-gate-skill-generates-per-gate-configuration
||||||| 0e893bd
Each gate configuration class is a plain Python dataclass — intentionally
lightweight so gate modules can be imported without pulling in Pydantic.
=======
Each gate configuration class extends ``BaseGateConfig``, which provides the
common ``enabled`` and ``fail_on_error`` flags understood by the gate runner.
Using Pydantic ``BaseModel`` gives us ``model_dump()`` / ``model_validate()``
for free, which the runner uses to merge YAML overrides onto profile defaults.
>>>>>>> feat/evaluation-gate-skill-generates-a-documentation-freshne
"""

from __future__ import annotations

<<<<<<< HEAD
<<<<<<< HEAD
import dataclasses
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# BaseGateConfig
# ---------------------------------------------------------------------------


@dataclass
class BaseGateConfig:
    """Base configuration class shared by all built-in evaluation gates.

    Provides two Pydantic-compatible shims (``model_dump`` /
    ``model_validate``) so that :class:`~harness_skills.gates.runner.\
HarnessConfigLoader` can merge YAML overrides onto dataclass defaults
    without requiring Pydantic in every gate module.

    Attributes
    ----------
    enabled:
        Whether the gate is active.  Set to ``False`` in
        ``harness.config.yaml`` to skip the gate entirely.
    fail_on_error:
        When ``True`` (the default), *error*-severity violations produced by
        the gate cause the overall evaluation to fail.  Setting this to
        ``False`` downgrades all violations to *warnings* and keeps the run
        green.
    """

    enabled: bool = True
    fail_on_error: bool = True

    # ------------------------------------------------------------------
    # Pydantic-compatible shims
    # ------------------------------------------------------------------

    def model_dump(self) -> dict[str, Any]:
        """Return all fields as a plain ``dict`` (mirrors Pydantic)."""
        return dataclasses.asdict(self)

    @classmethod
    def model_validate(cls, data: dict[str, Any]) -> "BaseGateConfig":
        """Construct an instance from *data*, ignoring unknown keys.

        Unknown keys present in the YAML (e.g. keys added in a future
        harness version) are silently dropped rather than raising an error.
        This ensures forward-compatibility when an older harness binary
        reads a newer ``harness.config.yaml``.
        """
        valid_fields = {f.name for f in dataclasses.fields(cls)}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)
||||||| 0e893bd
from dataclasses import dataclass, field
=======
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
>>>>>>> feat/evaluation-gate-skill-generates-per-gate-configuration
||||||| 0e893bd
from dataclasses import dataclass, field
=======
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# BaseGateConfig
# ---------------------------------------------------------------------------


class BaseGateConfig(BaseModel):
    """Common fields shared by every gate configuration.

    Attributes
    ----------
    enabled:
        When ``False`` the gate runner skips this gate entirely and records
        a ``skipped`` outcome.  Defaults to ``True``.
    fail_on_error:
        When ``True`` (the default), *error*-severity violations cause the
        gate to return ``passed=False`` and exit with a non-zero code.
        Setting this to ``False`` downgrades all violations to *warnings*
        and lets the gate pass regardless.
    """

    enabled: bool = True
    fail_on_error: bool = True

    model_config = {"extra": "ignore"}  # tolerate unknown YAML keys
>>>>>>> feat/evaluation-gate-skill-generates-a-documentation-freshne


# ---------------------------------------------------------------------------
# DocsFreshnessGate
# ---------------------------------------------------------------------------


<<<<<<< HEAD
<<<<<<< HEAD
@dataclass
class DocsFreshnessGateConfig(BaseGateConfig):
||||||| 0e893bd
@dataclass
class DocsFreshnessGateConfig:
=======
class DocsFreshnessGateConfig(BaseGateConfig):
>>>>>>> feat/evaluation-gate-skill-generates-per-gate-configuration
||||||| 0e893bd
@dataclass
class DocsFreshnessGateConfig:
=======
class DocsFreshnessGateConfig(BaseGateConfig):
>>>>>>> feat/evaluation-gate-skill-generates-a-documentation-freshne
    """Configuration for the documentation-freshness gate.

    Attributes
    ----------
    enabled:
        Inherited from :class:`BaseGateConfig`.  Defaults to ``True``.
    fail_on_error:
        Inherited from :class:`BaseGateConfig`.  Defaults to ``True``.
    max_staleness_days:
<<<<<<< HEAD
        Maximum number of days between the ``generated_at`` timestamp and
        today before the content is considered stale.  Defaults to 30.
||||||| 0e893bd
        Maximum number of days between the ``generated_at`` timestamp and
        today before the content is considered stale.  Defaults to 30.
    fail_on_error:
        When ``True`` (the default), *error*-severity violations cause the
        gate to return ``passed=False`` and exit with a non-zero code.
        Setting this to ``False`` downgrades all violations to *warnings*
        and lets the gate pass regardless.
=======
        Maximum number of days between the freshness timestamp
        (``generated_at`` or ``last_updated``) and today before the
        content is considered stale.  Defaults to 30.
>>>>>>> feat/evaluation-gate-skill-generates-a-documentation-freshne
    tracked_files:
        File names (basenames only) to scan for freshness timestamps.
<<<<<<< HEAD
        ``AGENTS.md`` is always included; additional names may be appended.

    Inherited from :class:`BaseGateConfig`:
        ``enabled``, ``fail_on_error``
||||||| 0e893bd
        ``AGENTS.md`` is always included; additional names may be appended.
=======
        ``AGENTS.md`` is always the primary target; additional names may
        be appended here.
>>>>>>> feat/evaluation-gate-skill-generates-a-documentation-freshne
    """

    max_staleness_days: int = 30
<<<<<<< HEAD
<<<<<<< HEAD
    tracked_files: list[str] = field(default_factory=lambda: ["AGENTS.md"])
||||||| 0e893bd
    fail_on_error: bool = True
    tracked_files: list[str] = field(default_factory=lambda: ["AGENTS.md"])
=======
    tracked_files: list[str] = Field(default_factory=lambda: ["AGENTS.md"])
>>>>>>> feat/evaluation-gate-skill-generates-per-gate-configuration
||||||| 0e893bd
    fail_on_error: bool = True
    tracked_files: list[str] = field(default_factory=lambda: ["AGENTS.md"])
=======
    tracked_files: list[str] = Field(default_factory=lambda: ["AGENTS.md"])
>>>>>>> feat/evaluation-gate-skill-generates-a-documentation-freshne


# ---------------------------------------------------------------------------
# CoverageGate
# ---------------------------------------------------------------------------


<<<<<<< HEAD
<<<<<<< HEAD
@dataclass
class CoverageGateConfig(BaseGateConfig):
||||||| 0e893bd
@dataclass
class CoverageGateConfig:
=======
class CoverageGateConfig(BaseGateConfig):
>>>>>>> feat/evaluation-gate-skill-generates-per-gate-configuration
||||||| 0e893bd
@dataclass
class CoverageGateConfig:
=======
class CoverageGateConfig(BaseGateConfig):
>>>>>>> feat/evaluation-gate-skill-generates-a-documentation-freshne
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
<<<<<<< HEAD
<<<<<<< HEAD
||||||| 0e893bd
    fail_on_error:
        When ``True`` (the default), a below-threshold result causes the
        gate to return ``passed=False`` and exit with a non-zero code.
        Setting this to ``False`` emits a *warning* violation but still
        allows the build to continue.
=======
    branch_coverage:
        When ``True``, also enforce branch/condition coverage in addition to
        line coverage.  Requires ``pytest-cov >= 4``.  Default: ``False``.
>>>>>>> feat/evaluation-gate-skill-generates-per-gate-configuration
||||||| 0e893bd
    fail_on_error:
        When ``True`` (the default), a below-threshold result causes the
        gate to return ``passed=False`` and exit with a non-zero code.
        Setting this to ``False`` emits a *warning* violation but still
        allows the build to continue.
=======
>>>>>>> feat/evaluation-gate-skill-generates-a-documentation-freshne
    coverage_file:
        Path to the coverage report, either absolute or relative to the
        repository root passed to :meth:`~CoverageGate.run`.
        Defaults to ``"coverage.xml"`` (the pytest-cov default).
    report_format:
        Hint for the report parser.  ``"auto"`` (default) detects the
        format from the file extension: ``.xml`` → xml, ``.json`` → json,
        ``.info`` / ``.out`` / ``.lcov`` → lcov.  Pass ``"xml"``,
        ``"json"``, or ``"lcov"`` to override auto-detection.
<<<<<<< HEAD
<<<<<<< HEAD
    branch_coverage:
        When ``True``, measure branch (condition) coverage in addition to
        line coverage.  Requires ``pytest-cov >= 4``.  Defaults to
        ``False``.
    exclude_patterns:
        Glob patterns (relative to the project root) to omit from the
        coverage measurement, e.g. ``["tests/", "migrations/"]``.

    Inherited from :class:`BaseGateConfig`:
        ``enabled``, ``fail_on_error``
||||||| 0e893bd
=======
    exclude_patterns:
        List of path patterns to exclude from coverage measurement.
        E.g. ``["tests/", "migrations/"]``.
>>>>>>> feat/evaluation-gate-skill-generates-per-gate-configuration
||||||| 0e893bd
=======
    branch_coverage:
        When ``True``, the runner also requests branch-level coverage data.
        Defaults to ``False`` (line coverage only).
    exclude_patterns:
        Glob patterns to omit from coverage collection (passed as
        ``--omit`` to pytest-cov).  Defaults to an empty list.
>>>>>>> feat/evaluation-gate-skill-generates-a-documentation-freshne
    """

    threshold: float = 90.0
<<<<<<< HEAD
<<<<<<< HEAD
||||||| 0e893bd
    fail_on_error: bool = True
=======
    branch_coverage: bool = False
>>>>>>> feat/evaluation-gate-skill-generates-per-gate-configuration
||||||| 0e893bd
    fail_on_error: bool = True
=======
>>>>>>> feat/evaluation-gate-skill-generates-a-documentation-freshne
    coverage_file: str = "coverage.xml"
    report_format: str = "auto"
<<<<<<< HEAD
<<<<<<< HEAD
    branch_coverage: bool = False
    exclude_patterns: list[str] = field(default_factory=list)
||||||| 0e893bd
=======
    exclude_patterns: list[str] = Field(default_factory=list)
>>>>>>> feat/evaluation-gate-skill-generates-per-gate-configuration
||||||| 0e893bd
=======
    branch_coverage: bool = False
    exclude_patterns: list[str] = Field(default_factory=list)
>>>>>>> feat/evaluation-gate-skill-generates-a-documentation-freshne


# ---------------------------------------------------------------------------
# RegressionGate
# ---------------------------------------------------------------------------


<<<<<<< HEAD
<<<<<<< HEAD
@dataclass
class RegressionGateConfig(BaseGateConfig):
    """Configuration for the regression (test-suite) gate.

    Attributes
    ----------
    timeout_seconds:
        Wall-clock time limit (seconds) for the full test suite run.
    extra_args:
        Additional arguments appended verbatim to the ``pytest`` (or
        equivalent) invocation, e.g. ``["--tb=short", "-x"]``.

    Inherited from :class:`BaseGateConfig`:
        ``enabled``, ``fail_on_error``
    """
||||||| 0e893bd
@dataclass
class RegressionGateConfig:
||||||| 0e893bd
@dataclass
class RegressionGateConfig:
=======
class RegressionGateConfig(BaseGateConfig):
>>>>>>> feat/evaluation-gate-skill-generates-a-documentation-freshne
    """Configuration for the regression (test-suite) gate."""
=======
class RegressionGateConfig(BaseGateConfig):
    """Configuration for the regression (test-suite) gate."""
>>>>>>> feat/evaluation-gate-skill-generates-per-gate-configuration

    timeout_seconds: int = 300
    extra_args: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# SecurityGate
# ---------------------------------------------------------------------------


<<<<<<< HEAD
<<<<<<< HEAD
@dataclass
class SecurityGateConfig(BaseGateConfig):
    """Configuration for the security-scan gate (pip-audit / npm audit / bandit).

    Attributes
    ----------
    severity_threshold:
        Minimum CVE severity to report.  One of ``CRITICAL``, ``HIGH``,
        ``MEDIUM``, or ``LOW``.  Vulnerabilities below this threshold are
        suppressed.  Defaults to ``"HIGH"``.
    scan_dependencies:
        When ``True`` (default), runs ``pip-audit`` / ``npm audit`` to
        check installed packages for known CVEs.
    scan_secrets:
        When ``True``, runs secret-detection heuristics to flag hardcoded
        API keys and tokens in source files.  Defaults to ``False``.
    ignore_ids:
        List of CVE IDs or Bandit rule IDs to suppress, e.g.
        ``["CVE-2023-12345", "B101"]``.

    Inherited from :class:`BaseGateConfig`:
        ``enabled``, ``fail_on_error``
    """
||||||| 0e893bd
@dataclass
class SecurityGateConfig:
||||||| 0e893bd
@dataclass
class SecurityGateConfig:
=======
class SecurityGateConfig(BaseGateConfig):
>>>>>>> feat/evaluation-gate-skill-generates-a-documentation-freshne
    """Configuration for the security-scan gate (pip-audit / npm audit / bandit)."""
=======
class SecurityGateConfig(BaseGateConfig):
    """Configuration for the security-scan gate (pip-audit / npm audit / bandit)."""
>>>>>>> feat/evaluation-gate-skill-generates-per-gate-configuration

    severity_threshold: str = "HIGH"   # CRITICAL | HIGH | MEDIUM | LOW
    scan_dependencies: bool = True
    scan_secrets: bool = False
    ignore_ids: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# PerformanceGate
# ---------------------------------------------------------------------------


<<<<<<< HEAD
<<<<<<< HEAD
@dataclass
class PerformanceGateConfig(BaseGateConfig):
    """Configuration for the performance-benchmark gate.
||||||| 0e893bd
@dataclass
class PerformanceGateConfig:
||||||| 0e893bd
@dataclass
class PerformanceGateConfig:
=======
class PerformanceGateConfig(BaseGateConfig):
>>>>>>> feat/evaluation-gate-skill-generates-a-documentation-freshne
    """Configuration for the performance-benchmark gate."""
=======
class PerformanceGateConfig(BaseGateConfig):
    """Configuration for the performance-benchmark gate."""
>>>>>>> feat/evaluation-gate-skill-generates-per-gate-configuration

<<<<<<< HEAD
    Attributes
    ----------
    budget_ms:
        P95 response-time ceiling in milliseconds.  Benchmark runs that
        exceed this value are flagged as failures.  Defaults to ``200``.
    regression_threshold_pct:
        Maximum allowed percentage degradation vs. the stored baseline
        before the gate fails.  Defaults to ``10.0`` (10 %).

    Inherited from :class:`BaseGateConfig`:
        ``enabled``, ``fail_on_error``
    """

    # Performance gate is off by default — override inherited enabled=True
    enabled: bool = False
||||||| 0e893bd
    enabled: bool = False
    fail_on_error: bool = True
=======
    enabled: bool = False  # off by default — requires .harness-perf.sh
>>>>>>> feat/evaluation-gate-skill-generates-a-documentation-freshne
    budget_ms: int = 200
    regression_threshold_pct: float = 10.0


# ---------------------------------------------------------------------------
# ArchitectureGate
# ---------------------------------------------------------------------------


<<<<<<< HEAD
<<<<<<< HEAD
@dataclass
class ArchitectureGateConfig(BaseGateConfig):
    """Configuration for the architecture (import-layer) gate.

    Attributes
    ----------
    rules:
        Names of the architectural rules to enforce.
    layer_order:
        Ordered list of architectural layers from innermost to outermost.
        Imports must respect this order (inner layers must not import
        from outer layers).
    report_only:
        When ``True``, violations are emitted as *warnings* rather than
        *errors*, so the gate never blocks a merge.

    Inherited from :class:`BaseGateConfig`:
        ``enabled``, ``fail_on_error``
    """
||||||| 0e893bd
@dataclass
class ArchitectureGateConfig:
||||||| 0e893bd
@dataclass
class ArchitectureGateConfig:
=======
class ArchitectureGateConfig(BaseGateConfig):
>>>>>>> feat/evaluation-gate-skill-generates-a-documentation-freshne
    """Configuration for the architecture (import-layer) gate."""
=======
class ArchitectureGateConfig(BaseGateConfig):
    """Configuration for the architecture (import-layer) gate."""
>>>>>>> feat/evaluation-gate-skill-generates-per-gate-configuration

<<<<<<< HEAD
<<<<<<< HEAD
    rules: list[str] = field(default_factory=lambda: [
||||||| 0e893bd
    enabled: bool = True
    fail_on_error: bool = True
    rules: list[str] = field(default_factory=lambda: [
=======
    rules: list[str] = Field(default_factory=lambda: [
>>>>>>> feat/evaluation-gate-skill-generates-per-gate-configuration
||||||| 0e893bd
    enabled: bool = True
    fail_on_error: bool = True
    rules: list[str] = field(default_factory=lambda: [
=======
    rules: list[str] = Field(default_factory=lambda: [
>>>>>>> feat/evaluation-gate-skill-generates-a-documentation-freshne
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


<<<<<<< HEAD
<<<<<<< HEAD
@dataclass
class PrinciplesGateConfig(BaseGateConfig):
    """Configuration for the golden-principles gate.
||||||| 0e893bd
@dataclass
class PrinciplesGateConfig:
||||||| 0e893bd
@dataclass
class PrinciplesGateConfig:
=======
class PrinciplesGateConfig(BaseGateConfig):
>>>>>>> feat/evaluation-gate-skill-generates-a-documentation-freshne
    """Configuration for the golden-principles gate."""
=======
class PrinciplesGateConfig(BaseGateConfig):
    """Configuration for the golden-principles gate."""
>>>>>>> feat/evaluation-gate-skill-generates-per-gate-configuration

<<<<<<< HEAD
<<<<<<< HEAD
    Attributes
    ----------
    principles_file:
        Path (relative to project root) of the principles definition file.
    rules:
        Subset of rule names to enforce.  ``["all"]`` applies every rule
        defined in *principles_file*.

    Inherited from :class:`BaseGateConfig`:
        ``enabled``, ``fail_on_error``
    """

    # Advisory by default — override inherited fail_on_error=True
    fail_on_error: bool = False
||||||| 0e893bd
    enabled: bool = True
||||||| 0e893bd
    enabled: bool = True
=======
>>>>>>> feat/evaluation-gate-skill-generates-a-documentation-freshne
    fail_on_error: bool = False   # advisory by default
=======
    fail_on_error: bool = False   # advisory by default
>>>>>>> feat/evaluation-gate-skill-generates-per-gate-configuration
    principles_file: str = ".claude/principles.yaml"
    rules: list[str] = Field(default_factory=lambda: ["all"])


# ---------------------------------------------------------------------------
# TypesGate
# ---------------------------------------------------------------------------


<<<<<<< HEAD
<<<<<<< HEAD
@dataclass
class TypesGateConfig(BaseGateConfig):
    """Configuration for the static type-checking gate (mypy / tsc / pyright).

    Attributes
    ----------
    strict:
        When ``True``, passes ``--strict`` (mypy) or equivalent flag.
    ignore_errors:
        List of mypy/pyright error codes to suppress, e.g.
        ``["misc", "import-untyped"]``.

    Inherited from :class:`BaseGateConfig`:
        ``enabled``, ``fail_on_error``
    """
||||||| 0e893bd
@dataclass
class TypesGateConfig:
||||||| 0e893bd
@dataclass
class TypesGateConfig:
=======
class TypesGateConfig(BaseGateConfig):
>>>>>>> feat/evaluation-gate-skill-generates-a-documentation-freshne
    """Configuration for the static type-checking gate (mypy / tsc / pyright)."""
=======
class TypesGateConfig(BaseGateConfig):
    """Configuration for the static type-checking gate (mypy / tsc / pyright)."""
>>>>>>> feat/evaluation-gate-skill-generates-per-gate-configuration

    strict: bool = False
    ignore_errors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# LintGate
# ---------------------------------------------------------------------------


<<<<<<< HEAD
<<<<<<< HEAD
@dataclass
class LintGateConfig(BaseGateConfig):
    """Configuration for the linting gate (ruff / eslint / golangci-lint).

    Attributes
    ----------
    autofix:
        When ``True``, attempt ``ruff --fix`` / ``eslint --fix`` before
        reporting remaining violations.  Defaults to ``False``.
    select:
        Rule codes to enable (empty = tool defaults).
    ignore:
        Rule codes to suppress, e.g. ``["E501"]`` for line-length.

    Inherited from :class:`BaseGateConfig`:
        ``enabled``, ``fail_on_error``
    """
||||||| 0e893bd
@dataclass
class LintGateConfig:
||||||| 0e893bd
@dataclass
class LintGateConfig:
=======
class LintGateConfig(BaseGateConfig):
>>>>>>> feat/evaluation-gate-skill-generates-a-documentation-freshne
    """Configuration for the linting gate (ruff / eslint / golangci-lint)."""
=======
class LintGateConfig(BaseGateConfig):
    """Configuration for the linting gate (ruff / eslint / golangci-lint)."""
>>>>>>> feat/evaluation-gate-skill-generates-per-gate-configuration

    autofix: bool = False
<<<<<<< HEAD
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
# GATE_CONFIG_CLASSES
# Registry of all built-in gate IDs → their configuration class.
# The order here matches the default execution order in GateEvaluator.
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
||||||| 0e893bd
    select: list[str] = field(default_factory=list)
    ignore: list[str] = field(default_factory=list)
=======
    select: list[str] = Field(default_factory=list)
    ignore: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# GATE_CONFIG_CLASSES
# Maps gate_id → config class.  Ordered to match the canonical execution order
# used by GateEvaluator.run() and harness:evaluate.
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
>>>>>>> feat/evaluation-gate-skill-generates-a-documentation-freshne


# ---------------------------------------------------------------------------
# PROFILE_GATE_DEFAULTS
<<<<<<< HEAD
# Canonical per-profile default configurations consumed by config_generator
# and HarnessConfigLoader.
||||||| 0e893bd
# Canonical per-profile default configurations consumed by config_generator.
=======
# Canonical per-profile default configurations consumed by config_generator
# and HarnessConfigLoader.gate_configs().
>>>>>>> feat/evaluation-gate-skill-generates-a-documentation-freshne
# ---------------------------------------------------------------------------

<<<<<<< HEAD
PROFILE_GATE_DEFAULTS: dict[str, dict[str, Any]] = {
||||||| 0e893bd
PROFILE_GATE_DEFAULTS: dict[str, dict[str, object]] = {
=======
PROFILE_GATE_DEFAULTS: dict[str, dict[str, BaseGateConfig]] = {
>>>>>>> feat/evaluation-gate-skill-generates-a-documentation-freshne
    "starter": {
<<<<<<< HEAD
<<<<<<< HEAD
        "regression":     RegressionGateConfig(enabled=True, fail_on_error=True),
        "coverage":       CoverageGateConfig(threshold=60.0, fail_on_error=True),
        "security":       SecurityGateConfig(enabled=False),
        "performance":    PerformanceGateConfig(enabled=False),
        "architecture":   ArchitectureGateConfig(enabled=False, fail_on_error=False, report_only=True),
        "principles":     PrinciplesGateConfig(enabled=True, fail_on_error=False),
        "docs_freshness": DocsFreshnessGateConfig(max_staleness_days=30),
        "types":          TypesGateConfig(enabled=False),
        "lint":           LintGateConfig(enabled=True, fail_on_error=True),
||||||| 0e893bd
        "regression":    RegressionGateConfig(enabled=True, fail_on_error=True),
        "coverage":      CoverageGateConfig(threshold=60.0, fail_on_error=True),
        "security":      SecurityGateConfig(enabled=False),
        "performance":   PerformanceGateConfig(enabled=False),
        "architecture":  ArchitectureGateConfig(enabled=False, fail_on_error=False, report_only=True),
        "principles":    PrinciplesGateConfig(enabled=True, fail_on_error=False),
||||||| 0e893bd
        "regression":    RegressionGateConfig(enabled=True, fail_on_error=True),
        "coverage":      CoverageGateConfig(threshold=60.0, fail_on_error=True),
        "security":      SecurityGateConfig(enabled=False),
        "performance":   PerformanceGateConfig(enabled=False),
        "architecture":  ArchitectureGateConfig(enabled=False, fail_on_error=False, report_only=True),
        "principles":    PrinciplesGateConfig(enabled=True, fail_on_error=False),
=======
        "regression":     RegressionGateConfig(enabled=True, fail_on_error=True),
        "coverage":       CoverageGateConfig(threshold=60.0, fail_on_error=True),
        "security":       SecurityGateConfig(enabled=False),
        "performance":    PerformanceGateConfig(enabled=False),
        "architecture":   ArchitectureGateConfig(
            enabled=False, fail_on_error=False, report_only=True
        ),
        "principles":     PrinciplesGateConfig(enabled=True, fail_on_error=False),
>>>>>>> feat/evaluation-gate-skill-generates-a-documentation-freshne
        "docs_freshness": DocsFreshnessGateConfig(max_staleness_days=30),
<<<<<<< HEAD
        "types":         TypesGateConfig(enabled=False),
        "lint":          LintGateConfig(enabled=True, fail_on_error=True),
=======
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
>>>>>>> feat/evaluation-gate-skill-generates-per-gate-configuration
||||||| 0e893bd
        "types":         TypesGateConfig(enabled=False),
        "lint":          LintGateConfig(enabled=True, fail_on_error=True),
=======
        "types":          TypesGateConfig(enabled=False),
        "lint":           LintGateConfig(enabled=True, fail_on_error=True),
>>>>>>> feat/evaluation-gate-skill-generates-a-documentation-freshne
    },
    "standard": {
<<<<<<< HEAD
<<<<<<< HEAD
        "regression":     RegressionGateConfig(enabled=True, fail_on_error=True),
        "coverage":       CoverageGateConfig(threshold=80.0, fail_on_error=True),
        "security":       SecurityGateConfig(enabled=True, severity_threshold="HIGH"),
        "performance":    PerformanceGateConfig(enabled=False),
        "architecture":   ArchitectureGateConfig(enabled=True, fail_on_error=True),
        "principles":     PrinciplesGateConfig(enabled=True, fail_on_error=True),
        "docs_freshness": DocsFreshnessGateConfig(max_staleness_days=30),
        "types":          TypesGateConfig(enabled=True, fail_on_error=True),
        "lint":           LintGateConfig(enabled=True, fail_on_error=True),
||||||| 0e893bd
        "regression":    RegressionGateConfig(enabled=True, fail_on_error=True),
        "coverage":      CoverageGateConfig(threshold=80.0, fail_on_error=True),
        "security":      SecurityGateConfig(enabled=True, severity_threshold="HIGH"),
        "performance":   PerformanceGateConfig(enabled=False),
        "architecture":  ArchitectureGateConfig(enabled=True, fail_on_error=True),
        "principles":    PrinciplesGateConfig(enabled=True, fail_on_error=True),
||||||| 0e893bd
        "regression":    RegressionGateConfig(enabled=True, fail_on_error=True),
        "coverage":      CoverageGateConfig(threshold=80.0, fail_on_error=True),
        "security":      SecurityGateConfig(enabled=True, severity_threshold="HIGH"),
        "performance":   PerformanceGateConfig(enabled=False),
        "architecture":  ArchitectureGateConfig(enabled=True, fail_on_error=True),
        "principles":    PrinciplesGateConfig(enabled=True, fail_on_error=True),
=======
        "regression":     RegressionGateConfig(enabled=True, fail_on_error=True),
        "coverage":       CoverageGateConfig(threshold=80.0, fail_on_error=True),
        "security":       SecurityGateConfig(enabled=True, severity_threshold="HIGH"),
        "performance":    PerformanceGateConfig(enabled=False),
        "architecture":   ArchitectureGateConfig(enabled=True, fail_on_error=True),
        "principles":     PrinciplesGateConfig(enabled=True, fail_on_error=True),
>>>>>>> feat/evaluation-gate-skill-generates-a-documentation-freshne
        "docs_freshness": DocsFreshnessGateConfig(max_staleness_days=30),
<<<<<<< HEAD
        "types":         TypesGateConfig(enabled=True, fail_on_error=True),
        "lint":          LintGateConfig(enabled=True, fail_on_error=True),
=======
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
>>>>>>> feat/evaluation-gate-skill-generates-per-gate-configuration
||||||| 0e893bd
        "types":         TypesGateConfig(enabled=True, fail_on_error=True),
        "lint":          LintGateConfig(enabled=True, fail_on_error=True),
=======
        "types":          TypesGateConfig(enabled=True, fail_on_error=True),
        "lint":           LintGateConfig(enabled=True, fail_on_error=True),
>>>>>>> feat/evaluation-gate-skill-generates-a-documentation-freshne
    },
    "advanced": {
<<<<<<< HEAD
<<<<<<< HEAD
        "regression":     RegressionGateConfig(enabled=True, fail_on_error=True),
        "coverage":       CoverageGateConfig(threshold=90.0, fail_on_error=True),
        "security":       SecurityGateConfig(
||||||| 0e893bd
        "regression":    RegressionGateConfig(enabled=True, fail_on_error=True),
        "coverage":      CoverageGateConfig(threshold=90.0, fail_on_error=True),
        "security":      SecurityGateConfig(
=======
        "regression":    RegressionGateConfig(enabled=True, fail_on_error=True),
        "coverage":      CoverageGateConfig(
            enabled=True, threshold=90.0, fail_on_error=True, branch_coverage=True,
        ),
        "security":      SecurityGateConfig(
>>>>>>> feat/evaluation-gate-skill-generates-per-gate-configuration
||||||| 0e893bd
        "regression":    RegressionGateConfig(enabled=True, fail_on_error=True),
        "coverage":      CoverageGateConfig(threshold=90.0, fail_on_error=True),
        "security":      SecurityGateConfig(
=======
        "regression":     RegressionGateConfig(enabled=True, fail_on_error=True),
        "coverage":       CoverageGateConfig(threshold=90.0, fail_on_error=True),
        "security":       SecurityGateConfig(
>>>>>>> feat/evaluation-gate-skill-generates-a-documentation-freshne
            enabled=True, severity_threshold="MEDIUM",
            scan_dependencies=True, scan_secrets=True,
        ),
<<<<<<< HEAD
<<<<<<< HEAD
        "performance":    PerformanceGateConfig(enabled=True, regression_threshold_pct=10.0),
        "architecture":   ArchitectureGateConfig(
||||||| 0e893bd
        "performance":   PerformanceGateConfig(enabled=True, regression_threshold_pct=10.0),
        "architecture":  ArchitectureGateConfig(
=======
        "performance":   PerformanceGateConfig(
            enabled=True, regression_threshold_pct=10.0,
        ),
        "architecture":  ArchitectureGateConfig(
>>>>>>> feat/evaluation-gate-skill-generates-per-gate-configuration
||||||| 0e893bd
        "performance":   PerformanceGateConfig(enabled=True, regression_threshold_pct=10.0),
        "architecture":  ArchitectureGateConfig(
=======
        "performance":    PerformanceGateConfig(enabled=True, regression_threshold_pct=10.0),
        "architecture":   ArchitectureGateConfig(
>>>>>>> feat/evaluation-gate-skill-generates-a-documentation-freshne
            enabled=True, fail_on_error=True,
            rules=[
                "no_circular_dependencies",
                "enforce_layer_boundaries",
                "require_interface_contracts",
                "enforce_naming_conventions",
            ],
        ),
<<<<<<< HEAD
<<<<<<< HEAD
        "principles":     PrinciplesGateConfig(enabled=True, fail_on_error=True),
        "docs_freshness": DocsFreshnessGateConfig(max_staleness_days=14),
        "types":          TypesGateConfig(enabled=True, fail_on_error=True, strict=True),
        "lint":           LintGateConfig(enabled=True, fail_on_error=True, autofix=False),
||||||| 0e893bd
        "principles":    PrinciplesGateConfig(enabled=True, fail_on_error=True),
||||||| 0e893bd
        "principles":    PrinciplesGateConfig(enabled=True, fail_on_error=True),
=======
        "principles":     PrinciplesGateConfig(enabled=True, fail_on_error=True),
>>>>>>> feat/evaluation-gate-skill-generates-a-documentation-freshne
        "docs_freshness": DocsFreshnessGateConfig(max_staleness_days=14),
<<<<<<< HEAD
        "types":         TypesGateConfig(enabled=True, fail_on_error=True, strict=True),
        "lint":          LintGateConfig(enabled=True, fail_on_error=True, autofix=False),
=======
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
>>>>>>> feat/evaluation-gate-skill-generates-per-gate-configuration
||||||| 0e893bd
        "types":         TypesGateConfig(enabled=True, fail_on_error=True, strict=True),
        "lint":          LintGateConfig(enabled=True, fail_on_error=True, autofix=False),
=======
        "types":          TypesGateConfig(enabled=True, fail_on_error=True, strict=True),
        "lint":           LintGateConfig(enabled=True, fail_on_error=True, autofix=False),
>>>>>>> feat/evaluation-gate-skill-generates-a-documentation-freshne
    },
}
