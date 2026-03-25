"""
dom_snapshot_utility/snapshot.py
=================================
Browser-free DOM inspection for agents.

Parses server-rendered HTML (or fetches a URL with ``requests``) and returns a
compact, structured ``DOMSnapshot`` together with a plain-text rendering sized
to fit comfortably inside an LLM context window.

Public helpers
--------------
    snapshot_from_html(html, base_url="about:blank", max_links=15) -> DOMSnapshot
    snapshot_from_url(url, timeout=15, max_links=15)               -> DOMSnapshot
    snapshot_to_text(snap, max_links=15)                           -> str
"""

from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass, field
from typing import List, Optional
from urllib.parse import urljoin

# ---------------------------------------------------------------------------
# Optional runtime dependencies
# ---------------------------------------------------------------------------
try:
    import requests as _requests
    _HAS_REQUESTS = True
except ImportError:  # pragma: no cover
    _HAS_REQUESTS = False

try:
    from bs4 import BeautifulSoup, Tag
    _HAS_BS4 = True
except ImportError:  # pragma: no cover
    _HAS_BS4 = False

# ---------------------------------------------------------------------------
# Data models (plain dataclasses — no Pydantic dependency required)
# ---------------------------------------------------------------------------

@dataclass
class PageMeta:
    url: str = "about:blank"
    title: str = ""
    description: str = ""
    lang: str = ""


@dataclass
class Heading:
    level: int          # 1-6
    text: str


@dataclass
class Link:
    text: str
    href: str


@dataclass
class AriaRegion:
    role: str
    label: str = ""


@dataclass
class Button:
    text: str
    aria_label: str = ""
    disabled: bool = False


@dataclass
class InputField:
    type: str = "text"
    name: str = ""
    label: str = ""
    placeholder: str = ""
    required: bool = False


@dataclass
class Form:
    id: str = ""
    action: str = ""
    method: str = "GET"
    fields: List[InputField] = field(default_factory=list)
    buttons: List[str] = field(default_factory=list)


@dataclass
class TableSnapshot:
    caption: str = ""
    row_count: int = 0
    headers: List[str] = field(default_factory=list)
    sample_rows: List[List[str]] = field(default_factory=list)


@dataclass
class ImageSnapshot:
    src: str = ""
    alt: str = ""
    width: str = ""
    height: str = ""


@dataclass
class DOMSnapshot:
    meta: PageMeta = field(default_factory=PageMeta)
    landmarks: List[AriaRegion] = field(default_factory=list)
    headings: List[Heading] = field(default_factory=list)
    nav_links: List[Link] = field(default_factory=list)
    nav_links_total: int = 0   # total found before max_links truncation
    forms: List[Form] = field(default_factory=list)
    buttons: List[Button] = field(default_factory=list)
    tables: List[TableSnapshot] = field(default_factory=list)
    images: List[ImageSnapshot] = field(default_factory=list)
    visible_text: str = ""
    errors: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_BLOCK_TAGS = {
    "p", "div", "section", "article", "aside", "header", "footer",
    "nav", "main", "h1", "h2", "h3", "h4", "h5", "h6",
    "li", "dt", "dd", "blockquote", "pre", "figure", "figcaption",
    "tr", "th", "td", "caption", "form", "fieldset", "legend",
    "table", "ul", "ol", "dl", "details", "summary",
}

_INVISIBLE_TAGS = {"script", "style", "noscript", "template", "head"}

_MAX_VISIBLE_CHARS = 1_500
_MAX_SAMPLE_ROWS   = 3
_MAX_IMAGES        = 10


def _clean(text: str) -> str:
    """Collapse whitespace and strip."""
    return re.sub(r"\s+", " ", text or "").strip()


def _get_text(el: "Tag") -> str:
    return _clean(el.get_text(" ", strip=True))


def _resolve(href: str, base_url: str) -> str:
    if not href:
        return ""
    return urljoin(base_url, href)


def _attr(el: "Tag", *attrs: str) -> str:
    for a in attrs:
        v = el.get(a, "")
        if isinstance(v, list):
            v = " ".join(v)
        if v:
            return v.strip()
    return ""


def _label_for(input_el: "Tag", soup: "BeautifulSoup") -> str:
    """Try to find a <label> associated with an input element."""
    el_id = input_el.get("id", "")
    if el_id:
        lbl = soup.find("label", attrs={"for": el_id})
        if lbl:
            return _get_text(lbl)
    # Wrapped label
    parent = input_el.find_parent("label")
    if parent:
        # Remove the input text itself
        clone_text = _clean(
            " ".join(
                str(c) for c in parent.children
                if getattr(c, "name", None) not in ("input", "select", "textarea")
            )
        )
        return re.sub(r"<[^>]+>", "", clone_text).strip()
    return _attr(input_el, "aria-label", "title")


