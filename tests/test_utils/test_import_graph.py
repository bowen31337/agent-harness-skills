"""Tests for import graph utility."""

from __future__ import annotations

from harness_skills.utils.import_graph import ImportEdge, ImportGraph


class TestImportEdge:

    def test_frozen(self) -> None:
        e = ImportEdge("a", "b", "direct", 1)
        assert e.source == "a"
        assert e.target == "b"

    def test_defaults(self) -> None:
        e = ImportEdge("a", "b")
        assert e.import_type == "direct"
        assert e.line_number == 0


class TestImportGraph:

    def _sample_graph(self) -> ImportGraph:
        return ImportGraph(edges=[
            ImportEdge("a.main", "a.utils", "direct", 1),
            ImportEdge("a.main", "b.core", "from", 2),
            ImportEdge("a.utils", "c.lib", "direct", 3),
            ImportEdge("b.core", "c.lib", "from", 4),
        ])

    def test_modules(self) -> None:
        g = self._sample_graph()
        mods = g.modules()
        assert "a.main" in mods
        assert "c.lib" in mods
        assert len(mods) == 4

    def test_dependencies_of(self) -> None:
        g = self._sample_graph()
        deps = g.dependencies_of("a.main")
        assert deps == {"a.utils", "b.core"}

    def test_dependents_of(self) -> None:
        g = self._sample_graph()
        deps = g.dependents_of("c.lib")
        assert deps == {"a.utils", "b.core"}

    def test_clusters_depth_1(self) -> None:
        g = self._sample_graph()
        clusters = g.clusters(depth=1)
        assert "a" in clusters
        assert "b" in clusters
        assert "c" in clusters
        assert "a.main" in clusters["a"]
        assert "a.utils" in clusters["a"]

    def test_clusters_depth_2(self) -> None:
        g = ImportGraph(edges=[
            ImportEdge("pkg.sub.mod1", "pkg.sub.mod2"),
            ImportEdge("pkg.other.mod3", "pkg.sub.mod1"),
        ])
        clusters = g.clusters(depth=2)
        assert "pkg.sub" in clusters
        assert "pkg.other" in clusters

    def test_detect_cycles_no_cycle(self) -> None:
        g = ImportGraph(edges=[
            ImportEdge("a", "b"),
            ImportEdge("b", "c"),
        ])
        cycles = g.detect_cycles()
        assert cycles == []

    def test_detect_cycles_with_cycle(self) -> None:
        g = ImportGraph(edges=[
            ImportEdge("a", "b"),
            ImportEdge("b", "c"),
            ImportEdge("c", "a"),
        ])
        cycles = g.detect_cycles()
        assert len(cycles) >= 1
        # The cycle should contain a, b, c
        cycle_mods = set()
        for c in cycles:
            cycle_mods.update(c)
        assert {"a", "b", "c"}.issubset(cycle_mods)

    def test_to_mermaid(self) -> None:
        g = ImportGraph(edges=[ImportEdge("a", "b")])
        mermaid = g.to_mermaid()
        assert "graph LR" in mermaid
        assert "a" in mermaid
        assert "b" in mermaid

    def test_subgraph(self) -> None:
        g = self._sample_graph()
        sub = g.subgraph("a.")
        assert sub.edge_count() == 1
        assert all(e.source.startswith("a.") for e in sub.edges)

    def test_add_edge(self) -> None:
        g = ImportGraph()
        assert g.edge_count() == 0
        g.add_edge(ImportEdge("x", "y"))
        assert g.edge_count() == 1
        assert "x" in g.modules()

    def test_empty_graph(self) -> None:
        g = ImportGraph()
        assert g.modules() == set()
        assert g.detect_cycles() == []
        assert g.to_mermaid() == "graph LR"
        assert g.clusters() == {}
