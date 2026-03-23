# AGENTS.md — harness_skills.generators

## Purpose

Artifact generators — one module per harness artifact type. Responsible for producing structured evaluation reports and other generated documents (config stubs, manifests). Generators consume gate results from `harness_skills.gates` and format them into persistent artifacts.

---

## Key Files

| File | Exports | Description |
|------|---------|-------------|
| `evaluation.py` | `EvaluationReport`, `GateFailure`, `GateId`, `GateResult`, `GateStatus`, `Severity`, `run_all_gates` | Produces the full evaluation report artifact by running all configured gates and aggregating results |
| `__init__.py` | All of the above | Single import surface |

---

## Internal Patterns

- **One module per artifact type** — each generator module is responsible for exactly one output artifact (e.g. `evaluation.py` → evaluation report).
- **`run_all_gates`** — top-level convenience function that wires together `GateEvaluator` from `gates` and serialises results into an `EvaluationReport`.
- **Typed result objects** — `EvaluationReport` is a Pydantic model; callers can call `.model_dump_json()` or `.model_dump()` for serialisation.
- **Local type aliases** — `GateId`, `GateStatus`, `Severity` are re-exported from this package to avoid forcing callers to reach into `models` directly.

---

## Domain-Specific Constraints

- **Generators are write-once per run** — they produce artifacts and return; no mutable state is kept between runs.
- **No direct I/O outside of artifact writing** — generators must not read source files directly; they receive gate results as input.
- **Depends on `gates` and `models`; nothing else** — `harness_skills.generators` must not import from `cli`, `plugins`, or top-level utility modules.
- **Naming convention** — new generator modules must be named after their artifact (e.g. `manifest.py`, `config.py`); avoid generic names like `utils.py` or `helpers.py`.
