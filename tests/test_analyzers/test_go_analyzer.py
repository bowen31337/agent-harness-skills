"""Tests for Go analyzer."""

from __future__ import annotations

from pathlib import Path

from harness_skills.analyzers.go_analyzer import GoAnalyzer


class TestGoAnalyzer:

    def test_language(self) -> None:
        assert GoAnalyzer().language() == "go"

    def test_can_analyze(self, tmp_path: Path) -> None:
        (tmp_path / "go.mod").write_text("module example.com/myapp\n\ngo 1.21\n")
        assert GoAnalyzer().can_analyze(tmp_path) is True

    def test_cannot_analyze(self, tmp_path: Path) -> None:
        assert GoAnalyzer().can_analyze(tmp_path) is False

    def test_extract_imports(self, tmp_path: Path) -> None:
        src = tmp_path / "main.go"
        src.write_text('package main\n\nimport (\n\t"fmt"\n\t"os"\n)\n')
        a = GoAnalyzer()
        edges = a.extract_imports(src, root=tmp_path)
        targets = {e.target for e in edges}
        assert "fmt" in targets
        assert "os" in targets

    def test_extract_symbols(self, tmp_path: Path) -> None:
        src = tmp_path / "handler.go"
        src.write_text(
            "package main\n\n"
            "type Server struct {\n\tPort int\n}\n\n"
            "func NewServer() *Server {\n\treturn &Server{}\n}\n\n"
            "const DefaultPort = 8080\n"
        )
        a = GoAnalyzer()
        symbols = a.extract_symbols(src, root=tmp_path)
        names = {s.name for s in symbols}
        assert "Server" in names
        assert "NewServer" in names
        assert "DefaultPort" in names

    def test_exported_check(self, tmp_path: Path) -> None:
        src = tmp_path / "pkg.go"
        src.write_text("package pkg\n\nfunc Public() {}\nfunc private() {}\n")
        a = GoAnalyzer()
        symbols = a.extract_symbols(src, root=tmp_path)
        pub = [s for s in symbols if s.name == "Public"]
        priv = [s for s in symbols if s.name == "private"]
        assert pub[0].exported is True
        assert priv[0].exported is False

    def test_full_analysis(self, tmp_path: Path) -> None:
        (tmp_path / "go.mod").write_text("module example.com/app\n\ngo 1.21\n")
        (tmp_path / "main.go").write_text(
            'package main\n\nimport "fmt"\n\nfunc main() {\n\tfmt.Println("hi")\n}\n'
        )
        handlers = tmp_path / "handlers"
        handlers.mkdir()
        (handlers / "api.go").write_text("package handlers\n\nfunc HandleRequest() {}\n")

        a = GoAnalyzer()
        result = a.analyze(tmp_path)
        assert result.language == "go"
        assert len(result.imports) >= 1
        assert len(result.symbols) >= 1
        assert "handlers" in result.domains

    def test_file_extensions(self) -> None:
        a = GoAnalyzer()
        assert ".go" in a.file_extensions()

    def test_extract_imports_oserror(self, tmp_path: Path) -> None:
        a = GoAnalyzer()
        assert a.extract_imports(tmp_path / "missing.go") == []

    def test_extract_symbols_oserror(self, tmp_path: Path) -> None:
        a = GoAnalyzer()
        assert a.extract_symbols(tmp_path / "missing.go") == []

    def test_single_import_line(self, tmp_path: Path) -> None:
        src = tmp_path / "main.go"
        src.write_text('package main\n\nimport "fmt"\n')
        a = GoAnalyzer()
        edges = a.extract_imports(src, root=tmp_path)
        assert any(e.target == "fmt" for e in edges)

    def test_excludes_test_files(self, tmp_path: Path) -> None:
        (tmp_path / "go.mod").write_text("module ex\n\ngo 1.21\n")
        (tmp_path / "main.go").write_text("package main\n\nfunc Main() {}\n")
        (tmp_path / "main_test.go").write_text("package main\n\nfunc TestMain() {}\n")
        a = GoAnalyzer()
        result = a.analyze(tmp_path)
        files = {s.file_path for s in result.symbols}
        assert not any("_test.go" in f for f in files)

    def test_excludes_vendor_dir(self, tmp_path: Path) -> None:
        (tmp_path / "go.mod").write_text("module ex\n\ngo 1.21\n")
        vendor = tmp_path / "vendor" / "pkg"
        vendor.mkdir(parents=True)
        (vendor / "lib.go").write_text("package pkg\n\nfunc VendorFunc() {}\n")
        (tmp_path / "main.go").write_text("package main\n\nfunc Main() {}\n")
        a = GoAnalyzer()
        result = a.analyze(tmp_path)
        names = {s.name for s in result.symbols}
        assert "VendorFunc" not in names
