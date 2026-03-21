#!/usr/bin/env python3
"""
capture_screenshot.py — Standalone CLI helper for the harness:screenshot skill.

Captures a browser page, desktop, or terminal output as a timestamped PNG
artifact.  Runs without installing the full harness package by adding the
project root to sys.path automatically.

Backends (auto-selected, first available wins):
  - playwright  →  browser / URL captures   (pip install playwright)
  - pillow      →  desktop / window captures (pip install Pillow)
  - terminal    →  terminal-to-image         (pip install Pillow pyte)

Usage
-----
# Capture a URL to the default output directory:
    python skills/screenshot/scripts/capture_screenshot.py \\
        --url http://localhost:3000

# Capture with a label and a custom output directory:
    python skills/screenshot/scripts/capture_screenshot.py \\
        --url http://localhost:3000 \\
        --label "home-after-refactor" \\
        --out .artifacts/screenshots/

# Capture the full desktop:
    python skills/screenshot/scripts/capture_screenshot.py \\
        --desktop

# Capture a specific viewport size and wait for a selector:
    python skills/screenshot/scripts/capture_screenshot.py \\
        --url http://localhost:3000 \\
        --width 1280 --height 800 \\
        --wait-for "#app.ready"

# Print base64-encoded PNG to stdout (no file written):
    python skills/screenshot/scripts/capture_screenshot.py \\
        --url http://localhost:3000 \\
        --base64

# List existing artifacts in the output directory:
    python skills/screenshot/scripts/capture_screenshot.py \\
        --list \\
        --out .artifacts/screenshots/
"""

from __future__ import annotations

import argparse
import base64
import datetime
import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure project root is importable regardless of CWD.
# ---------------------------------------------------------------------------

_SCRIPT_DIR   = Path(__file__).resolve().parent   # scripts/
_SKILL_DIR    = _SCRIPT_DIR.parent                # screenshot/
_SKILLS_DIR   = _SKILL_DIR.parent                 # skills/
_PROJECT_ROOT = _SKILLS_DIR.parent                # repo root

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Backend probe helpers (no hard deps at module level)
# ---------------------------------------------------------------------------

def _has_playwright() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


def _has_pillow() -> bool:
    try:
        from PIL import ImageGrab  # noqa: F401
        return True
    except ImportError:
        return False


def _has_pyte() -> bool:
    try:
        import pyte  # noqa: F401
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Core capture functions (inline — no package install required)
# ---------------------------------------------------------------------------

_DEFAULT_OUT = Path(".artifacts") / "screenshots"


