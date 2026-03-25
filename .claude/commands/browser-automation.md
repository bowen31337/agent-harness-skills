# Browser Automation Setup

Generate a browser automation integration config (Playwright **or** Puppeteer) so agents can drive the UI and capture screenshots.

---

## Instructions

### Step 1 — Detect project context

```bash
# Check package manager & existing deps
ls package.json pyproject.toml requirements*.txt 2>/dev/null
cat package.json 2>/dev/null | python3 -m json.tool 2>/dev/null || true
```

Determine:
- **Runtime**: Node.js (package.json present) or Python (pyproject.toml)
- **Existing framework**: React, Next.js, Vite, Express, FastAPI, Django, etc.
- **Already installed**: is `playwright`, `@playwright/test`, or `puppeteer` already a dep?

---

### Step 2 — Choose framework

**Prefer Playwright** unless the project already uses Puppeteer or the user explicitly requested Puppeteer.

| Signal | Choice |
|---|---|
| `puppeteer` in deps | Puppeteer |
| User said "puppeteer" | Puppeteer |
| Next.js / Vite / SPA | Playwright |
| Python project | Playwright (via `playwright` PyPI package) |
| Default | Playwright |

---

### Step 3A — Generate Playwright config (Node.js)

If Node.js project without Playwright already installed:

```bash
npm install --save-dev @playwright/test
npx playwright install chromium   # lightweight — just chromium
```

Write `playwright.config.ts`:

```typescript
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,

  use: {
    baseURL: process.env.BASE_URL ?? 'http://localhost:3000',
    headless: true,
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    trace: 'retain-on-failure',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  // Automatically start dev server when running tests locally
  // webServer: {
  //   command: 'npm run dev',
  //   url: 'http://localhost:3000',
  //   reuseExistingServer: !process.env.CI,
  // },
});
```

Write `e2e/screenshot-helper.ts` — a reusable agent utility:

```typescript
import { Page } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

const SCREENSHOT_DIR = process.env.SCREENSHOT_DIR ?? './screenshots';

/**
 * Capture a full-page screenshot and return the file path.
 * Agents call this to produce visual evidence of UI state.
 */
export async function captureScreenshot(
  page: Page,
  label: string,
): Promise<string> {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
  const filename = `${label}-${timestamp}.png`;
  const filepath = path.join(SCREENSHOT_DIR, filename);
  await page.screenshot({ path: filepath, fullPage: true });
  console.log(`[screenshot] ${filepath}`);
  return filepath;
}

/**
 * Navigate to a URL, wait for network idle, then capture a screenshot.
 */
export async function visitAndCapture(
  page: Page,
  url: string,
  label: string,
): Promise<string> {
  await page.goto(url, { waitUntil: 'networkidle' });
  return captureScreenshot(page, label);
}
```

Write `e2e/agent-driver.ts` — high-level helpers agents use to drive the UI:

```typescript
import { chromium, Browser, BrowserContext, Page } from 'playwright';
import { captureScreenshot } from './screenshot-helper';

/**
 * Lightweight harness for agent-driven browser sessions.
 *
 * Usage:
 *   const driver = await AgentDriver.launch();
 *   const page   = await driver.newPage();
 *   await page.goto('http://localhost:3000');
 *   await driver.screenshot(page, 'home');
 *   await driver.close();
 */
export class AgentDriver {
  private browser: Browser;
  private context: BrowserContext;

  private constructor(browser: Browser, context: BrowserContext) {
    this.browser = browser;
    this.context = context;
  }

  static async launch(options: { headless?: boolean; baseURL?: string } = {}): Promise<AgentDriver> {
    const browser = await chromium.launch({ headless: options.headless ?? true });
    const context = await browser.newContext({
      baseURL: options.baseURL ?? process.env.BASE_URL ?? 'http://localhost:3000',
      viewport: { width: 1280, height: 800 },
      recordVideo: process.env.RECORD_VIDEO ? { dir: './videos' } : undefined,
    });
    return new AgentDriver(browser, context);
  }

  async newPage(): Promise<Page> {
    return this.context.newPage();
  }

  async screenshot(page: Page, label: string): Promise<string> {
    return captureScreenshot(page, label);
  }

  async close(): Promise<void> {
    await this.context.close();
    await this.browser.close();
  }
}
```

---

### Step 3B — Generate Playwright config (Python)

If Python project:

```bash
uv add playwright pytest-playwright
playwright install chromium
```

Write `playwright.config.py` (used by `pytest-playwright`):

```python
# playwright.config.py
# pytest-playwright reads from pytest.ini / pyproject.toml — see below.
# This file documents agent-level defaults; actual config lives in pyproject.toml.
```

Add to `pyproject.toml` (under `[tool.pytest.ini_options]`):

```toml
[tool.pytest.ini_options]
addopts = "--browser chromium --headed=false"

[tool.playwright]
base_url = "http://localhost:3000"
```

Write `tests/browser/screenshot_helper.py`:

```python
"""Reusable screenshot utility for agent-driven browser tests."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Page

SCREENSHOT_DIR = Path(os.getenv("SCREENSHOT_DIR", "screenshots"))


def capture_screenshot(page: Page, label: str) -> Path:
    """Capture a full-page screenshot; return the file path."""
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    filepath = SCREENSHOT_DIR / f"{label}-{timestamp}.png"
    page.screenshot(path=str(filepath), full_page=True)
    print(f"[screenshot] {filepath}")
    return filepath


def visit_and_capture(page: Page, url: str, label: str) -> Path:
    """Navigate to *url*, wait for load, then capture a screenshot."""
    page.goto(url, wait_until="networkidle")
    return capture_screenshot(page, label)
```

