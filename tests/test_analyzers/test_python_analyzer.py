"""Tests for Python analyzer."""

from __future__ import annotations

from pathlib import Path

from harness_skills.analyzers.python_analyzer import PythonAnalyzer


class TestPythonAnalyzer:

    def test_language(self) -> None:
        a = PythonAnalyzer()
        assert a.language() == "python"

    def test_file_extensions(self) -> None:
        a = PythonAnalyzer()
        assert ".py" in a.file_extensions()

    def test_can_analyze_with_pyproject(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
        a = PythonAnalyzer()
        assert a.can_analyze(tmp_path) is True

    def test_can_analyze_with_requirements(self, tmp_path: Path) -> None:
        (tmp_path / "requirements.txt").write_text("requests\n")
        a = PythonAnalyzer()
        assert a.can_analyze(tmp_path) is True

    def test_cannot_analyze_empty_dir(self, tmp_path: Path) -> None:
        a = PythonAnalyzer()
        assert a.can_analyze(tmp_path) is False

    def test_extract_imports(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_text("import os\nfrom pathlib import Path\nimport json\n")
        a = PythonAnalyzer()
        edges = a.extract_imports(src, root=tmp_path)
        targets = {e.target for e in edges}
        assert "os" in targets
        assert "pathlib" in targets
        assert "json" in targets

    def test_extract_imports_from_type(self, tmp_path: Path) -> None:
        src = tmp_path / "app.py"
        src.write_text("from collections import OrderedDict\n")
        a = PythonAnalyzer()
        edges = a.extract_imports(src, root=tmp_path)
        assert any(e.import_type == "from" and e.target == "collections" for e in edges)

    def test_extract_imports_syntax_error(self, tmp_path: Path) -> None:
        src = tmp_path / "bad.py"
        src.write_text("def broken(\n")
        a = PythonAnalyzer()
        edges = a.extract_imports(src, root=tmp_path)
        assert edges == []

    def test_extract_symbols_functions(self, tmp_path: Path) -> None:
        src = tmp_path / "mod.py"
        src.write_text("def hello():\n    pass\n\ndef world():\n    pass\n")
        a = PythonAnalyzer()
        symbols = a.extract_symbols(src, root=tmp_path)
        names = {s.name for s in symbols}
        assert "hello" in names
        assert "world" in names

    def test_extract_symbols_classes(self, tmp_path: Path) -> None:
        src = tmp_path / "mod.py"
        src.write_text("class Foo:\n    pass\n\nclass Bar(Foo):\n    pass\n")
        a = PythonAnalyzer()
        symbols = a.extract_symbols(src, root=tmp_path)
        names = {s.name for s in symbols}
        assert "Foo" in names
        assert "Bar" in names

    def test_extract_symbols_respects_all(self, tmp_path: Path) -> None:
        src = tmp_path / "mod.py"
        src.write_text("__all__ = ['public_fn']\n\ndef public_fn(): pass\n\ndef private_fn(): pass\n")
        a = PythonAnalyzer()
        symbols = a.extract_symbols(src, root=tmp_path)
        public = [s for s in symbols if s.name == "public_fn"]
        private = [s for s in symbols if s.name == "private_fn"]
        assert public[0].exported is True
        assert private[0].exported is False

    def test_extract_symbols_constants(self, tmp_path: Path) -> None:
        src = tmp_path / "mod.py"
        src.write_text("MAX_RETRIES = 3\nDEFAULT_TIMEOUT = 30\n")
        a = PythonAnalyzer()
        symbols = a.extract_symbols(src, root=tmp_path)
        names = {s.name for s in symbols}
        assert "MAX_RETRIES" in names
        assert "DEFAULT_TIMEOUT" in names

    def test_extract_symbols_skips_private(self, tmp_path: Path) -> None:
        src = tmp_path / "mod.py"
        src.write_text("def _private(): pass\ndef public(): pass\n")
        a = PythonAnalyzer()
        symbols = a.extract_symbols(src, root=tmp_path)
        names = {s.name for s in symbols}
        assert "public" in names
        assert "_private" not in names

    def test_full_analysis(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        pkg = tmp_path / "myapp"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "main.py").write_text("import os\n\ndef run():\n    pass\n")
        (pkg / "utils.py").write_text("from myapp.main import run\n\nclass Helper:\n    pass\n")

        a = PythonAnalyzer()
        result = a.analyze(tmp_path)
        assert result.language == "python"
        assert len(result.imports) >= 2
        assert len(result.symbols) >= 2
        assert "myapp" in result.domains

    def test_detect_entry_points(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        (tmp_path / "main.py").write_text("print('hello')\n")
        (tmp_path / "other.py").write_text("x = 1\n")

        a = PythonAnalyzer()
        result = a.analyze(tmp_path)
        assert "main.py" in result.entry_points

    def test_discover_excludes_venv(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        venv = tmp_path / ".venv" / "lib"
        venv.mkdir(parents=True)
        (venv / "pkg.py").write_text("x = 1\n")
        (tmp_path / "app.py").write_text("x = 1\n")
        a = PythonAnalyzer()
        result = a.analyze(tmp_path)
        files = {s.file_path for s in result.symbols}
        assert not any(".venv" in f for f in files)

    def test_discover_excludes_tests_when_flag_set(self, tmp_path: Path) -> None:
        from harness_skills.analyzers.python_analyzer import _discover_py_files
        (tmp_path / "test_app.py").write_text("def test_foo(): pass\n")
        (tmp_path / "app.py").write_text("def foo(): pass\n")
        results = _discover_py_files(tmp_path, include_tests=False)
        names = {p.name for p in results}
        assert "test_app.py" not in names
        assert "app.py" in names

    def test_module_name_init_py(self, tmp_path: Path) -> None:
        from harness_skills.analyzers.python_analyzer import _module_name
        pkg = tmp_path / "myapp"
        pkg.mkdir()
        init = pkg / "__init__.py"
        result = _module_name(init, tmp_path)
        assert result == "myapp"

    def test_module_name_value_error(self) -> None:
        from harness_skills.analyzers.python_analyzer import _module_name
        result = _module_name(Path("/other/app.py"), Path("/root"))
        assert result == "app"

    def test_extract_symbols_syntax_error(self, tmp_path: Path) -> None:
        src = tmp_path / "bad.py"
        src.write_text("def broken(:\n")
        a = PythonAnalyzer()
        symbols = a.extract_symbols(src, root=tmp_path)
        assert symbols == []

    def test_detect_patterns_functional(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        # Create many functions and few classes to trigger functional-style
        content = "\n".join(f"def func_{i}(): pass" for i in range(30))
        (tmp_path / "funcs.py").write_text(content)
        a = PythonAnalyzer()
        result = a.analyze(tmp_path)
        # With 30 functions and 0 classes, should detect functional-style
        assert "functional-style" in result.patterns

    def test_detect_patterns_object_oriented(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        content = "\n".join(f"class Class{i}:\n    pass" for i in range(12))
        (tmp_path / "classes.py").write_text(content)
        a = PythonAnalyzer()
        result = a.analyze(tmp_path)
        assert "object-oriented" in result.patterns

    def test_async_function_extracted(self, tmp_path: Path) -> None:
        src = tmp_path / "async_mod.py"
        src.write_text("async def fetch():\n    pass\n")
        a = PythonAnalyzer()
        symbols = a.extract_symbols(src, root=tmp_path)
        names = {s.name for s in symbols}
        assert "fetch" in names
