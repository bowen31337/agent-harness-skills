"""Comprehensive tests for harness_skills.utils.tree_sitter — all paths mocked.

Covers lines 72, 83-112, 120-131, 136-138, 143-144, 154-171 that require
mocking since tree-sitter is not installed in the test environment.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from harness_skills.utils.tree_sitter import (
    LanguageNotAvailable,
    TreeSitterNotInstalled,
    _GRAMMAR_PACKAGES,
    _LANGUAGE_CACHE,
    _PARSER_CACHE,
    clear_caches,
    is_available,
)


@pytest.fixture(autouse=True)
def _clear_caches():
    """Clear caches before and after each test."""
    clear_caches()
    yield
    clear_caches()


# ── is_available ─────────────────────────────────────────────────────────────


class TestIsAvailable:
    def test_returns_false_when_not_installed(self):
        # tree-sitter is not installed in the test environment
        assert is_available() is False

    def test_returns_true_when_installed(self):
        mock_ts = MagicMock()
        with patch.dict("sys.modules", {"tree_sitter": mock_ts}):
            # Need to reload or call directly
            # Since is_available does a try/import, we mock at import level
            result = is_available()
            # The function does `import tree_sitter` which will find our mock
            assert result is True


# ── get_language ─────────────────────────────────────────────────────────────


class TestGetLanguage:
    def test_raises_when_tree_sitter_not_installed(self):
        from harness_skills.utils.tree_sitter import get_language
        # tree-sitter is not installed
        with pytest.raises(TreeSitterNotInstalled):
            get_language("python")

    def test_unknown_language_raises(self):
        from harness_skills.utils.tree_sitter import get_language

        mock_ts = MagicMock()
        mock_language_cls = MagicMock()
        mock_ts.Language = mock_language_cls

        with patch.dict("sys.modules", {"tree_sitter": mock_ts}):
            with pytest.raises(LanguageNotAvailable):
                get_language("brainfuck")

    def test_caches_language(self):
        from harness_skills.utils.tree_sitter import get_language

        mock_ts = MagicMock()
        mock_lang_obj = MagicMock()
        mock_ts.Language = MagicMock(return_value=mock_lang_obj)

        mock_grammar = MagicMock()
        mock_grammar.language = MagicMock(return_value="raw_lang")

        with patch.dict("sys.modules", {
            "tree_sitter": mock_ts,
            "tree_sitter_python": mock_grammar,
        }):
            lang1 = get_language("python")
            lang2 = get_language("python")  # from cache
            assert lang1 is lang2

    def test_typescript_language(self):
        from harness_skills.utils.tree_sitter import get_language

        mock_ts = MagicMock()
        mock_lang_obj = MagicMock()
        mock_ts.Language = MagicMock(return_value=mock_lang_obj)

        mock_grammar = MagicMock()
        mock_grammar.language_typescript = MagicMock(return_value="raw_ts")

        with patch.dict("sys.modules", {
            "tree_sitter": mock_ts,
            "tree_sitter_typescript": mock_grammar,
        }):
            lang = get_language("typescript")
            assert lang is mock_lang_obj

    def test_tsx_language(self):
        from harness_skills.utils.tree_sitter import get_language

        mock_ts = MagicMock()
        mock_lang_obj = MagicMock()
        mock_ts.Language = MagicMock(return_value=mock_lang_obj)

        mock_grammar = MagicMock()
        mock_grammar.language_tsx = MagicMock(return_value="raw_tsx")

        with patch.dict("sys.modules", {
            "tree_sitter": mock_ts,
            "tree_sitter_typescript": mock_grammar,
        }):
            lang = get_language("tsx")
            assert lang is mock_lang_obj

    def test_generic_language_function(self):
        from harness_skills.utils.tree_sitter import get_language

        mock_ts = MagicMock()
        mock_lang_obj = MagicMock()
        mock_ts.Language = MagicMock(return_value=mock_lang_obj)

        mock_grammar = MagicMock()
        mock_grammar.language = MagicMock(return_value="raw_go")

        with patch.dict("sys.modules", {
            "tree_sitter": mock_ts,
            "tree_sitter_go": mock_grammar,
        }):
            lang = get_language("go")
            assert lang is mock_lang_obj

    def test_language_fn_none_raises(self):
        from harness_skills.utils.tree_sitter import get_language

        mock_ts = MagicMock()
        mock_ts.Language = MagicMock()

        mock_grammar = MagicMock(spec=[])  # no language attribute

        with patch.dict("sys.modules", {
            "tree_sitter": mock_ts,
            "tree_sitter_go": mock_grammar,
        }):
            with pytest.raises(LanguageNotAvailable):
                get_language("go")

    def test_import_error_wraps_as_language_not_available(self):
        from harness_skills.utils.tree_sitter import get_language

        mock_ts = MagicMock()
        mock_ts.Language = MagicMock()

        with patch.dict("sys.modules", {"tree_sitter": mock_ts}):
            with patch("harness_skills.utils.tree_sitter.is_available", return_value=True):
                # __import__ of the grammar package fails
                original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__

                def failing_import(name, *args, **kwargs):
                    if name == "tree_sitter_rust":
                        raise ImportError("no module")
                    return original_import(name, *args, **kwargs)

                with patch("builtins.__import__", side_effect=failing_import):
                    with pytest.raises(LanguageNotAvailable):
                        get_language("rust")


# ── get_parser ───────────────────────────────────────────────────────────────


class TestGetParser:
    def test_raises_when_tree_sitter_not_installed(self):
        from harness_skills.utils.tree_sitter import get_parser
        with pytest.raises(TreeSitterNotInstalled):
            get_parser("python")

    def test_creates_and_caches_parser(self):
        from harness_skills.utils.tree_sitter import get_parser

        mock_ts = MagicMock()
        mock_parser = MagicMock()
        mock_ts.Parser = MagicMock(return_value=mock_parser)
        mock_lang_obj = MagicMock()
        mock_ts.Language = MagicMock(return_value=mock_lang_obj)

        mock_grammar = MagicMock()
        mock_grammar.language = MagicMock(return_value="raw")

        with patch.dict("sys.modules", {
            "tree_sitter": mock_ts,
            "tree_sitter_python": mock_grammar,
        }):
            p1 = get_parser("python")
            p2 = get_parser("python")
            assert p1 is p2
            assert p1 is mock_parser


# ── parse_file / parse_bytes ─────────────────────────────────────────────────


class TestParseFilAndBytes:
    def _setup_mocks(self):
        mock_ts = MagicMock()
        mock_parser = MagicMock()
        mock_tree = MagicMock()
        mock_parser.parse = MagicMock(return_value=mock_tree)
        mock_ts.Parser = MagicMock(return_value=mock_parser)
        mock_lang_obj = MagicMock()
        mock_ts.Language = MagicMock(return_value=mock_lang_obj)
        mock_grammar = MagicMock()
        mock_grammar.language = MagicMock(return_value="raw")
        return mock_ts, mock_grammar, mock_tree

    def test_parse_file(self, tmp_path):
        from harness_skills.utils.tree_sitter import parse_file

        mock_ts, mock_grammar, mock_tree = self._setup_mocks()
        py_file = tmp_path / "test.py"
        py_file.write_text("import os\n")

        with patch.dict("sys.modules", {
            "tree_sitter": mock_ts,
            "tree_sitter_python": mock_grammar,
        }):
            tree = parse_file(py_file, "python")
            assert tree is mock_tree

    def test_parse_bytes(self):
        from harness_skills.utils.tree_sitter import parse_bytes

        mock_ts, mock_grammar, mock_tree = self._setup_mocks()

        with patch.dict("sys.modules", {
            "tree_sitter": mock_ts,
            "tree_sitter_python": mock_grammar,
        }):
            tree = parse_bytes(b"import os\n", "python")
            assert tree is mock_tree


# ── query_matches ────────────────────────────────────────────────────────────


class TestQueryMatches:
    def test_query_matches_with_lang_query(self):
        from harness_skills.utils.tree_sitter import query_matches

        mock_ts = MagicMock()
        mock_query_cls = MagicMock()
        mock_ts.Query = mock_query_cls
        mock_lang_obj = MagicMock()
        mock_ts.Language = MagicMock(return_value=mock_lang_obj)

        # Mock lang.query() method
        mock_query = MagicMock()
        mock_query.matches = MagicMock(return_value=[
            (0, {"cap": "node1"}),
            (1, {"cap": "node2"}),
        ])
        mock_lang_obj.query = MagicMock(return_value=mock_query)

        mock_grammar = MagicMock()
        mock_grammar.language = MagicMock(return_value="raw")

        mock_tree = MagicMock()
        mock_tree.root_node = MagicMock()

        with patch.dict("sys.modules", {
            "tree_sitter": mock_ts,
            "tree_sitter_python": mock_grammar,
        }):
            # Put lang in cache
            _LANGUAGE_CACHE["python"] = mock_lang_obj
            results = query_matches(mock_tree, "python", "(import_statement) @imp")

        assert len(results) == 2
        assert results[0]["pattern_index"] == 0
        assert results[1]["pattern_index"] == 1

    def test_query_matches_fallback_to_query_class(self):
        from harness_skills.utils.tree_sitter import query_matches

        mock_ts = MagicMock()
        mock_lang_obj = MagicMock(spec=[])  # no .query attribute
        mock_ts.Language = MagicMock(return_value=mock_lang_obj)

        mock_query = MagicMock()
        mock_query.matches = MagicMock(return_value=[
            "direct_match",  # non-tuple match
        ])
        mock_ts.Query = MagicMock(return_value=mock_query)

        mock_tree = MagicMock()
        mock_tree.root_node = MagicMock()

        _LANGUAGE_CACHE["python"] = mock_lang_obj

        with patch.dict("sys.modules", {"tree_sitter": mock_ts}):
            results = query_matches(mock_tree, "python", "(query)")

        assert len(results) == 1
        assert results[0]["pattern_index"] == 0
        assert results[0]["captures"] == "direct_match"
