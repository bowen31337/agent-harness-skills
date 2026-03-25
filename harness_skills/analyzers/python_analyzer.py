"""Python codebase analyzer using stdlib ast (primary) + tree-sitter (enrichment)."""

from __future__ import annotations

import ast
import logging
import sys
from pathlib import Path

from harness_skills.analyzers import register_analyzer
from harness_skills.analyzers.base import AnalysisResult, BaseAnalyzer, Symbol
from harness_skills.utils.import_graph import ImportEdge

logger = logging.getLogger(__name__)

_EXCLUDE_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    "site-packages", "dist", "build", ".mypy_cache", ".ruff_cache",
    ".pytest_cache", ".tox", ".nox", "egg-info",
}

_STDLIB_NAMES: frozenset[str] = (
    frozenset(sys.stdlib_module_names)  # type: ignore[attr-defined]
    if hasattr(sys, "stdlib_module_names")
    else frozenset()
)


def _discover_py_files(root: Path, *, include_tests: bool = True) -> list[Path]:
    """Walk root for .py files, excluding common non-source directories."""
    results: list[Path] = []
    for p in root.rglob("*.py"):
        parts = set(p.relative_to(root).parts)
        if parts & _EXCLUDE_DIRS:
            continue
        if not include_tests and ("test_" in p.name or p.name.endswith("_test.py")):
            continue
        results.append(p)
    return sorted(results)


def _module_name(file_path: Path, root: Path) -> str:
    """Convert a file path to a dotted module name relative to root."""
    try:
        rel = file_path.relative_to(root)
    except ValueError:
        return file_path.stem
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    elif parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    return ".".join(parts)


@register_analyzer
class PythonAnalyzer(BaseAnalyzer):
    """Python analyzer using stdlib ``ast`` with optional tree-sitter enrichment."""

    def language(self) -> str:
        return "python"

    def file_extensions(self) -> tuple[str, ...]:
        return (".py",)

    def can_analyze(self, root: Path) -> bool:
        indicators = ["pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "Pipfile"]
        return any((root / f).exists() for f in indicators)

    def analyze(
        self, root: Path, *, file_paths: list[Path] | None = None
    ) -> AnalysisResult:
        files = file_paths or _discover_py_files(root)
        all_imports: list[ImportEdge] = []
        all_symbols: list[Symbol] = []

        for fp in files:
            try:
                all_imports.extend(self.extract_imports(fp, root=root))
                all_symbols.extend(self.extract_symbols(fp, root=root))
            except Exception:
                logger.debug("Skipping %s: parse error", fp)

        # Infer candidate domains from top-level packages
        domains = self._detect_domains(root)
        patterns = self._detect_patterns(all_symbols)
        entry_points = self._detect_entry_points(root, files)

        return AnalysisResult(
            language="python",
            imports=all_imports,
            symbols=all_symbols,
            domains=domains,
            patterns=patterns,
            entry_points=entry_points,
        )

    def extract_imports(
        self, file_path: Path, *, root: Path | None = None
    ) -> list[ImportEdge]:
        """Extract import edges from a Python file using ``ast``."""
        try:
            source = file_path.read_text(errors="ignore")
            tree = ast.parse(source, filename=str(file_path))
        except (SyntaxError, UnicodeDecodeError):
            return []

        src_root = root or file_path.parent
        src_mod = _module_name(file_path, src_root)
        edges: list[ImportEdge] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    edges.append(ImportEdge(
                        source=src_mod,
                        target=alias.name,
                        import_type="direct",
                        line_number=node.lineno,
                    ))
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    edges.append(ImportEdge(
                        source=src_mod,
                        target=node.module,
                        import_type="from",
                        line_number=node.lineno,
                    ))

        return edges

    def extract_symbols(
        self, file_path: Path, *, root: Path | None = None
    ) -> list[Symbol]:
        """Extract top-level symbols from a Python file."""
        try:
            source = file_path.read_text(errors="ignore")
            tree = ast.parse(source, filename=str(file_path))
        except (SyntaxError, UnicodeDecodeError):
            return []

        src_root = root or file_path.parent
        rel_path = str(file_path.relative_to(src_root)) if root else file_path.name

        # Check for __all__ to determine exported symbols
        all_names: set[str] | None = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "__all__":
                        if isinstance(node.value, (ast.List, ast.Tuple)):
                            all_names = set()
                            for elt in node.value.elts:
                                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                    all_names.add(elt.value)

        symbols: list[Symbol] = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                if not node.name.startswith("_"):
                    exported = all_names is None or node.name in all_names
                    symbols.append(Symbol(
                        name=node.name,
                        kind="function",
                        file_path=rel_path,
                        line_number=node.lineno,
                        exported=exported,
                    ))
            elif isinstance(node, ast.ClassDef):
                if not node.name.startswith("_"):
                    exported = all_names is None or node.name in all_names
                    symbols.append(Symbol(
                        name=node.name,
                        kind="class",
                        file_path=rel_path,
                        line_number=node.lineno,
                        exported=exported,
                    ))
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.isupper():
                        exported = all_names is None or target.id in all_names
                        symbols.append(Symbol(
                            name=target.id,
                            kind="constant",
                            file_path=rel_path,
                            line_number=node.lineno,
                            exported=exported,
                        ))

        return symbols

    def _detect_domains(self, root: Path) -> list[str]:
        """Infer candidate domain names from top-level packages."""
        domains: list[str] = []
        for child in sorted(root.iterdir()):
            if child.is_dir() and (child / "__init__.py").exists():
                name = child.name
                if name not in _EXCLUDE_DIRS and not name.startswith("."):
                    domains.append(name)
        return domains

    def _detect_patterns(self, symbols: list[Symbol]) -> list[str]:
        """Detect common patterns from symbol analysis."""
        patterns: list[str] = []
        class_count = sum(1 for s in symbols if s.kind == "class")
        func_count = sum(1 for s in symbols if s.kind == "function")
        if class_count > 10:
            patterns.append("object-oriented")
        if func_count > class_count * 2:
            patterns.append("functional-style")
        return patterns

    def _detect_entry_points(self, root: Path, files: list[Path]) -> list[str]:
        """Find likely entry point files."""
        entry_names = {"__main__.py", "main.py", "app.py", "cli.py", "manage.py", "wsgi.py"}
        return [
            str(f.relative_to(root))
            for f in files
            if f.name in entry_names
        ]
