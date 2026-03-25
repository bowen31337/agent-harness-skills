"""
Tests covering uncovered lines in dom_snapshot_utility/snapshot.py and
harness_skills/dom_snapshot_skill.py.

Snapshot uncovered lines:
  164: _attr returns list-joined value
  181-187: _label_for wrapped label path
  279-282: fallback to all <a> when no <nav> links
  335-338: role=button elements
  380-381: _parse_visible_text exception fallback
  404-406: snapshot_from_html when bs4 unavailable
  410-411: snapshot_from_html lxml fallback to html.parser
  423-426: snapshot_from_url when requests unavailable
  428-431: snapshot_from_url when bs4 unavailable
  482: duplicate ARIA landmark dedup in snapshot_to_text

dom_snapshot_skill uncovered lines:
  55-56: sys.path insertion (already covered by import, but test explicitly)
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

pytest.importorskip("bs4", reason="beautifulsoup4 is required for DOM snapshot tests")
pytest.importorskip("lxml", reason="lxml is required for DOM snapshot tests")

from dom_snapshot_utility.snapshot import (
    DOMSnapshot,
    PageMeta,
    AriaRegion,
    Link,
    Button,
    snapshot_from_html,
    snapshot_from_url,
    snapshot_to_text,
    _attr,
    _label_for,
    _parse_visible_text,
)
from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# _attr — list attribute joined (line 164)
# ---------------------------------------------------------------------------

class TestAttrListValue:
    def test_list_class_attribute(self):
        """When an attribute is a list (like class), join with spaces."""
        html = '<div class="foo bar">text</div>'
        soup = BeautifulSoup(html, "lxml")
        el = soup.find("div")
        result = _attr(el, "class")
        assert "foo" in result
        assert "bar" in result

    def test_fallback_to_second_attr(self):
        html = '<input title="Search">'
        soup = BeautifulSoup(html, "lxml")
        el = soup.find("input")
        result = _attr(el, "aria-label", "title")
        assert result == "Search"


# ---------------------------------------------------------------------------
# _label_for — wrapped label path (lines 181-187)
# ---------------------------------------------------------------------------

class TestLabelForWrapped:
    def test_wrapped_label(self):
        """Input inside a <label> — text from parent label excluding input."""
        html = """
        <html><body>
        <label>Username <input type="text" name="user"></label>
        </body></html>
        """
        soup = BeautifulSoup(html, "lxml")
        inp = soup.find("input")
        label = _label_for(inp, soup)
        assert "Username" in label

    def test_label_by_for_id(self):
        html = """
        <html><body>
        <label for="email">Email</label>
        <input id="email" name="email" type="email">
        </body></html>
        """
        soup = BeautifulSoup(html, "lxml")
        inp = soup.find("input")
        label = _label_for(inp, soup)
        assert label == "Email"

    def test_no_label_falls_to_aria(self):
        html = '<html><body><input aria-label="Phone" type="tel"></body></html>'
        soup = BeautifulSoup(html, "lxml")
        inp = soup.find("input")
        label = _label_for(inp, soup)
        assert label == "Phone"


# ---------------------------------------------------------------------------
# _parse_nav_links — fallback to all <a> (lines 279-282)
# ---------------------------------------------------------------------------

class TestNavLinksFallback:
    def test_no_nav_element_falls_back_to_all_links(self):
        """When no <nav> element exists, all <a> tags are used."""
        html = """
        <html><body>
            <a href="/page1">Page 1</a>
            <a href="/page2">Page 2</a>
        </body></html>
        """
        snap = snapshot_from_html(html, base_url="https://example.com")
        assert len(snap.nav_links) == 2
        hrefs = [lnk.href for lnk in snap.nav_links]
        assert "https://example.com/page1" in hrefs


# ---------------------------------------------------------------------------
# _parse_buttons — role=button elements (lines 335-338)
# ---------------------------------------------------------------------------

class TestRoleButton:
    def test_role_button_detected(self):
        html = """
        <html><body>
            <div role="button" aria-label="Close">X</div>
        </body></html>
        """
        snap = snapshot_from_html(html)
        assert any(b.text == "X" and b.aria_label == "Close" for b in snap.buttons)

    def test_role_button_disabled(self):
        html = """
        <html><body>
            <div role="button" aria-disabled="true">Disabled Action</div>
        </body></html>
        """
        snap = snapshot_from_html(html)
        btn = next(b for b in snap.buttons if b.text == "Disabled Action")
        assert btn.disabled is True


# ---------------------------------------------------------------------------
# _parse_visible_text — exception fallback (lines 380-381)
# ---------------------------------------------------------------------------

class TestParseVisibleTextFallback:
    def test_copy_exception_fallback(self):
        """If copy.copy raises, falls back to using original soup (lines 380-381)."""
        html = "<html><body><p>Hello world</p></body></html>"
        soup = BeautifulSoup(html, "lxml")
        # Patch the copy module that is imported inside the function
        import copy as real_copy
        mock_copy = MagicMock()
        mock_copy.copy.side_effect = Exception("copy failed")
        with patch.dict("sys.modules", {"copy": mock_copy}):
            # Since copy is imported inside the function via `import copy as _copy_mod`,
            # patching sys.modules won't work because it's already cached.
            # Instead, patch at the point of use: the function re-imports each call.
            # Actually, the function does `import copy as _copy_mod` which uses
            # the cached module. Let's patch copy.copy directly.
            pass
        # Simpler approach: just patch copy.copy
        with patch("copy.copy", side_effect=Exception("copy failed")):
            result = _parse_visible_text(soup)
            assert "Hello" in result


# ---------------------------------------------------------------------------
# snapshot_from_html — lxml fallback (lines 410-411)
# ---------------------------------------------------------------------------

class TestSnapshotFromHtmlFallback:
    def test_lxml_failure_falls_back_to_html_parser(self):
        """When lxml raises, fallback to html.parser."""
        html = "<html><body><h1>Test</h1></body></html>"
        with patch("dom_snapshot_utility.snapshot.BeautifulSoup") as MockBS:
            # First call (lxml) raises, second (html.parser) works
            real_bs = BeautifulSoup
            call_count = [0]
            def side_effect(h, parser):
                call_count[0] += 1
                if call_count[0] == 1:
                    raise Exception("lxml not available")
                return real_bs(h, parser)
            MockBS.side_effect = side_effect
            snap = snapshot_from_html(html)
            assert isinstance(snap, DOMSnapshot)


# ---------------------------------------------------------------------------
# snapshot_from_html — bs4 unavailable (lines 404-406)
# ---------------------------------------------------------------------------

class TestSnapshotFromHtmlNoBs4:
    def test_returns_error_when_bs4_missing(self):
        with patch("dom_snapshot_utility.snapshot._HAS_BS4", False):
            snap = snapshot_from_html("<html></html>")
            assert any("beautifulsoup4" in e for e in snap.errors)


# ---------------------------------------------------------------------------
# snapshot_from_url — requests unavailable (lines 423-426)
# ---------------------------------------------------------------------------

class TestSnapshotFromUrlNoRequests:
    def test_returns_error_when_requests_missing(self):
        with patch("dom_snapshot_utility.snapshot._HAS_REQUESTS", False):
            snap = snapshot_from_url("https://example.com")
            assert any("requests" in e for e in snap.errors)
            assert snap.meta.url == "https://example.com"


# ---------------------------------------------------------------------------
# snapshot_from_url — bs4 unavailable (lines 428-431)
# ---------------------------------------------------------------------------

class TestSnapshotFromUrlNoBs4:
    def test_returns_error_when_bs4_missing(self):
        with patch("dom_snapshot_utility.snapshot._HAS_REQUESTS", True):
            with patch("dom_snapshot_utility.snapshot._HAS_BS4", False):
                snap = snapshot_from_url("https://example.com")
                assert any("beautifulsoup4" in e for e in snap.errors)
                assert snap.meta.url == "https://example.com"


# ---------------------------------------------------------------------------
# snapshot_to_text — ARIA landmark dedup (line 482)
# ---------------------------------------------------------------------------

class TestSnapshotToTextDedup:
    def test_duplicate_landmarks_deduped(self):
        snap = DOMSnapshot()
        snap.landmarks = [
            AriaRegion(role="navigation", label="Main"),
            AriaRegion(role="navigation", label="Main"),  # duplicate
            AriaRegion(role="main", label=""),
        ]
        text = snapshot_to_text(snap)
        # Should only appear once
        assert text.count("[navigation] role=navigation label='Main'") == 1

    def test_landmark_without_label(self):
        snap = DOMSnapshot()
        snap.landmarks = [AriaRegion(role="main", label="")]
        text = snapshot_to_text(snap)
        assert "[main] role=main" in text
        assert "label=" not in text  # no label shown when empty


# ---------------------------------------------------------------------------
# snapshot_to_text — various sections formatting
# ---------------------------------------------------------------------------

class TestSnapshotToTextSections:
    def test_form_with_all_details(self):
        """Test form rendering in text output with all field attributes."""
        html = """
        <html><body>
        <form id="login" action="/auth" method="POST">
            <label for="user">Username</label>
            <input id="user" name="user" type="text" placeholder="Enter name" required>
            <select name="role">
                <option>Admin</option>
            </select>
            <textarea name="notes" placeholder="Notes"></textarea>
            <button type="submit">Login</button>
        </form>
        </body></html>
        """
        snap = snapshot_from_html(html, base_url="https://example.com")
        text = snapshot_to_text(snap)
        assert "### Forms" in text
        assert "FORM" in text
        assert "method='POST'" in text

    def test_images_with_dimensions_in_text(self):
        html = '<html><body><img src="/pic.png" alt="Logo" width="100" height="50"></body></html>'
        snap = snapshot_from_html(html, base_url="https://example.com")
        text = snapshot_to_text(snap)
        assert "(100" in text
        assert "50)" in text

    def test_image_no_alt(self):
        html = '<html><body><img src="/pic.png"></body></html>'
        snap = snapshot_from_html(html, base_url="https://example.com")
        text = snapshot_to_text(snap)
        assert "[no alt]" in text

    def test_visible_text_section(self):
        html = "<html><body><p>Some visible paragraph content.</p></body></html>"
        snap = snapshot_from_html(html)
        text = snapshot_to_text(snap)
        assert "### Visible Text" in text


# ---------------------------------------------------------------------------
# dom_snapshot_skill — sys.path insertion
# ---------------------------------------------------------------------------

class TestDomSnapshotSkillImport:
    def test_skill_functions_importable(self):
        from harness_skills.dom_snapshot_skill import dom_snapshot_html, dom_snapshot_url
        assert callable(dom_snapshot_html)
        assert callable(dom_snapshot_url)

    def test_dom_snapshot_html_with_max_links(self):
        from harness_skills.dom_snapshot_skill import dom_snapshot_html
        html = "<html><body><h1>Test</h1></body></html>"
        result = dom_snapshot_html(html, base_url="https://example.com", max_links=5)
        assert isinstance(result, str)
        assert "Test" in result
