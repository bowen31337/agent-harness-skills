---
name: dom-snapshot
description: "Browser-free DOM inspection for agents. Fetches or parses server-rendered HTML and returns a compact, structured text snapshot covering headings, ARIA landmarks, navigation, forms, interactive buttons, tables, images, and visible body text — sized to fit comfortably in an LLM context window. Use when: (1) understanding a page's structure before deciding the next action, (2) checking whether a form, heading, or link is present after a navigation event, (3) verifying UI state in a test harness without spinning up Playwright or Selenium, (4) parsing raw HTML retrieved by a previous step. Triggers on: inspect page, DOM snapshot, page structure, check form, check heading, check link, UI state, parse HTML, page metadata, navigation links, accessible landmarks."
---

# DOM Snapshot Skill

## Overview

The DOM Snapshot skill gives agents a **browser-free window into page
structure**.  It uses `requests` + `BeautifulSoup` to parse server-rendered
HTML and emits a compact, labelled text block that fits comfortably inside an
LLM context window.

Sections returned:

| Section | What it contains |
|---------|-----------------|
| **Page Metadata** | URL, `<title>`, meta description, `lang` attribute |
| **ARIA Landmarks** | Explicit `role=` attributes + implicit landmarks (`<main>`, `<nav>`, …) |
| **Headings** | All `<h1>`–`<h6>` in document order |
| **Navigation Links** | Links inside `<nav>` elements (or all `<a>` when no `<nav>` is found) |
| **Forms** | Each `<form>` with its fields (type, name, label, required) and buttons |
| **Interactive Buttons** | Standalone `<button>` elements and `role=button` nodes outside forms |
| **Data Tables** | Caption, headers, row count, and up to 3 sample rows per `<table>` |
| **Images** | `src`, `alt`, and optional `width`×`height` for up to 10 `<img>` tags |
| **Visible Text** | First 1 500 characters of stripped body text (scripts/styles removed) |
| **Errors / Warnings** | Present only when something went wrong (HTTP error, missing dependency) |

> **Limitation** — only server-rendered HTML is visible.  Content injected by
> JavaScript after the initial response will *not* appear.  For SPAs, capture
> the page source at the right moment and pass it to `dom_snapshot_html`.

---

## Workflow

