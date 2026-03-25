"""Plugin discovery via Python entry_points."""

from __future__ import annotations

import logging
from importlib.metadata import entry_points
from typing import Any

logger = logging.getLogger(__name__)

ANALYZER_GROUP = "harness_skills.analyzers"
GATE_GROUP = "harness_skills.gates"
GENERATOR_GROUP = "harness_skills.generators"

ALL_GROUPS = [ANALYZER_GROUP, GATE_GROUP, GENERATOR_GROUP]


def discover_plugins(group: str) -> dict[str, type]:
    """Load plugins registered under the given entry_points group.

    Returns a dict mapping plugin name to the loaded class.
    Gracefully skips plugins that fail to load.
    """
    eps = entry_points(group=group)
    plugins: dict[str, type] = {}
    for ep in eps:
        try:
            cls = ep.load()
            plugins[ep.name] = cls
        except Exception as exc:
            logger.warning("Failed to load plugin %s from group %s: %s", ep.name, group, exc)
    return plugins


def discover_all() -> dict[str, dict[str, type]]:
    """Discover plugins across all known groups.

    Returns ``{"harness_skills.analyzers": {"python": PythonAnalyzer, ...}, ...}``.
    """
    return {group: discover_plugins(group) for group in ALL_GROUPS}
