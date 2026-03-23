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
