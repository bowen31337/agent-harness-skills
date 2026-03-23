# AGENTS.md

<!-- harness:auto-generated — do not edit this block manually -->
last_updated: 2026-03-23
head: 157af7b
service: agent-harness-skills
<!-- /harness:auto-generated -->

Agent-facing reference for this repository.

---

## Architecture Overview

### Domain Map

| # | Domain | Lang | API Surface | Key Symbols | Role |
|---|--------|------|-------------|-------------|------|
| 1 | `harness_skills/models` | Python | ✅ EXPLICIT | `Status`, `Severity`, `GateResult`, `Violation`, `HarnessResponse`, … | Foundation — no local deps |
| 2 | `harness_skills/utils` | Python | ✅ EXPLICIT | *(internal helpers only)* | Foundation — no local deps |
| 3 | `harness_skills/plugins` | Python | ✅ EXPLICIT | `PluginGateConfig`, `PluginGateRunner`, `load_plugin_gates`, `run_plugin_gates` | Gate plugin system |
| 4 | `harness_skills/gates` | Python | ✅ EXPLICIT | `CoverageGate`, `GateEvaluator`, `run_gates`, `DocsFreshnessGate` | Built-in evaluation gate runners |
| 5 | `harness_skills/generators` | Python | ✅ EXPLICIT | `EvaluationReport`, `GateResult`, `run_all_gates` | Artifact generators |
| 6 | `harness_skills/cli` | Python | ✅ EXPLICIT | `cli`, `PipelineGroup` | Orchestration — CLI entry point |
| 7 | `dom_snapshot_utility` | Python | ✅ EXPLICIT | `DOMSnapshot`, `snapshot_from_html`, `snapshot_from_url`, `snapshot_to_text` | Standalone — browser-free DOM inspection |
| 8 | `harness_dashboard` | Python | ✅ EXPLICIT | `compute_scores`, `render_dashboard`, `generate_dataset`, `HarnessRecord` | Standalone — effectiveness scoring |
| 9 | `log_format_linter` | Python | ✅ EXPLICIT | `generate_rules`, `detect_framework`, `check_file`, `check_directory` | Standalone — structured-log linter |
| 10 | `harness_skills` (root) | Python | ✅ EXPLICIT | `__all__ = []` (all symbols owned by sub-packages) | Namespace root |

### Dependency Flow

```
harness_skills/cli  ──────────────────► harness_skills/models
        │                             ► harness_skills/generators
        │
harness_skills/gates ─────────────────► harness_skills/models
        │                             ► harness_skills/plugins
        │
harness_skills/generators ────────────► harness_skills/models
        │
harness_skills/plugins ───────────────► harness_skills/models
        │
harness_skills/models     (foundation — no outgoing local deps)
harness_skills/utils      (foundation — no outgoing local deps)

── facade / script layer ──────────────────────────────────────
harness_skills.dom_snapshot_skill  ──► dom_snapshot_utility
harness_skills.effectiveness_stats ──► harness_skills.pr_effectiveness

── skills/ agent scripts ──────────────────────────────────────
context-handoff   ──► harness_skills.handoff
write_handoff     ──► harness_skills.handoff
harness-resume    ──► harness_skills.resume
dom-snapshot      ──► harness_skills.dom_snapshot_skill
error-aggregation ──► harness_skills.error_aggregation
                  ──► harness_skills.error_query_agent

── top-level orchestration scripts ────────────────────────────
coordinate.py        ──► harness_skills.task_lock
harness_status.py    ──► harness_skills.handoff
harness_telemetry.py ──► harness_skills (CLI / models)
harness_context.py   ──► harness_skills (context helpers)

── standalone (no local deps — safe to import anywhere) ───────
dom_snapshot_utility
harness_dashboard
log_format_linter
```

### Module Boundary Status

> Source of truth: run `/module-boundaries` to refresh. Full violation list in `ARCHITECTURE.md`.

