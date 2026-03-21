"""High-level browser driver for claw-forge agents.

Agents should use :class:`AgentDriver` as their entry point for all
browser interactions.  The class wraps Playwright's sync API and
provides a concise interface for navigation, interaction, and
screenshot capture.

Example usage::

    from tests.browser.agent_driver import AgentDriver

    with AgentDriver.launch() as driver:
        page = driver.new_page()
        page.goto("/dashboard")
        driver.screenshot(page, "dashboard")
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from .screenshot_helper import capture_screenshot


class AgentDriver:
    """Thin wrapper around Playwright for agent-driven UI sessions.

    Manages browser lifecycle (launch → context → pages → close) and
    exposes helper methods that agents commonly need.

    Prefer using the context-manager form so the browser is always
    closed cleanly, even on failure::

        with AgentDriver.launch() as driver:
            page = driver.new_page()
            page.goto("/")
            driver.screenshot(page, "home")

    You can also manage the lifecycle manually::

        driver = AgentDriver.launch()
        try:
            ...
        finally:
            driver.close()
    """

    def __init__(self, browser: Browser, context: BrowserContext) -> None:
        self._browser = browser
        self._context = context

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def launch(
        cls,
        headless: bool = True,
        base_url: Optional[str] = None,
        record_video: bool = False,
    ) -> "AgentDriver":
        """Launch a Chromium browser and return an :class:`AgentDriver`.

        Args:
            headless:     Run headless (default ``True``).  Pass
                          ``False`` for local debugging.
            base_url:     Base URL prepended to relative ``goto()`` calls.
                          Defaults to the ``BASE_URL`` env var or
                          ``http://localhost:3000``.
            record_video: Save video of the session to ``./videos/``
                          (useful for CI post-mortems).
        """
        pw = sync_playwright().start()
        browser: Browser = pw.chromium.launch(headless=headless)

        video_opts = {"dir": "videos"} if record_video else None
        context: BrowserContext = browser.new_context(
            base_url=base_url or os.getenv("BASE_URL", "http://localhost:3000"),
            viewport={"width": 1280, "height": 800},
            record_video=video_opts,  # type: ignore[arg-type]
        )
        return cls(browser, context)

    # ------------------------------------------------------------------
    # Page management
    # ------------------------------------------------------------------

    def new_page(self) -> Page:
        """Open a new browser tab and return the :class:`Page`."""
        return self._context.new_page()

    # ------------------------------------------------------------------
    # Screenshot helpers
    # ------------------------------------------------------------------

    def screenshot(self, page: Page, label: str) -> Path:
        """Capture a full-page screenshot.

        Args:
            page:  The :class:`Page` to capture.
            label: Short descriptive name used in the filename.

        Returns:
            :class:`Path` to the saved PNG.
        """
        return capture_screenshot(page, label)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the browser context and the underlying browser process."""
        self._context.close()
        self._browser.close()

    def __enter__(self) -> "AgentDriver":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
