"""Go codebase analyzer using regex (primary) + tree-sitter (enrichment)."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from harness_skills.analyzers import register_analyzer
from harness_skills.analyzers.base import AnalysisResult, BaseAnalyzer, Symbol
from harness_skills.utils.import_graph import ImportEdge

logger = logging.getLogger(__name__)

_EXCLUDE_DIRS = {".git", "vendor", "node_modules", "testdata"}

_IMPORT_RE = re.compile(r'"([^"]+)"')
_FUNC_RE = re.compile(r"^func\s+(?:\([^)]+\)\s+)?(\w+)")
_TYPE_RE = re.compile(r"^type\s+(\w+)\s+struct")
_CONST_RE = re.compile(r"^(?:const|var)\s+(\w+)")


def _discover_go_files(root: Path) -> list[Path]:
    results: list[Path] = []
    for p in root.rglob("*.go"):
        parts = set(p.relative_to(root).parts)
        if parts & _EXCLUDE_DIRS:
            continue
        if p.name.endswith("_test.go"):
            continue
        results.append(p)
    return sorted(results)


@register_analyzer
class GoAnalyzer(BaseAnalyzer):

    def language(self) -> str:
        return "go"

    def file_extensions(self) -> tuple[str, ...]:
        return (".go",)

    def can_analyze(self, root: Path) -> bool:
        return (root / "go.mod").exists()

    def analyze(
        self, root: Path, *, file_paths: list[Path] | None = None
    ) -> AnalysisResult:
        files = file_paths or _discover_go_files(root)
        all_imports: list[ImportEdge] = []
        all_symbols: list[Symbol] = []

        for fp in files:
            try:
                all_imports.extend(self.extract_imports(fp, root=root))
                all_symbols.extend(self.extract_symbols(fp, root=root))
            except Exception:
                logger.debug("Skipping %s", fp)

        return AnalysisResult(
            language="go",
            imports=all_imports,
            symbols=all_symbols,
            domains=self._detect_domains(root),
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
        in_import_block = False

        for i, line in enumerate(source.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("import ("):
                in_import_block = True
                continue
            if in_import_block and stripped == ")":
                in_import_block = False
                continue
            if in_import_block or stripped.startswith("import "):
                m = _IMPORT_RE.search(line)
                if m:
                    edges.append(ImportEdge(
                        source=src_mod, target=m.group(1),
                        import_type="direct", line_number=i,
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
                (_FUNC_RE, "function"),
                (_TYPE_RE, "class"),
                (_CONST_RE, "constant"),
            ]:
                m = pattern.match(line)
                if m:
                    name = m.group(1)
                    exported = name[0].isupper() if name else False
                    symbols.append(Symbol(
                        name=name, kind=kind,
                        file_path=rel_path, line_number=i,
                        exported=exported,
                    ))

        return symbols

    def _detect_domains(self, root: Path) -> list[str]:
        domains: list[str] = []
        for child in sorted(root.iterdir()):
            if child.is_dir() and not child.name.startswith(".") and child.name not in _EXCLUDE_DIRS:
                go_files = list(child.glob("*.go"))
                if go_files:
                    domains.append(child.name)
        return domains
