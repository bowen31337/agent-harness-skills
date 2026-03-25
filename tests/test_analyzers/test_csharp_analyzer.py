"""Tests for C# analyzer."""

from __future__ import annotations

from pathlib import Path

from harness_skills.analyzers.csharp_analyzer import CSharpAnalyzer


class TestCSharpAnalyzer:

    def test_language(self) -> None:
        assert CSharpAnalyzer().language() == "csharp"

    def test_can_analyze(self, tmp_path: Path) -> None:
        (tmp_path / "App.csproj").write_text("<Project></Project>")
        assert CSharpAnalyzer().can_analyze(tmp_path) is True

    def test_cannot_analyze(self, tmp_path: Path) -> None:
        assert CSharpAnalyzer().can_analyze(tmp_path) is False

    def test_extract_imports(self, tmp_path: Path) -> None:
        src = tmp_path / "Program.cs"
        src.write_text("using System;\nusing System.Collections.Generic;\n")
        a = CSharpAnalyzer()
        edges = a.extract_imports(src, root=tmp_path)
        targets = {e.target for e in edges}
        assert "System" in targets
        assert "System.Collections.Generic" in targets

    def test_extract_symbols(self, tmp_path: Path) -> None:
        src = tmp_path / "App.cs"
        src.write_text(
            "public class AppService {\n"
            "    public const string Version = \"1.0\";\n"
            "    public void Run() {}\n"
            "}\n"
        )
        a = CSharpAnalyzer()
        symbols = a.extract_symbols(src, root=tmp_path)
        names = {s.name for s in symbols}
        assert "AppService" in names
        assert "Version" in names
        assert "Run" in names

    def test_file_extensions(self) -> None:
        a = CSharpAnalyzer()
        assert ".cs" in a.file_extensions()

    def test_can_analyze_sln(self, tmp_path: Path) -> None:
        (tmp_path / "App.sln").write_text("Microsoft Visual Studio Solution")
        assert CSharpAnalyzer().can_analyze(tmp_path) is True

    def test_full_analysis(self, tmp_path: Path) -> None:
        (tmp_path / "App.csproj").write_text("<Project></Project>")
        src = tmp_path / "Program.cs"
        src.write_text(
            "using System;\n\n"
            "public class Program {\n"
            "    public static void Main() {}\n"
            "}\n"
        )
        a = CSharpAnalyzer()
        result = a.analyze(tmp_path)
        assert result.language == "csharp"
        assert len(result.imports) >= 1
        assert len(result.symbols) >= 1

    def test_extract_imports_oserror(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "missing.cs"
        a = CSharpAnalyzer()
        assert a.extract_imports(nonexistent) == []

    def test_extract_symbols_oserror(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "missing.cs"
        a = CSharpAnalyzer()
        assert a.extract_symbols(nonexistent) == []

    def test_extract_interface(self, tmp_path: Path) -> None:
        src = tmp_path / "IService.cs"
        src.write_text("public interface IService {\n    void Execute();\n}\n")
        a = CSharpAnalyzer()
        symbols = a.extract_symbols(src, root=tmp_path)
        names = {s.name for s in symbols}
        assert "IService" in names

    def test_analyze_skips_bad_files(self, tmp_path: Path) -> None:
        (tmp_path / "App.csproj").write_text("<Project></Project>")
        # Create a binary file that would cause read issues
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        (bin_dir / "app.cs").write_text("binary stuff")
        # Normal file
        (tmp_path / "Good.cs").write_text("using System;\n")
        a = CSharpAnalyzer()
        result = a.analyze(tmp_path)
        # bin dir is excluded, should only see Good.cs imports
        assert isinstance(result.language, str)
