"""Tests for TypeScript analyzer."""

from __future__ import annotations

from pathlib import Path

from harness_skills.analyzers.typescript_analyzer import TypeScriptAnalyzer


class TestTypeScriptAnalyzer:

    def test_language(self) -> None:
        assert TypeScriptAnalyzer().language() == "typescript"

    def test_can_analyze_with_package_json(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text('{"name": "test"}')
        assert TypeScriptAnalyzer().can_analyze(tmp_path) is True

    def test_can_analyze_with_tsconfig(self, tmp_path: Path) -> None:
        (tmp_path / "tsconfig.json").write_text("{}")
        assert TypeScriptAnalyzer().can_analyze(tmp_path) is True

    def test_cannot_analyze_empty_dir(self, tmp_path: Path) -> None:
        assert TypeScriptAnalyzer().can_analyze(tmp_path) is False

    def test_extract_imports(self, tmp_path: Path) -> None:
        src = tmp_path / "app.ts"
        src.write_text('import { useState } from "react";\nimport axios from "axios";\n')
        a = TypeScriptAnalyzer()
        edges = a.extract_imports(src, root=tmp_path)
        targets = {e.target for e in edges}
        assert "react" in targets
        assert "axios" in targets

    def test_extract_imports_require(self, tmp_path: Path) -> None:
        src = tmp_path / "app.js"
        src.write_text('const fs = require("fs");\n')
        a = TypeScriptAnalyzer()
        edges = a.extract_imports(src, root=tmp_path)
        assert any(e.target == "fs" for e in edges)

    def test_extract_symbols(self, tmp_path: Path) -> None:
        src = tmp_path / "components.tsx"
        src.write_text(
            "export function Button() { return null; }\n"
            "export class Modal {}\n"
            "export const API_URL = 'http://localhost';\n"
        )
        a = TypeScriptAnalyzer()
        symbols = a.extract_symbols(src, root=tmp_path)
        names = {s.name for s in symbols}
        assert "Button" in names
        assert "Modal" in names
        assert "API_URL" in names

    def test_full_analysis(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text('{"name": "test"}')
        src = tmp_path / "src"
        src.mkdir()
        (src / "index.ts").write_text('import { foo } from "./utils";\nexport function main() {}\n')
        (src / "utils.ts").write_text("export function foo() {}\n")
        auth = src / "auth"
        auth.mkdir()
        (auth / "login.ts").write_text("export class LoginPage {}\n")

        a = TypeScriptAnalyzer()
        result = a.analyze(tmp_path)
        assert result.language == "typescript"
        assert len(result.imports) >= 1
        assert len(result.symbols) >= 2
        assert "auth" in result.domains

    def test_file_extensions(self) -> None:
        a = TypeScriptAnalyzer()
        exts = a.file_extensions()
        assert ".ts" in exts
        assert ".tsx" in exts
        assert ".js" in exts

    def test_extract_imports_oserror(self, tmp_path: Path) -> None:
        a = TypeScriptAnalyzer()
        assert a.extract_imports(tmp_path / "missing.ts") == []

    def test_extract_symbols_oserror(self, tmp_path: Path) -> None:
        a = TypeScriptAnalyzer()
        assert a.extract_symbols(tmp_path / "missing.ts") == []

    def test_export_default(self, tmp_path: Path) -> None:
        src = tmp_path / "App.tsx"
        src.write_text("export default class App {}\n")
        a = TypeScriptAnalyzer()
        symbols = a.extract_symbols(src, root=tmp_path)
        names = {s.name for s in symbols}
        assert "App" in names

    def test_detect_domains_no_src(self, tmp_path: Path) -> None:
        a = TypeScriptAnalyzer()
        domains = a._detect_domains(tmp_path)
        assert domains == []

    def test_excludes_node_modules(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text('{"name": "test"}')
        nm = tmp_path / "node_modules" / "pkg"
        nm.mkdir(parents=True)
        (nm / "index.ts").write_text("export function lib() {}\n")
        (tmp_path / "app.ts").write_text("export function main() {}\n")
        a = TypeScriptAnalyzer()
        result = a.analyze(tmp_path)
        names = {s.name for s in result.symbols}
        assert "lib" not in names
