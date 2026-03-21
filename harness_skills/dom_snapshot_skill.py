"""
harness_skills/dom_snapshot_skill.py
=====================================
Skill wrapper — exposes ``dom_snapshot_url`` and ``dom_snapshot_html`` so that
agent harnesses can inspect UI state without spinning up a full browser session.

Under the hood this delegates to ``dom_snapshot_utility``, which uses
``requests`` + ``BeautifulSoup`` to parse server-rendered HTML.

Usage (programmatic)
--------------------
    from harness_skills.dom_snapshot_skill import dom_snapshot_url, dom_snapshot_html

    # Fetch and snapshot a live URL
    print(dom_snapshot_url("https://example.com"))

    # Snapshot a raw HTML string you already have in memory
    html = "<html><body><h1>Hello</h1></body></html>"
    print(dom_snapshot_html(html, base_url="https://example.com"))

Usage (CLI / agent snippet)
---------------------------
    import sys
    sys.path.insert(0, ".")
    from harness_skills.dom_snapshot_skill import dom_snapshot_url
    print(dom_snapshot_url("https://example.com", timeout=15, max_links=15))

Return value
------------
Both functions return a single string — the compact text snapshot produced by
``dom_snapshot_utility.snapshot_to_text``.  The snapshot contains labelled
sections: Page Metadata, ARIA Landmarks, Headings, Navigation Links, Forms,
Interactive Buttons, Data Tables, Images, Visible Text, and (if any)
Errors / Warnings.

Notes
-----
- Only server-rendered HTML is visible.  JavaScript-rendered content that is
  absent from the initial HTTP response will *not* appear in the snapshot.
- For SPA pages pass the already-captured page source to ``dom_snapshot_html``.
- Cookies / session headers can be injected by using
  ``dom_snapshot_utility.snapshot_from_url`` directly with a custom
  ``requests.Session``.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the sibling ``dom_snapshot_utility`` package importable when this file
# is executed from the repo root (``python -m harness_skills.dom_snapshot_skill``)
# or via ``sys.path.insert(0, ".")``.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from dom_snapshot_utility import snapshot_from_html, snapshot_from_url, snapshot_to_text


# ---------------------------------------------------------------------------
# Public skill functions
# ---------------------------------------------------------------------------

def dom_snapshot_url(
    url: str,
    timeout: int = 15,
    max_links: int = 15,
) -> str:
    """Fetch *url* and return a compact text snapshot of the page.

    Parameters
    ----------
    url:
        The fully-qualified URL to fetch (must start with ``http://`` or
        ``https://``).
    timeout:
        HTTP request timeout in seconds (default ``15``).
    max_links:
        Maximum number of navigation links to include in the output
        (default ``15``).

    Returns
    -------
    str
        A multi-section text block describing the page structure and content.
    """
    snap = snapshot_from_url(url, timeout=timeout, max_links=max_links)
    return snapshot_to_text(snap, max_links=max_links)


def dom_snapshot_html(
    html: str,
    base_url: str = "about:blank",
    max_links: int = 15,
) -> str:
    """Parse raw *html* and return a compact text snapshot.

    Parameters
    ----------
    html:
        Raw HTML string to parse.
    base_url:
        Origin URL used to resolve relative ``href`` / ``src`` attributes.
        Set this to the page's real URL when known (default ``"about:blank"``).
    max_links:
        Maximum number of navigation links to include in the output
        (default ``15``).

    Returns
    -------
    str
        A multi-section text block describing the page structure and content.
    """
    snap = snapshot_from_html(html, base_url=base_url, max_links=max_links)
    return snapshot_to_text(snap, max_links=max_links)


# ---------------------------------------------------------------------------
# CLI entry point (convenience — mirrors the skill doc's usage snippets)
# ---------------------------------------------------------------------------

def _main() -> None:  # pragma: no cover
    import argparse

    parser = argparse.ArgumentParser(
        description="DOM Snapshot — inspect page structure without a browser.",
    )
    parser.add_argument(
        "url_or_html",
        metavar="url-or-keyword",
        help="A URL to fetch, or 'html' when --html is supplied.",
    )
    parser.add_argument(
        "--html",
        action="store_true",
        help="Treat the positional argument as raw HTML input.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=15,
        metavar="N",
        help="HTTP request timeout in seconds (default: 15).",
    )
    parser.add_argument(
        "--max-links",
        type=int,
        default=15,
        dest="max_links",
        metavar="N",
        help="Maximum links shown per section (default: 15).",
    )
    args = parser.parse_args()

    if args.html:
        print(dom_snapshot_html(args.url_or_html, max_links=args.max_links))
    else:
        print(dom_snapshot_url(args.url_or_html, timeout=args.timeout, max_links=args.max_links))


if __name__ == "__main__":
    _main()
