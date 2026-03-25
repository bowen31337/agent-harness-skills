"""Pattern frequency extraction for golden principles generation."""

from __future__ import annotations

import ast
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_EXCLUDE_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    "site-packages", "dist", "build",
}


@dataclass
class PatternFrequency:
    """A detected code pattern with frequency data."""

    pattern_name: str
    category: str  # "decorator", "base_class", "naming", "error_handling"
    occurrences: int = 0
    example_files: list[str] = field(default_factory=list)
    suggested_principle: str = ""


def extract_patterns(
    root: Path,
    *,
    max_examples: int = 3,
) -> list[PatternFrequency]:
    """Scan Python files for recurring patterns and return frequency-ranked results."""
    decorator_counts: Counter[str] = Counter()
    base_class_counts: Counter[str] = Counter()
    decorator_files: dict[str, list[str]] = {}
    base_class_files: dict[str, list[str]] = {}

    py_files = [
        p for p in root.rglob("*.py")
        if not (set(p.relative_to(root).parts) & _EXCLUDE_DIRS)
    ]

    for py_file in py_files:
        try:
            source = py_file.read_text(errors="ignore")
            tree = ast.parse(source, filename=str(py_file))
        except (SyntaxError, UnicodeDecodeError):
            continue

        rel = str(py_file.relative_to(root))

        for node in ast.walk(tree):
            # Decorator patterns
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                for dec in node.decorator_list:
                    name = _decorator_name(dec)
                    if name:
                        decorator_counts[name] += 1
                        decorator_files.setdefault(name, []).append(rel)

            # Base class patterns
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    name = _node_name(base)
                    if name and name not in ("object",):
                        base_class_counts[name] += 1
                        base_class_files.setdefault(name, []).append(rel)

    results: list[PatternFrequency] = []

    # Decorator patterns
    for name, count in decorator_counts.most_common(20):
        if count >= 2:
            results.append(PatternFrequency(
                pattern_name=f"@{name}",
                category="decorator",
                occurrences=count,
                example_files=decorator_files[name][:max_examples],
                suggested_principle=f"Use @{name} decorator consistently for this pattern.",
            ))

    # Base class patterns
    for name, count in base_class_counts.most_common(20):
        if count >= 2:
            results.append(PatternFrequency(
                pattern_name=f"extends {name}",
                category="base_class",
                occurrences=count,
                example_files=base_class_files[name][:max_examples],
                suggested_principle=f"New components of this type should extend {name}.",
            ))

    results.sort(key=lambda p: -p.occurrences)
    return results


def _decorator_name(node: ast.expr) -> str | None:
    """Extract a human-readable name from a decorator AST node."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        value = _node_name(node.value)
        return f"{value}.{node.attr}" if value else node.attr
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    return None


def _node_name(node: ast.expr) -> str | None:
    """Extract a name from an AST expression node."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        value = _node_name(node.value)
        return f"{value}.{node.attr}" if value else node.attr
    return None


_EFFORT_THRESHOLDS = [
    (10, "low"),
    (25, "medium"),
    (50, "high"),
]


def _estimate_effort(occurrences: int) -> str:
    """Estimate cleanup effort based on how many occurrences need enforcement."""
    for threshold, level in _EFFORT_THRESHOLDS:
        if occurrences <= threshold:
            return level
    return "very-high"


def _slugify(name: str) -> str:
    """Convert a pattern name to a URL/ID-safe slug."""
    slug = name.lower().replace("@", "").replace(" ", "-")
    slug = re.sub(r"[^a-z0-9\-]", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug


def generate_cleanup_tasks(
    patterns: list[PatternFrequency],
    *,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Generate YAML cleanup task definitions from pattern frequency data.

    Each task represents a principle that should be enforced more broadly
    across the codebase. Tasks are derived from the pattern frequency
    results produced by ``extract_patterns()``.

    Args:
        patterns: Pattern frequency results to convert into tasks.
        output_path: Optional path to write the YAML file. If *None*,
            the YAML dict is returned without writing to disk.

    Returns:
        The generated YAML structure as a Python dict.
    """
    tasks: list[dict[str, Any]] = []
    for pattern in patterns:
        task_id = f"cleanup-{_slugify(pattern.pattern_name)}"
        file_glob = "**/*.py"
        tasks.append({
            "id": task_id,
            "title": f"Enforce {pattern.pattern_name} pattern across codebase",
            "description": (
                f"Pattern '{pattern.pattern_name}' ({pattern.category}) appears "
                f"{pattern.occurrences} time(s). {pattern.suggested_principle}"
            ),
            "file_glob": file_glob,
            "estimated_effort": _estimate_effort(pattern.occurrences),
        })

    result: dict[str, Any] = {
        "task_count": len(tasks),
        "tasks": tasks,
    }

    if output_path is not None:
        try:
            import yaml
        except ImportError:  # pragma: no cover
            # Fall back to writing a simple representation if PyYAML missing
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(str(result))
            return result
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(yaml.dump(result, default_flow_style=False, sort_keys=False))

    return result
