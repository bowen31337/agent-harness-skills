# Error Handling Pattern Rules

> Auto-generated for `agent-harness-skills` — Python 3.11+ / Pydantic v2 / Rich

---

## 1. Core Philosophy

| Principle | Rule |
|-----------|------|
| **Results, not exceptions** | Gate execution MUST return a `GateResult`; never let exceptions escape a gate runner. |
| **Structured violations** | Every failure MUST be expressed as a `Violation` with a canonical `rule_id`. |
| **Severity-driven logging** | Log level MUST match `Severity`; no raw `print()` in library code. |
| **Silent boundaries** | Telemetry and plugin metadata recording MUST swallow all exceptions. |
| **Loud boundaries** | Public API entry-points (CLI, `evaluate()`) MUST surface errors to the caller. |

---

## 2. Structured Error Model

### 2.1 `Violation` — the atomic error unit

Every detected problem MUST be captured as a `Violation`:

```python
from harness_skills.models.base import Violation, Severity

Violation(
    rule_id  = "arch/layer-violation",   # REQUIRED — see §3
    severity = Severity.ERROR,           # REQUIRED — see §4
    message  = "Domain layer imports infrastructure module 'db.orm'",  # REQUIRED
    file_path    = "src/domain/user.py", # recommended when applicable
    line_number  = 42,                   # recommended when applicable
    column       = 8,                    # optional
    suggestion   = "Move DB access to the infrastructure layer",        # optional
)
```

Rules:
- `rule_id` MUST be a slash-namespaced string (see §3). No free-form strings.
- `message` MUST be a complete, human-readable sentence. No stack traces in `message`.
- `suggestion` SHOULD be populated for `ERROR` and `CRITICAL` violations.
- `file_path` MUST be a relative path from the project root, not absolute.

### 2.2 `GateResult` — the gate-level envelope

```python
from harness_skills.models.base import GateResult, Status

# success
GateResult(status=Status.PASSED)

# failure with structured violations
GateResult(
    status     = Status.FAILED,
    violations = [v1, v2],
    message    = "2 architecture violations detected",  # human summary
)

# infra/system error (gate could not run)
GateResult(
    status  = Status.FAILED,
    message = "AST parse error in src/foo.py: unexpected EOF",
)
```

Rules:
- `message` is required when `status != PASSED`.
- `violations` MUST be empty when `status == PASSED`.
- Do NOT set `status = PASSED` alongside non-empty `violations`.

---

## 3. Error Code (`rule_id`) Conventions

### 3.1 Format

```
<namespace>/<kebab-slug>
```

| Segment | Rule |
|---------|------|
| `namespace` | Lowercase, matches the `GateId` enum slug (e.g. `arch`, `security`, `lint`, `types`, `freshness`, `principles`, `plugin`, `coverage`, `perf`) |
| `kebab-slug` | Lowercase, hyphen-separated, verb-noun or noun-noun, no version suffix |

### 3.2 Canonical Rule ID Registry

#### `plugin/*`
| rule_id | Meaning |
|---------|---------|
| `plugin/exit-nonzero` | Plugin subprocess exited with non-zero code |
| `plugin/timeout` | Plugin subprocess exceeded `timeout_seconds` |
| `plugin/invalid-config` | Plugin YAML/JSON config failed validation |
| `plugin/output-parse-error` | Could not parse plugin stdout as expected format |

#### `arch/*`
| rule_id | Meaning |
|---------|---------|
| `arch/layer-violation` | Import crosses architectural layer boundary |
| `arch/circular-dependency` | Circular import chain detected |
| `arch/forbidden-import` | Import of an explicitly banned module |

#### `principles/*`
| rule_id | Meaning |
|---------|---------|
| `principles/no-magic-numbers` | Bare numeric literal outside allowed contexts |
| `principles/no-hardcoded-urls` | Hard-coded URL string in source |
| `principles/no-hardcoded-secrets` | Credential or key literal detected |
| `principles/too-many-args` | Function signature exceeds argument limit |

#### `freshness/*`
| rule_id | Meaning |
|---------|---------|
| `freshness/not-found` | Referenced documentation artifact missing |
| `freshness/stale` | Artifact timestamp exceeds staleness threshold |
| `freshness/broken-link` | Hyperlink in documentation returns non-2xx |

