"""Tests for harness_skills.analyzers.__init__ module."""

from __future__ import annotations

from unittest.mock import patch

import pytest

import harness_skills.analyzers as analyzers_mod
from harness_skills.analyzers import available_languages, get_analyzer


class TestAnalyzerRegistry:

    def test_get_analyzer_python(self) -> None:
        a = get_analyzer("python")
        assert a.language() == "python"

    def test_get_analyzer_typescript(self) -> None:
        a = get_analyzer("typescript")
        assert a.language() == "typescript"

    def test_get_analyzer_go(self) -> None:
        a = get_analyzer("go")
        assert a.language() == "go"

    def test_get_analyzer_java(self) -> None:
        a = get_analyzer("java")
        assert a.language() == "java"

    def test_get_analyzer_csharp(self) -> None:
        a = get_analyzer("csharp")
        assert a.language() == "csharp"

    def test_get_analyzer_rust(self) -> None:
        a = get_analyzer("rust")
        assert a.language() == "rust"

    def test_get_analyzer_unknown_raises(self) -> None:
        with pytest.raises(KeyError, match="No analyzer registered"):
            get_analyzer("brainfuck")

    def test_available_languages(self) -> None:
        langs = available_languages()
        assert isinstance(langs, list)
        assert "python" in langs
        assert "typescript" in langs
        assert "go" in langs
        assert langs == sorted(langs)

    def test_load_builtins_populates_registry(self) -> None:
        """_load_builtins() is a no-op when registry is already populated (import triggers registration)."""
        # Since modules are already imported, _REGISTRY is non-empty.
        # But the code path `if not _REGISTRY: _load_builtins()` is used
        # only on fresh import. We can test the logic directly:
        from harness_skills.analyzers import _load_builtins
        _load_builtins()  # Should not crash even when called multiple times
        assert len(analyzers_mod._REGISTRY) >= 6

    def test_register_analyzer_adds_to_registry(self) -> None:
        from harness_skills.analyzers import register_analyzer
        from harness_skills.analyzers.base import BaseAnalyzer, AnalysisResult
        from harness_skills.utils.import_graph import ImportEdge

        class FakeAnalyzer(BaseAnalyzer):
            def language(self) -> str:
                return "fake-lang"
            def can_analyze(self, root):
                return False
            def analyze(self, root, *, file_paths=None):
                return AnalysisResult(language="fake-lang")
            def extract_imports(self, file_path):
                return []
            def extract_symbols(self, file_path):
                return []

        register_analyzer(FakeAnalyzer)
        assert "fake-lang" in analyzers_mod._REGISTRY
        # Clean up
        del analyzers_mod._REGISTRY["fake-lang"]
