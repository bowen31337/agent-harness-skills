# harness screenshot

> Capture an application's current visual state via Playwright, store as PNG under `screenshots/`.

`screenshot` wraps Playwright headless-Chromium for harness-managed visual artefacts. Two modes: capture a fresh screenshot from a URL, or list / re-emit previously captured ones. Captured PNGs land in the configured output directory with deterministic filenames so they can be diffed across runs (visual regression style).

Requires Playwright to be installed (`uv tool install agent-harness-skills` already declares it as a dependency, but the browser binary itself needs `uv run playwright install chromium` once per environment — or `playwright install chromium` if Playwright is on your `PATH`).

## Synopsis

```bash
harness screenshot [OPTIONS]
```

## Options

| Flag | Type | Default | Description |
|---|---|---|---|
| `--url` | str | `http://localhost:3000` | URL to navigate to. |
| `--label` | str | — | Label for the screenshot filename. Sanitized into a slug. |
| `--out` | path | `screenshots` | Output directory. Created if missing. |
| `--width` | int | `1280` | Viewport width in pixels. |
| `--height` | int | `800` | Viewport height in pixels. |
| `--base64` | flag | — | Emit base64-encoded image bytes on stdout (useful for inline embedding). |
| `--list` | flag | — | List existing screenshots in `--out` instead of capturing. |
| `--output-format` | choice (`json` / `text`) | TTY-aware | Output of the *report* about the capture (file path, size, dimensions). |

## Workflows

### Smoke-capture a local dev server

```bash
harness screenshot --url http://localhost:3000 --label home-page
# Writes screenshots/home-page-<timestamp>.png
```

### Inventory existing captures

```bash
harness screenshot --list --output-format json | jq '.screenshots[].path'
```

### Inline base64 (for embedding into a report)

```bash
harness screenshot --url https://example.com --base64
# Stdout: data: URI ready to drop into HTML/Markdown
```

### Custom viewport for mobile checks

```bash
harness screenshot --url http://localhost:3000 --label mobile --width 375 --height 812
```

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Screenshot captured (or list emitted). |
| `1` | Capture failed — Playwright not installed, browser binary missing, URL unreachable. |
| `2` | Internal error — unwritable output dir, invalid arguments. |

## See also

- [`harness boot`](boot.md) — launch the app `screenshot` will then capture.
- `tests/browser/` — Playwright e2e tests; `screenshot` shares the same Playwright install.