#### `security/*`
| rule_id | Meaning |
|---------|---------|
| `security/sql-injection` | Unsanitised input in SQL query |
| `security/command-injection` | Unsanitised input in shell command |
| `security/insecure-hash` | Use of MD5 / SHA1 for security purposes |

#### `lint/*`
| rule_id | Meaning |
|---------|---------|
| `lint/style-error` | Tool-reported style violation |
| `lint/unused-import` | Imported symbol never referenced |

#### `types/*`
| rule_id | Meaning |
|---------|---------|
| `types/annotation-missing` | Public API missing type annotation |
| `types/type-error` | Static type checker reported an error |

#### `coverage/*`
| rule_id | Meaning |
|---------|---------|
| `coverage/below-threshold` | Line/branch coverage below configured minimum |
| `coverage/file-uncovered` | File has zero test coverage |

#### `perf/*`
| rule_id | Meaning |
|---------|---------|
| `perf/regression` | Benchmark exceeds allowed regression percentage |
| `perf/benchmark-missing` | Expected benchmark fixture not found |

### 3.3 Adding New Rule IDs

1. Choose the most specific existing namespace; create a new one only if none fit.
2. Add the rule_id to this registry before shipping.
3. Rule IDs MUST NOT be renamed once published (they appear in persisted reports).

---

## 4. Severity Levels

```python
class Severity(str, Enum):
    INFO     = "info"      # informational, never blocks a gate
    WARNING  = "warning"   # notable, does not fail the gate
    ERROR    = "error"     # gate-level failure
    CRITICAL = "critical"  # immediately blocks the entire evaluation run
```

| Level | When to use | Blocks gate? | Blocks run? |
|-------|-------------|:---:|:---:|
| `INFO` | Metrics, suggestions, non-actionable notes | No | No |
| `WARNING` | Degraded quality, approaching a threshold | No | No |
| `ERROR` | Policy violation, test failure, rule breach | Yes | No |
| `CRITICAL` | Security credential exposure, data corruption risk | Yes | Yes |

Rules:
- Default to `ERROR` when in doubt between `ERROR` and `WARNING`.
- `CRITICAL` is reserved for security and data-integrity issues only.
- Never emit `CRITICAL` for configuration or style issues.

---

## 5. Exception Handling Rules

### 5.1 Inside `GateRunner` subclasses

```python
class MyGate(GateRunner):
    def run(self) -> GateResult:
        try:
            # ... gate logic ...
            return GateResult(status=Status.PASSED)
        except subprocess.TimeoutExpired:
            return GateResult(
                status=Status.FAILED,
                message=f"Gate timed out after {self.config.timeout_seconds}s",
                violations=[Violation(rule_id="plugin/timeout", severity=Severity.ERROR,
                                      message="Subprocess exceeded timeout")],
            )
        except json.JSONDecodeError as exc:
            return GateResult(
                status=Status.FAILED,
                message=f"Could not parse gate output: {exc}",
                violations=[Violation(rule_id="plugin/output-parse-error",
                                      severity=Severity.ERROR,
                                      message=str(exc))],
            )
        except Exception as exc:                           # last resort
            logger.exception("Unhandled error in %s", self.__class__.__name__)
            return GateResult(
                status=Status.FAILED,
                message=f"Internal gate error: {type(exc).__name__}: {exc}",
            )
```

Rules:
- Catch specific exceptions first, broad `Exception` last.
- NEVER let an exception escape `run()`; always return a `GateResult`.
- Log with `logger.exception()` (not `.error()`) so the traceback is captured.
- Do NOT include raw tracebacks in `GateResult.message`.

### 5.2 Silent-boundary pattern (telemetry, metadata)

```python
def _record_telemetry(self, result: GateResult) -> None:
    try:
        self._telemetry.record(result)
    except Exception:                 # intentionally broad and silent
        pass                          # telemetry MUST NOT affect gate outcome
```

Rules:
- A comment MUST accompany every bare `except Exception: pass` explaining why silence is intentional.
- Silent boundaries MUST NOT be used inside gate logic.

### 5.3 Pydantic validation errors

```python
try:
    plugin = PluginConfig.model_validate(raw)
except ValidationError as exc:
    logger.warning("Skipping invalid plugin config: %s", exc)
    return None          # caller handles None
```

