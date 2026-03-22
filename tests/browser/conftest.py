"""Pytest-playwright fixtures for browser tests.

This conftest wires up the pytest-playwright plugin so that:
  - All ``page`` fixtures use Chromium by default.
  - The ``base_url`` respects the ``BASE_URL`` environment variable.
  - Every page opens at a consistent 1280×800 viewport.
  - Failed tests automatically capture a screenshot.

Agents that use the pytest-playwright ``page`` fixture get all of the
above for free; agents that use :class:`~tests.browser.agent_driver.AgentDriver`
directly do not need this file.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Page


# ---------------------------------------------------------------------------
# Session-scoped fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def base_url() -> str:  # noqa: D401
    """Base URL used by pytest-playwright's built-in ``page`` fixture.

    Override by setting the ``BASE_URL`` environment variable, e.g.::

        BASE_URL=https://staging.example.com pytest tests/browser/ -v
    """
    return os.getenv("BASE_URL", "http://localhost:3000")


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args: dict[str, Any]) -> dict[str, Any]:
    """Extend the default browser context with project-wide defaults."""
    return {
        **browser_context_args,
        "viewport": {"width": 1280, "height": 800},
    }


# ---------------------------------------------------------------------------
# Per-test screenshot-on-failure
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def screenshot_on_failure(page: Page, request: pytest.FixtureRequest) -> None:
    """Automatically capture a screenshot when a test fails.

    The PNG is written to ``screenshots/failures/<test-name>.png`` so it
    can be attached to CI artefacts or inspected locally.
    """
    yield
    if request.node.rep_call.failed if hasattr(request.node, "rep_call") else False:
        screenshot_dir = Path(os.getenv("SCREENSHOT_DIR", "screenshots")) / "failures"
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        safe_name = request.node.nodeid.replace("/", "_").replace("::", "__")
        filepath = screenshot_dir / f"{safe_name}.png"
        page.screenshot(path=str(filepath), full_page=True)
        print(f"\n[screenshot-on-failure] {filepath}")


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo) -> None:  # type: ignore[override]
    """Attach the call outcome to the request node for use in fixtures."""
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)
