"""Rust codebase analyzer using regex."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from harness_skills.analyzers import register_analyzer
from harness_skills.analyzers.base import AnalysisResult, BaseAnalyzer, Symbol
from harness_skills.utils.import_graph import ImportEdge

logger = logging.getLogger(__name__)

_USE_RE = re.compile(r"^use\s+([\w:]+)")
_FN_RE = re.compile(r"^pub\s+(?:async\s+)?fn\s+(\w+)")
_STRUCT_RE = re.compile(r"^pub\s+struct\s+(\w+)")
_CONST_RE = re.compile(r"^pub\s+const\s+(\w+)")


@register_analyzer
class RustAnalyzer(BaseAnalyzer):

    def language(self) -> str:
        return "rust"

    def file_extensions(self) -> tuple[str, ...]:
        return (".rs",)

    def can_analyze(self, root: Path) -> bool:
        return (root / "Cargo.toml").exists()

    def analyze(
        self, root: Path, *, file_paths: list[Path] | None = None
    ) -> AnalysisResult:
        files = file_paths or sorted(
            p for p in root.rglob("*.rs")
            if ".git" not in p.parts and "target" not in p.parts
        )
        all_imports: list[ImportEdge] = []
        all_symbols: list[Symbol] = []

        for fp in files:
            try:
                all_imports.extend(self.extract_imports(fp, root=root))
                all_symbols.extend(self.extract_symbols(fp, root=root))
            except Exception:
                logger.debug("Skipping %s", fp)

        return AnalysisResult(
            language="rust", imports=all_imports, symbols=all_symbols,
        )

    def extract_imports(
        self, file_path: Path, *, root: Path | None = None
    ) -> list[ImportEdge]:
        try:
            source = file_path.read_text(errors="ignore")
        except OSError:
            return []

        src_root = root or file_path.parent
        src_mod = str(file_path.relative_to(src_root))
        edges: list[ImportEdge] = []

        for i, line in enumerate(source.splitlines(), 1):
            m = _USE_RE.match(line.strip())
            if m:
                edges.append(ImportEdge(
                    source=src_mod, target=m.group(1).replace("::", "."),
                    import_type="use", line_number=i,
                ))

        return edges

    def extract_symbols(
        self, file_path: Path, *, root: Path | None = None
    ) -> list[Symbol]:
        try:
            source = file_path.read_text(errors="ignore")
        except OSError:
            return []

        src_root = root or file_path.parent
        rel_path = str(file_path.relative_to(src_root))
        symbols: list[Symbol] = []

        for i, line in enumerate(source.splitlines(), 1):
            for pattern, kind in [
                (_FN_RE, "function"),
                (_STRUCT_RE, "class"),
                (_CONST_RE, "constant"),
            ]:
                m = pattern.match(line.strip())
                if m:
                    symbols.append(Symbol(
                        name=m.group(1), kind=kind,
                        file_path=rel_path, line_number=i,
                    ))

        return symbols
