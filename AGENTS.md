# AGENTS.md

<!-- harness:auto-generated — do not edit this block manually -->
last_updated: 2026-03-22
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

<!-- harness:cross-links — do not edit this block manually -->

---

## Related Documents

| Document | Relationship |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | project structure and package map |
| [PRINCIPLES.md](PRINCIPLES.md) | agent behaviour rules |
| [SPEC.md](SPEC.md) | logging convention |
| [.claude/commands/browser-automation.md](.claude/commands/browser-automation.md) | browser automation setup skill |
| [.claude/commands/harness/screenshot.md](.claude/commands/harness/screenshot.md) | screenshot helper skill |
| [.claude/commands/harness/observe.md](.claude/commands/harness/observe.md) | log observation skill |
| [DOCS_INDEX.md](DOCS_INDEX.md) | full documentation index |

<!-- /harness:cross-links -->
