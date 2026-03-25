"""Layered architecture definitions with configurable stacks."""

from __future__ import annotations

from pydantic import BaseModel, Field

from harness_skills.models.base import Violation


class LayerDefinition(BaseModel):
    """A single layer in an architecture stack."""

    name: str
    rank: int
    aliases: list[str] = Field(default_factory=list)


class LayerStack(BaseModel):
    """An ordered set of architecture layers."""

    layers: list[LayerDefinition] = Field(default_factory=list)

    def layer_rank(self, name: str) -> int | None:
        """Return the rank of a layer by name or alias, or None if not found."""
        for layer in self.layers:
            if layer.name.lower() == name.lower():
                return layer.rank
            if name.lower() in [a.lower() for a in layer.aliases]:
                return layer.rank
        return None

    def may_import(self, from_layer: str, to_layer: str) -> bool:
        """Check if from_layer is allowed to import to_layer.

        Rule: higher-rank layers may import from lower-rank layers only.
        """
        from_rank = self.layer_rank(from_layer)
        to_rank = self.layer_rank(to_layer)
        if from_rank is None or to_rank is None:
            return True  # unknown layers are allowed
        return from_rank >= to_rank


# Pre-defined architecture presets
PRESETS: dict[str, LayerStack] = {
    "clean": LayerStack(layers=[
        LayerDefinition(name="entities", rank=1, aliases=["domain", "models"]),
        LayerDefinition(name="use_cases", rank=2, aliases=["services", "interactors"]),
        LayerDefinition(name="interfaces", rank=3, aliases=["adapters", "gateways"]),
        LayerDefinition(name="frameworks", rank=4, aliases=["infrastructure", "external"]),
    ]),
    "layered": LayerStack(layers=[
        LayerDefinition(name="types", rank=1, aliases=["models", "schemas"]),
        LayerDefinition(name="config", rank=2, aliases=["settings"]),
        LayerDefinition(name="repository", rank=3, aliases=["data", "db"]),
        LayerDefinition(name="service", rank=4, aliases=["business", "logic"]),
        LayerDefinition(name="runtime", rank=5, aliases=["api", "handlers"]),
        LayerDefinition(name="ui", rank=6, aliases=["views", "pages", "components"]),
    ]),
    "hexagonal": LayerStack(layers=[
        LayerDefinition(name="domain", rank=1, aliases=["core", "entities"]),
        LayerDefinition(name="ports", rank=2, aliases=["interfaces"]),
        LayerDefinition(name="adapters", rank=3, aliases=["infrastructure", "driven"]),
        LayerDefinition(name="application", rank=4, aliases=["drivers", "primary"]),
    ]),
    "mvc": LayerStack(layers=[
        LayerDefinition(name="models", rank=1, aliases=["entities", "data"]),
        LayerDefinition(name="controllers", rank=2, aliases=["handlers", "actions"]),
        LayerDefinition(name="views", rank=3, aliases=["templates", "ui"]),
    ]),
    "ddd": LayerStack(layers=[
        LayerDefinition(name="domain", rank=1, aliases=["core", "entities", "aggregates"]),
        LayerDefinition(name="application", rank=2, aliases=["services", "commands", "queries"]),
        LayerDefinition(name="infrastructure", rank=3, aliases=["persistence", "messaging"]),
        LayerDefinition(name="presentation", rank=4, aliases=["api", "web", "cli"]),
    ]),
}


def resolve_layer_stack(config: dict) -> LayerStack:
    """Resolve a LayerStack from harness config.

    Checks for:
    1. ``layer_definitions`` — custom layer list
    2. ``arch_style`` — preset name (clean, layered, hexagonal, mvc, ddd)
    3. ``layer_order`` — simple list of names → auto-ranked
    4. Default: layered preset
    """
    if "layer_definitions" in config:
        layers = [LayerDefinition(**ld) for ld in config["layer_definitions"]]
        return LayerStack(layers=layers)

    if "arch_style" in config:
        style = config["arch_style"].lower()
        if style in PRESETS:
            return PRESETS[style]

    if "layer_order" in config:
        layers = [
            LayerDefinition(name=name, rank=i + 1)
            for i, name in enumerate(config["layer_order"])
        ]
        return LayerStack(layers=layers)

    return PRESETS["layered"]


def check_import_boundary(
    from_module: str, to_module: str, stack: LayerStack
) -> list[Violation]:
    """Check if an import violates layer boundaries.

    Extracts layer names from module paths by matching against layer names/aliases.
    """
    from_layer = _infer_layer(from_module, stack)
    to_layer = _infer_layer(to_module, stack)

    if from_layer is None or to_layer is None:
        return []  # Can't determine layers

    if not stack.may_import(from_layer, to_layer):
        return [Violation(
            rule_id="ARCH-001",
            severity="error",
            message=f"Layer violation: {from_layer} (rank {stack.layer_rank(from_layer)}) "
                    f"may not import from {to_layer} (rank {stack.layer_rank(to_layer)}). "
                    f"Import direction: {from_module} → {to_module}",
        )]

    return []


def _infer_layer(module: str, stack: LayerStack) -> str | None:
    """Try to infer which layer a module belongs to from its path components."""
    parts = module.lower().replace("/", ".").split(".")
    for part in parts:
        for layer in stack.layers:
            if part == layer.name.lower() or part in [a.lower() for a in layer.aliases]:
                return layer.name
    return None
