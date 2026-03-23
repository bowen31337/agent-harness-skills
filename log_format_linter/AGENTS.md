# AGENTS.md — log_format_linter

## Purpose

Structured-log linter. Validates log entries across Python, TypeScript, Go, and Java services against the five-field logging convention (`timestamp`, `level`, `domain`, `trace_id`, `message`). Produces the `log-lint` CLI command (registered via `pyproject.toml`). Also generates versioned `SPEC.md` / JSON Schema for documenting a project's logging standard.

---

## Key Files

| File | Key Exports | Description |
|------|------------|-------------|
| `checker.py` | `check_file` | Validates a single log file or source file for compliant log entries; returns a list of violations |
| `detector.py` | `detect_framework` | Detects the logging framework in use (Python `logging`, `structlog`, TypeScript `pino`, Go `zerolog`, etc.) |
| `generator.py` | `generate_rules` | Generates framework-specific linting rules and a `SPEC.md` / JSON Schema for a project |
| `models.py` | Violation models, framework enum, spec models | Pydantic models for linting input/output |
| `cli.py` | `log_lint` Click command | Entry-point for the `log-lint` CLI; delegates to `checker`, `detector`, `generator` |
| `__init__.py` | `check_file`, `detect_framework`, `generate_rules` | Public API surface |

---

## Internal Patterns

- **Five required fields** — every compliant log entry must carry: `timestamp` (ISO-8601 UTC), `level` (DEBUG/INFO/WARN/ERROR/FATAL), `domain` (dot-separated service scope), `trace_id` (W3C-compatible 32-hex-char ID), `message` (non-empty UTF-8 string).
- **Framework-first detection** — `detect_framework()` runs before `check_file()`; rules are framework-specific, not generic regex patterns.
- **NDJSON as canonical format** — linter validates NDJSON log streams by default; structured logs in other formats (JSON array, logfmt) must be converted before linting.
- **`generate_rules` produces both human and machine outputs** — a `SPEC.md` for team review and a JSON Schema snippet for cross-language validation.
- **`log-lint` CLI exit codes** — `0` = all compliant, `1` = violations found, `2` = configuration error; callers must check exit codes.

---

## Domain-Specific Constraints

- **No dependency on `harness_skills`** — `log_format_linter` is a standalone package; it must not import from `harness_skills` or `skills/`.
- **`trace_id` validation is strict** — must be exactly 32 lowercase hex characters (W3C `traceparent` compatible); do not accept UUIDs with dashes.
- **`level` values are case-sensitive** — only uppercase `DEBUG`, `INFO`, `WARN`, `ERROR`, `FATAL` are valid; reject `warning`, `Warning`, etc.
- **`check_file` is non-destructive** — it only reads and reports; never modify the log files being linted.
- **Framework detection is best-effort** — if the framework cannot be determined, `detect_framework` returns `UNKNOWN` and `check_file` falls back to generic JSON field checks; this must be logged as a warning, not an error.
- **`generate_rules` versioning** — generated `SPEC.md` files must include a `version` field (semver); bump the minor version on field additions, major version on field removals.
