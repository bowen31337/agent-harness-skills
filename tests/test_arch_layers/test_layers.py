"""Tests for layered architecture definitions."""

from __future__ import annotations

from harness_skills.architecture.layers import (
    PRESETS,
    LayerDefinition,
    LayerStack,
    check_import_boundary,
    resolve_layer_stack,
)


class TestLayerStack:

    def test_clean_preset(self) -> None:
        stack = PRESETS["clean"]
        assert len(stack.layers) == 4
        assert stack.layers[0].name == "entities"

    def test_layered_preset(self) -> None:
        stack = PRESETS["layered"]
        assert len(stack.layers) == 6
        assert stack.layer_rank("types") == 1
        assert stack.layer_rank("ui") == 6

    def test_may_import_allowed(self) -> None:
        stack = PRESETS["layered"]
        # Higher rank can import lower rank
        assert stack.may_import("service", "repository") is True
        assert stack.may_import("ui", "types") is True

    def test_may_import_denied(self) -> None:
        stack = PRESETS["layered"]
        # Lower rank cannot import higher rank
        assert stack.may_import("types", "ui") is False
        assert stack.may_import("config", "service") is False

    def test_may_import_same_rank(self) -> None:
        stack = PRESETS["layered"]
        assert stack.may_import("types", "types") is True

    def test_may_import_unknown_layer(self) -> None:
        stack = PRESETS["layered"]
        assert stack.may_import("unknown", "types") is True

    def test_layer_rank_by_alias(self) -> None:
        stack = PRESETS["layered"]
        assert stack.layer_rank("models") == 1  # alias for types
        assert stack.layer_rank("schemas") == 1

    def test_all_presets_valid(self) -> None:
        for name, stack in PRESETS.items():
            assert len(stack.layers) >= 3, f"Preset {name} has too few layers"
            ranks = [l.rank for l in stack.layers]
            assert ranks == sorted(ranks), f"Preset {name} ranks not sorted"


class TestResolveLayerStack:

    def test_default_is_layered(self) -> None:
        stack = resolve_layer_stack({})
        assert stack == PRESETS["layered"]

    def test_arch_style(self) -> None:
        stack = resolve_layer_stack({"arch_style": "clean"})
        assert stack == PRESETS["clean"]

    def test_layer_order(self) -> None:
        stack = resolve_layer_stack({"layer_order": ["data", "logic", "api"]})
        assert len(stack.layers) == 3
        assert stack.layer_rank("data") == 1
        assert stack.layer_rank("api") == 3

    def test_custom_definitions(self) -> None:
        stack = resolve_layer_stack({
            "layer_definitions": [
                {"name": "core", "rank": 1, "aliases": ["domain"]},
                {"name": "infra", "rank": 2},
            ],
        })
        assert len(stack.layers) == 2
        assert stack.layer_rank("domain") == 1


class TestCheckImportBoundary:

    def test_no_violation(self) -> None:
        stack = PRESETS["layered"]
        violations = check_import_boundary("app.service.handler", "app.types.models", stack)
        assert violations == []

    def test_violation(self) -> None:
        stack = PRESETS["layered"]
        violations = check_import_boundary("app.types.schema", "app.ui.pages", stack)
        assert len(violations) == 1
        assert violations[0].rule_id == "ARCH-001"
        assert "violation" in violations[0].message.lower()

    def test_unknown_modules(self) -> None:
        stack = PRESETS["layered"]
        violations = check_import_boundary("app.unknown.foo", "app.other.bar", stack)
        assert violations == []