**Inspect a live URL?**
→ [URL mode](#url-mode)

**Already have the HTML string in memory?**
→ [HTML mode](#html-mode)

**Need a quick CLI one-liner?**
→ [CLI usage](#cli-usage)

**Embedding the snapshot inside an agent?**
→ [Programmatic usage](#programmatic-usage)

---

## CLI Usage

```bash
# Snapshot a live URL:
python skills/dom-snapshot/scripts/snapshot_dom.py https://example.com

# Pass raw HTML via stdin:
curl -s https://example.com | \
    python skills/dom-snapshot/scripts/snapshot_dom.py --html -

# Read HTML from a file:
python skills/dom-snapshot/scripts/snapshot_dom.py --html page.html

# Tune timeouts and link limits:
python skills/dom-snapshot/scripts/snapshot_dom.py \
    https://example.com --timeout 30 --max-links 25
```

---

## URL Mode

Run the following Python snippet inside an agent or harness step:

```python
import sys
sys.path.insert(0, ".")
from harness_skills.dom_snapshot_skill import dom_snapshot_url

result = dom_snapshot_url(
    "https://example.com",
    timeout=15,    # HTTP timeout in seconds
    max_links=15,  # max navigation links shown
)
print(result)
```

---

## HTML Mode

Use when you already hold the raw HTML (e.g. captured from a Playwright page
or retrieved by a previous `requests.get` call):

```python
import sys
sys.path.insert(0, ".")
from harness_skills.dom_snapshot_skill import dom_snapshot_html

html = "<html><body><h1>Hello</h1><p>World</p></body></html>"

result = dom_snapshot_html(
    html,
    base_url="https://example.com",  # resolves relative hrefs/srcs
    max_links=15,
)
print(result)
```

---

## Programmatic Usage

For more control, use the lower-level `dom_snapshot_utility` API directly:

```python
import sys
sys.path.insert(0, ".")
from dom_snapshot_utility import (
    snapshot_from_url,
    snapshot_from_html,
    snapshot_to_text,
    DOMSnapshot,
)

# Fetch and parse
snap: DOMSnapshot = snapshot_from_url("https://example.com", timeout=20)

# Inspect fields directly
print(snap.meta.title)
print([h.text for h in snap.headings])
print([f.id for f in snap.forms])

# Or render as text
print(snapshot_to_text(snap, max_links=15))
```

### Injecting custom session headers (cookies, auth)

```python
import requests
import sys
sys.path.insert(0, ".")
from dom_snapshot_utility.snapshot import snapshot_from_html

session = requests.Session()
session.headers["Cookie"] = "session=abc123"
resp = session.get("https://example.com/dashboard", timeout=15)
snap = snapshot_from_html(resp.text, base_url="https://example.com/dashboard")

from dom_snapshot_utility import snapshot_to_text
print(snapshot_to_text(snap))
```

---

## Output Format

```
### Page Metadata
URL      : https://example.com
Title    : Example Domain
Desc     : This domain is for use in illustrative examples...
Lang     : en

### ARIA Landmarks
  [main] role=main
  [navigation] role=navigation

### Headings
H1: Example Domain

### Navigation Links (3 total)
  'Home' -> https://example.com/
  'Docs' -> https://example.com/docs/
  'Blog' -> https://example.com/blog/

### Forms (1 total)
  FORM id='search' action='/search' method='GET'
    [search] name='q' * label='Search' placeholder='Search docs…'
    Buttons: ['Search']

### Interactive Buttons (2 total)
  [button] 'Open menu'
  [button] 'Close dialog' aria='Close'

### Data Tables (1 total)
  TABLE 'Results' — 42 rows
    Headers: ['Name', 'Status', 'Updated']
    Row: ['alpha', 'passing', '2025-01-10']

### Images (1 total)
  <img> alt='Site logo' (200×50) src=https://example.com/logo.png

### Visible Text (first 1 500 chars)
Example Domain
This domain is for use in illustrative examples in documents…

### Errors / Warnings        ← only present when something went wrong
  ⚠  HTTP 404: Not Found
```

---

## Data Structures

### `DOMSnapshot`

The structured object returned by `snapshot_from_html` / `snapshot_from_url`.

| Field | Type | Description |
|-------|------|-------------|
| `meta` | `PageMeta` | URL, title, description, lang. |
| `landmarks` | `list[AriaRegion]` | ARIA landmark regions. |
| `headings` | `list[Heading]` | Headings in document order. |
| `nav_links` | `list[Link]` | Navigation links (truncated to `max_links`). |
| `nav_links_total` | `int` | Total links found before truncation. |
| `forms` | `list[Form]` | Forms with fields and buttons. |
| `buttons` | `list[Button]` | Standalone interactive buttons. |
| `tables` | `list[TableSnapshot]` | Table summaries with sample rows. |
| `images` | `list[ImageSnapshot]` | Image metadata (up to 10). |
| `visible_text` | `str` | Stripped body text (first 1 500 chars). |
| `errors` | `list[str]` | Any fetch or parse errors encountered. |

### `Form` / `InputField`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Form `id` attribute. |
| `action` | `str` | Resolved `action` URL. |
| `method` | `str` | `GET` or `POST`. |
| `fields` | `list[InputField]` | Visible input fields (hidden/submit excluded). |
| `buttons` | `list[str]` | Button labels inside the form. |

**`InputField`**: `type`, `name`, `label`, `placeholder`, `required`.

---

## Key Files

| Path | Purpose |
|------|---------|
| `dom_snapshot_utility/snapshot.py` | Core implementation — parsing, dataclasses, `snapshot_to_text`. |
| `dom_snapshot_utility/__init__.py` | Public API exports for the utility package. |
| `harness_skills/dom_snapshot_skill.py` | Skill wrapper — `dom_snapshot_url`, `dom_snapshot_html`, CLI entry point. |
| `skills/dom-snapshot/scripts/snapshot_dom.py` | Standalone CLI helper (no install required). |
| `tests/test_dom_snapshot.py` | Full unit test suite (offline — HTTP mocked). |
