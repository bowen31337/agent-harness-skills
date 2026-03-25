"""Tests for generated linter rules."""

from __future__ import annotations

import yaml

from harness_skills.architecture.layers import PRESETS
from harness_skills.architecture.linter_rules import (
    generate_eslint_rules,
    generate_ruff_rules,
    write_rules_file,
)


class TestGenerateRuffRules:

    def test_clean_preset(self) -> None:
        rules = generate_ruff_rules(PRESETS["clean"])
        assert len(rules["layers"]) == 4
        assert len(rules["banned_imports"]) >= 1

    def test_entities_cannot_import_frameworks(self) -> None:
        rules = generate_ruff_rules(PRESETS["clean"])
        entities_ban = [b for b in rules["banned_imports"] if b["from_layer"] == "entities"]
        assert len(entities_ban) == 1
        assert "frameworks" in entities_ban[0]["banned_from"]


class TestGenerateEslintRules:

    def test_generates_zones(self) -> None:
        rules = generate_eslint_rules(PRESETS["layered"])
        zones = rules["import/no-restricted-paths"]["zones"]
        assert len(zones) > 0
        assert all("target" in z and "from" in z for z in zones)


class TestWriteRulesFile:

    def test_writes_yaml(self, tmp_path) -> None:
        rules = generate_ruff_rules(PRESETS["clean"])
        out = tmp_path / "rules" / "arch.yaml"
        write_rules_file(rules, out)
        assert out.exists()
        loaded = yaml.safe_load(out.read_text())
        assert "layers" in loaded
