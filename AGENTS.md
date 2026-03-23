# AGENTS.md

<!-- harness:auto-generated — do not edit this block manually -->
last_updated: 2026-03-23
head: 157af7b
service: agent-harness-skills
<!-- /harness:auto-generated -->

Agent-facing reference for this repository.

---

## Build, Test & Lint

### Install

```bash
# Install the package in editable mode with all dev dependencies
pip install -e ".[dev]"

# Download the Chromium binary required by Playwright
playwright install chromium
```

### Test

```bash
# Run the full test suite
pytest tests/ -v

# Browser (Playwright) e2e tests only
pytest tests/browser/ -v

# Headed mode — opens a visible browser window (useful for local debugging)
pytest tests/browser/ --headed

# Single test file
pytest tests/browser/test_smoke.py -v

# Target a non-default environment
BASE_URL=https://staging.example.com pytest tests/browser/ -v

# Run with coverage collection (outputs XML + terminal summary)
uv run pytest --cov --cov-report=xml --cov-report=term-missing -q
```

### Lint & Format

```bash
# Check for linting errors (ruff: E/W/F/I/N/UP/B/SIM/PTH rule sets)
ruff check .

# Auto-fix linting errors where possible
ruff check . --fix

# Check formatting without writing changes
ruff format --check .

# Apply formatting
ruff format .
```

### Type Check

```bash
# Strict mypy type check (configured via pyproject.toml [tool.mypy])
mypy .
```

### Quality Gates

These gates are run in CI (GitHub Actions + GitLab CI) and can be invoked locally:

```bash
# Coverage gate — enforces ≥ 90 % line coverage
uv run python -m harness_skills.gates.coverage \
    --root . --threshold 90 \
    --coverage-file coverage.xml --format auto

# Principles gate — checks Golden Principles compliance
uv run python scripts/check_principles.py \
    --path . --format json \
    --output principles-report.json --skill check-code

# Type safety gate
uv run harness evaluate --gate types --fail-on error --format json

# Security gates (secrets scan, dependency audit, input-validation)
uv run harness evaluate --gate secrets       --fail-on error --format json
uv run harness evaluate --gate dependencies  --fail-on error --format json
uv run harness evaluate --gate input-validation --fail-on error --format json

# Performance gate (thresholds defined in .harness/perf-thresholds.yml)
uv run harness evaluate --gate performance \
    --thresholds .harness/perf-thresholds.yml --format json

# Run all evaluation gates at once
uv run harness evaluate --format json
```

---

## Browser Automation

Framework: **Playwright** (Python)
Browser:   Chromium (headless)
Base URL:  `http://localhost:3000` (override with `BASE_URL` env var)
Screenshots saved to: `./screenshots/`

### Quick start

```python
from tests.browser.agent_driver import AgentDriver

# Context-manager form (recommended — always cleans up the browser)
with AgentDriver.launch() as driver:
    page = driver.new_page()
    page.goto("/")                          # relative to BASE_URL
    driver.screenshot(page, "home")         # → screenshots/home-<timestamp>.png

# Or navigate to an absolute URL
with AgentDriver.launch(base_url="http://localhost:8080") as driver:
    page = driver.new_page()
    page.goto("http://localhost:8080/login")
    driver.screenshot(page, "login")
```

### Screenshot helper (lower level)

```python
from tests.browser.screenshot_helper import capture_screenshot, visit_and_capture

# Capture the current state of any page
path = capture_screenshot(page, "checkout-step-2")

# Navigate + capture in one call
path = visit_and_capture(page, "/dashboard", "dashboard")
```

### Running e2e tests

```bash
# All browser tests
pytest tests/browser/ -v

# Single test file
pytest tests/browser/test_smoke.py -v

# Run headed (shows browser window — useful for local debugging)
pytest tests/browser/ --headed

# Target a different environment
BASE_URL=https://staging.example.com pytest tests/browser/ -v
```

### Environment variables

| Variable         | Default                   | Purpose                                  |
|------------------|---------------------------|------------------------------------------|
| `BASE_URL`       | `http://localhost:3000`   | Base URL for relative `goto()` calls     |
| `SCREENSHOT_DIR` | `./screenshots`           | Directory where PNGs are saved           |

