"""Tests for Java analyzer."""

from __future__ import annotations

from pathlib import Path

from harness_skills.analyzers.java_analyzer import JavaAnalyzer


class TestJavaAnalyzer:

    def test_language(self) -> None:
        assert JavaAnalyzer().language() == "java"

    def test_can_analyze_maven(self, tmp_path: Path) -> None:
        (tmp_path / "pom.xml").write_text("<project></project>")
        assert JavaAnalyzer().can_analyze(tmp_path) is True

    def test_can_analyze_gradle(self, tmp_path: Path) -> None:
        (tmp_path / "build.gradle").write_text("apply plugin: 'java'\n")
        assert JavaAnalyzer().can_analyze(tmp_path) is True

    def test_cannot_analyze(self, tmp_path: Path) -> None:
        assert JavaAnalyzer().can_analyze(tmp_path) is False

    def test_extract_imports(self, tmp_path: Path) -> None:
        src = tmp_path / "App.java"
        src.write_text("import java.util.List;\nimport com.example.Service;\n")
        a = JavaAnalyzer()
        edges = a.extract_imports(src, root=tmp_path)
        targets = {e.target for e in edges}
        assert "java.util.List" in targets
        assert "com.example.Service" in targets

    def test_extract_symbols(self, tmp_path: Path) -> None:
        src = tmp_path / "App.java"
        src.write_text(
            "public class App {\n"
            "    public static final int MAX = 100;\n"
            "    public void run() {}\n"
            "}\n"
        )
        a = JavaAnalyzer()
        symbols = a.extract_symbols(src, root=tmp_path)
        names = {s.name for s in symbols}
        assert "App" in names
        assert "MAX" in names
        assert "run" in names

    def test_file_extensions(self) -> None:
        a = JavaAnalyzer()
        assert ".java" in a.file_extensions()

    def test_can_analyze_gradle_kts(self, tmp_path: Path) -> None:
        (tmp_path / "build.gradle.kts").write_text("plugins { id(\"java\") }")
        assert JavaAnalyzer().can_analyze(tmp_path) is True

    def test_full_analysis(self, tmp_path: Path) -> None:
        (tmp_path / "pom.xml").write_text("<project></project>")
        src = tmp_path / "App.java"
        src.write_text(
            "import java.util.List;\n\n"
            "public class App {\n"
            "    public void run() {}\n"
            "}\n"
        )
        a = JavaAnalyzer()
        result = a.analyze(tmp_path)
        assert result.language == "java"
        assert len(result.imports) >= 1
        assert len(result.symbols) >= 1

    def test_extract_imports_oserror(self, tmp_path: Path) -> None:
        a = JavaAnalyzer()
        assert a.extract_imports(tmp_path / "missing.java") == []

    def test_extract_symbols_oserror(self, tmp_path: Path) -> None:
        a = JavaAnalyzer()
        assert a.extract_symbols(tmp_path / "missing.java") == []

    def test_extract_interface(self, tmp_path: Path) -> None:
        src = tmp_path / "IService.java"
        src.write_text("public interface IService {\n    void run();\n}\n")
        a = JavaAnalyzer()
        symbols = a.extract_symbols(src, root=tmp_path)
        names = {s.name for s in symbols}
        assert "IService" in names