def _make_filename(label: str, ext: str = "png") -> str:
    ts = datetime.datetime.now(tz=datetime.timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    safe_label = label.replace(" ", "-").replace("/", "-")
    return f"{safe_label}_{ts}.{ext}"


def capture_url_playwright(
    url: str,
    out_path: Path | None,
    width: int,
    height: int,
    wait_for: str | None,
    full_page: bool,
) -> bytes:
    """Capture *url* using Playwright (Chromium headless) and return PNG bytes."""
    from playwright.sync_api import sync_playwright  # type: ignore

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        page.goto(url, wait_until="networkidle")
        if wait_for:
            page.wait_for_selector(wait_for, state="visible", timeout=15_000)
        png_bytes = page.screenshot(full_page=full_page)
        browser.close()
    return png_bytes


def capture_desktop_pillow() -> bytes:
    """Capture the full desktop using Pillow and return PNG bytes."""
    from PIL import ImageGrab  # type: ignore
    import io

    img = ImageGrab.grab()
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def capture_window_pillow(title_substr: str) -> bytes:
    """Capture a window whose title contains *title_substr* and return PNG bytes."""
    import io

    try:
        import pygetwindow as gw  # type: ignore
        from PIL import ImageGrab

        wins = gw.getWindowsWithTitle(title_substr)
        if not wins:
            raise RuntimeError(f"No window found with title containing '{title_substr}'")
        win = wins[0]
        bbox = (win.left, win.top, win.right, win.bottom)
        img = ImageGrab.grab(bbox=bbox)
    except ImportError:
        # Fallback: full desktop
        from PIL import ImageGrab
        img = ImageGrab.grab()

    buf = __import__("io").BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _save(png_bytes: bytes, out_dir: Path, filename: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / filename
    dest.write_bytes(png_bytes)
    return dest


def _metadata_record(
    path: Path | None,
    filename: str,
    label: str,
    backend: str,
    size_bytes: int,
    extra: dict | None = None,
) -> dict:
    return {
        "filename": filename,
        "path": str(path) if path else None,
        "label": label,
        "timestamp": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        "size_bytes": size_bytes,
        "backend": backend,
        **(extra or {}),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="capture_screenshot",
        description="Capture application state as a visual PNG artifact.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # --- Source ---
    src = p.add_mutually_exclusive_group()
    src.add_argument(
        "--url",
        metavar="URL",
        help="URL to load in a headless browser and screenshot (requires playwright).",
    )
    src.add_argument(
        "--desktop",
        action="store_true",
        help="Capture the full desktop (requires Pillow + platform grab support).",
    )
    src.add_argument(
        "--window",
        metavar="TITLE",
        help="Capture a specific window by title substring (requires Pillow + pygetwindow).",
    )

    # --- Output ---
    p.add_argument(
        "--out",
        metavar="DIR",
        default=str(_DEFAULT_OUT),
        help=f"Output directory for PNG artifacts (default: {_DEFAULT_OUT}).",
    )
    p.add_argument(
        "--label",
        metavar="TEXT",
        default="screenshot",
        help="Human-readable label embedded in the filename and metadata (default: screenshot).",
    )
    p.add_argument(
        "--base64",
        action="store_true",
        help="Print the PNG as a base64-encoded string to stdout instead of writing a file.",
    )
    p.add_argument(
        "--json",
        action="store_true",
        dest="json_out",
        help="Print artifact metadata as JSON to stdout after saving (or instead of, with --base64).",
    )

    # --- Browser options ---
    p.add_argument("--width",    type=int, default=1280, metavar="PX", help="Viewport width in pixels (default: 1280).")
    p.add_argument("--height",   type=int, default=800,  metavar="PX", help="Viewport height in pixels (default: 800).")
    p.add_argument("--wait-for", metavar="SELECTOR",     help="CSS selector to wait for before capturing (browser only).")
    p.add_argument("--full-page", action="store_true",   help="Capture the full scrollable page, not just the viewport (browser only).")

    # --- Utility ---
    p.add_argument(
        "--list",
        action="store_true",
        help="List existing PNG artifacts in --out directory and exit.",
    )
    p.add_argument(
        "--backends",
        action="store_true",
        help="Print available backends and exit.",
    )

    return p


def _print_backends() -> None:
    print(f"playwright : {'✓ available' if _has_playwright() else '✗ not installed  (pip install playwright && playwright install chromium)'}")
    print(f"pillow     : {'✓ available' if _has_pillow()     else '✗ not installed  (pip install Pillow)'}")
    print(f"pyte       : {'✓ available' if _has_pyte()       else '✗ not installed  (pip install pyte)'}")


def _list_artifacts(out_dir: Path) -> None:
    pngs = sorted(out_dir.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not pngs:
        print(f"(no PNG artifacts found in {out_dir})")
        return
    col = max(len(p.name) for p in pngs) + 2
    print(f"{'Filename':<{col}}  {'Size':>10}  {'Modified (UTC)'}")
    print("─" * (col + 30))
    for p in pngs:
        st = p.stat()
        mtime = datetime.datetime.utcfromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        print(f"{p.name:<{col}}  {st.st_size:>9,}B  {mtime}")


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    # ── Utility modes ──────────────────────────────────────────────────────
    if args.backends:
        _print_backends()
        return

    out_dir = Path(args.out)

    if args.list:
        _list_artifacts(out_dir)
        return

    # ── Require at least one source ────────────────────────────────────────
    if not args.url and not args.desktop and not args.window:
        parser.error("Specify a capture source: --url URL, --desktop, or --window TITLE")

    # ── Capture ────────────────────────────────────────────────────────────
    png_bytes: bytes
    backend: str
    extra_meta: dict = {}

    if args.url:
        if not _has_playwright():
            print(
                "[capture_screenshot] ERROR: 'playwright' is not installed.\n"
                "  pip install playwright && playwright install chromium",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"[capture_screenshot] Capturing {args.url} …", file=sys.stderr)
        png_bytes = capture_url_playwright(
            url=args.url,
            out_path=None,
            width=args.width,
            height=args.height,
            wait_for=args.wait_for,
            full_page=args.full_page,
        )
        backend = "playwright"
        extra_meta = {"url": args.url, "viewport": {"width": args.width, "height": args.height}}

    elif args.desktop:
        if not _has_pillow():
            print(
                "[capture_screenshot] ERROR: 'Pillow' is not installed.\n"
                "  pip install Pillow",
                file=sys.stderr,
            )
            sys.exit(1)
        print("[capture_screenshot] Capturing full desktop …", file=sys.stderr)
        png_bytes = capture_desktop_pillow()
        backend = "pillow"
        extra_meta = {"source": "desktop"}

    else:  # --window
        if not _has_pillow():
            print(
                "[capture_screenshot] ERROR: 'Pillow' is not installed.\n"
                "  pip install Pillow",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"[capture_screenshot] Capturing window '{args.window}' …", file=sys.stderr)
        png_bytes = capture_window_pillow(args.window)
        backend = "pillow"
        extra_meta = {"source": "window", "window_title": args.window}

    filename = _make_filename(args.label)

    # ── Output ─────────────────────────────────────────────────────────────
    if args.base64:
        b64 = base64.b64encode(png_bytes).decode()
        if args.json_out:
            record = _metadata_record(
                path=None,
                filename=filename,
                label=args.label,
                backend=backend,
                size_bytes=len(png_bytes),
                extra={**extra_meta, "base64": b64},
            )
            print(json.dumps(record, indent=2))
        else:
            print(b64)
        return

    dest = _save(png_bytes, out_dir, filename)
    size = dest.stat().st_size
    print(f"[capture_screenshot] Saved → {dest}  ({size:,} bytes)", file=sys.stderr)

    if args.json_out:
        record = _metadata_record(
            path=dest,
            filename=filename,
            label=args.label,
            backend=backend,
            size_bytes=size,
            extra=extra_meta,
        )
        print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
