# AGENTS.md

<!-- harness:auto-generated — do not edit this block manually -->
last_updated: 2026-03-23
head: 157af7b
service: agent-harness-skills
<!-- /harness:auto-generated -->

Agent-facing reference for this repository.

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

## Testing Conventions

Test runner: **pytest** + **pytest-playwright**
Coverage threshold: **80 %** (configured in `harness.config.yaml`)

### Test file naming

| Category | Location | Pattern | Example |
|---|---|---|---|
| Unit (top-level modules) | `tests/` | `test_<module>.py` | `tests/test_exec_plan.py` |
| Gate tests | `tests/gates/` | `test_<gate>.py` | `tests/gates/test_docs_freshness.py` |
| CLI command tests | `tests/test_cli/` | `test_<command>.py` | `tests/test_cli/test_status_cmd.py` |
| Generator tests | `tests/test_generators/` | `test_<generator>.py` | `tests/test_generators/test_config_generator.py` |
| Browser / e2e tests | `tests/browser/` | `test_<feature>.py` | `tests/browser/test_smoke.py` |
| Model tests | `tests/test_models/` | `test_<model>.py` | `tests/test_models/test_gate_configs.py` |

Rules:
- All test files use the `test_` prefix (pytest discovery default).
- Mirror the source module path under `tests/`.  A module at
  `harness_skills/gates/coverage.py` has its tests at
  `tests/gates/test_coverage.py`.
- Browser/e2e tests live in `tests/browser/` and require `pytest-playwright`.

### Assertion style

Use **plain pytest assertions** — never `unittest`-style `self.assert*` methods.

```python
# ✅ correct
assert result.passed
assert len(violations) == 1
assert "dead_ref" in violation.message

# ❌ avoid
self.assertTrue(result.passed)
self.assertEqual(len(violations), 1)
```

Group related assertions in a single test function; each test should exercise
one logical behaviour:

```python
def test_missing_ref_violation(tmp_path):
    agents(tmp_path, TS + "\n[ghost](src/ghost.py)\n")
    r = DocsFreshnessGate().run(tmp_path)
    dead = [v for v in r.violations if v.kind == "dead_ref"]
    assert len(dead) == 1
    assert "src/ghost.py" in dead[0].message
```

### Coverage expectations

| Profile | Line coverage | Branch coverage |
|---|---|---|
| `starter` | **80 %** | optional |
| `standard` | **80 %** | optional |
| `advanced` | **90 %** | enabled |

The active threshold is set in `harness.config.yaml`:

```yaml
gates:
  coverage:
    threshold: 80        # minimum line coverage %
    branch_coverage: false
```

New tests should bring the module they exercise to **≥ 80 % line coverage**.
Aim for **boundary tests** (exactly at threshold, one over) for any
threshold-based logic.

### Fixture patterns

#### `tmp_path` — filesystem isolation

Use the built-in `tmp_path` fixture for any test that reads or writes files.
Never use real project paths in tests.

```python
def test_existing_ref_ok(tmp_path):
    touch(tmp_path / "src" / "models" / "foo.py")
    agents(tmp_path, TS + "\n[foo](src/models/foo.py)\n")
    r = DocsFreshnessGate().run(tmp_path)
    assert not [v for v in r.violations if v.kind == "dead_ref"]
```

#### `monkeypatch` — deterministic state

Use `monkeypatch` to freeze time-dependent values so tests are repeatable:

```python
@pytest.fixture(autouse=True)
def freeze_today(monkeypatch):
    monkeypatch.setattr(
        "harness_skills.gates.docs_freshness._today",
        lambda: date(2025, 6, 15),
    )
```

Mark cross-cutting fixtures `autouse=True` so all tests in the module benefit
automatically.

#### Helper factory functions

Prefer lightweight factory helpers over complex fixtures when setup is short
and test-local:

```python
def agents(tmp_path, content, sub=""):
    """Write an AGENTS.md file under tmp_path (optionally in a subdirectory)."""
    d = tmp_path / sub if sub else tmp_path
    d.mkdir(parents=True, exist_ok=True)
    f = d / "AGENTS.md"
    f.write_text(textwrap.dedent(content))
    return f

def touch(p: Path) -> Path:
    """Create an empty file, making parent directories as needed."""
    p.parent.mkdir(parents=True, exist_ok=True)
    p.touch()
    return p
```

#### Session-scoped fixtures — expensive resources

Use `scope="session"` for anything expensive to set up (browser instances,
server processes, network connections):

```python
@pytest.fixture(scope="session")
def base_url():
    return os.environ.get("BASE_URL", "http://localhost:3000")
```

#### `autouse` failure hooks

Register failure-capture logic as `autouse` fixtures in `conftest.py` so it
applies automatically to every test in the suite:

```python
# tests/browser/conftest.py
@pytest.fixture(autouse=True)
def screenshot_on_failure(page, request):
    yield
    if request.node.rep_call.failed:
        capture_screenshot(page, f"failures/{request.node.nodeid}")
```

### Running tests

```bash
# All tests
pytest tests/ -v

# Specific category
pytest tests/gates/ -v
pytest tests/browser/ -v

# With coverage report
pytest tests/ --cov=harness_skills --cov-report=term-missing

# Browser tests headed (shows window — useful for local debugging)
pytest tests/browser/ --headed

# Target a different environment
BASE_URL=https://staging.example.com pytest tests/browser/ -v
```
