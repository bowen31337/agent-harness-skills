"""harness_skills/gates — built-in gate runners.

Public API
----------
    CoverageGate            — line-coverage gate (XML / JSON / lcov)
    DocsFreshnessGate       — documentation-staleness gate
    DocsGateConfig          — configuration for DocsFreshnessGate
    SecurityGate            — security gate (secret scan / dep audit / input validation)
    SecurityGateConfig      — configuration for SecurityGate
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
from harness_skills.gates.security import SecurityGate
from harness_skills.gates.runner import (
    EvaluationSummary,
    GateEvaluator,
    GateFailure,
    GateOutcome,
    HarnessConfigLoader,
    run_gates,
)
from harness_skills.models.gate_configs import SecurityGateConfig

__all__ = [
    # ── coverage gate ────────────────────────────────────────────────────────
    "CoverageGate",
    # ── docs-freshness gate ──────────────────────────────────────────────────
    "DocsFreshnessGate",
    "DocsGateConfig",
    # ── security gate ────────────────────────────────────────────────────────
    "SecurityGate",
    "SecurityGateConfig",
    # ── runner ──────────────────────────────────────────────────────────────
    "EvaluationSummary",
    "GateEvaluator",
    "GateFailure",
    "GateOutcome",
    "HarnessConfigLoader",
    "run_gates",
]
