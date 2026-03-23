# AGENTS.md — harness_dashboard

## Purpose

Effectiveness scoring and terminal dashboard for agent harness sessions. Computes composite effectiveness scores from PR records and gate results, then renders an interactive terminal dashboard. Used by `harness effectiveness` CLI sub-command and the `harness:effectiveness` skill.

---

## Key Files

| File | Key Exports | Description |
|------|------------|-------------|
| `models.py` | Effectiveness data models (scores, records) | Pydantic models for score computation input and output |
| `scorer.py` | `compute_scores` | Aggregates per-dimension scores (coverage, type safety, security, docs, principles) into a composite effectiveness score |
| `dashboard.py` | `render_dashboard` | Renders a terminal-friendly dashboard (Rich or plain text) from computed scores |
| `data_generator.py` | `generate_dataset` | Generates synthetic effectiveness datasets for testing and demos |
| `__init__.py` | All of the above | Public API surface |

---

## Internal Patterns

- **Score computation is pure** — `compute_scores()` takes data models as input and returns score models; no I/O.
- **`render_dashboard` is a terminal concern** — it writes to stdout; always pass a `console` parameter to redirect output in tests.
- **`generate_dataset` for demos** — produces synthetic but realistic data; used in CI to verify dashboard rendering without real gate results.
- **No dependency on `harness_skills`** — this is a standalone package; effectiveness logic must not depend on gate runner internals.
- **Dimensions map to gates** — each score dimension corresponds to a built-in gate (coverage → `CoverageGate`, etc.); dimension names must stay in sync with `harness_skills.gates` gate IDs.

---

## Domain-Specific Constraints

- **No local imports from `harness_skills`** — `harness_dashboard` is an independent package; receive gate results as plain dicts or Pydantic models passed by the caller.
- **Terminal output only** — `render_dashboard` must not write to files; if callers need file output, they capture stdout and redirect it themselves.
- **Score range is 0–100** — all score values must be clamped to `[0, 100]` before storage or display; never emit negative or >100 scores.
- **`data_generator` is test-only** — do not import `generate_dataset` in production code paths; it is only for tests and demos.
- **Principle HD001** — dashboard rendering must degrade gracefully if Rich is not installed; fall back to plain-text output.
