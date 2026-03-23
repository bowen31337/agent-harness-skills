"""
harness_skills/generators/import_convention_detector.py
=========================================================
Scans Python source files to detect prevailing import ordering and grouping
conventions, then generates a principle entry that matches the most common
patterns found across the codebase.

Public API
----------
    detect_import_conventions(root, *, known_first_party, min_files)
        -> ImportConventionResult

    generate_import_principle(result, *, principle_id, applies_to)
        -> dict  (principle entry compatible with .claude/principles.yaml)

Usage::

    from harness_skills.generators.import_convention_detector import (
        detect_import_conventions,
        generate_import_principle,
    )

    result = detect_import_conventions(".")
    principle = generate_import_principle(result, principle_id="P013")
    print(principle["rule"])
"""

from __future__ import annotations

import ast
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
import sys

# ---------------------------------------------------------------------------
# Standard-library module name set (Python 3.10+ exposes sys.stdlib_module_names)
# ---------------------------------------------------------------------------

_STDLIB_NAMES: frozenset[str] = (
    frozenset(sys.stdlib_module_names)  # type: ignore[attr-defined]
    if hasattr(sys, "stdlib_module_names")
    else frozenset()
)

# Future pseudo-module name
_FUTURE_MODULE = "__future__"

# Canonical isort group labels in precedence order
_GROUP_ORDER = ("future", "stdlib", "third_party", "first_party")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _classify_import(
    node: ast.Import | ast.ImportFrom,
    known_first_party: frozenset[str],
) -> str:
    """Return the import group label for *node*.

    Groups (in isort canonical order):
        - ``"future"``      — ``from __future__ import …``
        - ``"stdlib"``      — modules in :data:`sys.stdlib_module_names`
        - ``"third_party"`` — anything else that is not first-party
        - ``"first_party"`` — packages listed in *known_first_party*
    """
    if isinstance(node, ast.ImportFrom):
        # Relative imports (level > 0) are always intra-package / first-party
        if node.level and node.level > 0:
            return "first_party"
        module_root = (node.module or "").split(".")[0]
        if module_root == _FUTURE_MODULE:
            return "future"
    else:
        module_root = node.names[0].name.split(".")[0]

    if module_root in known_first_party:
        return "first_party"
    if module_root in _STDLIB_NAMES:
        return "stdlib"
    return "third_party"


def _group_rank(label: str) -> int:
    """Return sort key for a group label; unknown labels sort last."""
    try:
        return _GROUP_ORDER.index(label)
    except ValueError:
        return len(_GROUP_ORDER)


def _is_sorted(names: list[str]) -> bool:
    """Return True iff *names* is already in case-insensitive ascending order."""
    lowered = [n.lower() for n in names]
    return lowered == sorted(lowered)


def _import_sort_key(node: ast.Import | ast.ImportFrom) -> str:
    """Return a string key used for intra-group alphabetical comparison."""
    if isinstance(node, ast.ImportFrom):
        module = node.module or ""
        alias_names = ",".join(a.name for a in node.names)
        return f"{module}.{alias_names}"
    return node.names[0].name


# ---------------------------------------------------------------------------
# Per-file analysis
# ---------------------------------------------------------------------------


@dataclass
class _FileStats:
    """Raw import statistics for a single Python source file."""

    path: Path
    parse_error: bool = False
    # True if ``from __future__ import annotations`` is the very first import
    future_annotations_first: bool = False
    # True if all groups appear in isort canonical order (no out-of-order group)
    group_order_correct: bool = False
    # True if every pair of adjacent different-group imports is separated by
    # at least one blank line
    blank_line_separation: bool = False
    # True if imports within every non-empty group are alphabetically sorted
    sorted_within_groups: bool = False
    # True if any relative import is present (``from .foo import …``)
    has_relative_imports: bool = False


