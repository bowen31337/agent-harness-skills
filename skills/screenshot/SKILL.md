---
name: harness:screenshot
description: "Screenshot capture skill for recording application state as a visual artifact. Captures browser pages, desktop windows, or terminal output and saves them as timestamped PNG files (or base64-encoded inline artifacts). Use when: (1) documenting the visual state of a running web application, (2) capturing a UI before/after a code change, (3) recording terminal or CLI output as an image, (4) producing evidence artifacts for a bug report or test run, (5) snapshotting intermediate UI states during an automated agent workflow, (6) comparing layouts across breakpoints or themes. Triggers on: take a screenshot, capture the screen, screenshot the app, record the UI, capture application state, visual snapshot, screenshot artifact, capture browser, capture window, harness screenshot."
---

# harness:screenshot

## Workflow

**Do you want a quick one-shot capture?**
→ [Run the CLI](#cli-usage)

**Do you want to embed captures inside an agent pipeline?**
→ [Programmatic usage](#programmatic-usage)

**Do you want Claude to decide when to capture?**
→ [Agent-driven capture](#agent-driven-capture)

---

## Overview

The screenshot skill captures the visual state of a running application and
saves it as a **timestamped PNG artifact**.  It supports three capture backends,
selected automatically based on what is available:

| Backend | Target | Dependency |
|---------|--------|------------|
| `playwright` | Browser pages (Chromium / Firefox / WebKit) | `playwright` Python package |
| `pillow` | Full desktop or specific window (X11 / macOS / Win) | `Pillow` + `python-xlib` or `pygetwindow` |
| `terminal` | Terminal / CLI output rendered to image | `Pillow` + `pyte` |

All backends produce the same output shape — a `ScreenshotArtifact` — so the
rest of the pipeline never needs to know which backend ran.

---

## CLI Usage

```bash
# Capture a browser page at a URL:
python skills/screenshot/scripts/capture_screenshot.py \
    --url http://localhost:3000 \
    --out .artifacts/screenshots/

# Capture the full desktop:
python skills/screenshot/scripts/capture_screenshot.py \
    --desktop \
    --out .artifacts/screenshots/

# Capture and print base64 to stdout (for inline embedding):
python skills/screenshot/scripts/capture_screenshot.py \
    --url http://localhost:3000 \
    --base64

# Capture with a label (embedded in filename and metadata):
python skills/screenshot/scripts/capture_screenshot.py \
    --url http://localhost:3000 \
    --label "after-nav-refactor" \
    --out .artifacts/screenshots/

# Capture a specific viewport size:
python skills/screenshot/scripts/capture_screenshot.py \
    --url http://localhost:3000 \
    --width 1280 \
    --height 800 \
    --out .artifacts/screenshots/

# Wait for a CSS selector to appear before capturing:
python skills/screenshot/scripts/capture_screenshot.py \
    --url http://localhost:3000 \
    --wait-for "#app.ready" \
    --out .artifacts/screenshots/
```

---

## Programmatic Usage

### 1 — Simple browser capture

```python
from harness_skills.screenshot import capture_url, ScreenshotOptions

artifact = capture_url(
    url="http://localhost:3000",
    options=ScreenshotOptions(width=1280, height=800, label="home-page"),
    out_dir=".artifacts/screenshots/",
)

print(artifact.path)        # PosixPath('.artifacts/screenshots/home-page_2026-03-20T….png')
print(artifact.label)       # "home-page"
print(artifact.timestamp)   # datetime(2026, 3, 20, …, tzinfo=UTC)
print(artifact.size_bytes)  # 84320
```

### 2 — Desktop / window capture

```python
from harness_skills.screenshot import capture_desktop, capture_window

# Full desktop:
artifact = capture_desktop(out_dir=".artifacts/screenshots/")

# Specific window by title substring:
artifact = capture_window(title="My App", out_dir=".artifacts/screenshots/")
```

### 3 — Base64 inline artifact (no file written)

```python
from harness_skills.screenshot import capture_url_base64

b64 = capture_url_base64("http://localhost:3000")
# Embed in an agent message, a bug report, or an HTML page:
html = f'<img src="data:image/png;base64,{b64}" />'
```

### 4 — Sequence capture (before / after)

```python
from harness_skills.screenshot import SequenceCapture

with SequenceCapture(label="nav-refactor", out_dir=".artifacts/screenshots/") as seq:
    before = seq.snap("before", url="http://localhost:3000/nav")
    # … apply code change or trigger action …
    after  = seq.snap("after",  url="http://localhost:3000/nav")

print(seq.diff_summary())   # {"before": "…", "after": "…", "size_delta_bytes": -1240}
```

---

## Agent-Driven Capture

Wire `screenshot_tool` into a Claude agent session so Claude can decide when to
take a screenshot:

```python
import asyncio
from harness_skills.screenshot_agent import build_screenshot_tools, run_screenshot_agent
from claude_agent_sdk import ClaudeAgentOptions

# Build an MCP server exposing the screenshot tool to Claude:
server = build_screenshot_tools(out_dir=".artifacts/screenshots/")

options = ClaudeAgentOptions(
    mcp_servers={"screenshot": server},
    allowed_tools=["take_screenshot", "list_screenshots"],
)

# Or let run_screenshot_agent manage the full session:
result = asyncio.run(
    run_screenshot_agent(
        prompt="Take a screenshot of http://localhost:3000 before and after clicking the login button.",
        out_dir=".artifacts/screenshots/",
        model="claude-opus-4-6",
        max_turns=8,
    )
)
print(result)
```

### MCP Tools exposed to Claude

| Tool | Description |
|------|-------------|
| `take_screenshot` | Captures a URL, desktop, or window. Accepts `url`, `label`, `width`, `height`, `wait_for`, `desktop` (bool). Returns `ScreenshotArtifact` JSON. |
| `list_screenshots` | Lists all PNG artifacts in `out_dir` with metadata (label, timestamp, size). |

---

## Output Artifact

Every capture returns a `ScreenshotArtifact`:

```python
@dataclass
class ScreenshotArtifact:
    path: Path          # Absolute path to the saved PNG (None if base64-only)
    filename: str       # e.g. "home-page_2026-03-20T14-05-33Z.png"
    label: str          # Human-readable label (from --label or auto-generated)
    timestamp: datetime # UTC capture time
    size_bytes: int     # File size in bytes (0 if base64-only)
    backend: str        # "playwright" | "pillow" | "terminal"
    base64: str | None  # Populated only when base64 mode is requested
    metadata: dict      # url, viewport, window_title, etc.
```

Artifacts are written to `out_dir` (default: `.artifacts/screenshots/`) with the
naming pattern:

```
{label}_{ISO-8601-timestamp}.png
```

where timestamp colons are replaced with hyphens for filesystem compatibility.

---

## Backend Detection & Fallback

The capture functions probe available backends at import time:

1. **`playwright`** — preferred for URL captures; falls back to `pillow` if not installed.
2. **`pillow`** — used for desktop / window captures; required for terminal captures.
3. **`terminal`** — activated only when `--terminal` / `capture_terminal()` is called.

Install the recommended extras:

```bash
# Browser capture:
uv add playwright && playwright install chromium

# Desktop capture (Linux/X11):
uv add Pillow python-xlib

# Desktop capture (macOS / Windows):
uv add Pillow pygetwindow

# Terminal-to-image:
uv add Pillow pyte
```

---

## Key Files

| Path | Purpose |
|------|---------|
| `harness_skills/screenshot.py` | Core capture logic — `ScreenshotArtifact`, `ScreenshotOptions`, `SequenceCapture`, all `capture_*` helpers. |
| `harness_skills/screenshot_agent.py` | Agent SDK interface — `build_screenshot_tools`, `run_screenshot_agent`, MCP tool definitions. |
| `skills/screenshot/scripts/capture_screenshot.py` | Standalone CLI helper; runs without installing the package. |
