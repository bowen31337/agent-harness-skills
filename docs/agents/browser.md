# Browser Automation & DOM Snapshots — agent-harness-skills

← [AGENTS.md](../../AGENTS.md)

Two complementary tools are available: **`AgentDriver`** (full Playwright browser, for
interactive e2e tests) and **`dom_snapshot_utility`** (browser-free HTML parser, for
fast structural inspection without launching Chromium).

---

## 1 · AgentDriver (Playwright)

Framework: **Playwright** (Python)
Browser: Chromium (headless by default)
Base URL: `http://localhost:3000` — override with `BASE_URL` env var
Screenshots: `./screenshots/`

### Quick start

```python
from tests.browser.agent_driver import AgentDriver

# Context-manager form — always cleans up the browser
with AgentDriver.launch() as driver:
    page = driver.new_page()
    page.goto("/")                          # relative to BASE_URL
    driver.screenshot(page, "home")         # → screenshots/home-<timestamp>.png

# Absolute URL
with AgentDriver.launch(base_url="http://localhost:8080") as driver:
    page = driver.new_page()
    page.goto("http://localhost:8080/login")
    driver.screenshot(page, "login")
```

### Screenshot helpers

```python
from tests.browser.screenshot_helper import capture_screenshot, visit_and_capture

path = capture_screenshot(page, "checkout-step-2")
path = visit_and_capture(page, "/dashboard", "dashboard")
```

### Video recording (post-mortems)

```python
with AgentDriver.launch(record_video=True) as driver:
    page = driver.new_page()
    page.goto("/checkout")
# .webm written to ./videos/ when the context closes
```

### Failure screenshots (pytest-playwright)

`tests/browser/conftest.py` captures a full-page PNG on every test failure:

```
screenshots/failures/<test-nodeid>.png
```

Upload `screenshots/` as a CI artefact to inspect failures without re-running.

### Running e2e tests

```bash
pytest tests/browser/ -v
pytest tests/browser/test_smoke.py -v
pytest tests/browser/ --headed          # visible browser for local debug
BASE_URL=https://staging.example.com pytest tests/browser/ -v
```

### Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `BASE_URL` | `http://localhost:3000` | Base URL for relative `goto()` calls |
| `SCREENSHOT_DIR` | `./screenshots` | Directory where PNGs are saved |

### Capturing a screenshot from an agent task

1. Start the dev server if needed (`python -m uvicorn app:app --reload`)
2. Set `BASE_URL` if targeting staging/CI
3. Call `driver.screenshot(page, '<meaningful-label>')`
4. Find the PNG at `screenshots/<label>-<timestamp>.png`
5. Attach the path in your task result or claw-forge state update

### Install (first time)

```bash
uv add playwright pytest-playwright
playwright install chromium   # downloads the Chromium binary
```

Both are already declared in `pyproject.toml`.

---

## 2 · DOM Snapshot (Browser-Free)

`dom_snapshot_utility` parses HTML without a running browser.  Use it when you need
structural page inspection without the overhead of launching Chromium.

```python
from dom_snapshot_utility import (
    DOMSnapshot,
    snapshot_from_html,
    snapshot_from_url,
    snapshot_to_text,
)

# From a URL (fetches with requests, no Playwright needed)
snap: DOMSnapshot = snapshot_from_url("http://localhost:3000/")

# From raw HTML
snap = snapshot_from_html("<html><body><h1>Hello</h1></body></html>")

# Human-readable summary
print(snapshot_to_text(snap))
```

### Available models

`DOMSnapshot`, `PageMeta`, `Heading`, `Link`, `Button`, `InputField`, `Form`,
`AriaRegion`, `TableSnapshot`, `ImageSnapshot`

### Facade

`harness_skills.dom_snapshot_skill` wraps `dom_snapshot_utility` and is used by
the `skills/dom-snapshot/` agent skill.

### DOM snapshot skill

```bash
# invoke via Claude Code skill system
/dom-snapshot
```

Skill doc: `.claude/commands/dom-snapshot.md`

---

## Deeper References

- **Browser automation skill** → `.claude/commands/browser-automation.md` (462 lines)
- **Screenshot skill** → `.claude/commands/harness/screenshot.md`
- **DOM snapshot skill** → `.claude/commands/dom-snapshot.md` (151 lines)
- **DOM snapshot source** → `dom_snapshot_utility/snapshot.py`
- **Playwright tests** → `tests/browser/`
- **Test dom snapshot** → `tests/test_dom_snapshot.py`
- **Architecture** → [ARCHITECTURE.md](../../ARCHITECTURE.md) (§ `dom_snapshot_utility`)
