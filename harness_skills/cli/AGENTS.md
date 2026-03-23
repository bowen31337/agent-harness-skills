# AGENTS.md — harness_skills.cli

## Purpose

Command-line interface entry point for the entire harness-skills toolkit. Exposes the `harness` CLI command (registered via `pyproject.toml` entry-points) with sub-commands for `create`, `evaluate`, `lint`, `observe`, `status`, and `telemetry`. Also provides a verbosity system used across all CLI output.

---

## Key Files

| File | Exports | Description |
|------|---------|-------------|
| `main.py` | `cli`, `PipelineGroup` | Root Click command group; `PipelineGroup` is a subclassable Click group for pipeline integrations |
| `verbosity.py` | `VerbosityLevel`, `get_verbosity`, `vecho` | Four-level verbosity system (`quiet`, `normal`, `verbose`, `debug`); `vecho` is a verbosity-aware `click.echo` wrapper |
| `__init__.py` | `cli`, `PipelineGroup`, `VerbosityLevel`, `get_verbosity`, `vecho` | Public API surface |

---

## Internal Patterns

- **Click command groups** — each sub-command lives in its own module under `cli/`; all are registered onto the root `cli` group via `cli.add_command()`.
- **`PipelineGroup` for extensibility** — external tools can subclass `PipelineGroup` to inject pipeline-specific hooks (pre/post command callbacks).
- **Verbosity via Click context** — the active `VerbosityLevel` is stored in the Click context object; use `get_verbosity(ctx)` to retrieve it; use `vecho(msg, level=...)` to emit conditional output.
- **Gate invocation pattern** — `harness evaluate` calls `run_gates()` from `harness_skills.gates`; `harness create` calls generators; CLI commands never implement business logic directly.
- **Error handling** — CLI commands catch `GateFailure` and non-zero gate results and exit with code `1`; unhandled exceptions propagate and produce a traceback.

---

## Domain-Specific Constraints

- **CLI commands are thin wrappers** — no gate logic, model instantiation, or file I/O belongs in CLI command functions; delegate to `gates`, `generators`, or utility modules.
- **`harness` is the only registered entry-point** — do not add additional top-level entry-points without updating `pyproject.toml` and `ARCHITECTURE.md`.
- **`vecho` instead of `print` or `click.echo`** — all user-facing output in CLI modules must go through `vecho` so verbosity flags are honoured.
- **`PipelineGroup` is the only subclassable surface** — external callers must not subclass individual command functions.
- **Principle MB009** — `cli` package is a terminal node; it may import from any other package but nothing may import from `cli` except tests and entry-points.