# ---------------------------------------------------------------------------
# Core parsing
# ---------------------------------------------------------------------------

def _parse(soup: "BeautifulSoup", base_url: str, max_links: int) -> DOMSnapshot:
    snap = DOMSnapshot()
    snap.meta = _parse_meta(soup, base_url)
    snap.landmarks = _parse_landmarks(soup)
    snap.headings = _parse_headings(soup)
    snap.nav_links, snap.nav_links_total = _parse_nav_links(soup, base_url, max_links)
    snap.forms = _parse_forms(soup, base_url)
    snap.buttons = _parse_buttons(soup)
    snap.tables = _parse_tables(soup)
    snap.images = _parse_images(soup, base_url)
    snap.visible_text = _parse_visible_text(soup)
    return snap


def _parse_meta(soup: "BeautifulSoup", base_url: str) -> PageMeta:
    title_tag = soup.find("title")
    title = _get_text(title_tag) if title_tag else ""

    desc_tag = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
    desc = ""
    if desc_tag:
        desc = _attr(desc_tag, "content")

    html_tag = soup.find("html")
    lang = _attr(html_tag, "lang") if html_tag else ""

    return PageMeta(url=base_url, title=title, description=desc, lang=lang)


def _parse_landmarks(soup: "BeautifulSoup") -> List[AriaRegion]:
    regions: List[AriaRegion] = []
    # Explicit role= attributes
    for el in soup.find_all(attrs={"role": True}):
        role = _attr(el, "role")
        if role:
            label = _attr(el, "aria-label", "aria-labelledby")
            regions.append(AriaRegion(role=role, label=label))
    # Implicit landmark elements
    implicit = {
        "main": "main", "nav": "navigation", "header": "banner",
        "footer": "contentinfo", "aside": "complementary",
        "section": "region", "form": "form",
    }
    for tag, role in implicit.items():
        for el in soup.find_all(tag):
            # Skip if already has role attribute (already captured above)
            if not el.get("role"):
                label = _attr(el, "aria-label", "aria-labelledby")
                regions.append(AriaRegion(role=role, label=label))
    return regions


def _parse_headings(soup: "BeautifulSoup") -> List[Heading]:
    headings = []
    for level in range(1, 7):
        for h in soup.find_all(f"h{level}"):
            txt = _get_text(h)
            if txt:
                headings.append(Heading(level=level, text=txt))
    # Re-sort by document order
    all_tags = soup.find_all(re.compile(r"^h[1-6]$"))
    ordered: List[Heading] = []
    for el in all_tags:
        txt = _get_text(el)
        if txt:
            ordered.append(Heading(level=int(el.name[1]), text=txt))
    return ordered


def _parse_nav_links(
    soup: "BeautifulSoup", base_url: str, max_links: int
) -> "tuple[List[Link], int]":
    """Return (truncated_links, total_found)."""
    all_links: List[Link] = []
    # Prefer links inside <nav>
    for nav in soup.find_all("nav"):
        for a in nav.find_all("a", href=True):
            txt = _get_text(a)
            href = _resolve(_attr(a, "href"), base_url)
            if txt or href:
                all_links.append(Link(text=txt or href, href=href))
    # Fall back to all <a> if no nav links found
    if not all_links:
        for a in soup.find_all("a", href=True):
            txt = _get_text(a)
            href = _resolve(_attr(a, "href"), base_url)
            if txt or href:
                all_links.append(Link(text=txt or href, href=href))
    total = len(all_links)
    return all_links[:max_links], total


def _parse_forms(soup: "BeautifulSoup", base_url: str) -> List[Form]:
    forms = []
    for form_el in soup.find_all("form"):
        f = Form(
            id=_attr(form_el, "id"),
            action=_resolve(_attr(form_el, "action"), base_url),
            method=(_attr(form_el, "method") or "GET").upper(),
        )
        # Fields
        for inp in form_el.find_all(["input", "select", "textarea"]):
            inp_type = _attr(inp, "type") or (
                "select" if inp.name == "select" else
                "textarea" if inp.name == "textarea" else
                "text"
            )
            if inp_type.lower() in ("hidden", "submit", "button", "reset", "image"):
                continue
            field_obj = InputField(
                type=inp_type,
                name=_attr(inp, "name", "id"),
                label=_label_for(inp, soup),
                placeholder=_attr(inp, "placeholder"),
                required=inp.has_attr("required"),
            )
            f.fields.append(field_obj)
        # Buttons
        for btn in form_el.find_all(["button", "input"]):
            btn_type = _attr(btn, "type") or "button"
            if btn.name == "button" or btn_type in ("submit", "button", "reset"):
                txt = _get_text(btn) or _attr(btn, "value") or btn_type
                if txt:
                    f.buttons.append(txt)
        forms.append(f)
    return forms


