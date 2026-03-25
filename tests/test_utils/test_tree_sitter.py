"""Tests for tree-sitter utility (graceful degradation)."""

from __future__ import annotations

import pytest

from harness_skills.utils.tree_sitter import (
    LanguageNotAvailable,
    clear_caches,
    is_available,
)


class TestTreeSitterAvailability:

    def test_is_available_returns_bool(self) -> None:
        result = is_available()
        assert isinstance(result, bool)

    def test_clear_caches(self) -> None:
        # Should not raise
        clear_caches()


class TestLanguageNotAvailable:

    def test_exception_stores_language(self) -> None:
        exc = LanguageNotAvailable("cobol")
        assert exc.language == "cobol"
        assert "cobol" in str(exc)

    def test_is_import_error(self) -> None:
        exc = LanguageNotAvailable("fortran")
        assert isinstance(exc, ImportError)


class TestTreeSitterIntegration:
    """Tests that require tree-sitter to be installed. Skipped if not available."""

    @pytest.fixture(autouse=True)
    def _check_available(self):
        if not is_available():
            pytest.skip("tree-sitter not installed")

    def test_get_parser_python(self) -> None:
        from harness_skills.utils.tree_sitter import get_parser

        try:
            parser = get_parser("python")
            assert parser is not None
        except LanguageNotAvailable:
            pytest.skip("tree-sitter-python not installed")

    def test_parse_bytes(self, tmp_path) -> None:
        from harness_skills.utils.tree_sitter import parse_bytes

        try:
            tree = parse_bytes(b"import os\n", "python")
            assert tree is not None
            assert tree.root_node is not None
        except LanguageNotAvailable:
            pytest.skip("tree-sitter-python not installed")

    def test_parse_file(self, tmp_path) -> None:
        from harness_skills.utils.tree_sitter import parse_file

        py_file = tmp_path / "sample.py"
        py_file.write_text("def hello():\n    pass\n")
        try:
            tree = parse_file(py_file, "python")
            assert tree is not None
        except LanguageNotAvailable:
            pytest.skip("tree-sitter-python not installed")

    def test_unknown_language_raises(self) -> None:
        from harness_skills.utils.tree_sitter import get_parser

        with pytest.raises(LanguageNotAvailable):
            get_parser("brainfuck")
