"""
tests/test_dom_snapshot.py
==========================
Unit tests for:
  - dom_snapshot_utility.snapshot  (core parsing)
  - harness_skills.dom_snapshot_skill  (skill wrapper)

All tests run without network access — URL-fetching is mocked where needed.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure repo root is on path so both packages are importable.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dom_snapshot_utility.snapshot import (
    DOMSnapshot,
    Form,
    Heading,
    InputField,
    Link,
    PageMeta,
    snapshot_from_html,
    snapshot_from_url,
    snapshot_to_text,
)
from harness_skills.dom_snapshot_skill import dom_snapshot_html, dom_snapshot_url


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

SIMPLE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <title>Test Page</title>
  <meta name="description" content="A simple test page.">
</head>
<body>
  <nav aria-label="Main navigation">
    <a href="/home">Home</a>
    <a href="/about">About</a>
  </nav>
  <main>
    <h1>Hello World</h1>
    <h2>Sub-heading</h2>
    <p>Visible paragraph text.</p>
    <form id="search" action="/search" method="GET">
      <label for="q">Search</label>
      <input id="q" name="q" type="search" placeholder="Search docs…" required>
      <button type="submit">Go</button>
    </form>
    <button>Open menu</button>
  </main>
</body>
</html>
"""

TABLE_HTML = """
<html><body>
<table>
  <caption>Results</caption>
  <tr><th>Name</th><th>Status</th></tr>
  <tr><td>alpha</td><td>passing</td></tr>
  <tr><td>beta</td><td>failing</td></tr>
</table>
</body></html>
"""

IMAGE_HTML = """
<html><body>
  <img src="/logo.png" alt="Site logo" width="200" height="50">
  <img src="/hero.jpg">
</body></html>
"""


# ---------------------------------------------------------------------------
# snapshot_from_html — PageMeta
# ---------------------------------------------------------------------------

class TestPageMeta:
    def test_title(self):
        snap = snapshot_from_html(SIMPLE_HTML, base_url="https://example.com")
        assert snap.meta.title == "Test Page"

    def test_description(self):
        snap = snapshot_from_html(SIMPLE_HTML, base_url="https://example.com")
        assert snap.meta.description == "A simple test page."

    def test_lang(self):
        snap = snapshot_from_html(SIMPLE_HTML, base_url="https://example.com")
        assert snap.meta.lang == "en"

    def test_url_preserved(self):
        snap = snapshot_from_html(SIMPLE_HTML, base_url="https://example.com")
        assert snap.meta.url == "https://example.com"

    def test_empty_html_no_crash(self):
        snap = snapshot_from_html("", base_url="about:blank")
        assert isinstance(snap, DOMSnapshot)
        assert snap.meta.title == ""


# ---------------------------------------------------------------------------
# snapshot_from_html — Headings
# ---------------------------------------------------------------------------

class TestHeadings:
    def test_h1_found(self):
        snap = snapshot_from_html(SIMPLE_HTML)
        assert any(h.level == 1 and h.text == "Hello World" for h in snap.headings)

    def test_h2_found(self):
        snap = snapshot_from_html(SIMPLE_HTML)
        assert any(h.level == 2 and h.text == "Sub-heading" for h in snap.headings)

    def test_order(self):
        snap = snapshot_from_html(SIMPLE_HTML)
        levels = [h.level for h in snap.headings]
        assert levels == sorted(levels) or levels[0] <= levels[-1]  # roughly ascending


# ---------------------------------------------------------------------------
# snapshot_from_html — Navigation links
# ---------------------------------------------------------------------------

class TestNavLinks:
    def test_links_found(self):
        snap = snapshot_from_html(SIMPLE_HTML, base_url="https://example.com")
        hrefs = [lnk.href for lnk in snap.nav_links]
        assert "https://example.com/home" in hrefs
        assert "https://example.com/about" in hrefs

    def test_max_links_respected(self):
        many_links = "".join(f'<a href="/p{i}">Page {i}</a>' for i in range(50))
        html = f"<html><body><nav>{many_links}</nav></body></html>"
        snap = snapshot_from_html(html, max_links=5)
        assert len(snap.nav_links) <= 5

    def test_link_text(self):
        snap = snapshot_from_html(SIMPLE_HTML, base_url="https://example.com")
        texts = [lnk.text for lnk in snap.nav_links]
        assert "Home" in texts
        assert "About" in texts


# ---------------------------------------------------------------------------
# snapshot_from_html — Forms
# ---------------------------------------------------------------------------

