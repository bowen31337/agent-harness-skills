"""Generate linter rules for architectural boundary enforcement."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from harness_skills.architecture.layers import LayerStack


def generate_ruff_rules(stack: LayerStack) -> dict[str, Any]:
    """Generate Ruff per-file-ignores and banned-import patterns from layer stack."""
    rules: dict[str, Any] = {
        "description": "Auto-generated architectural boundary rules",
        "layers": [],
        "banned_imports": [],
    }

    for i, layer in enumerate(stack.layers):
        higher_layers = [l.name for l in stack.layers if l.rank > layer.rank]
        if higher_layers:
            rules["banned_imports"].append({
                "from_layer": layer.name,
                "banned_from": higher_layers,
                "reason": f"{layer.name} (rank {layer.rank}) must not import from higher layers",
            })
        rules["layers"].append({
            "name": layer.name,
            "rank": layer.rank,
            "aliases": layer.aliases,
        })

    return rules


def generate_eslint_rules(stack: LayerStack) -> dict[str, Any]:
    """Generate ESLint import restriction rules from layer stack."""
    rules: dict[str, Any] = {
        "description": "Auto-generated ESLint import restrictions",
        "import/no-restricted-paths": {
            "zones": [],
        },
    }

    for layer in stack.layers:
        higher_layers = [l for l in stack.layers if l.rank > layer.rank]
        for higher in higher_layers:
            rules["import/no-restricted-paths"]["zones"].append({
                "target": f"./{layer.name}/**",
                "from": f"./{higher.name}/**",
                "message": f"{layer.name} must not import from {higher.name}",
            })

    return rules


def write_rules_file(rules: dict[str, Any], output_path: Path) -> None:
    """Write architecture rules to a YAML file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as f:
        yaml.dump(rules, f, default_flow_style=False, sort_keys=False)