def _parse_buttons(soup: "BeautifulSoup") -> List[Button]:
    buttons: List[Button] = []
    # Standalone buttons not inside forms
    for btn in soup.find_all("button"):
        if btn.find_parent("form"):
            continue
        txt = _get_text(btn)
        aria = _attr(btn, "aria-label")
        disabled = btn.has_attr("disabled")
        buttons.append(Button(text=txt, aria_label=aria, disabled=disabled))
    # role=button elements
    for el in soup.find_all(attrs={"role": "button"}):
        txt = _get_text(el)
        aria = _attr(el, "aria-label")
        disabled = el.get("aria-disabled", "").lower() == "true"
        buttons.append(Button(text=txt, aria_label=aria, disabled=disabled))
    return buttons


def _parse_tables(soup: "BeautifulSoup") -> List[TableSnapshot]:
    tables = []
    for tbl in soup.find_all("table"):
        ts = TableSnapshot()
        cap = tbl.find("caption")
        if cap:
            ts.caption = _get_text(cap)
        # Headers
        for th in tbl.find_all("th"):
            ts.headers.append(_get_text(th))
        # Rows
        rows = tbl.find_all("tr")
        ts.row_count = len(rows)
        for row in rows[:_MAX_SAMPLE_ROWS]:
            cells = row.find_all(["td", "th"])
            if cells:
                ts.sample_rows.append([_get_text(c) for c in cells])
        tables.append(ts)
    return tables


def _parse_images(soup: "BeautifulSoup", base_url: str) -> List[ImageSnapshot]:
    images = []
    for img in soup.find_all("img")[:_MAX_IMAGES]:
        src = _resolve(_attr(img, "src"), base_url)
        alt = _attr(img, "alt")
        w   = _attr(img, "width")
        h   = _attr(img, "height")
        images.append(ImageSnapshot(src=src, alt=alt, width=w, height=h))
    return images


def _parse_visible_text(soup: "BeautifulSoup") -> str:
    # Work on a shallow copy so decompose() doesn't mutate the caller's tree.
    from copy import copy as _copy
    try:
        import copy as _copy_mod
        working = _copy_mod.copy(soup)
    except Exception:
        working = soup

    # Remove invisible elements before extracting text.
    for tag in list(working.find_all(_INVISIBLE_TAGS)):
        tag.decompose()

    # Use BS4's built-in get_text() — robust across all parser back-ends.
    text = working.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:_MAX_VISIBLE_CHARS]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def snapshot_from_html(
    html: str,
    base_url: str = "about:blank",
    max_links: int = 15,
) -> "DOMSnapshot":
    """Parse *html* string and return a :class:`DOMSnapshot`."""
    if not _HAS_BS4:
        snap = DOMSnapshot()
        snap.errors.append("beautifulsoup4 is not installed — uv add beautifulsoup4 lxml")
        return snap

    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")

    return _parse(soup, base_url, max_links)


def snapshot_from_url(
    url: str,
    timeout: int = 15,
    max_links: int = 15,
) -> "DOMSnapshot":
    """Fetch *url* via HTTP GET and return a :class:`DOMSnapshot`."""
    if not _HAS_REQUESTS:
        snap = DOMSnapshot()
        snap.meta = PageMeta(url=url)
        snap.errors.append("requests is not installed — uv add requests")
        return snap
    if not _HAS_BS4:
        snap = DOMSnapshot()
        snap.meta = PageMeta(url=url)
        snap.errors.append("beautifulsoup4 is not installed — uv add beautifulsoup4 lxml")
        return snap

    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (compatible; dom-snapshot-agent/1.0; "
                "+https://github.com/claw-forge)"
            ),
            "Accept": "text/html,application/xhtml+xml",
        }
        resp = _requests.get(url, timeout=timeout, headers=headers)
        if resp.status_code != 200:
            snap = DOMSnapshot()
            snap.meta = PageMeta(url=url)
            snap.errors.append(f"HTTP {resp.status_code}: {resp.reason}")
            return snap

        encoding = resp.apparent_encoding or "utf-8"
        html = resp.content.decode(encoding, errors="replace")
        snap = snapshot_from_html(html, base_url=url, max_links=max_links)
        snap.meta.url = url          # ensure URL is set to the resolved URL
        return snap

    except Exception as exc:  # noqa: BLE001
        snap = DOMSnapshot()
        snap.meta = PageMeta(url=url)
        snap.errors.append(f"Request failed: {exc}")
        return snap


