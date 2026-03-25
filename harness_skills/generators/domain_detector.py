"""Domain boundary inference from directory structure and import clustering."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from harness_skills.utils.import_graph import ImportGraph

_EXCLUDE_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    "site-packages", "dist", "build", ".mypy_cache", ".ruff_cache",
    "tests", "test", "docs", "scripts", ".github", ".gitlab",
}


@dataclass
class DetectedDomain:
    """A candidate domain boundary in the codebase."""

    name: str
    root_path: str
    file_count: int = 0
    internal_imports: int = 0
    external_imports: int = 0
    confidence: float = 0.0


def detect_domains(
    root: Path,
    import_graph: ImportGraph | None = None,
    *,
    min_files: int = 2,
    min_confidence: float = 0.3,
) -> list[DetectedDomain]:
    """Detect candidate domain boundaries from directory structure and imports.

    Strategy:
    1. Scan for directories containing source files (heuristic).
    2. If an ImportGraph is available, compute import clustering to score confidence.
    3. Return domains sorted by confidence descending.
    """
    candidates: dict[str, DetectedDomain] = {}

    # Heuristic: directories with source files
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name.startswith(".") or child.name in _EXCLUDE_DIRS:
            continue
        files = _count_source_files(child)
        if files >= min_files:
            candidates[child.name] = DetectedDomain(
                name=child.name,
                root_path=str(child.relative_to(root)),
                file_count=files,
                confidence=0.5,  # baseline for having enough files
            )

    # Also check src/<name>/ pattern
    src = root / "src"
    if src.is_dir():
        for child in sorted(src.iterdir()):
            if not child.is_dir() or child.name.startswith(".") or child.name in _EXCLUDE_DIRS:
                continue
            files = _count_source_files(child)
            if files >= min_files:
                key = f"src/{child.name}"
                candidates[key] = DetectedDomain(
                    name=child.name,
                    root_path=key,
                    file_count=files,
                    confidence=0.5,
                )

    # Import clustering enrichment
    if import_graph and candidates:
        clusters = import_graph.clusters(depth=1)
        for domain_key, domain in candidates.items():
            name = domain.name
            if name in clusters:
                cluster_mods = clusters[name]
                internal = 0
                external = 0
                for mod in cluster_mods:
                    for dep in import_graph.dependencies_of(mod):
                        if any(dep.startswith(cm.split(".")[0]) for cm in cluster_mods):
                            internal += 1
                        else:
                            external += 1
                domain.internal_imports = internal
                domain.external_imports = external
                total = internal + external
                if total > 0:
                    domain.confidence = min(1.0, 0.3 + 0.7 * (internal / total))

    result = [d for d in candidates.values() if d.confidence >= min_confidence]
    result.sort(key=lambda d: (-d.confidence, d.name))
    return result


def _count_source_files(directory: Path) -> int:
    """Count source files in a directory (non-recursive for top-level)."""
    extensions = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".cs"}
    count = 0
    for p in directory.rglob("*"):
        if p.is_file() and p.suffix in extensions:
            parts = set(p.relative_to(directory).parts)
            if not parts & _EXCLUDE_DIRS:
                count += 1
    return count
