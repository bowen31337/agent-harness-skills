# DOM Snapshot

Inspect the current UI state of a web page or raw HTML without a full browser
session.  Returns a compact, structured text snapshot covering headings, ARIA
landmarks, navigation, forms, interactive buttons, tables, images, and visible
body text — sized to fit comfortably in an LLM context window.

## When to use

- You need to understand a page's structure before deciding the next action.
- You want to check whether a form, heading, or link is present after a
  navigation event.
- You are verifying UI state in a test harness without spinning up Playwright
  or Selenium.
- A previous step retrieved raw HTML and you need to parse it structurally.

## Usage

```
/dom-snapshot <url-or-keyword> [--html] [--timeout N] [--max-links N]
```

| Argument | Default | Description |
|---|---|---|
| `url-or-keyword` | *(required)* | A URL to fetch **or** the keyword `html` when passing raw HTML |
| `--html` | off | Treat the first argument as raw HTML instead of a URL |
| `--timeout N` | `15` | HTTP request timeout in seconds |
| `--max-links N` | `15` | Maximum links shown per section |

## Instructions

### Step 1 — Determine input mode

If `$ARGUMENTS` starts with `http://` or `https://`, use **URL mode**.
Otherwise, if `--html` is present, use **HTML mode**.
Otherwise, attempt URL mode and fall back to HTML mode on error.

### Step 2 — Call the skill function

**URL mode** — run the following Python snippet:

```python
import sys
sys.path.insert(0, ".")
from harness_skills.dom_snapshot_skill import dom_snapshot_url

url     = "$ARGUMENTS".split()[0]
timeout = 15   # override from --timeout if provided
max_lnk = 15  # override from --max-links if provided

print(dom_snapshot_url(url, timeout=timeout, max_links=max_lnk))
```

**HTML mode** — run the following Python snippet:

```python
import sys, pathlib
sys.path.insert(0, ".")
from harness_skills.dom_snapshot_skill import dom_snapshot_html

# html_string should be set to the raw HTML to inspect
html_string = """PASTE_OR_PIPE_HTML_HERE"""
base_url    = "about:blank"  # set to origin URL when known
max_lnk     = 15

print(dom_snapshot_html(html_string, base_url=base_url, max_links=max_lnk))
```

### Step 3 — Read and interpret the snapshot

The output is structured in labelled sections:

```
### Page Metadata
URL      : https://example.com
Title    : Example Domain
Desc     : This domain is for use in illustrative examples...
Lang     : en

### ARIA Landmarks
  [main] role=main

### Headings
H1: Example Domain

### Navigation Links (3 total)
  'Home' -> https://example.com/
  'Docs' -> https://example.com/docs/
  'Blog' -> https://example.com/blog/

### Forms (1 total)
  FORM id='search' action='/search' method='GET'
    [text] name='q' * label='Search' placeholder='Search docs…'
    Buttons: ['Search']

### Interactive Buttons (2 total)
  [button] 'Open menu'
  [button] 'Close dialog' aria='Close'

### Data Tables (1 total)
  TABLE 'Results' — 42 rows
    Headers: ['Name', 'Status', 'Updated']
    Row: ['alpha', 'passing', '2025-01-10']

### Visible Text (first 1 500 chars)
Example Domain
This domain is for use in illustrative examples in documents…

### Errors / Warnings        ← only present when something went wrong
  ⚠  HTTP 404: Not Found
```

### Step 4 — Summarise findings

After printing the raw snapshot, provide a **3–5 bullet point summary** of the
key UI state findings most relevant to the current task:

- Note which forms are present and their required fields.
- Highlight navigation structure and primary CTAs.
- Flag any errors or accessibility issues (missing alt text, disabled inputs).
- Confirm or refute the expected page state for the current workflow step.

### Step 5 — Decide next action

Based on the snapshot, recommend or take the next action:

- **If a form must be filled**: list the fields and their types.
- **If navigation is needed**: identify the correct link href.
- **If content is missing**: note it and suggest a follow-up check.
- **If errors were reported**: diagnose and propose a retry strategy.

## Output format

Always emit:

1. The raw snapshot block (inside a fenced code block).
2. The **Summary** bullet list.
3. A one-sentence **Next Action** recommendation.

## Notes

- The utility uses `requests` + `BeautifulSoup` — it reads server-rendered
  HTML only.  JavaScript-rendered content that is not present in the initial
  HTML response will not appear in the snapshot.
- For SPA pages, prefer calling after a `snapshot_from_html` with the page
  source captured at the right moment, or combine with a lightweight JS
  evaluation step.
- Cookies / session headers can be injected by passing a custom
  `requests.Session` to `dom_snapshot_url` in Python.
- The `dom_snapshot_utility` package must be importable from the working
  directory (it lives at `dom_snapshot_utility/` in this repo).
