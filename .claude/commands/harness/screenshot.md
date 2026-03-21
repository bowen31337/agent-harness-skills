# Harness Screenshot

Capture a **full-page screenshot** of a running application and save it as a
visual artifact.  The screenshot is written to the `screenshots/` directory and
the file path is returned in a machine-readable envelope so downstream agents
and CI pipelines can attach it to reports, pull-request comments, or telemetry.

Use this skill to preserve a **point-in-time visual snapshot** of application
state — before/after a UI change, on test failure, or as a quality gate step.

---

## Usage

```bash
# Capture the root page of a local dev server
/harness:screenshot http://localhost:3000

# Capture with a meaningful label (default: "screenshot")
/harness:screenshot http://localhost:3000 --label login-form

# Save to a custom directory
/harness:screenshot http://localhost:8080/dashboard --output-dir artifacts/screenshots

# Use an already-open Playwright session (pass a session tag)
/harness:screenshot --session my-e2e-session --label post-submit

# Emit only raw JSON (no human-readable header)
/harness:screenshot http://localhost:3000 --format json

# Wait for a specific selector before capturing
/harness:screenshot http://localhost:3000 --wait-for "#app-ready"

# Capture a specific viewport size
/harness:screenshot http://localhost:3000 --width 1280 --height 800
```

---

## Instructions

### Step 1 — Resolve the target URL

Determine the capture target from the arguments:

- If a **URL** is provided as the first positional argument, use it directly.
- If `--session <tag>` is provided instead, reuse the open Playwright session
  identified by that tag (skip navigation in Step 3).
- If neither is provided, look for a running dev server by probing common ports:

```bash
for PORT in 3000 3001 5173 8000 8080; do
  curl -sf --max-time 1 "http://localhost:$PORT" -o /dev/null && \
    echo "http://localhost:$PORT" && break
done
```

If no server responds, emit an error and exit with code `2`.

---

### Step 2 — Resolve output path

Compute the output file path:

```python
import os
from datetime import datetime
from pathlib import Path

output_dir = Path(os.getenv("SCREENSHOT_DIR", args.output_dir or "screenshots"))
output_dir.mkdir(parents=True, exist_ok=True)

label     = args.label or "screenshot"
timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
filepath  = output_dir / f"{label}-{timestamp}.png"
```

The `SCREENSHOT_DIR` environment variable overrides `--output-dir` if set.

---

### Step 3 — Capture the screenshot

Use the reusable helper in `tests/browser/screenshot_helper.py` when running
inside the test suite, or invoke Playwright directly for ad-hoc captures:

#### Option A — Helper function (preferred inside tests)

```python
from tests.browser.screenshot_helper import visit_and_capture, capture_screenshot
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page    = browser.new_page(
        viewport={"width": args.width or 1280, "height": args.height or 800}
    )
    filepath = visit_and_capture(page, url=target_url, label=label)
    browser.close()
```

#### Option B — Playwright CLI (no Python runtime required)

```bash
npx playwright screenshot \
  --full-page \
  --wait-for-selector "${WAIT_FOR:-body}" \
  --viewport-size "${WIDTH:-1280},${HEIGHT:-800}" \
  "$TARGET_URL" \
  "$FILEPATH"
```

#### Option C — Fallback (puppeteer via node)

```bash
node -e "
const puppeteer = require('puppeteer');
(async () => {
  const browser = await puppeteer.launch({args: ['--no-sandbox']});
  const page    = await browser.newPage();
  await page.setViewport({width: ${WIDTH:-1280}, height: ${HEIGHT:-800}});
  await page.goto('$TARGET_URL', {waitUntil: 'networkidle2'});
  ${WAIT_FOR:+await page.waitForSelector('$WAIT_FOR');}
  await page.screenshot({path: '$FILEPATH', fullPage: true});
  await browser.close();
})();
"
```

Try options in order A → B → C.  If all fail, emit an error with instructions
for installing Playwright (`pip install playwright && playwright install chromium`)
and exit with code `2`.

---

### Step 4 — Verify the artifact

After capture, confirm the file was written and is non-empty:

