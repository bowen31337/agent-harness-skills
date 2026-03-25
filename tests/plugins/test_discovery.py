"""Tests for plugin discovery via entry_points."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from harness_skills.plugins.discovery import (
    ANALYZER_GROUP,
    GATE_GROUP,
    discover_all,
    discover_plugins,
)


class TestDiscoverPlugins:

    def test_empty_group(self) -> None:
        with patch("harness_skills.plugins.discovery.entry_points", return_value=[]):
            result = discover_plugins("nonexistent.group")
            assert result == {}

    def test_loads_valid_plugin(self) -> None:
        fake_ep = MagicMock()
        fake_ep.name = "test_plugin"
        fake_ep.load.return_value = type("FakePlugin", (), {})

        with patch("harness_skills.plugins.discovery.entry_points", return_value=[fake_ep]):
            result = discover_plugins(ANALYZER_GROUP)
            assert "test_plugin" in result

    def test_skips_failed_plugin(self) -> None:
        good_ep = MagicMock()
        good_ep.name = "good"
        good_ep.load.return_value = type("Good", (), {})

        bad_ep = MagicMock()
        bad_ep.name = "bad"
        bad_ep.load.side_effect = ImportError("missing")

        with patch("harness_skills.plugins.discovery.entry_points", return_value=[good_ep, bad_ep]):
            result = discover_plugins(ANALYZER_GROUP)
            assert "good" in result
            assert "bad" not in result

    def test_discover_all(self) -> None:
        with patch("harness_skills.plugins.discovery.entry_points", return_value=[]):
            result = discover_all()
            assert ANALYZER_GROUP in result
            assert GATE_GROUP in result
