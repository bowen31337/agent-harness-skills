# ADR-0001: Adopt Playwright for Browser / E2E Testing

> **Status:** Accepted
> **Date:** 2026-03-20
> **Deciders:** agent-harness-skills maintainers
> **Tags:** testing, browser, e2e, infrastructure

---

## Context

The harness needs an automated way to verify UI and end-to-end flows in addition to unit and integration tests.
We evaluated several Python-compatible browser automation frameworks.
Key requirements:

- Supports Chromium, Firefox, and WebKit from a single API.
- Async-first design compatible with `anyio`.
- Active maintenance and strong community.
- Works inside CI (headless) without extra config.

## Decision

We will use **Playwright** (via `pytest-playwright`) as the primary browser automation framework for all E2E and browser-layer tests under `tests/browser/`.

## Alternatives Considered

### Option A — Selenium + WebDriver

**Description:** Industry-standard protocol wrapping browser drivers (chromedriver, geckodriver).

**Pros:**
- Very mature ecosystem.
- Large talent pool familiar with the API.

**Cons:**
- Requires managing driver binaries separately (or `webdriver-manager`).
- Slower due to HTTP round-trips for each command.
- No built-in auto-wait; flaky tests common without explicit waits.

**Why rejected:** Higher maintenance burden and inherent flakiness compared to Playwright's auto-waiting model.

---

### Option B — Playwright *(chosen)*

**Description:** Microsoft's modern browser automation library that controls Chromium, Firefox, and WebKit through a single protocol.

**Pros:**
- Auto-waiting on elements eliminates most timing issues.
- Native `async`/`await` with `anyio` compatibility.
- `pytest-playwright` plugin provides fixtures out of the box.
- `--headed` flag makes local debugging straightforward.
- Browser binaries managed via `playwright install`.

**Cons:**
- Heavier initial install (browser binaries ~200 MB each).
- Smaller community than Selenium, though growing rapidly.

---

### Option C — Cypress (via Node.js bridge)

**Description:** Popular JavaScript-native E2E framework.

**Pros:**
- Excellent developer experience for JS-heavy teams.
- Built-in video recording and time-travel debugging.

**Cons:**
- Requires a Node.js runtime alongside Python; adds complexity.
- Python interop is unofficial and awkward.
- Out of scope for a Python-first project.

**Why rejected:** Language mismatch and added toolchain complexity.

## Consequences

**Positive:**
- Consistent cross-browser coverage (Chromium, Firefox, WebKit) from one test suite.
- `pytest-playwright` integrates naturally with existing `pytest` config in `conftest.py`.
- Headed mode (`--headed`) makes debugging locally painless.

**Negative / Trade-offs:**
- CI image must run `playwright install --with-deps` on first setup, adding ~1 min to cold builds.
- Team must learn Playwright's page/locator model if coming from Selenium.

**Neutral:**
- All browser tests live under `tests/browser/` to keep them isolated from unit tests.

## Implementation Notes

- Install: `uv add pytest-playwright && playwright install chromium`
- CI: add `playwright install --with-deps chromium` as a `before_script` step in `.gitlab-ci.yml`.
- Fixtures provided by `conftest.py` (`page`, `browser`, `context`).
- Use `BASE_URL` env var to target different environments:
  ```bash
  BASE_URL=https://staging.example.com pytest tests/browser/ -v
  ```

## References

- [Playwright Python docs](https://playwright.dev/python/)
- [pytest-playwright](https://pypi.org/project/pytest-playwright/)
- [Project CLAUDE.md](../../CLAUDE.md)
