"""harness screenshot — capture application state as a visual artifact.

Exit codes:
    0  Screenshot captured or list printed.
    1  Capture failed (Playwright not installed or URL unreachable).
    2  Internal error.
"""

from __future__ import annotations

import base64
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import click

from harness_skills.cli.fmt import output_format_option, resolve_output_format
from harness_skills.models.base import Status
from harness_skills.models.screenshot import ScreenshotResponse


def _iso_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="milliseconds")


@click.command("screenshot")
@click.option("--url", default="http://localhost:3000", help="URL to capture.")
@click.option("--label", default=None, help="Label for the screenshot filename.")
@click.option(
    "--out",
    type=click.Path(file_okay=False),
    default="screenshots",
    help="Output directory.",
)
@click.option("--width", type=int, default=1280, help="Viewport width.")
@click.option("--height", type=int, default=800, help="Viewport height.")
@click.option("--base64", "emit_base64", is_flag=True, default=False, help="Emit base64 data.")
@click.option("--list", "list_existing", is_flag=True, default=False, help="List existing screenshots.")
@output_format_option()
def screenshot_cmd(
    url: str,
    label: str | None,
    out: str,
    width: int,
    height: int,
    emit_base64: bool,
    list_existing: bool,
    output_format: str | None,
) -> None:
    """Capture application state as a screenshot."""
    fmt = resolve_output_format(output_format)
    out_dir = Path(out)

    try:
        if list_existing:
            out_dir.mkdir(parents=True, exist_ok=True)
            files = sorted(
                str(f.relative_to(out_dir))
                for f in out_dir.rglob("*.png")
            )
            resp = ScreenshotResponse(
                status=Status.PASSED,
                timestamp=_iso_now(),
                message=f"Found {len(files)} screenshot(s).",
                existing_screenshots=files,
            )
            if fmt == "json":
                click.echo(json.dumps(resp.model_dump(), indent=2))
            else:
                if files:
                    for f in files:
                        click.echo(f)
                else:
                    click.echo("No screenshots found.")
            sys.exit(0)

        # Capture mode — lazy import playwright
        try:
            from playwright.sync_api import sync_playwright  # noqa: PLC0415
        except ImportError:
            resp = ScreenshotResponse(
                status=Status.FAILED,
                timestamp=_iso_now(),
                message="Playwright not installed. Run: uv add playwright && playwright install chromium",
            )
            if fmt == "json":
                click.echo(json.dumps(resp.model_dump(), indent=2))
            else:
                click.echo(f"ERROR: {resp.message}", err=True)
            sys.exit(1)

        out_dir.mkdir(parents=True, exist_ok=True)
        tag = label or "screenshot"
        ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d-%H%M%S")
        filename = f"{tag}-{ts}.png"
        filepath = out_dir / filename

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": width, "height": height})
            page.goto(url, wait_until="networkidle")
            page.screenshot(path=str(filepath))
            browser.close()

        b64_data = None
        if emit_base64:
            b64_data = base64.b64encode(filepath.read_bytes()).decode()

        resp = ScreenshotResponse(
            status=Status.PASSED,
            timestamp=_iso_now(),
            message=f"Screenshot saved to {filepath}.",
            file_path=str(filepath),
            dimensions=f"{width}x{height}",
            base64_data=b64_data,
        )

    except Exception:
        traceback.print_exc()
        resp = ScreenshotResponse(
            status=Status.FAILED,
            timestamp=_iso_now(),
            message="Internal error capturing screenshot.",
        )
        if fmt == "json":
            click.echo(json.dumps(resp.model_dump(), indent=2))
        else:
            click.echo(f"ERROR: {resp.message}", err=True)
        sys.exit(2)

    if fmt == "json":
        click.echo(json.dumps(resp.model_dump(), indent=2))
    else:
        click.echo(f"Saved: {resp.file_path}")
        if resp.dimensions:
            click.echo(f"Dimensions: {resp.dimensions}")

    sys.exit(0)
