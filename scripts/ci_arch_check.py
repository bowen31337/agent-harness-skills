#!/usr/bin/env python3
"""CI architecture validation script.

Loads harness.config.yaml, resolves the layer stack, walks Python AST for
import violations, and exits non-zero on violations.

Usage:
    python scripts/ci_arch_check.py [--config harness.config.yaml] [--project-root .]
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

import yaml

from harness_skills.architecture.layers import check_import_boundary, resolve_layer_stack


def _find_imports(file_path: Path) -> list[tuple[str, str, int]]:
    """Extract (source_module, target_module, line) from a Python file."""
    try:
        source = file_path.read_text(errors="ignore")
        tree = ast.parse(source, filename=str(file_path))
    except (SyntaxError, UnicodeDecodeError):
        return []

    results: list[tuple[str, str, int]] = []
    source_mod = file_path.stem

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                results.append((source_mod, alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom) and node.module:
            results.append((source_mod, node.module, node.lineno))

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Architecture boundary checker")
    parser.add_argument("--config", default="harness.config.yaml", help="Config file path")
    parser.add_argument("--project-root", default=".", help="Project root directory")
    parser.add_argument("--format", choices=["json", "text"], default="text")
    args = parser.parse_args()

    config_path = Path(args.config)
    root = Path(args.project_root)

    if not config_path.exists():
        print(f"Config not found: {config_path}", file=sys.stderr)
        return 2

    with config_path.open() as f:
        config = yaml.safe_load(f) or {}

    # Extract architecture config from active profile
    profile_name = config.get("active_profile", "starter")
    profile = config.get("profiles", {}).get(profile_name, {})
    arch_config = profile.get("gates", {}).get("architecture", {})

    stack = resolve_layer_stack(arch_config)
    violations = []

    for py_file in root.rglob("*.py"):
        if any(d in py_file.parts for d in [".venv", "venv", "__pycache__", ".git", "node_modules"]):
            continue
        for src, tgt, line in _find_imports(py_file):
            viols = check_import_boundary(src, tgt, stack)
            for v in viols:
                v.file_path = str(py_file)
                v.line_number = line
                violations.append(v)

    if args.format == "json":
        print(json.dumps([v.model_dump() for v in violations], indent=2))
    else:
        if violations:
            print(f"Found {len(violations)} architecture violation(s):")
            for v in violations:
                print(f"  {v.file_path}:{v.line_number} — {v.message}")
        else:
            print("No architecture violations found.")

    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
