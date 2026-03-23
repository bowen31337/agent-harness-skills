"""
harness_skills/models/gate_configs.py
=======================================
Dataclass configuration models for all evaluation gates.

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
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# ARCHITECTURE_STYLE_PRESETS
# Built-in layer stacks for common architectural styles.  Engineers set
# ``arch_style`` in harness.config.yaml to use one of these presets instead
# of specifying a plain ``layer_order`` list.
#
# Each entry is a list of layer dicts with the keys:
#   name    — canonical layer name used in violation messages
#   rank    — integer ordering; lower rank = more inner / foundational
#   aliases — additional directory/module name fragments that map to this layer
# ---------------------------------------------------------------------------

ARCHITECTURE_STYLE_PRESETS: dict[str, list[dict[str, Any]]] = {
    # Traditional layered architecture
    "layered": [
        {"name": "models",       "rank": 0, "aliases": ["model", "entity", "entities"]},
        {"name": "repositories", "rank": 1, "aliases": ["repo", "repository", "persistence"]},
        {"name": "services",     "rank": 2, "aliases": ["service", "use_cases", "usecases"]},
        {"name": "api",          "rank": 3, "aliases": ["controllers", "routes", "views", "handlers"]},
    ],
    # Clean Architecture (Uncle Bob)
    "clean": [
        {"name": "entities",           "rank": 0, "aliases": ["domain", "core", "model"]},
        {"name": "use_cases",          "rank": 1, "aliases": ["usecases", "interactors", "application", "services"]},
        {"name": "interface_adapters", "rank": 2, "aliases": ["adapters", "controllers", "presenters", "gateways"]},
        {"name": "frameworks_drivers", "rank": 3, "aliases": ["infrastructure", "frameworks", "drivers", "external"]},
    ],
    # Hexagonal / Ports-and-Adapters Architecture
    "hexagonal": [
        {"name": "domain",         "rank": 0, "aliases": ["core", "entities", "model"]},
        {"name": "application",    "rank": 1, "aliases": ["use_cases", "services", "ports"]},
        {"name": "adapters",       "rank": 2, "aliases": ["adapter", "secondary", "primary", "driven", "driving"]},
        {"name": "infrastructure", "rank": 3, "aliases": ["frameworks", "external", "drivers", "repositories"]},
    ],
    # Model-View-Controller
    "mvc": [
        {"name": "models",      "rank": 0, "aliases": ["model", "entities", "domain", "data"]},
        {"name": "controllers", "rank": 1, "aliases": ["controller", "handlers", "routes"]},
        {"name": "views",       "rank": 2, "aliases": ["view", "templates", "presenters", "ui"]},
    ],
    # Domain-Driven Design
    "ddd": [
        {"name": "domain",         "rank": 0, "aliases": ["entities", "core", "value_objects", "aggregates"]},
        {"name": "application",    "rank": 1, "aliases": ["use_cases", "services", "commands", "queries", "handlers"]},
        {"name": "infrastructure", "rank": 2, "aliases": ["repositories", "adapters", "persistence", "external"]},
        {"name": "presentation",   "rank": 3, "aliases": ["api", "controllers", "views", "ui", "web"]},
    ],
}


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
    tracked_files:
        File names (basenames only) to scan for freshness timestamps.
        ``AGENTS.md`` is always included; additional names may be appended.

    Inherited from :class:`BaseGateConfig`:
        ``enabled``, ``fail_on_error``
    """

    max_staleness_days: int = 30
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
        When ``True``, measure branch (condition) coverage in addition to
        line coverage.  Requires ``pytest-cov >= 4``.  Defaults to
        ``False``.
    exclude_patterns:
        Glob patterns (relative to the project root) to omit from the
        coverage measurement, e.g. ``["tests/", "migrations/"]``.

    Inherited from :class:`BaseGateConfig`:
        ``enabled``, ``fail_on_error``
    """

    threshold: float = 90.0
    coverage_file: str = "coverage.xml"
    report_format: str = "auto"
    branch_coverage: bool = False
    exclude_patterns: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# RegressionGate
# ---------------------------------------------------------------------------


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
    budget_ms: int = 200
    regression_threshold_pct: float = 10.0


# ---------------------------------------------------------------------------
# ArchitectureGate
# ---------------------------------------------------------------------------


@dataclass
class ArchitectureGateConfig(BaseGateConfig):
    """Configuration for the architecture (import-layer) gate.

    Attributes
    ----------
    rules:
        Names of the architectural rules to enforce.
    layer_order:
        Ordered list of architectural layer names from innermost to outermost.
        Imports must respect this order (inner layers must not import from
        outer layers).  Used when neither ``arch_style`` nor
        ``layer_definitions`` is set.
    arch_style:
        Named preset that overrides ``layer_order`` with a well-known layer
        stack.  Supported values: ``"layered"``, ``"clean"``,
        ``"hexagonal"``, ``"mvc"``, ``"ddd"``.  When set, the preset's
        layer order *and* name aliases are applied automatically.  An
        unrecognised value silently falls back to ``layer_order``.
    layer_definitions:
        Fully custom layer definitions with optional aliases.  Each entry
        is a dict with keys:

        * ``name`` (str) — canonical layer name used in messages.
        * ``rank`` (int) — ordering: lower rank = more inner / foundational.
        * ``aliases`` (list[str]) — extra directory/module name fragments
          that map to this layer (e.g. ``["repo", "persistence"]`` for a
          layer named ``"repositories"``).

        When set, this takes priority over both ``arch_style`` and
        ``layer_order``.
    report_only:
        When ``True``, violations are emitted as *warnings* rather than
        *errors*, so the gate never blocks a merge.

    Resolution priority (highest to lowest)
    ----------------------------------------
    1. ``layer_definitions`` — explicit custom definitions with aliases
    2. ``arch_style``        — named preset from ARCHITECTURE_STYLE_PRESETS
    3. ``layer_order``       — plain ordered name list (backward-compatible)

    Inherited from :class:`BaseGateConfig`:
        ``enabled``, ``fail_on_error``
    """

    rules: list[str] = field(default_factory=lambda: [
        "no_circular_dependencies",
        "enforce_layer_boundaries",
    ])
    layer_order: list[str] = field(default_factory=lambda: [
        "models", "repositories", "services", "api",
    ])
    arch_style: str | None = None
    layer_definitions: list[dict[str, Any]] | None = None
    report_only: bool = False


# ---------------------------------------------------------------------------
# PrinciplesGate
# ---------------------------------------------------------------------------


@dataclass
class PrinciplesGateConfig(BaseGateConfig):
    """Configuration for the golden-principles gate.

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
    principles_file: str = ".claude/principles.yaml"
    rules: list[str] = field(default_factory=lambda: ["all"])