```bash
if [ -f "$FILEPATH" ] && [ -s "$FILEPATH" ]; then
  SIZE=$(du -h "$FILEPATH" | cut -f1)
  echo "[screenshot] saved: $FILEPATH ($SIZE)"
else
  echo "[screenshot] ERROR: file missing or empty — $FILEPATH" >&2
  exit 1
fi
```

---

### Step 5 — Render the human-readable summary

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Harness Screenshot — ✅ CAPTURED
  Label  : <label>
  URL    : <target_url>
  File   : <filepath>
  Size   : <file_size>
  Taken  : <ISO-8601 timestamp>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

If capture failed, emit:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Harness Screenshot — ❌ FAILED
  URL    : <target_url>
  Reason : <error message>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

### Step 6 — Emit structured data (agent-readable)

Always emit a fenced JSON block after the summary so downstream agents can
consume the result without re-reading the filesystem:

**On success:**

```json
{
  "command": "harness screenshot",
  "status": "success",
  "label": "login-form",
  "url": "http://localhost:3000",
  "filepath": "screenshots/login-form-20260320T143512.png",
  "file_size_bytes": 184320,
  "viewport": { "width": 1280, "height": 800 },
  "captured_at": "2026-03-20T14:35:12Z",
  "wait_for_selector": null,
  "tool_used": "playwright"
}
```

**On failure:**

```json
{
  "command": "harness screenshot",
  "status": "error",
  "label": "login-form",
  "url": "http://localhost:3000",
  "filepath": null,
  "error": "<human-readable reason>",
  "captured_at": "2026-03-20T14:35:12Z"
}
```

---

## Options

| Flag | Default | Effect |
|---|---|---|
| `URL` | *(positional)* | Target URL to navigate to and capture |
| `--label TEXT` | `screenshot` | Short name used in the filename and JSON envelope |
| `--output-dir PATH` | `screenshots/` | Directory to save the PNG; overridden by `$SCREENSHOT_DIR` |
| `--session TAG` | — | Reuse an open Playwright session instead of launching a new browser |
| `--wait-for SELECTOR` | — | CSS selector to wait for before capturing (e.g. `"#app-ready"`) |
| `--width N` | `1280` | Viewport width in pixels |
| `--height N` | `800` | Viewport height in pixels |
| `--full-page` | on | Capture the full scrollable page (not just the visible viewport) |
| `--no-full-page` | — | Capture only the visible viewport |
| `--format table\|json` | `table` | Output format — `table` (human-readable + JSON) or `json` (raw JSON only) |
| `--timeout MS` | `30000` | Navigation + selector wait timeout in milliseconds |

---

## When to use this skill

| Scenario | Recommended skill |
|---|---|
| Capture app state before/after a UI change | **`/harness:screenshot`** ← you are here |
| Verify the DOM structure of a live page | `/dom-snapshot` |
| Run full browser automation workflows | `/browser-automation` |
| Full quality gate before merge | `/check-code` |
| Detect stalled agents or plans | `/harness:detect-stale` |
| Detect cross-agent file conflicts | `/coordinate` |

---

## Notes

- **Read-only** — this skill never modifies source files or the state service.
  It only writes a PNG to the `screenshots/` output directory.
- **Headless by default** — Playwright is launched with `headless=True`.
  Set `PLAYWRIGHT_HEADFUL=1` in the environment to display the browser window.
- **Full-page capture** — by default the entire scrollable page is captured,
  not just the visible viewport.  Pass `--no-full-page` to restrict to the
  viewport area.
- **Helper compatibility** — the Python `capture_screenshot` and
  `visit_and_capture` functions in `tests/browser/screenshot_helper.py` are
  fully compatible with this skill's output schema; filenames follow the same
  `<label>-<timestamp>.png` convention.
- **CI-safe** — the skill runs headless and writes only to the designated
  output directory.  Add `screenshots/` to `.gitignore` to avoid committing
  artifacts, or archive the directory as a CI artifact for visual review.
- **Exit codes** — `0` = success, `1` = screenshot written but verification
  failed, `2` = browser launch or navigation error.
