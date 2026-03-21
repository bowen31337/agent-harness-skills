#!/usr/bin/env python3
"""
snapshot_dom.py — Standalone CLI helper for the dom-snapshot skill.

Fetches a URL (or reads raw HTML from a file / stdin) and prints a compact,
structured text snapshot of the page's DOM — no browser required.

This script adds the project root to sys.path automatically so it can be run
from any working directory without installing the package.

Usage
-----
# Snapshot a live URL:
    python skills/dom-snapshot/scripts/snapshot_dom.py https://example.com

# Snapshot with a longer timeout and more links:
    python skills/dom-snapshot/scripts/snapshot_dom.py \\
        https://example.com --timeout 30 --max-links 25

# Pass raw HTML from a file (use the filename as the positional argument):
    python skills/dom-snapshot/scripts/snapshot_dom.py --html page.html

# Pass raw HTML from stdin (use '-' as the filename):
    curl -s https://example.com | \\
        python skills/dom-snapshot/scripts/snapshot_dom.py --html -

# Provide a base URL when snapshotting raw HTML so relative links resolve:
    python skills/dom-snapshot/scripts/snapshot_dom.py \\
        --html page.html --base-url https://example.com
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure the project root is importable regardless of CWD.
# ---------------------------------------------------------------------------

_SCRIPT_DIR   = Path(__file__).resolve().parent   # scripts/
_SKILL_DIR    = _SCRIPT_DIR.parent                # dom-snapshot/
_SKILLS_DIR   = _SKILL_DIR.parent                 # skills/
_PROJECT_ROOT = _SKILLS_DIR.parent                # repo root

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Imports (deferred so the path fix above takes effect first).
# ---------------------------------------------------------------------------

from harness_skills.dom_snapshot_skill import (   # noqa: E402
    dom_snapshot_html,
    dom_snapshot_url,
)


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="snapshot_dom.py",
        description=(
            "DOM Snapshot — inspect page structure without a browser.\n\n"
            "Fetches a URL or parses raw HTML and prints a compact structured\n"
            "text snapshot: metadata, ARIA landmarks, headings, navigation,\n"
            "forms, buttons, tables, images, and visible body text."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "target",
        metavar="url-or-file",
        help=(
            "A URL to fetch (must start with http:// or https://) "
            "OR, when --html is set, a path to an HTML file or '-' to read from stdin."
        ),
    )
    parser.add_argument(
        "--html",
        action="store_true",
        default=False,
        help=(
            "Treat the positional argument as a path to a raw HTML file "
            "(use '-' to read from stdin) instead of a URL to fetch."
        ),
    )
    parser.add_argument(
        "--base-url",
        metavar="URL",
        default="about:blank",
        dest="base_url",
        help=(
            "Base URL used to resolve relative href/src attributes when "
            "--html mode is active (default: about:blank)."
        ),
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=15,
        metavar="N",
        help="HTTP request timeout in seconds, URL mode only (default: 15).",
    )
    parser.add_argument(
        "--max-links",
        type=int,
        default=15,
        dest="max_links",
        metavar="N",
        help="Maximum navigation links shown in the snapshot (default: 15).",
    )
    return parser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_html(target: str) -> str:
    """Read HTML from *target* (file path or '-' for stdin)."""
    if target == "-":
        return sys.stdin.read()
    path = Path(target)
    if not path.exists():
        print(f"error: file not found: {target}", file=sys.stderr)
        sys.exit(1)
    return path.read_text(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.html:
        html = _read_html(args.target)
        output = dom_snapshot_html(
            html,
            base_url=args.base_url,
            max_links=args.max_links,
        )
    else:
        target = args.target
        if not (target.startswith("http://") or target.startswith("https://")):
            # Give a helpful hint if the user forgot the scheme.
            print(
                f"warning: '{target}' does not look like a URL — "
                "did you mean to pass --html?",
                file=sys.stderr,
            )
        output = dom_snapshot_url(
            target,
            timeout=args.timeout,
            max_links=args.max_links,
        )

    print(output)


if __name__ == "__main__":
    main()
