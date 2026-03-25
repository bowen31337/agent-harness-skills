"""TypeScript/JavaScript codebase analyzer using regex (primary) + tree-sitter (enrichment)."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from harness_skills.analyzers import register_analyzer
from harness_skills.analyzers.base import AnalysisResult, BaseAnalyzer, Symbol
from harness_skills.utils.import_graph import ImportEdge

logger = logging.getLogger(__name__)

_EXCLUDE_DIRS = {
    "node_modules", ".git", "dist", "build", ".next", ".nuxt",
    "coverage", "__pycache__", ".turbo",
}

_IMPORT_RE = re.compile(
    r"""(?:import\s+(?:(?:\{[^}]+\}|[\w*]+)\s+from\s+)?['"]([^'"]+)['"]"""
    r"""|require\s*\(\s*['"]([^'"]+)['"]\s*\))""",
    re.MULTILINE,
)

_EXPORT_FUNC_RE = re.compile(r"export\s+(?:async\s+)?function\s+(\w+)")
_EXPORT_CLASS_RE = re.compile(r"export\s+class\s+(\w+)")
_EXPORT_CONST_RE = re.compile(r"export\s+(?:const|let|var)\s+(\w+)")
_EXPORT_DEFAULT_RE = re.compile(r"export\s+default\s+(?:class|function)\s+(\w+)")


def _discover_ts_files(root: Path) -> list[Path]:
    results: list[Path] = []
    for ext in ("*.ts", "*.tsx", "*.js", "*.jsx"):
        for p in root.rglob(ext):
            parts = set(p.relative_to(root).parts)
            if parts & _EXCLUDE_DIRS:
                continue
            results.append(p)
    return sorted(results)


@register_analyzer
class TypeScriptAnalyzer(BaseAnalyzer):
    """TypeScript/JavaScript analyzer using regex with tree-sitter fallback."""

    def language(self) -> str:
        return "typescript"

    def file_extensions(self) -> tuple[str, ...]:
        return (".ts", ".tsx", ".js", ".jsx")

    def can_analyze(self, root: Path) -> bool:
        return (root / "package.json").exists() or (root / "tsconfig.json").exists()

    def analyze(
        self, root: Path, *, file_paths: list[Path] | None = None
    ) -> AnalysisResult:
        files = file_paths or _discover_ts_files(root)
        all_imports: list[ImportEdge] = []
        all_symbols: list[Symbol] = []

        for fp in files:
            try:
                all_imports.extend(self.extract_imports(fp, root=root))
                all_symbols.extend(self.extract_symbols(fp, root=root))
            except Exception:
                logger.debug("Skipping %s: parse error", fp)

        domains = self._detect_domains(root)
        return AnalysisResult(
            language="typescript",
            imports=all_imports,
            symbols=all_symbols,
            domains=domains,
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
            m = _IMPORT_RE.search(line)
            if m:
                target = m.group(1) or m.group(2)
                edges.append(ImportEdge(
                    source=src_mod,
                    target=target,
                    import_type="from" if "from" in line else "direct",
                    line_number=i,
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
                (_EXPORT_CLASS_RE, "class"),
                (_EXPORT_FUNC_RE, "function"),
                (_EXPORT_CONST_RE, "constant"),
                (_EXPORT_DEFAULT_RE, "class"),
            ]:
                m = pattern.search(line)
                if m:
                    symbols.append(Symbol(
                        name=m.group(1), kind=kind,
                        file_path=rel_path, line_number=i,
                    ))

        return symbols

    def _detect_domains(self, root: Path) -> list[str]:
        src = root / "src"
        if not src.is_dir():
            return []
        return sorted(
            d.name for d in src.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        )