class TestForms:
    def test_form_found(self):
        snap = snapshot_from_html(SIMPLE_HTML, base_url="https://example.com")
        assert len(snap.forms) == 1

    def test_form_attributes(self):
        snap = snapshot_from_html(SIMPLE_HTML, base_url="https://example.com")
        frm = snap.forms[0]
        assert frm.id == "search"
        assert frm.method == "GET"
        assert "search" in frm.action

    def test_input_field(self):
        snap = snapshot_from_html(SIMPLE_HTML, base_url="https://example.com")
        frm = snap.forms[0]
        assert len(frm.fields) == 1
        field = frm.fields[0]
        assert field.name == "q"
        assert field.required is True
        assert field.placeholder == "Search docs…"

    def test_form_button(self):
        snap = snapshot_from_html(SIMPLE_HTML, base_url="https://example.com")
        frm = snap.forms[0]
        assert "Go" in frm.buttons

    def test_no_hidden_fields(self):
        html = """<html><body>
          <form>
            <input type="hidden" name="csrf" value="abc">
            <input type="text" name="username">
          </form>
        </body></html>"""
        snap = snapshot_from_html(html)
        frm = snap.forms[0]
        names = [f.name for f in frm.fields]
        assert "csrf" not in names
        assert "username" in names


# ---------------------------------------------------------------------------
# snapshot_from_html — Buttons
# ---------------------------------------------------------------------------

class TestButtons:
    def test_standalone_button(self):
        snap = snapshot_from_html(SIMPLE_HTML)
        texts = [b.text for b in snap.buttons]
        assert "Open menu" in texts

    def test_disabled_button(self):
        html = '<html><body><button disabled>Submit</button></body></html>'
        snap = snapshot_from_html(html)
        btn = next((b for b in snap.buttons if b.text == "Submit"), None)
        assert btn is not None
        assert btn.disabled is True


# ---------------------------------------------------------------------------
# snapshot_from_html — Tables
# ---------------------------------------------------------------------------

class TestTables:
    def test_table_found(self):
        snap = snapshot_from_html(TABLE_HTML)
        assert len(snap.tables) == 1

    def test_caption(self):
        snap = snapshot_from_html(TABLE_HTML)
        assert snap.tables[0].caption == "Results"

    def test_headers(self):
        snap = snapshot_from_html(TABLE_HTML)
        assert "Name" in snap.tables[0].headers
        assert "Status" in snap.tables[0].headers

    def test_row_count(self):
        snap = snapshot_from_html(TABLE_HTML)
        assert snap.tables[0].row_count >= 2

    def test_sample_rows(self):
        snap = snapshot_from_html(TABLE_HTML)
        flat = [cell for row in snap.tables[0].sample_rows for cell in row]
        assert "alpha" in flat or "passing" in flat


# ---------------------------------------------------------------------------
# snapshot_from_html — Images
# ---------------------------------------------------------------------------

class TestImages:
    def test_images_found(self):
        snap = snapshot_from_html(IMAGE_HTML, base_url="https://example.com")
        assert len(snap.images) == 2

    def test_alt_text(self):
        snap = snapshot_from_html(IMAGE_HTML, base_url="https://example.com")
        alts = [img.alt for img in snap.images]
        assert "Site logo" in alts

    def test_src_resolved(self):
        snap = snapshot_from_html(IMAGE_HTML, base_url="https://example.com")
        srcs = [img.src for img in snap.images]
        assert "https://example.com/logo.png" in srcs

    def test_dimensions(self):
        snap = snapshot_from_html(IMAGE_HTML, base_url="https://example.com")
        logo = next(img for img in snap.images if "logo" in img.src)
        assert logo.width == "200"
        assert logo.height == "50"


# ---------------------------------------------------------------------------
# snapshot_from_html — Visible text
# ---------------------------------------------------------------------------

class TestVisibleText:
    def test_contains_paragraph_text(self):
        snap = snapshot_from_html(SIMPLE_HTML)
        assert "Visible paragraph text" in snap.visible_text

    def test_no_script_content(self):
        html = "<html><body><script>alert('xss')</script><p>Hello</p></body></html>"
        snap = snapshot_from_html(html)
        assert "alert" not in snap.visible_text

    def test_max_length(self):
        long_text = " ".join(["word"] * 2000)
        html = f"<html><body><p>{long_text}</p></body></html>"
        snap = snapshot_from_html(html)
        assert len(snap.visible_text) <= 1_500 + 50  # small tolerance for newlines


# ---------------------------------------------------------------------------
# snapshot_to_text — Output formatting
# ---------------------------------------------------------------------------

class TestSnapshotToText:
    def setup_method(self):
        self.snap = snapshot_from_html(SIMPLE_HTML, base_url="https://example.com")
        self.text = snapshot_to_text(self.snap)

    def test_page_metadata_section(self):
        assert "### Page Metadata" in self.text

    def test_title_in_output(self):
        assert "Test Page" in self.text

    def test_headings_section(self):
        assert "### Headings" in self.text
        assert "H1: Hello World" in self.text

    def test_nav_links_section(self):
        assert "### Navigation Links" in self.text
        assert "Home" in self.text

    def test_forms_section(self):
        assert "### Forms" in self.text

    def test_buttons_section(self):
        assert "### Interactive Buttons" in self.text

    def test_no_errors_section_on_clean_page(self):
        assert "### Errors" not in self.text

    def test_errors_shown_on_bad_snap(self):
        bad = DOMSnapshot()
        bad.errors.append("HTTP 404: Not Found")
        out = snapshot_to_text(bad)
        assert "### Errors" in out
        assert "404" in out

    def test_max_links_truncation_message(self):
        many_links = "".join(f'<a href="/p{i}">Page {i}</a>' for i in range(30))
        html = f"<html><body><nav>{many_links}</nav></body></html>"
        snap = snapshot_from_html(html, max_links=5)
        text = snapshot_to_text(snap, max_links=5)
        assert "omitted" in text

    def test_table_shown_in_output(self):
        snap = snapshot_from_html(TABLE_HTML)
        text = snapshot_to_text(snap)
        assert "### Data Tables" in text
        assert "Results" in text

    def test_images_shown_in_output(self):
        snap = snapshot_from_html(IMAGE_HTML, base_url="https://example.com")
        text = snapshot_to_text(snap)
        assert "### Images" in text
        assert "Site logo" in text


