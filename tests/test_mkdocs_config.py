"""Tests for MkDocs configuration validity."""

from __future__ import annotations

from pathlib import Path

import yaml


class TestMkDocsConfig:

    def test_mkdocs_yml_exists(self) -> None:
        assert Path("mkdocs.yml").exists()

    def test_mkdocs_yml_is_valid_yaml(self) -> None:
        config = yaml.safe_load(Path("mkdocs.yml").read_text())
        assert isinstance(config, dict)
        assert "site_name" in config
        assert "nav" in config
        assert "theme" in config

    def test_theme_is_material(self) -> None:
        config = yaml.safe_load(Path("mkdocs.yml").read_text())
        assert config["theme"]["name"] == "material"

    def test_nav_structure(self) -> None:
        config = yaml.safe_load(Path("mkdocs.yml").read_text())
        nav = config["nav"]
        assert len(nav) >= 3
        # First item should be Home
        assert "Home" in nav[0]
