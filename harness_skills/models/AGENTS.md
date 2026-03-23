# AGENTS.md — harness_skills.models

## Purpose

Foundation layer for the entire harness-skills framework. Defines all shared Pydantic response models and dataclasses that flow between CLI commands, gate runners, plugins, and external callers. This package has **zero local dependencies** — nothing in `harness_skills` may be imported here.

---

## Key Files

| File | Exports | Description |
|------|---------|-------------|
| `base.py` | `Status`, `Severity`, `GateResult`, `Violation`, `HarnessResponse`, `ArtifactFreshness`, `FreshnessScore`, `FileLocation`, `TaskInfo`, `AgentConflict` | Core status/severity enums and universal response wrapper |
| `create.py` | `CreateConfigResponse`, `CreateResponse` | Models returned by `harness create` |
| `manifest.py` | `ManifestValidateResponse`, `ManifestValidationError` | Harness manifest validation results |
| `context.py` | `ContextManifest`, `ContextManifestFile`, `ContextStats`, `SearchPattern`, `SkipEntry` | Context inspection models |
| `observe.py` | `LogEntry`, `ObserveResponse` | Log-observation query results |
| `lock.py` | `LockAcquireRequest`, `LockExtendRequest`, `LockReleaseRequest`, `LockRecord`, `LockStateResponse`, `LockOperationResponse`, `LockListResponse` | Cross-process task-lock protocol models |
| `stale.py` | `ArtifactResult`, `ArtifactStaleness`, `StaleTask`, `StalePlanSummary`, `StalePlanResponse` | Stale-plan and stale-artifact detection results |
| `gate_configs.py` | `CoverageGateConfig`, `SecurityGateConfig`, `TypesGateConfig`, `PerformanceGateConfig`, `PrinciplesGateConfig`, `DocsGateConfig`, `ArtifactAuditGateConfig` | Per-gate configuration dataclasses loaded from `harness.config.yaml` |
| `errors.py` | `ErrorGroupResponse`, `DomainOverview`, `ErrorAggregationResponse` | Error aggregation response models |
| `__init__.py` | All of the above re-exported | Single import surface for consumers |

---

## Internal Patterns

- **Pydantic v2** — all models use `model_config = ConfigDict(...)` where needed; no mutable defaults.
- **Strict `__all__`** — `__init__.py` declares every public symbol; nothing undeclared leaves this package.
- **Enums over strings** — `Status` and `Severity` are `str`-enum subclasses for JSON serialisation.
- **Dataclasses for gate configs** — gate configuration objects use `@dataclass` (not Pydantic) to stay lightweight and import-free.
- **No I/O** — models are pure data containers; all file/network access belongs to the gate or CLI layers.

---

## Domain-Specific Constraints

- **No local imports** — `harness_skills.models` must never import from `harness_skills.gates`, `harness_skills.cli`, `harness_skills.plugins`, or any other sibling package.
- **Backwards-compatible field additions only** — adding optional fields is safe; renaming or removing fields is a breaking change requiring a version bump.
- **Gate configs live here, runners live in `gates/`** — the config dataclass (e.g. `CoverageGateConfig`) belongs in `gate_configs.py`; the runner class belongs in `harness_skills/gates/`.
- **Principle MB001** — all cross-boundary data exchange must use a type declared in this package.