### Recording video (for post-mortems)

Pass `record_video=True` to `AgentDriver.launch()` to save a `.webm` session
recording to `./videos/`:

```python
with AgentDriver.launch(record_video=True) as driver:
    page = driver.new_page()
    page.goto("/checkout")
    driver.screenshot(page, "checkout")
# video is written when the context closes (i.e. on __exit__)
```

### Failure screenshots (pytest-playwright)

`tests/browser/conftest.py` registers an `autouse` fixture that captures a
full-page PNG whenever a browser test fails.  Screenshots land in:

```
screenshots/failures/<test-nodeid>.png
```

Upload this directory as a CI artefact to inspect failures without re-running.

### Capturing screenshots from an agent task

1. Start the dev server (if needed): `python -m uvicorn app:app --reload` or equivalent
2. Set `BASE_URL` if targeting staging/CI
3. Call `driver.screenshot(page, '<meaningful-label>')`
4. Find the PNG at `screenshots/<label>-<timestamp>.png`
5. Attach the path in your task result or claw-forge state update

### Install / setup (first time)

```bash
pip install playwright pytest-playwright
playwright install chromium   # downloads the Chromium binary
```

Both `playwright` and `pytest-playwright` are already listed in `requirements.txt`.

---

## Error Handling Patterns

> Derived from `ERROR_HANDLING_RULES.md` and the conventions in `harness_skills/`.

### Core philosophy — Results over Exceptions

Gate code **never raises**. Every `run()` method returns a `GateResult`; exceptions are
caught at the gate boundary and converted into structured violations.

```python
# harness_skills/models/base.py
from harness_skills.models.base import GateResult, Violation, Status, Severity

# ALWAYS: catch at the boundary and return a result
def run(self) -> GateResult:
    try:
        violations = self._analyse()
        return GateResult(status=Status.PASSED, violations=violations, ...)
    except SomeSpecificError as exc:
        return GateResult(
            status=Status.FAILED,
            violations=[Violation(rule_id="my-gate/specific-error", severity=Severity.ERROR,
                                  message=str(exc), ...)],
        )
    except Exception:
        logger.exception("Unhandled error in gate %r", self.gate_id)
        return GateResult(status=Status.FAILED, message="Internal gate error", ...)
```

### Violation model

Every `Violation` **must** carry a `rule_id` from the canonical registry:

| Field        | Type            | Required | Notes                                        |
|--------------|-----------------|----------|----------------------------------------------|
| `rule_id`    | `str`           | Yes      | Slash-namespaced, e.g. `arch/layer-violation`|
| `severity`   | `Severity`      | Yes      | `INFO \| WARNING \| ERROR \| CRITICAL`       |
| `message`    | `str`           | Yes      | A complete, human-readable sentence          |
| `file_path`  | `str \| None`   | No       | **Relative** to project root                 |
| `line_number`| `int \| None`   | No       |                                              |
| `suggestion` | `str \| None`   | No       | Required for `ERROR` and `CRITICAL`          |

```python
Violation(
    rule_id="security/insecure-hash",
    severity=Severity.ERROR,
    message="MD5 used for password hashing in auth.py.",
    file_path="app/auth.py",
    line_number=42,
    suggestion="Replace with bcrypt or argon2.",
)
```

### Canonical `rule_id` registry

| Namespace     | Examples                                                  |
|---------------|-----------------------------------------------------------|
| `plugin/*`    | `exit-nonzero`, `timeout`, `invalid-config`, `output-parse-error` |
| `arch/*`      | `layer-violation`, `circular-dependency`, `forbidden-import`       |
| `principles/*`| `no-magic-numbers`, `no-hardcoded-urls`, `no-hardcoded-secrets`, `too-many-args` |
| `freshness/*` | `not-found`, `stale`, `broken-link`                       |
| `security/*`  | `sql-injection`, `command-injection`, `insecure-hash`     |
| `lint/*`      | `style-error`, `unused-import`                            |
| `types/*`     | `annotation-missing`, `type-error`                        |
| `coverage/*`  | `below-threshold`, `file-uncovered`                       |
| `perf/*`      | `regression`, `benchmark-missing`                         |

