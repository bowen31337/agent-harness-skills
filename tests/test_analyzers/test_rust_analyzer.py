"""Tests for Rust analyzer."""

from __future__ import annotations

from pathlib import Path

from harness_skills.analyzers.rust_analyzer import RustAnalyzer


class TestRustAnalyzer:

    def test_language(self) -> None:
        assert RustAnalyzer().language() == "rust"

    def test_can_analyze(self, tmp_path: Path) -> None:
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"\n')
        assert RustAnalyzer().can_analyze(tmp_path) is True

    def test_cannot_analyze(self, tmp_path: Path) -> None:
        assert RustAnalyzer().can_analyze(tmp_path) is False

    def test_extract_imports(self, tmp_path: Path) -> None:
        src = tmp_path / "main.rs"
        src.write_text("use std::io;\nuse serde::Deserialize;\n")
        a = RustAnalyzer()
        edges = a.extract_imports(src, root=tmp_path)
        targets = {e.target for e in edges}
        assert "std.io" in targets
        assert "serde.Deserialize" in targets

    def test_extract_symbols(self, tmp_path: Path) -> None:
        src = tmp_path / "lib.rs"
        src.write_text(
            "pub struct Config {\n    pub port: u16,\n}\n\n"
            "pub fn init() {}\n\n"
            "pub const VERSION: &str = \"1.0\";\n"
        )
        a = RustAnalyzer()
        symbols = a.extract_symbols(src, root=tmp_path)
        names = {s.name for s in symbols}
        assert "Config" in names
        assert "init" in names
        assert "VERSION" in names

    def test_file_extensions(self) -> None:
        a = RustAnalyzer()
        assert ".rs" in a.file_extensions()

    def test_full_analysis(self, tmp_path: Path) -> None:
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"\n')
        src = tmp_path / "main.rs"
        src.write_text("use std::io;\n\npub fn main() {}\n")
        a = RustAnalyzer()
        result = a.analyze(tmp_path)
        assert result.language == "rust"
        assert len(result.imports) >= 1
        assert len(result.symbols) >= 1

    def test_extract_imports_oserror(self, tmp_path: Path) -> None:
        a = RustAnalyzer()
        assert a.extract_imports(tmp_path / "missing.rs") == []

    def test_extract_symbols_oserror(self, tmp_path: Path) -> None:
        a = RustAnalyzer()
        assert a.extract_symbols(tmp_path / "missing.rs") == []

    def test_async_fn_detected(self, tmp_path: Path) -> None:
        src = tmp_path / "lib.rs"
        src.write_text("pub async fn serve() {}\n")
        a = RustAnalyzer()
        symbols = a.extract_symbols(src, root=tmp_path)
        names = {s.name for s in symbols}
        assert "serve" in names

    def test_analyze_excludes_target_dir(self, tmp_path: Path) -> None:
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"\n')
        target = tmp_path / "target" / "debug"
        target.mkdir(parents=True)
        (target / "generated.rs").write_text("pub fn auto_gen() {}\n")
        (tmp_path / "src.rs").write_text("pub fn real() {}\n")
        a = RustAnalyzer()
        result = a.analyze(tmp_path)
        names = {s.name for s in result.symbols}
        assert "auto_gen" not in names
