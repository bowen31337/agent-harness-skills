# CLI Commands — agent-harness-skills

← [AGENTS.md](https://github.com/bowen31337/agent-harness-skills/blob/main/AGENTS.md)

The `harness` CLI is the primary interface for creating, evaluating, and inspecting
harness artefacts.  All sub-commands are implemented under `harness_skills/cli/` and
exposed through the `harness_skills.cli.cli` Click group.

---

## Quick Reference

All 17 sub-commands registered by `harness_skills/cli/main.py`:

| Command | What it does |
|---------|-------------|
| `harness audit` | Verify generated artefacts (config, manifest, principles) are present and valid |
| `harness boot` | Boot an agent instance with sandbox isolation and health checks |
| `harness completion-report` | Aggregate plan-completion status into a JSON/YAML/table report |
| `harness context` | Provision agent context for the current task |
| `harness coordinate` | Cross-agent task conflict dashboard (locks + plan slots) |
| `harness create` | Scaffold a new harness from a profile (minimal / standard / full) |
| `harness evaluate` | Run all configured gates and emit an `EvaluateResponse` |
| `harness lint` | Static analysis via ruff + mypy |
| `harness manifest` | Generate / validate the project's `harness_manifest.json` |
| `harness observe` | Tail / query structured logs |
| `harness plan` | Manage and inspect execution plans |
| `harness resume` | Resume a previously interrupted plan or task |
| `harness screenshot` | Capture browser screenshots via Playwright |
| `harness search` | Search across structured logs and harness state |
| `harness status` | Print live harness status dashboard |
| `harness telemetry` | Aggregate and report telemetry |
| `harness update` | Regenerate auto-managed artefacts after stack changes |

Most commands accept `--format json|yaml|table` and `--help`. Run `harness <command> --help` for the authoritative flag list.

---

## Installation & Entry Point

```bash
pip install agent-harness-skills    # registers the `harness` script
harness --help
```

For a source checkout (development), `uv sync --extra dev` does the same and adds dev tooling.

`pyproject.toml` declares `harness = "harness_skills.cli.main:cli"` as the entry point.

---

## Common Workflows

### Evaluate gates on a PR branch

```bash
harness evaluate --config harness.config.yaml --format json
```

Returns a JSON `EvaluateResponse`.  Exit code `0` = all gates passed;  non-zero =
one or more gates failed.  CI consumes the exit code — see
[docs/agents/gates.md](gates.md) for gate details.

### Create a new harness

```bash
harness create --profile standard --output harness.config.yaml
```

Profiles: `minimal` (coverage + lint), `standard` (+ security + docs), `full` (all gates).

### Inspect logs in real time

```bash
harness observe --tail 50 --level ERROR
```

Streams NDJSON lines from the configured log sink.  See
[docs/agents/logging.md](logging.md) for the log format contract.

### Print status dashboard

```bash
harness status
```

Renders a Rich terminal table from `StatusDashboardResponse`.  Useful after running
`harness evaluate` to see per-gate results side-by-side.

---

## Key Source Files

| File | Purpose |
|------|---------|
| `harness_skills/cli/main.py` | Click group entry point — `cli` object |
| `harness_skills/cli/create.py` | `harness create` — calls `ConfigGenerator` |
| `harness_skills/cli/evaluate.py` | `harness evaluate` — calls `GateEvaluator` |
| `harness_skills/cli/lint.py` | `harness lint` — ruff + mypy integration |
| `harness_skills/cli/observe.py` | `harness observe` — log streaming |
| `harness_skills/cli/status.py` | `harness status` — dashboard rendering |
| `harness_skills/cli/boot.py` | `harness boot` — agent sandbox isolation |
| `harness_skills/cli/context.py` | `harness context` — task context provisioning |

---

## Response Models

All CLI commands emit typed Pydantic models (importable from `harness_skills.models`):

```python
from harness_skills.models import (
    CreateResponse,
    EvaluateResponse,
    LintResponse,
    ObserveResponse,
    StatusDashboardResponse,
    TelemetryReport,
)
```

---

## Deeper References

- **Gate configuration** → [docs/agents/gates.md](gates.md)
- **Full model reference** → `harness_skills/models/` source directory
- **Config YAML schema** → `harness.config.yaml` (16 KB annotated reference)
- **Skill docs** → `.claude/commands/harness/create.md`, `evaluate.md`, `lint.md`, etc.
- **Architecture** → [ARCHITECTURE.md](../ARCHITECTURE.md) (dependency graph)
