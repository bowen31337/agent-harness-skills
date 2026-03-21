"""Reusable screenshot utility for agent-driven browser tests."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Page

SCREENSHOT_DIR = Path(os.getenv("SCREENSHOT_DIR", "screenshots"))


def capture_screenshot(page: Page, label: str) -> Path:
    """Capture a full-page screenshot; return the file path.

    Args:
        page:  An active Playwright Page object.
        label: A short, meaningful name for the screenshot (e.g. ``"login-form"``).

    Returns:
        The :class:`Path` to the saved PNG file.
    """
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    filepath = SCREENSHOT_DIR / f"{label}-{timestamp}.png"
    page.screenshot(path=str(filepath), full_page=True)
    print(f"[screenshot] {filepath}")
    return filepath


def visit_and_capture(page: Page, url: str, label: str) -> Path:
    """Navigate to *url*, wait for load, then capture a screenshot.

    Args:
        page:  An active Playwright Page object.
        url:   Absolute or relative URL to visit.
        label: A short, meaningful name for the screenshot.

    Returns:
        The :class:`Path` to the saved PNG file.
    """
    page.goto(url, wait_until="networkidle")
    return capture_screenshot(page, label)