def _analyse_file(path: Path, known_first_party: frozenset[str]) -> _FileStats:
    """Parse *path* and return a :class:`_FileStats` for it."""
    stats = _FileStats(path=path)

    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        stats.parse_error = True
        return stats

    # ------------------------------------------------------------------ #
    # Collect top-level import nodes with their source line numbers        #
    # ------------------------------------------------------------------ #
    import_nodes: list[ast.Import | ast.ImportFrom] = []
    for _node in ast.walk(tree):
        # Only consider module-level imports (direct children of Module)
        break  # ast.walk doesn't preserve parent; use direct children instead

    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            import_nodes.append(node)

    if not import_nodes:
        return stats

    # ------------------------------------------------------------------ #
    # 1. future-annotations first                                          #
    # ------------------------------------------------------------------ #
    first = import_nodes[0]
    if (
        isinstance(first, ast.ImportFrom)
        and first.module == _FUTURE_MODULE
        and any(alias.name == "annotations" for alias in first.names)
    ):
        stats.future_annotations_first = True

    # ------------------------------------------------------------------ #
    # 2. Classify each import into a group                                 #
    # ------------------------------------------------------------------ #
    groups: list[str] = [
        _classify_import(n, known_first_party) for n in import_nodes
    ]

    # ------------------------------------------------------------------ #
    # 3. Relative imports present?                                         #
    # ------------------------------------------------------------------ #
    stats.has_relative_imports = any(
        isinstance(n, ast.ImportFrom) and n.level and n.level > 0
        for n in import_nodes
    )

    # ------------------------------------------------------------------ #
    # 4. Group order correct?                                              #
    # Strip duplicate consecutive labels to get ordered unique sequence.  #
    # ------------------------------------------------------------------ #
    seen_groups: list[str] = []
    for g in groups:
        if not seen_groups or g != seen_groups[-1]:
            seen_groups.append(g)

    ranks = [_group_rank(g) for g in seen_groups]
    stats.group_order_correct = ranks == sorted(ranks)

    # ------------------------------------------------------------------ #
    # 5. Blank-line separation between groups                              #
    # We look at the *end* line of one import node and the *start* line   #
    # of the next.  A gap of > 1 line means there is at least one blank.  #
    # ------------------------------------------------------------------ #
    all_separated = True
    if len(import_nodes) > 1:
        for prev_node, curr_node, prev_group, curr_group in zip(
            import_nodes,
            import_nodes[1:],
            groups,
            groups[1:],
            strict=False,
        ):
            if prev_group == curr_group:
                continue  # same group — no separation required
            # ast nodes carry lineno (1-based)
            prev_end = getattr(prev_node, "end_lineno", prev_node.lineno)
            curr_start = curr_node.lineno
            if curr_start - prev_end < 2:
                # Adjacent lines → no blank line between them
                all_separated = False
                break
    stats.blank_line_separation = all_separated

    # ------------------------------------------------------------------ #
    # 6. Alphabetical sorting within groups                                #
    # ------------------------------------------------------------------ #
    # Collect per-group lists of sort keys
    per_group: dict[str, list[str]] = {}
    for node, group in zip(import_nodes, groups, strict=False):
        per_group.setdefault(group, []).append(_import_sort_key(node))

    stats.sorted_within_groups = all(
        _is_sorted(keys) for keys in per_group.values() if len(keys) > 1
    )

    return stats


# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------


@dataclass
class ImportConventionResult:
    """Aggregated import convention statistics across multiple Python files.

    Each ``*_count`` field records the number of files that exhibit the
    corresponding pattern.  The ``uses_*`` boolean flags are ``True`` when
    the pattern is present in the majority (> 50 %) of successfully parsed
    files.
    """

    files_scanned: int = 0
    files_with_parse_errors: int = 0

    future_annotations_first_count: int = 0
    group_order_correct_count: int = 0
    blank_line_separation_count: int = 0
    sorted_within_groups_count: int = 0
    relative_imports_count: int = 0

    # Majority-vote booleans
    uses_future_annotations_first: bool = False
    uses_group_order: bool = False
    uses_blank_line_separation: bool = False
    uses_sorted_within_groups: bool = False
    uses_relative_imports: bool = False

    # Detected first-party package names (top-level dirs containing __init__.py)
    detected_first_party: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_import_conventions(
    root: str | Path,
    *,
    known_first_party: Sequence[str] | None = None,
    min_files: int = 1,
    exclude_dirs: Sequence[str] = (
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        "env",
        "node_modules",
        "dist",
        "build",
        ".tox",
        "site-packages",
    ),
) -> ImportConventionResult:
    """Scan Python files under *root* and return prevailing import conventions.

    Parameters
    ----------
    root:
        Project root directory to search recursively.
    known_first_party:
        Package names to classify as *first-party*.  When ``None`` the
        function auto-detects first-party packages by looking for top-level
        directories that contain an ``__init__.py``.
    min_files:
        Minimum number of successfully parsed files required to set the
        majority-vote booleans.  Defaults to ``1`` (any file is enough).
    exclude_dirs:
        Directory names to skip during traversal.

    Returns
    -------
    ImportConventionResult
        Aggregated statistics and majority-vote flags.
    """
    root = Path(root)
    exclude_set = frozenset(exclude_dirs)

    # ------------------------------------------------------------------ #
    # Auto-detect first-party packages                                     #
    # ------------------------------------------------------------------ #
    if known_first_party is None:
        fp_names: list[str] = []
        for child in root.iterdir():
            if child.is_dir() and (child / "__init__.py").exists() and child.name not in exclude_set:
                fp_names.append(child.name)
        fp_frozenset = frozenset(fp_names)
    else:
        fp_names = list(known_first_party)
        fp_frozenset = frozenset(fp_names)

    # ------------------------------------------------------------------ #
    # Collect Python files (excluding excluded dirs)                       #
    # ------------------------------------------------------------------ #
    py_files: list[Path] = []
    for py_file in root.rglob("*.py"):
        if any(part in exclude_set for part in py_file.parts):
            continue
        py_files.append(py_file)

    result = ImportConventionResult(detected_first_party=sorted(fp_names))

    if not py_files:
        return result

    # ------------------------------------------------------------------ #
    # Analyse each file                                                    #
    # ------------------------------------------------------------------ #
    file_stats: list[_FileStats] = [
        _analyse_file(f, fp_frozenset) for f in py_files
    ]

    result.files_scanned = len(file_stats)
    result.files_with_parse_errors = sum(1 for s in file_stats if s.parse_error)

    valid = [s for s in file_stats if not s.parse_error]
    if not valid:
        return result

    result.future_annotations_first_count = sum(
        1 for s in valid if s.future_annotations_first
    )
    result.group_order_correct_count = sum(
        1 for s in valid if s.group_order_correct
    )
    result.blank_line_separation_count = sum(
        1 for s in valid if s.blank_line_separation
    )
    result.sorted_within_groups_count = sum(
        1 for s in valid if s.sorted_within_groups
    )
    result.relative_imports_count = sum(
        1 for s in valid if s.has_relative_imports
    )

    n = len(valid)
    if n >= min_files:
        result.uses_future_annotations_first = (
            result.future_annotations_first_count / n > 0.5
        )
        result.uses_group_order = result.group_order_correct_count / n > 0.5
        result.uses_blank_line_separation = (
            result.blank_line_separation_count / n > 0.5
        )
        result.uses_sorted_within_groups = (
            result.sorted_within_groups_count / n > 0.5
        )
        result.uses_relative_imports = result.relative_imports_count / n > 0.5

    return result


