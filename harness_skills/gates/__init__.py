"""harness_skills/gates — built-in gate runners.

Public API
----------
    CoverageGate            — line-coverage gate (XML / JSON / lcov)
    DocsFreshnessGate       — documentation-staleness gate
    DocsGateConfig          — configuration for DocsFreshnessGate
    TypesGate               — static type-checking gate (mypy / tsc / pyright)
    TypesGateResult         — result type returned by TypesGate
    TypeViolation           — single type violation from TypesGate
    EvaluationSummary       — aggregate outcome from run_gates()
    GateEvaluator           — orchestrates gate execution against a config
    GateFailure             — single gate failure descriptor
    GateOutcome             — single gate pass/fail result
    HarnessConfigLoader     — reads and validates harness.config.yaml
    run_gates               — convenience entry-point used by `harness evaluate`
"""

from harness_skills.gates.coverage import CoverageGate
from harness_skills.gates.docs_freshness import DocsFreshnessGate
from harness_skills.gates.docs_freshness import GateConfig as DocsGateConfig
from harness_skills.gates.types import TypesGate, TypesGateResult, TypeViolation
from harness_skills.gates.runner import (
    EvaluationSummary,
    GateEvaluator,
    GateFailure,
    GateOutcome,
    HarnessConfigLoader,
    run_gates,
)

__all__ = [
    # ── coverage gate ────────────────────────────────────────────────────────
    "CoverageGate",
    # ── docs-freshness gate ──────────────────────────────────────────────────
    "DocsFreshnessGate",
    "DocsGateConfig",
    # ── type-safety gate ─────────────────────────────────────────────────────
    "TypesGate",
    "TypesGateResult",
    "TypeViolation",
    # ── runner ──────────────────────────────────────────────────────────────
    "EvaluationSummary",
    "GateEvaluator",
    "GateFailure",
    "GateOutcome",
    "HarnessConfigLoader",
    "run_gates",
]
