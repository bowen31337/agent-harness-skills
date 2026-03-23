# AGENTS.md — dom_snapshot_utility

## Purpose

Browser-free DOM inspection package. Provides structured snapshots of HTML pages (from a URL or raw HTML string) without launching a browser. Built on `requests` + `BeautifulSoup4` + `lxml`. Consumed by `harness_skills.dom_snapshot_skill` as a façade; agent tasks should call the façade, not this package directly.

---

## Key Files

| File | Key Exports | Description |
|------|------------|-------------|
| `snapshot.py` | `DOMSnapshot`, `snapshot_from_html`, `snapshot_from_url`, `snapshot_to_text` | Core snapshot data class and factory functions |
| `models.py` | `PageMeta`, `Heading`, `Link`, `Button`, `Form`, `AriaRegion`, `TableSnapshot` | Structured sub-components of a DOM snapshot |
| `__init__.py` | All of the above | Public API surface |

---

## Internal Patterns

- **Two entry-points** — `snapshot_from_url(url)` fetches then parses; `snapshot_from_html(html_str)` parses raw HTML; both return a `DOMSnapshot`.
- **`snapshot_to_text(snapshot)`** — serialises a `DOMSnapshot` to a human-readable text representation suitable for agent context consumption.
- **BeautifulSoup + lxml parser** — always use `lxml` as the parser (`BeautifulSoup(html, "lxml")`); `html.parser` is slower and less spec-compliant.
- **Pydantic models** — all sub-components are Pydantic v2 models; callers can call `.model_dump()` for JSON serialisation.
- **No JavaScript execution** — this package cannot handle JS-rendered pages; for those, use the Playwright-backed `screenshot` skill or `AgentDriver`.
- **Stateless** — no persistent state; each call to `snapshot_from_*` creates a fresh `DOMSnapshot`.

---

## Domain-Specific Constraints

- **No dependencies on `harness_skills`** — `dom_snapshot_utility` is a standalone package; it must never import from `harness_skills` or `skills/`.
- **`snapshot_from_url` respects `requests` timeout** — always pass a `timeout` argument (default 10 s); never allow an unbounded network call.
- **Static pages only** — document in any PR touching this package that JS-rendered content will not be captured; direct callers to the `screenshot` skill if JS is needed.
- **`lxml` is a hard dependency** — if `lxml` is unavailable, raise `ImportError` with a clear message; do not silently fall back to `html.parser`.
- **Package is a dependency of `harness_skills`, not the reverse** — changes here may break the façade; run `pytest tests/test_dom_snapshot*.py` after any modification.
