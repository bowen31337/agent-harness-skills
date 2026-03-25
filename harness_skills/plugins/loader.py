"""Load and validate plugin gate configurations from profile config and entry_points."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from harness_skills.plugins.gate_plugin import PluginGateConfig

logger = logging.getLogger("harness_skills.plugins.loader")


def load_plugin_gates(profile: dict[str, Any]) -> list[PluginGateConfig]:
    """Load plugin gates from profile config YAML."""
    gates = profile.get("gates")
    if not isinstance(gates, dict):
        return []
    plugins = gates.get("plugins")
    if plugins is None:
        return []
    if not isinstance(plugins, list):
        logger.warning("plugins must be a list, got %s", type(plugins).__name__)
        return []
    results = []
    seen_ids: set[str] = set()
    for entry in plugins:
        if not isinstance(entry, dict):
            logger.warning("Plugin entry is not a mapping, skipping: %r", entry)
            continue
        try:
            cfg = PluginGateConfig.model_validate(entry)
        except ValidationError as e:
            logger.warning("Plugin entry failed schema validation, skipping: %s", e)
            continue
        if cfg.gate_id in seen_ids:
            logger.warning("Duplicate gate_id %r found, skipping.", cfg.gate_id)
            continue
        seen_ids.add(cfg.gate_id)
        results.append(cfg)
    return results


def load_all_gates(profile: dict[str, Any]) -> list[PluginGateConfig]:
    """Load gates from config, then merge with entry_points-discovered plugins."""
    config_gates = load_plugin_gates(profile)
    seen_ids = {g.gate_id for g in config_gates}
    try:
        from harness_skills.plugins.discovery import GATE_GROUP, discover_plugins  # noqa: PLC0415

        for name, cls in discover_plugins(GATE_GROUP).items():
            if name not in seen_ids and hasattr(cls, "gate_config"):
                try:
                    cfg = cls.gate_config()
                    if isinstance(cfg, PluginGateConfig):
                        config_gates.append(cfg)
                        seen_ids.add(cfg.gate_id)
                except Exception as exc:
                    logger.warning("entry_point gate %r failed: %s", name, exc)
    except ImportError:
        pass
    return config_gates
