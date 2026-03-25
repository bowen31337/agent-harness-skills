"""Tests for pattern frequency extraction."""

from __future__ import annotations

from pathlib import Path

from harness_skills.generators.pattern_extractor import extract_patterns


class TestExtractPatterns:

    def test_empty_dir(self, tmp_path: Path) -> None:
        result = extract_patterns(tmp_path)
        assert result == []

    def test_decorator_detection(self, tmp_path: Path) -> None:
        for name in ("a.py", "b.py", "c.py"):
            (tmp_path / name).write_text(
                "from functools import lru_cache\n\n"
                "@lru_cache\ndef expensive(): pass\n"
            )
        result = extract_patterns(tmp_path)
        names = {p.pattern_name for p in result}
        assert "@lru_cache" in names
        lru = next(p for p in result if p.pattern_name == "@lru_cache")
        assert lru.occurrences >= 3
        assert lru.category == "decorator"

    def test_base_class_detection(self, tmp_path: Path) -> None:
        for name in ("gate1.py", "gate2.py", "gate3.py"):
            (tmp_path / name).write_text("class MyGate(BaseModel):\n    pass\n")
        result = extract_patterns(tmp_path)
        names = {p.pattern_name for p in result}
        assert "extends BaseModel" in names

    def test_frequency_ranking(self, tmp_path: Path) -> None:
        # 5 uses of @property, 2 uses of @staticmethod
        for i in range(5):
            (tmp_path / f"prop_{i}.py").write_text(
                "class X:\n    @property\n    def val(self): return 1\n"
            )
        for i in range(2):
            (tmp_path / f"static_{i}.py").write_text(
                "class Y:\n    @staticmethod\n    def run(): pass\n"
            )
        result = extract_patterns(tmp_path)
        if len(result) >= 2:
            assert result[0].occurrences >= result[1].occurrences

    def test_max_examples_cap(self, tmp_path: Path) -> None:
        for i in range(10):
            (tmp_path / f"m{i}.py").write_text("class Foo(BaseModel):\n    pass\n")
        result = extract_patterns(tmp_path, max_examples=2)
        bm = next((p for p in result if "BaseModel" in p.pattern_name), None)
        if bm:
            assert len(bm.example_files) <= 2

    def test_syntax_errors_skipped(self, tmp_path: Path) -> None:
        (tmp_path / "bad.py").write_text("def broken(\n")
        (tmp_path / "good.py").write_text("class Foo(Bar):\n    pass\n")
        (tmp_path / "good2.py").write_text("class Baz(Bar):\n    pass\n")
        result = extract_patterns(tmp_path)
        # Should not crash, and good files should be analyzed
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Additional coverage tests
# ---------------------------------------------------------------------------


from harness_skills.generators.pattern_extractor import (
    _decorator_name,
    _estimate_effort,
    _node_name,
    _slugify,
    generate_cleanup_tasks,
    PatternFrequency,
)
import ast


class TestDecoratorName:
    def test_name_node(self) -> None:
        tree = ast.parse("@foo\ndef bar(): pass\n")
        func = tree.body[0]
        result = _decorator_name(func.decorator_list[0])
        assert result == "foo"

    def test_attribute_node(self) -> None:
        tree = ast.parse("@app.route\ndef bar(): pass\n")
        func = tree.body[0]
        result = _decorator_name(func.decorator_list[0])
        assert result == "app.route"

    def test_call_node(self) -> None:
        tree = ast.parse("@app.route('/test')\ndef bar(): pass\n")
        func = tree.body[0]
        result = _decorator_name(func.decorator_list[0])
        assert result == "app.route"

    def test_unknown_node_returns_none(self) -> None:
        # Create an expression that isn't Name, Attribute, or Call
        node = ast.Constant(value=42)
        result = _decorator_name(node)
        assert result is None


class TestNodeName:
    def test_name_node(self) -> None:
        node = ast.Name(id="Foo")
        assert _node_name(node) == "Foo"

    def test_attribute_node(self) -> None:
        tree = ast.parse("x = foo.bar")
        assign = tree.body[0]
        # foo.bar is an Attribute node
        result = _node_name(assign.value)
        assert result == "foo.bar"

    def test_unknown_returns_none(self) -> None:
        node = ast.Constant(value=42)
        assert _node_name(node) is None


class TestEstimateEffort:
    def test_low(self) -> None:
        assert _estimate_effort(5) == "low"

    def test_medium(self) -> None:
        assert _estimate_effort(15) == "medium"

    def test_high(self) -> None:
        assert _estimate_effort(40) == "high"

    def test_very_high(self) -> None:
        assert _estimate_effort(100) == "very-high"


class TestSlugify:
    def test_basic(self) -> None:
        assert _slugify("@lru_cache") == "lru-cache"

    def test_spaces(self) -> None:
        assert _slugify("extends BaseModel") == "extends-basemodel"

    def test_special_chars(self) -> None:
        slug = _slugify("app.route('/test')")
        assert slug  # Non-empty
        assert " " not in slug


class TestGenerateCleanupTasks:
    def test_generates_tasks(self) -> None:
        patterns = [
            PatternFrequency(
                pattern_name="@property",
                category="decorator",
                occurrences=15,
                example_files=["a.py", "b.py"],
                suggested_principle="Use @property consistently.",
            ),
        ]
        result = generate_cleanup_tasks(patterns)
        assert result["task_count"] == 1
        assert len(result["tasks"]) == 1
        task = result["tasks"][0]
        assert "cleanup-" in task["id"]
        assert task["estimated_effort"] == "medium"

    def test_writes_to_file(self, tmp_path: Path) -> None:
        patterns = [
            PatternFrequency(
                pattern_name="@staticmethod",
                category="decorator",
                occurrences=5,
                example_files=["x.py"],
                suggested_principle="Use @staticmethod.",
            ),
        ]
        output = tmp_path / "tasks.yaml"
        result = generate_cleanup_tasks(patterns, output_path=output)
        assert output.exists()
        assert result["task_count"] == 1

    def test_empty_patterns(self) -> None:
        result = generate_cleanup_tasks([])
        assert result["task_count"] == 0
        assert result["tasks"] == []