def snapshot_to_text(snap: "DOMSnapshot", max_links: int = 15) -> str:
    """Render *snap* as a compact, human/LLM-readable text block."""
    lines: List[str] = []

    # ── Page Metadata ──────────────────────────────────────────────────────
    lines.append("### Page Metadata")
    lines.append(f"URL      : {snap.meta.url}")
    if snap.meta.title:
        lines.append(f"Title    : {snap.meta.title}")
    if snap.meta.description:
        lines.append(f"Desc     : {textwrap.shorten(snap.meta.description, 120)}")
    if snap.meta.lang:
        lines.append(f"Lang     : {snap.meta.lang}")

    # ── ARIA Landmarks ─────────────────────────────────────────────────────
    if snap.landmarks:
        lines.append("\n### ARIA Landmarks")
        seen: set = set()
        for lm in snap.landmarks:
            key = (lm.role, lm.label)
            if key in seen:
                continue
            seen.add(key)
            label_str = f" label='{lm.label}'" if lm.label else ""
            lines.append(f"  [{lm.role}] role={lm.role}{label_str}")

    # ── Headings ───────────────────────────────────────────────────────────
    if snap.headings:
        lines.append("\n### Headings")
        for h in snap.headings:
            lines.append(f"H{h.level}: {h.text}")

    # ── Navigation Links ───────────────────────────────────────────────────
    if snap.nav_links:
        total = snap.nav_links_total or len(snap.nav_links)
        shown = snap.nav_links[:max_links]
        lines.append(f"\n### Navigation Links ({total} total)")
        for lnk in shown:
            lines.append(f"  '{lnk.text}' -> {lnk.href}")
        if total > max_links:
            lines.append(f"  … {total - max_links} more links omitted")

    # ── Forms ──────────────────────────────────────────────────────────────
    if snap.forms:
        lines.append(f"\n### Forms ({len(snap.forms)} total)")
        for frm in snap.forms:
            id_str     = f" id='{frm.id}'"     if frm.id     else ""
            action_str = f" action='{frm.action}'" if frm.action else ""
            method_str = f" method='{frm.method}'"
            lines.append(f"  FORM{id_str}{action_str}{method_str}")
            for inp in frm.fields:
                req_str  = " *"            if inp.required     else ""
                lbl_str  = f" label='{inp.label}'"           if inp.label       else ""
                ph_str   = f" placeholder='{inp.placeholder}'" if inp.placeholder else ""
                name_str = f" name='{inp.name}'"             if inp.name        else ""
                lines.append(f"    [{inp.type}]{name_str}{req_str}{lbl_str}{ph_str}")
            if frm.buttons:
                lines.append(f"    Buttons: {frm.buttons}")

    # ── Interactive Buttons ────────────────────────────────────────────────
    if snap.buttons:
        lines.append(f"\n### Interactive Buttons ({len(snap.buttons)} total)")
        for btn in snap.buttons:
            aria_str     = f" aria='{btn.aria_label}'" if btn.aria_label else ""
            disabled_str = " [disabled]"               if btn.disabled   else ""
            lines.append(f"  [button] '{btn.text}'{aria_str}{disabled_str}")

    # ── Data Tables ────────────────────────────────────────────────────────
    if snap.tables:
        lines.append(f"\n### Data Tables ({len(snap.tables)} total)")
        for tbl in snap.tables:
            cap_str = f" '{tbl.caption}'" if tbl.caption else ""
            lines.append(f"  TABLE{cap_str} — {tbl.row_count} rows")
            if tbl.headers:
                lines.append(f"    Headers: {tbl.headers}")
            for row in tbl.sample_rows[:_MAX_SAMPLE_ROWS]:
                lines.append(f"    Row: {row}")

    # ── Images ─────────────────────────────────────────────────────────────
    if snap.images:
        lines.append(f"\n### Images ({len(snap.images)} total)")
        for img in snap.images:
            alt_str = f" alt='{img.alt}'" if img.alt else " [no alt]"
            dim_str = f" ({img.width}×{img.height})" if img.width and img.height else ""
            lines.append(f"  <img>{alt_str}{dim_str} src={img.src}")

    # ── Visible Text ───────────────────────────────────────────────────────
    if snap.visible_text:
        lines.append(f"\n### Visible Text (first {_MAX_VISIBLE_CHARS} chars)")
        lines.append(snap.visible_text)

    # ── Errors / Warnings ──────────────────────────────────────────────────
    if snap.errors:
        lines.append("\n### Errors / Warnings")
        for err in snap.errors:
            lines.append(f"  ⚠  {err}")

    return "\n".join(lines)
