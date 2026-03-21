"""Load and validate plugin gate configurations from a profile config dict."""
from __future__ import annotations
import logging
from typing import Any
from harness_skills.plugins.gate_plugin import PluginGateConfig
from pydantic import ValidationError

logger = logging.getLogger("harness_skills.plugins.loader")


def load_plugin_gates(profile: dict[str, Any]) -> list[PluginGateConfig]:
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
