# Structured Logging & Observability — agent-harness-skills

← [AGENTS.md](../../AGENTS.md)

All log output must be **NDJSON** (one JSON object per line).  Every entry is validated
by `log_format_linter`.  Observability tooling (Vector → Loki → Grafana) is provisioned
by the `/observability` skill.

---

## Log Entry Contract

Every entry **must** carry exactly these five fields:

| Field | Type | Example | Notes |
|-------|------|---------|-------|
| `timestamp` | ISO-8601 UTC string | `"2026-03-23T14:05:00.123Z"` | Always UTC, always Z-suffix |
| `level` | `DEBUG`/`INFO`/`WARN`/`ERROR`/`FATAL` | `"INFO"` | Uppercase only |
| `domain` | dot-separated scope | `"harness.gates.coverage"` | Identifies the source component |
| `trace_id` | 32 hex chars (W3C) | `"4bf92f3577b34da6..."` | Links all events in a single request/task |
| `message` | non-empty UTF-8 string | `"Gate passed"` | Human-readable; never empty |

Optional `extra` object for structured context:

```json
{"timestamp":"2026-03-23T14:05:01Z","level":"ERROR","domain":"harness.gates.coverage",
 "trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","message":"Below threshold",
 "extra":{"actual":71,"threshold":80,"file":"harness_skills/gates/coverage.py"}}
```

Full specification: **[SPEC.md](../../SPEC.md)** (12 KB).

---

## Emitting Logs

```python
from harness_skills.logging_config import configure, get_logger, set_trace_id
import uuid

# Call once at process startup
configure(level="INFO", sink="stdout")

# Per-task: set a W3C-compatible trace ID
set_trace_id(uuid.uuid4().hex)

log = get_logger("harness.gates.coverage")
log.info("Gate passed", extra={"threshold": 80, "actual": 85})
log.error("Gate failed", extra={"threshold": 80, "actual": 71})
```

`logging_config.py` is the **single logging provider** — do not configure Python's
`logging` module directly.

---

## Linting Logs

The `log_format_linter` package scans source files for log statements that violate the
five-field contract:

```python
from log_format_linter import check_file, check_directory, generate_rules, detect_framework

# Check all Python files in a directory
violations = check_directory("harness_skills/", recursive=True)
for v in violations:
    print(v.rule_id, v.file, v.line, v.message)
```

```bash
# CLI
python -m log_format_linter check harness_skills/
python -m log_format_linter check --format json harness_skills/
```

Skill: `/log-format-linter`.
Skill doc: `.claude/commands/log-format-linter.md` (411 lines).

---

## Linting Rules

`generate_rules(framework)` produces per-framework rules.  Supported frameworks
(`LogFramework` enum): `python_logging`, `structlog`, `loguru`, `typescript_pino`,
`typescript_winston`, `go_zap`, `java_slf4j`.

```python
from log_format_linter import generate_rules, detect_framework, Language

framework = detect_framework(Language.PYTHON, "harness_skills/")
rules = generate_rules(framework)
```

---

## Observability Stack (Local Dev)

The `/observability` skill provisions a lightweight stack:

```
Application → Vector (log router) → Loki (log store) → Grafana (dashboards)
```

```bash
# Provision the stack
/observability

# Or invoke skill
harness observe --tail 100 --level ERROR
```

Skill doc: `.claude/commands/observability.md` (749 lines).

---

## Telemetry

`harness_skills.telemetry_reporter` aggregates gate run metrics and emits a
`TelemetryReport`:

```python
from harness_skills.models import TelemetryReport
```

```bash
harness telemetry --since 24h --format json
```

Skill doc: `.claude/commands/harness/telemetry.md` (16 KB).
Raw telemetry data: `docs/harness-telemetry.json`.

---

## JSON Schema

Machine-readable log entry schema: `schemas/log_entry.schema.json`.

Validate a log file:

```bash
cat my.log | python -c "
import sys, json, jsonschema
schema = json.load(open('schemas/log_entry.schema.json'))
for line in sys.stdin:
    jsonschema.validate(json.loads(line), schema)
print('All entries valid')
"
```

---

## Deeper References

- **Full log spec** → [SPEC.md](../../SPEC.md) (12 KB — field rules, examples, JSON Schema)
- **Logging convention skill** → `.claude/commands/logging-convention.md` (585 lines)
- **Log format linter skill** → `.claude/commands/log-format-linter.md` (411 lines)
- **Log linter source** → `log_format_linter/` package
- **Log linter tests** → `tests/test_log_format_linter.py`
- **Logging config source** → `harness_skills/logging_config.py` (18 KB)
- **Observability skill** → `.claude/commands/observability.md` (749 lines)
- **Telemetry skill** → `.claude/commands/harness/telemetry.md`
- **Log schema** → `schemas/log_entry.schema.json`
- **Logging convention spec (extended)** → `spec/logging_convention_spec.txt` (26 KB)