| Domain | Boundary | Violations |
|--------|----------|------------|
| `harness_skills` (root) | ✅ EXPLICIT | 0 |
| `harness_skills/models` | ✅ EXPLICIT | 17 (tests + internal — deep-import pattern) |
| `harness_skills/plugins` | ✅ EXPLICIT | 6 (tests + `gates/runner.py`) |
| `harness_skills/gates` | ✅ EXPLICIT | 5 (tests only) |
| `harness_skills/generators` | ✅ EXPLICIT | 3 (`cli/` + test) |
| `harness_skills/cli` | ✅ EXPLICIT | 1 (private symbol in test) |
| `harness_skills/utils` | ✅ EXPLICIT | 0 |
| `dom_snapshot_utility` | ✅ EXPLICIT | 1 (test only) |
| `harness_dashboard` | ✅ EXPLICIT | 5 (tests only) |
| `log_format_linter` | ✅ EXPLICIT | 1 (test only) |

**Rules agents must follow:**
- Always import from the domain root: `from harness_skills.models import Status, GateResult` — never `from harness_skills.models.base import …`
- Never import a private symbol (leading `_`) across a domain boundary.
- Standalone packages (`dom_snapshot_utility`, `harness_dashboard`, `log_format_linter`) have no local deps — safe to use anywhere.
- Enforcement: `/check-code` and `/review-pr` enforce `MB001`–`MB014` in `.claude/principles.yaml`.

> Regenerate this section at any time: `/agents-md-generator --arch-only`

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

<!-- harness:code-conventions-start — do not edit this block manually -->
## Code Conventions

> Auto-generated from `pyproject.toml` linter config and detected codebase patterns.
> Run `/harness:update` to refresh after changing linter settings.

### Python
- **Version**: Python 3.12+ (use modern syntax: `match`, `X | Y` unions, PEP 604, `tomllib`, etc.)
- **Max line length**: 100 characters
- **String quotes**: Double quotes (enforced by Ruff formatter)
- **Indentation**: 4 spaces
- **Line endings**: LF

### Linter (Ruff)

Active rule sets:

| Code | Rule set | Purpose |
|------|----------|---------|
| `E`/`W` | pycodestyle | PEP 8 style errors and warnings |
| `F` | Pyflakes | Undefined names, unused imports |
| `I` | isort | Import ordering |
| `N` | pep8-naming | Class, function, and variable naming |
| `UP` | pyupgrade | Modernise syntax for Python 3.12 |
| `B` | flake8-bugbear | Likely bugs and design issues |
| `SIM` | flake8-simplify | Simplifiable code patterns |
| `PTH` | flake8-use-pathlib | Prefer `pathlib` over `os.path` |

Ignored rules (with rationale):

| Rule | Rationale |
|------|-----------|
| `E501` | Long lines allowed when they contain a URL |
| `B011` | `assert` is fine in tests |
| `F401` | Star imports allowed in `__init__` re-export files |

Per-file overrides:
- `tests/**/*.py`, `test_*.py` — relaxed naming rules (`N802`, `N803`, `N806`)
- `*_example.py` — relaxed naming and import-order rules (`N802`, `E402`)
- `harness_skills/cli/*.py` — relaxed naming rules (`N802`)

### Type Checking (Mypy)
- **Strict mode**: enabled — run `mypy --strict` (all strictness flags on)
- **`warn_return_any`**: `true` — functions must not silently return `Any`
- **`ignore_missing_imports`**: `true` — third-party stubs not required
- All functions must carry **full type annotations** (parameters + return type)

### Imports
- First-party modules: `harness_skills`, `harness_dashboard`, `log_format_linter`, `dom_snapshot_utility`
- Import ordering enforced by Ruff `I` (isort) rules
- `force-sort-within-sections = true` — no blank lines between import groups within a section

### Naming
- **Classes**: `PascalCase`
- **Functions / methods / variables**: `snake_case`
- **Constants**: `UPPER_SNAKE_CASE`
- `pydantic.validator` and `pydantic.model_validator` decorators treated as classmethod-equivalents (may use PascalCase)
- Test fixtures and parametrize IDs are exempt from naming rules (`tests/`, `test_*.py`)

### Paths
- Use `pathlib.Path` instead of `os.path` string manipulation (Ruff `PTH` rules)
- Example: `Path("some/file").read_text()` not `open("some/file").read()`
<!-- harness:code-conventions-end -->