Write `tests/browser/agent_driver.py`:

```python
"""High-level browser driver for claw-forge agents."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from .screenshot_helper import capture_screenshot


class AgentDriver:
    """Thin wrapper around Playwright for agent-driven UI sessions.

    Example::

        with AgentDriver.launch() as driver:
            page = driver.new_page()
            page.goto("/dashboard")
            driver.screenshot(page, "dashboard")
    """

    def __init__(self, browser: Browser, context: BrowserContext) -> None:
        self._browser = browser
        self._context = context

    @classmethod
    def launch(
        cls,
        headless: bool = True,
        base_url: Optional[str] = None,
    ) -> "AgentDriver":
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=headless)
        context = browser.new_context(
            base_url=base_url or os.getenv("BASE_URL", "http://localhost:3000"),
            viewport={"width": 1280, "height": 800},
        )
        return cls(browser, context)

    def new_page(self) -> Page:
        return self._context.new_page()

    def screenshot(self, page: Page, label: str) -> Path:
        return capture_screenshot(page, label)

    def close(self) -> None:
        self._context.close()
        self._browser.close()

    def __enter__(self) -> "AgentDriver":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
```

---

### Step 3C — Generate Puppeteer config (Node.js only)

Only if Puppeteer was chosen in Step 2:

```bash
npm install --save-dev puppeteer
```

Write `puppeteer.config.cjs`:

```js
/** @type {import('puppeteer').Configuration} */
module.exports = {
  cacheDirectory: '.cache/puppeteer',
  defaultProduct: 'chrome',
};
```

Write `e2e/screenshot-helper.ts` (Puppeteer version):

```typescript
import puppeteer, { Page } from 'puppeteer';
import * as fs from 'fs';
import * as path from 'path';

const SCREENSHOT_DIR = process.env.SCREENSHOT_DIR ?? './screenshots';

export async function captureScreenshot(page: Page, label: string): Promise<string> {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
  const filename = `${label}-${timestamp}.png`;
  const filepath = path.join(SCREENSHOT_DIR, filename);
  await page.screenshot({ path: filepath, fullPage: true });
  console.log(`[screenshot] ${filepath}`);
  return filepath;
}

export async function launchAndCapture(
  url: string,
  label: string,
): Promise<{ filepath: string }> {
  const browser = await puppeteer.launch({ headless: true });
  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 800 });
  await page.goto(url, { waitUntil: 'networkidle2' });
  const filepath = await captureScreenshot(page, label);
  await browser.close();
  return { filepath };
}
```

---

### Step 4 — Write AGENTS.md section

Append (or create) `AGENTS.md` with a **Browser Automation** section so all agents know how to drive the UI:

```markdown
## Browser Automation

Framework: **<Playwright|Puppeteer>**
Base URL:  `http://localhost:3000` (override with `BASE_URL` env var)
Screenshots saved to: `./screenshots/`

### Quick start (agents)

**Node.js / Playwright**
```ts
import { AgentDriver } from './e2e/agent-driver';

const driver = await AgentDriver.launch();
const page   = await driver.newPage();
await page.goto('/');
await driver.screenshot(page, 'home');
await driver.close();
```

**Python / Playwright**
```python
from tests.browser.agent_driver import AgentDriver

with AgentDriver.launch() as driver:
    page = driver.new_page()
    page.goto("/dashboard")
    driver.screenshot(page, "dashboard")
```

### Running e2e tests

```bash
# Node — Playwright
npx playwright test

# Node — single file / headed (debug)
npx playwright test e2e/my-flow.spec.ts --headed

# Python — pytest-playwright
pytest tests/browser/ -v

# View last report (Playwright HTML)
npx playwright show-report
```

### Capturing screenshots from an agent task

1. Start the dev server: `npm run dev` (or equivalent)
2. Set `BASE_URL` if running against staging / CI
3. Call `driver.screenshot(page, '<meaningful-label>')`
4. Find the PNG at `screenshots/<label>-<timestamp>.png`
5. Attach the path in your task result or claw-forge state update
```

---

### Step 5 — Validate install

```bash
# Playwright (Node)
npx playwright --version 2>/dev/null && echo "✅ Playwright ready" || echo "⚠️  Playwright not found"

# Playwright (Python)
python3 -c "import playwright; print('✅ Playwright Python ready')" 2>/dev/null || true

# Puppeteer (Node)
node -e "require('puppeteer'); console.log('✅ Puppeteer ready')" 2>/dev/null || true
```

---

### Step 6 — Report

Print a summary:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Browser Automation — Setup Complete
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Framework  : <Playwright|Puppeteer> <version>
  Browser    : Chromium (headless)
  Base URL   : http://localhost:3000
  Screenshots: ./screenshots/

  Files written:
    ✅ <playwright.config.ts|puppeteer.config.cjs>
    ✅ e2e/agent-driver.ts
    ✅ e2e/screenshot-helper.ts   (or tests/browser/)
    ✅ AGENTS.md  (browser section appended)

  Run tests  : npx playwright test
  Debug UI   : npx playwright test --headed
  Show report: npx playwright show-report

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

If anything failed (missing binary, install error), explain the exact fix.

---

### Notes

- **Headless by default** — agents never need a display; set `HEADLESS=false` or pass `--headed` for local debugging.
- **Screenshots on failure** — Playwright is configured with `screenshot: 'only-on-failure'`; use `driver.screenshot()` for deliberate captures.
- **CI-safe** — `retries: 2` on CI, single worker to avoid port conflicts.
- **`BASE_URL` env var** — lets agents target dev, staging, or production without changing code.
- **Video & trace** — retained on failure for post-mortem analysis; find them in `test-results/`.