def generate_import_principle(
    result: ImportConventionResult,
    *,
    principle_id: str = "P013",
    applies_to: list[str] | None = None,
) -> dict:
    """Generate a principle dict from *result* for ``.claude/principles.yaml``.

    The returned dict can be appended directly to ``principles:`` in the YAML
    file and is compatible with the schema produced by :mod:`define-principles`.

    Parameters
    ----------
    result:
        Output of :func:`detect_import_conventions`.
    principle_id:
        ID string to assign (e.g. ``"P013"``).
    applies_to:
        List of skill names that enforce this principle.
        Defaults to ``["review-pr", "check-code"]``.

    Returns
    -------
    dict
        A principle entry with keys ``id``, ``category``, ``severity``,
        ``applies_to``, and ``rule``.
    """
    if applies_to is None:
        applies_to = ["review-pr", "check-code"]

    rule_parts: list[str] = []

    # -- Group order --------------------------------------------------------
    if result.uses_group_order:
        rule_parts.append(
            "Imports must follow the four-group isort order — "
            "future, stdlib, third-party, first-party."
        )
    else:
        rule_parts.append("Imports should be organised into logical groups.")

    # -- Blank-line separation ---------------------------------------------
    if result.uses_blank_line_separation:
        rule_parts.append(
            "Each group must be separated by exactly one blank line; "
            "no blank lines within a group."
        )

    # -- future annotations first ------------------------------------------
    if result.uses_future_annotations_first:
        rule_parts.append(
            "`from __future__ import annotations` must appear as the very "
            "first import in every Python module."
        )

    # -- Alphabetical sorting ----------------------------------------------
    if result.uses_sorted_within_groups:
        rule_parts.append(
            "Imports within each group must be sorted alphabetically."
        )

    # -- Relative imports --------------------------------------------------
    if result.uses_relative_imports:
        rule_parts.append(
            "Intra-package references must use relative imports "
            "(`from .module import Thing`) rather than absolute paths that "
            "repeat the package name."
        )

    # -- Evidence note ------------------------------------------------------
    n = result.files_scanned - result.files_with_parse_errors
    fp_note = ""
    if result.detected_first_party:
        fp_packages = ", ".join(f"`{p}`" for p in result.detected_first_party)
        fp_note = f" First-party packages detected: {fp_packages}."
    rule_parts.append(
        f"Detected from the prevailing pattern across {n} file(s) in the "
        f"codebase; enforced by isort or ruff `[tool.ruff.lint.isort]`."
        + fp_note
    )

    rule_text = "\n".join(rule_parts)

    return {
        "id": principle_id,
        "category": "style",
        "severity": "suggestion",
        "applies_to": applies_to,
        "rule": rule_text,
        "generated_by": "import_convention_detector",
        "files_scanned": result.files_scanned,
        "files_with_parse_errors": result.files_with_parse_errors,
    }