Add new `rule_id` values to `ERROR_HANDLING_RULES.md` before shipping.

### Exception handling inside a gate

```python
import subprocess
import logging
from pydantic import ValidationError

logger = logging.getLogger(__name__)

def run(self) -> GateResult:
    # 1. Catch specific exceptions first
    try:
        proc = subprocess.run(self.cmd, shell=True, timeout=self.timeout)
    except subprocess.TimeoutExpired:
        return GateResult(
            status=Status.FAILED,
            violations=[Violation(rule_id="plugin/timeout", severity=Severity.ERROR,
                                  message=f"Gate timed out after {self.timeout}s.")],
        )
    # 2. Pydantic validation errors: catch ValidationError, not ValueError
    try:
        cfg = MyConfig.model_validate(raw)
    except ValidationError as exc:
        logger.warning("Config failed schema validation, skipping: %s", exc)
        return GateResult(status=Status.SKIPPED, ...)
    # 3. Broad Exception last — always log with logger.exception()
    except Exception:
        logger.exception("Unhandled error in gate %r", self.gate_id)
        return GateResult(status=Status.FAILED, message="Internal gate error")
```

### Silent-boundary pattern (telemetry / metadata)

Non-critical side-effects (telemetry writes, metadata recording) **must** swallow
all exceptions and include an explanatory comment so reviewers know the silence is
intentional.

```python
# harness_skills/telemetry.py
def flush(self) -> None:
    try:
        path.write_text(json.dumps(self._data, indent=2))
    except Exception:
        pass  # intentionally silent — telemetry MUST NOT affect gate outcome
```

### Severity guidelines

| Severity   | When to use                                           | Blocks gate? |
|------------|-------------------------------------------------------|--------------|
| `INFO`     | Informational only; never blocks                      | No           |
| `WARNING`  | Notable but recoverable; skipped optional component   | No           |
| `ERROR`    | Blocks gate; default when unsure vs WARNING           | Yes          |
| `CRITICAL` | Security/data-integrity only; blocks entire run       | Yes (all)    |

- Default to `ERROR` when uncertain between `ERROR` and `WARNING`.
- Never emit `CRITICAL` for configuration or style issues.
- Respect `fail_on_error: false` to downgrade violations to advisory.

### Logging conventions

```python
import logging
logger = logging.getLogger(__name__)   # module-level; never use print() in library code

# Use %-style formatting (lazy evaluation) — not f-strings
logger.warning("Skipping plugin %r: invalid config — %s", plugin_id, exc)
logger.exception("Unhandled error in gate %r", gate_id)   # captures traceback automatically
# logger.error(...)  ← use only when you DON'T have an active exception
```

Five required fields in every structured log entry (enforced by `ConventionFormatter`):

| Field        | Format / constraint                          |
|--------------|----------------------------------------------|
| `timestamp`  | ISO-8601 UTC (`2026-03-23T12:00:00.000Z`)    |
| `level`      | `DEBUG \| INFO \| WARN \| ERROR \| FATAL`    |
| `domain`     | Dot-separated scope (`harness.gates.coverage`)|
| `trace_id`   | 32-char hex W3C Trace Context ID             |
| `message`    | Non-empty UTF-8, format: `<verb> <subject>: <detail>` |

Never log secrets, tokens, or credentials.

### Error handling checklist

Before shipping gate or plugin code, verify:

- [ ] `run()` returns `GateResult` on every path — never raises
- [ ] Every `Violation` has a `rule_id` from the canonical registry
- [ ] `severity` matches the guidelines above
- [ ] `file_path` is **relative**, not absolute
- [ ] Logger is `logging.getLogger(__name__)` — no `print()` in library code
- [ ] All `logger.*()` calls use `%`-style formatting
- [ ] `logger.exception()` used (not `.error()`) when catching unexpected exceptions
- [ ] Silent `except Exception: pass` blocks carry an explanatory comment
- [ ] No credentials, tokens, or secrets in log messages or violation fields
- [ ] New `rule_id` values added to the registry in `ERROR_HANDLING_RULES.md`