# ---------------------------------------------------------------------------
# snapshot_from_url — mocked HTTP
# ---------------------------------------------------------------------------

class TestSnapshotFromUrl:
    def _mock_response(self, html: str, status: int = 200, reason: str = "OK"):
        mock_resp = MagicMock()
        mock_resp.status_code = status
        mock_resp.reason = reason
        mock_resp.content = html.encode("utf-8")
        mock_resp.apparent_encoding = "utf-8"
        return mock_resp

    def test_successful_fetch(self):
        with patch("dom_snapshot_utility.snapshot._requests") as mock_req:
            mock_req.get.return_value = self._mock_response(SIMPLE_HTML)
            snap = snapshot_from_url("https://example.com")
        assert snap.meta.title == "Test Page"
        assert not snap.errors

    def test_http_error_recorded(self):
        with patch("dom_snapshot_utility.snapshot._requests") as mock_req:
            mock_req.get.return_value = self._mock_response("", status=404, reason="Not Found")
            snap = snapshot_from_url("https://example.com/missing")
        assert any("404" in e for e in snap.errors)

    def test_connection_error_recorded(self):
        with patch("dom_snapshot_utility.snapshot._requests") as mock_req:
            mock_req.get.side_effect = Exception("Connection refused")
            snap = snapshot_from_url("https://example.com")
        assert any("Connection refused" in e for e in snap.errors)

    def test_url_preserved_in_meta(self):
        with patch("dom_snapshot_utility.snapshot._requests") as mock_req:
            mock_req.get.return_value = self._mock_response(SIMPLE_HTML)
            snap = snapshot_from_url("https://example.com")
        assert snap.meta.url == "https://example.com"


# ---------------------------------------------------------------------------
# Skill wrapper — dom_snapshot_html / dom_snapshot_url
# ---------------------------------------------------------------------------

class TestSkillWrappers:
    def test_dom_snapshot_html_returns_string(self):
        result = dom_snapshot_html(SIMPLE_HTML, base_url="https://example.com")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_dom_snapshot_html_contains_sections(self):
        result = dom_snapshot_html(SIMPLE_HTML, base_url="https://example.com")
        assert "### Page Metadata" in result
        assert "### Headings" in result

    def test_dom_snapshot_html_max_links(self):
        many = "".join(f'<a href="/p{i}">P{i}</a>' for i in range(20))
        html = f"<html><body><nav>{many}</nav></body></html>"
        result = dom_snapshot_html(html, max_links=3)
        assert "omitted" in result

    def test_dom_snapshot_url_returns_string(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = SIMPLE_HTML.encode()
        mock_resp.apparent_encoding = "utf-8"
        with patch("dom_snapshot_utility.snapshot._requests") as mock_req:
            mock_req.get.return_value = mock_resp
            result = dom_snapshot_url("https://example.com")
        assert isinstance(result, str)
        assert "Test Page" in result

    def test_dom_snapshot_url_error_propagates(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.reason = "Service Unavailable"
        with patch("dom_snapshot_utility.snapshot._requests") as mock_req:
            mock_req.get.return_value = mock_resp
            result = dom_snapshot_url("https://example.com")
        assert "503" in result


# ---------------------------------------------------------------------------
# ARIA landmarks
# ---------------------------------------------------------------------------

class TestAriaLandmarks:
    def test_implicit_main(self):
        snap = snapshot_from_html(SIMPLE_HTML)
        roles = [lm.role for lm in snap.landmarks]
        assert "main" in roles

    def test_implicit_nav(self):
        snap = snapshot_from_html(SIMPLE_HTML)
        roles = [lm.role for lm in snap.landmarks]
        assert "navigation" in roles

    def test_explicit_role(self):
        html = '<html><body><div role="dialog" aria-label="Confirm delete">…</div></body></html>'
        snap = snapshot_from_html(html)
        roles = [lm.role for lm in snap.landmarks]
        assert "dialog" in roles

    def test_explicit_role_label_captured(self):
        html = '<html><body><div role="dialog" aria-label="Confirm delete">…</div></body></html>'
        snap = snapshot_from_html(html)
        dlg = next(lm for lm in snap.landmarks if lm.role == "dialog")
        assert dlg.label == "Confirm delete"
