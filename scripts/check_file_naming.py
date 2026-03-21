#!/usr/bin/env python3
"""
File-naming convention linter for agent-harness-skills.

Detected conventions (auto-generated — edit rules below if conventions change):

  Python modules      → snake_case.py
  Python packages     → snake_case/  (dirs containing __init__.py)
  Test files          → test_*.py    (must start with "test_")
  Example files       → *_example.py or *.example (suffix)
  Shell scripts       → kebab-case.sh
  Skill directories   → kebab-case/  (direct children of skills/)
  CI/CD workflows     → kebab-case.yml  (under .github/workflows/ or .gitlab-ci.yml)
  Root documentation  → UPPERCASE.md   (root-level .md files)
  Config YAML         → kebab-case.yaml|yml  OR  snake_case.yaml|yml

Usage:
    python scripts/check_file_naming.py [--fix] [paths ...]

    If no paths are given the whole repository root is scanned.
    --fix  is a no-op flag reserved for future auto-rename support.

Exit codes:
    0  all names are compliant
    1  one or more violations found
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

_SNAKE_CASE = re.compile(r"^[a-z][a-z0-9_]*$")
_KEBAB_CASE = re.compile(r"^[a-z][a-z0-9-]*$")
_UPPERCASE_STEM = re.compile(r"^[A-Z][A-Z0-9_]*$")
_TEST_PREFIX = re.compile(r"^test_.+$")
_EXAMPLE_SUFFIX = re.compile(r"^.+_example$")        # stem only
_EXAMPLE_EXT = re.compile(r"^\.example$")            # whole suffix e.g. .env.example
_WORKFLOW_NAME = re.compile(r"^[a-z][a-z0-9-]*$")   # stem

# Directories that are always skipped during traversal
_SKIP_DIRS: set[str] = {
    ".git", ".venv", "venv", "__pycache__", ".mypy_cache",
    ".ruff_cache", "dist", "build", "node_modules", "*.egg-info",
    ".claw-forge",  # state / snapshot artefacts
    "observability",
}


# ---------------------------------------------------------------------------
# Violation model
# ---------------------------------------------------------------------------

@dataclass
class Violation:
    path: Path
    rule: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}  [{self.rule}]  {self.message}"


# ---------------------------------------------------------------------------
# Rule checkers
# ---------------------------------------------------------------------------

def _stem(p: Path) -> str:
    """Return the file stem with ALL suffixes stripped (e.g. foo.test.py → foo)."""
    name = p.name
    while True:
        s = Path(name).stem
        if s == name:
            return s
        name = s


def check_python_module(path: Path) -> list[Violation]:
    """Python source files must be snake_case (excluding dunder files)."""
    violations: list[Violation] = []
    stem = path.stem
    # __init__, __main__ etc. are always OK
    if stem.startswith("__") and stem.endswith("__"):
        return violations
    if not _SNAKE_CASE.match(stem):
        violations.append(Violation(
            path=path,
            rule="PY001",
            message=f"Python module name '{stem}' must be snake_case",
        ))
    return violations


def check_test_file(path: Path) -> list[Violation]:
    """Files inside a tests/ tree or anywhere with a test-like name must follow test_*.py."""
    violations: list[Violation] = []
    stem = path.stem
    # Files sitting inside a tests/ subtree must be prefixed
    in_tests_dir = any(part == "tests" or part.startswith("test_") for part in path.parts[:-1])
    if in_tests_dir and not stem.startswith("__"):
        # Allow helper / conftest / __init__ files without prefix
        helpers = {"conftest", "agent_driver", "screenshot_helper"}
        if stem not in helpers and not _TEST_PREFIX.match(stem):
            violations.append(Violation(
                path=path,
                rule="PY002",
                message=(
                    f"Test module '{stem}.py' inside tests/ must be named test_<something>.py"
                ),
            ))
    return violations


def check_shell_script(path: Path) -> list[Violation]:
    """Shell scripts must be kebab-case."""
    violations: list[Violation] = []
    stem = path.stem
    if not _KEBAB_CASE.match(stem):
        violations.append(Violation(
            path=path,
            rule="SH001",
            message=f"Shell script '{stem}.sh' must be kebab-case",
        ))
    return violations


def check_skill_directory(path: Path, skills_root: Path) -> list[Violation]:
    """Direct children of skills/ that are directories must be kebab-case."""
    violations: list[Violation] = []
    if path.parent == skills_root and path.is_dir():
        name = path.name
        if not _KEBAB_CASE.match(name):
            violations.append(Violation(
                path=path,
                rule="SK001",
                message=f"Skill directory '{name}' must be kebab-case",
            ))
    return violations


def check_python_package(path: Path) -> list[Violation]:
    """Directories that are Python packages (contain __init__.py) must be snake_case."""
    violations: list[Violation] = []
    name = path.name
    if (path / "__init__.py").exists():
        if not _SNAKE_CASE.match(name):
            violations.append(Violation(
                path=path,
                rule="PY003",
                message=f"Python package directory '{name}' must be snake_case",
            ))
    return violations


def check_root_doc(path: Path, repo_root: Path) -> list[Violation]:
    """Top-level .md files must be UPPERCASE (e.g. README.md, PRINCIPLES.md)."""
    violations: list[Violation] = []
    if path.parent == repo_root:
        stem = path.stem
        if not _UPPERCASE_STEM.match(stem):
            violations.append(Violation(
                path=path,
                rule="DOC001",
                message=(
                    f"Root-level markdown file '{path.name}' must have an UPPERCASE stem "
                    f"(e.g. README.md)"
                ),
            ))
    return violations


def check_workflow_file(path: Path) -> list[Violation]:
    """GitHub/GitLab CI YAML files must be kebab-case."""
    violations: list[Violation] = []
    stem = path.stem
    if not _WORKFLOW_NAME.match(stem):
        violations.append(Violation(
            path=path,
            rule="CI001",
            message=f"Workflow file '{path.name}' stem must be kebab-case",
        ))
    return violations


def check_config_yaml(path: Path) -> list[Violation]:
    """Config YAML files must be kebab-case or snake_case (no spaces, no mixed case)."""
    violations: list[Violation] = []
    stem = path.stem
    # Accept kebab or snake
    if not (_KEBAB_CASE.match(stem) or _SNAKE_CASE.match(stem)):
        violations.append(Violation(
            path=path,
            rule="CFG001",
            message=(
                f"Config file '{path.name}' stem must be kebab-case or snake_case"
            ),
        ))
    return violations


# ---------------------------------------------------------------------------
# Walker
# ---------------------------------------------------------------------------

def _should_skip(part: str) -> bool:
    return part in _SKIP_DIRS or part.endswith(".egg-info")


def walk(root: Path) -> list[Path]:
    """Yield all non-skipped paths under root."""
    result: list[Path] = []
    for p in root.rglob("*"):
        if any(_should_skip(part) for part in p.parts):
            continue
        result.append(p)
    return result


def lint(paths: list[Path], repo_root: Path) -> list[Violation]:
    skills_root = repo_root / "skills"
    violations: list[Violation] = []

    for p in paths:
        suffix = p.suffix.lower()
        name = p.name

        # ── Directories ──────────────────────────────────────────────────
        if p.is_dir():
            violations += check_python_package(p)
            if skills_root.exists():
                violations += check_skill_directory(p, skills_root)
            continue

        # ── Python source ─────────────────────────────────────────────────
        if suffix == ".py":
            violations += check_python_module(p)
            violations += check_test_file(p)
            continue

        # ── Shell scripts ─────────────────────────────────────────────────
        if suffix == ".sh":
            violations += check_shell_script(p)
            continue

        # ── Markdown docs ─────────────────────────────────────────────────
        if suffix == ".md":
            violations += check_root_doc(p, repo_root)
            continue

        # ── CI/CD workflows ───────────────────────────────────────────────
        wf_dirs = {".github/workflows", ".gitlab-ci.yml"}
        in_workflow = any(
            ".github/workflows" in str(p) or ".gitlab-ci" in str(p)
            for _ in [None]
        )
        if suffix in (".yml", ".yaml") and in_workflow:
            violations += check_workflow_file(p)
            continue

        # ── Other YAML/YML (not workflows) ────────────────────────────────
        if suffix in (".yml", ".yaml"):
            violations += check_config_yaml(p)
            continue

    return violations


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="File-naming convention linter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Files or directories to check (default: repo root)",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="(Reserved) auto-rename files to match conventions",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Repository root (default: parent of scripts/)",
    )
    args = parser.parse_args(argv)

    repo_root: Path = args.repo_root.resolve()
    scan_targets: list[Path] = [p.resolve() for p in args.paths] if args.paths else [repo_root]

    all_paths: list[Path] = []
    for target in scan_targets:
        if target.is_file():
            all_paths.append(target)
        else:
            all_paths.extend(walk(target))

    violations = lint(all_paths, repo_root)

    if violations:
        print(f"\n{'─' * 70}")
        print(f"  File-naming violations found: {len(violations)}")
        print(f"{'─' * 70}\n")
        for v in sorted(violations, key=lambda x: str(x.path)):
            print(f"  {v}")
        print()
        return 1

    print("✓ All file names comply with naming conventions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