Rules:
- Catch `pydantic.ValidationError` explicitly; do NOT catch `ValueError` as a substitute.
- Log at `WARNING`, not `ERROR`, when skipping an optional component.
- Include the full `ValidationError` string in the log message.

### 5.4 Raising custom errors

Raise `ValueError` only for programmer errors caught in `@field_validator` or `__init__`:

```python
@field_validator("timeout_seconds")
@classmethod
def _validate_timeout(cls, v: int) -> int:
    if not 1 <= v <= 3600:
        raise ValueError(f"timeout_seconds must be 1–3600, got {v}")
    return v
```

Rules:
- `ValueError` for invalid input to public constructors/validators only.
- `RuntimeError` for unrecoverable infrastructure failures (e.g., missing binary).
- Never raise `Exception` directly; use a specific subclass.

---

## 6. Logging Format Conventions

### 6.1 Logger initialisation

Every module MUST declare a module-level logger with the full dotted path:

```python
import logging
logger = logging.getLogger(__name__)
# Resolves to e.g. "harness_skills.plugins.loader"
```

Never use `logging.getLogger("harness_skills.plugins.loader")` as a hard-coded string — use `__name__`.

### 6.2 Log-level mapping

| Scenario | Level |
|----------|-------|
| Normal operation milestones | `DEBUG` |
| Skipped optional component (e.g. bad plugin config) | `WARNING` |
| Recoverable error inside a gate | `WARNING` |
| Unhandled exception caught at gate boundary | `ERROR` via `logger.exception()` |
| Infrastructure failure (can't write telemetry, etc.) | `DEBUG` (silent boundary) |
| Successful gate evaluation start/finish | `DEBUG` |

### 6.3 Message format

```
<verb> <subject>: <detail>
```

Examples:
```python
logger.warning("Skipping plugin %r: invalid config — %s", plugin_id, exc)
logger.debug("Running gate %r (timeout=%ds)", gate_id, timeout)
logger.exception("Unhandled error in gate %r", gate_id)
```

Rules:
- Use `%`-style formatting (lazy evaluation), NOT f-strings, in logger calls.
- Include the entity name (gate id, plugin id, file path) as the subject.
- NEVER log secrets, tokens, or credentials at any level.
- NEVER log full stack traces via `.error()`; use `.exception()` which appends `exc_info` automatically.
- Log messages MUST be lowercase (the logging framework capitalises where needed).

### 6.4 Rich console output (CLI layer only)

Rich output is permitted ONLY in CLI entry-points (`cli.py`, `__main__.py`). Library code MUST use `logging`.

```python
from rich.console import Console
console = Console(stderr=True)

console.print(f"[bold red]ERROR[/] {message}")   # user-facing errors
console.print(f"[yellow]WARN[/]  {message}")      # user-facing warnings
console.print(f"[green]PASS[/]   {gate_id}")      # success output
```

---

## 7. Quick Reference Checklist

Before submitting code that handles errors, verify:

- [ ] Every failure returns a `GateResult` (not a raised exception) from gate code
- [ ] Every `Violation` has a `rule_id` from the registry in §3
- [ ] `severity` matches the severity guidelines in §4
- [ ] `file_path` is relative, not absolute
- [ ] Logger is `logging.getLogger(__name__)`; no `print()` in library code
- [ ] `%`-style formatting used in all `logger.*()` calls
- [ ] `logger.exception()` used (not `.error()`) when catching unexpected exceptions
- [ ] Silent `except Exception: pass` blocks have an explanatory comment
- [ ] No credentials, tokens, or secrets appear in any log message or `Violation.message`
- [ ] New `rule_id` values added to the registry in §3 of this document

<!-- harness:cross-links — do not edit this block manually -->

---

## Related Documents

| Document | Relationship |
|---|---|
| [ARCHITECTURE.md](../ARCHITECTURE.md) | package structure these rules apply to |
| [PRINCIPLES.md](../PRINCIPLES.md) | code quality and tool usage rules |
| [SPEC.md](SPEC.md) | structured logging spec (§6) |
| [EVALUATION.md](../EVALUATION.md) | latest gate run results |
| [DOCS_INDEX.md](../DOCS_INDEX.md) | full documentation index |

<!-- /harness:cross-links -->