# ---------------------------------------------------------------------------
# TypesGate
# ---------------------------------------------------------------------------


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

    strict: bool = False
    ignore_errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# LintGate
# ---------------------------------------------------------------------------


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

    autofix: bool = False
    select: list[str] = field(default_factory=list)
    ignore: list[str] = field(default_factory=list)


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


# ---------------------------------------------------------------------------
# PROFILE_GATE_DEFAULTS
# Canonical per-profile default configurations consumed by config_generator.
# ---------------------------------------------------------------------------

PROFILE_GATE_DEFAULTS: dict[str, dict[str, object]] = {
    "starter": {
        "regression":     RegressionGateConfig(enabled=True, fail_on_error=True),
        "coverage":       CoverageGateConfig(threshold=60.0, fail_on_error=True),
        "security":       SecurityGateConfig(enabled=False),
        "performance":    PerformanceGateConfig(enabled=False),
        "architecture":   ArchitectureGateConfig(enabled=False, fail_on_error=False, report_only=True),
        "principles":     PrinciplesGateConfig(enabled=True, fail_on_error=False),
        "docs_freshness": DocsFreshnessGateConfig(max_staleness_days=30),
        "types":          TypesGateConfig(enabled=False),
        "lint":           LintGateConfig(enabled=True, fail_on_error=True),
    },
    "standard": {
        "regression":     RegressionGateConfig(enabled=True, fail_on_error=True),
        "coverage":       CoverageGateConfig(threshold=80.0, fail_on_error=True),
        "security":       SecurityGateConfig(enabled=True, severity_threshold="HIGH"),
        "performance":    PerformanceGateConfig(enabled=False),
        "architecture":   ArchitectureGateConfig(enabled=True, fail_on_error=True),
        "principles":     PrinciplesGateConfig(enabled=True, fail_on_error=True),
        "docs_freshness": DocsFreshnessGateConfig(max_staleness_days=30),
        "types":          TypesGateConfig(enabled=True, fail_on_error=True),
        "lint":           LintGateConfig(enabled=True, fail_on_error=True),
    },
    "advanced": {
        "regression":     RegressionGateConfig(enabled=True, fail_on_error=True),
        "coverage":       CoverageGateConfig(threshold=90.0, fail_on_error=True),
        "security":       SecurityGateConfig(
            enabled=True, severity_threshold="MEDIUM",
            scan_dependencies=True, scan_secrets=True,
        ),
        "performance":    PerformanceGateConfig(enabled=True, regression_threshold_pct=10.0),
        "architecture":   ArchitectureGateConfig(
            enabled=True, fail_on_error=True,
            rules=[
                "no_circular_dependencies",
                "enforce_layer_boundaries",
                "require_interface_contracts",
                "enforce_naming_conventions",
            ],
        ),
        "principles":     PrinciplesGateConfig(enabled=True, fail_on_error=True),
        "docs_freshness": DocsFreshnessGateConfig(max_staleness_days=14),
        "types":          TypesGateConfig(enabled=True, fail_on_error=True, strict=True),
        "lint":           LintGateConfig(enabled=True, fail_on_error=True, autofix=False),
    },
}
