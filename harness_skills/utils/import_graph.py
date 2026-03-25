"""Import graph construction and analysis.

Builds a directed graph from import edges and provides query methods for
dependency analysis, cycle detection, and domain clustering.

Usage::

    from harness_skills.utils.import_graph import ImportEdge, ImportGraph

    edges = [ImportEdge("a.main", "a.utils", "direct", 1)]
    graph = ImportGraph(edges)
    print(graph.modules())
    print(graph.detect_cycles())
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ImportEdge:
    """A single import relationship between two modules."""

    source: str  # importing module, e.g. "harness_skills.cli.main"
    target: str  # imported module, e.g. "harness_skills.models.create"
    import_type: str = "direct"  # "direct" | "from"
    line_number: int = 0


@dataclass
class ImportGraph:
    """Directed import graph with analysis methods."""

    edges: list[ImportEdge] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._forward: dict[str, set[str]] = defaultdict(set)
        self._reverse: dict[str, set[str]] = defaultdict(set)
        for e in self.edges:
            self._forward[e.source].add(e.target)
            self._reverse[e.target].add(e.source)

    def add_edge(self, edge: ImportEdge) -> None:
        """Add a single edge to the graph."""
        self.edges.append(edge)
        self._forward[edge.source].add(edge.target)
        self._reverse[edge.target].add(edge.source)

    def modules(self) -> set[str]:
        """Return all unique module names in the graph."""
        mods: set[str] = set()
        for e in self.edges:
            mods.add(e.source)
            mods.add(e.target)
        return mods

    def dependencies_of(self, module: str) -> set[str]:
        """Modules that *module* imports (direct dependencies)."""
        return set(self._forward.get(module, set()))

    def dependents_of(self, module: str) -> set[str]:
        """Modules that import *module* (reverse dependencies)."""
        return set(self._reverse.get(module, set()))

    def clusters(self, depth: int = 2) -> dict[str, set[str]]:
        """Group modules by shared path prefix at the given depth.

        For ``depth=2``, ``"harness_skills.cli.main"`` → cluster ``"harness_skills.cli"``.
        """
        groups: dict[str, set[str]] = defaultdict(set)
        for mod in self.modules():
            parts = mod.split(".")
            key = ".".join(parts[:depth]) if len(parts) >= depth else mod
            groups[key].add(mod)
        return dict(groups)

    def detect_cycles(self) -> list[list[str]]:
        """Find all simple cycles in the graph using DFS.

        Returns a list of cycles, where each cycle is a list of module names.
        """
        visited: set[str] = set()
        rec_stack: set[str] = set()
        path: list[str] = []
        cycles: list[list[str]] = []

        def _dfs(node: str) -> None:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in self._forward.get(node, set()):
                if neighbor not in visited:
                    _dfs(neighbor)
                elif neighbor in rec_stack:
                    # Found a cycle
                    idx = path.index(neighbor)
                    cycle = path[idx:] + [neighbor]
                    cycles.append(cycle)

            path.pop()
            rec_stack.discard(node)

        for mod in sorted(self.modules()):
            if mod not in visited:
                _dfs(mod)

        return cycles

    def to_mermaid(self) -> str:
        """Render the graph as a Mermaid diagram string."""
        lines = ["graph LR"]
        seen: set[tuple[str, str]] = set()
        for e in self.edges:
            key = (e.source, e.target)
            if key not in seen:
                seen.add(key)
                src = e.source.replace(".", "_")
                tgt = e.target.replace(".", "_")
                lines.append(f"    {src}[{e.source}] --> {tgt}[{e.target}]")
        return "\n".join(lines)

    def subgraph(self, prefix: str) -> ImportGraph:
        """Return a new graph containing only edges where both modules match prefix."""
        filtered = [
            e for e in self.edges
            if e.source.startswith(prefix) and e.target.startswith(prefix)
        ]
        return ImportGraph(edges=filtered)

    def edge_count(self) -> int:
        """Return total number of edges."""
        return len(self.edges)
