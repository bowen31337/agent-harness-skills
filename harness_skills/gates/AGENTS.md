# AGENTS.md — harness_skills.gates

## Purpose

Built-in evaluation gate runners. Each gate inspects a specific quality dimension of the codebase (coverage, type safety, security, documentation freshness, principles compliance, performance) and returns a structured list of violations. The `GateEvaluator` orchestrates all gates against a `harness.config.yaml` profile.

---

## Key Files

| File | Class / Function | What it checks |
|------|-----------------|----------------|
| `coverage.py` | `CoverageGate` | Line-coverage % against a configured threshold; reads XML (Cobertura), JSON, or lcov reports |
| `types.py` | `TypesGate`, `TypesGateResult`, `TypeViolation` | Static type errors via mypy / tsc / pyright — enforces a zero-error policy |
| `security.py` | `SecurityGate` | Secrets detection, dependency CVEs, unvalidated input flows |
| `principles.py` | `PrinciplesGate`, `PrinciplesGateConfig` | Golden-principles compliance from `.claude/principles.yaml` |
| `docs_freshness.py` | `DocsFreshnessGate`, `DocsGateConfig` | Documentation staleness — configurable max age per file |
| `artifact_audit.py` | `ArtifactAuditGate` | Artifact freshness (AGENTS.md, ARCHITECTURE.md timestamps) |
| `performance.py` | `PerformanceGate` | Span latency benchmarks for API endpoints, DB queries, HTTP calls |
| `runner.py` | `GateEvaluator`, `HarnessConfigLoader`, `run_gates`, `EvaluationSummary`, `GateOutcome`, `GateFailure` | Orchestrates gate execution; loads and validates `harness.config.yaml` |
| `__init__.py` | All public symbols | Single import surface; also re-exports `SecurityGateConfig` from `models` |

---

## Internal Patterns

- **Gate interface** — each gate class exposes a `run(config: <GateConfig>) -> list[GateResult]` method returning `GateResult` objects from `harness_skills.models`.
- **Config objects** — configuration dataclasses live in `harness_skills.models.gate_configs`; runners import them from there, not locally.
- **`HarnessConfigLoader`** — reads `harness.config.yaml` and returns typed config objects for each gate; used exclusively by `GateEvaluator`.
- **`run_gates` convenience entry-point** — called by `harness evaluate` CLI command; accepts a profile name and returns `EvaluationSummary`.
- **Standalone invocation** — every gate module can be run directly: `python -m harness_skills.gates.<gate_name>` for ad-hoc checks.
- **Violations over exceptions** — gates return `GateResult` lists rather than raising; only fatal misconfiguration should raise.

---

## Domain-Specific Constraints

- **Gate runners must not import from `harness_skills.cli` or `harness_skills.plugins`** — dependency flows downward only.
- **Config classes stay in `models/gate_configs.py`** — adding a new gate means adding its config dataclass there first, then the runner here.
- **Zero-error policy for `TypesGate`** — any type violation is a `BLOCKING` severity; do not soften this threshold in code.
- **`SecurityGate` never auto-fixes** — it only reports; remediation is the caller's responsibility.
- **Principle MB005** — gates package may only import from `harness_skills.models`; never from other sibling packages except via the `runner`.
- **Merge conflicts present in `__init__.py`** — the file contains unresolved `<<<<<<< HEAD` / `>>>>>>>` markers from two concurrent branches; resolve before adding new gates.
