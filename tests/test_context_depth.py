"""Tests for context depth map."""

from __future__ import annotations

from harness_skills.context_depth import (
    ContextDepthMap,
    ContextTier,
    TieredFile,
    build_depth_map,
)


class TestBuildDepthMap:

    def test_empty_input(self) -> None:
        dm = build_depth_map([])
        assert dm.files == []
        assert dm.l0_files() == []

    def test_all_fit_l0(self) -> None:
        files = [("a.md", 100), ("b.md", 200)]
        dm = build_depth_map(files, l0_budget=500)
        assert len(dm.l0_files()) == 2
        assert len(dm.l1_files()) == 0

    def test_overflow_to_l1(self) -> None:
        files = [("a.md", 300), ("b.md", 300), ("c.md", 200)]
        dm = build_depth_map(files, l0_budget=500, l1_budget=500)
        # a.md(300)→L0, b.md(300)→L1 (300+300>500), c.md(200)→L0 (300+200=500)
        assert len(dm.l0_files()) == 2
        assert len(dm.l1_files()) == 1

    def test_overflow_to_l2(self) -> None:
        files = [("a.md", 600), ("b.md", 600), ("c.md", 600)]
        dm = build_depth_map(files, l0_budget=500, l1_budget=500)
        # None fit in L0 (600 > 500), none in L1
        l2 = dm.l2_files()
        assert len(l2) >= 1

    def test_tier_assignment(self) -> None:
        files = [("root.md", 100), ("domain.md", 400), ("file.py", 300), ("other.py", 500)]
        dm = build_depth_map(files, l0_budget=500, l1_budget=1000)
        # root.md (100) + domain.md (400) = 500 → L0
        # file.py (300) → L1
        # other.py (500) → L1
        assert dm.l0_files()[0].file_path == "root.md"
        assert len(dm.l0_files()) == 2
        assert len(dm.l1_files()) == 2

    def test_budgets_stored(self) -> None:
        dm = build_depth_map([], l0_budget=750, l1_budget=2000)
        assert dm.l0_budget == 750
        assert dm.l1_budget == 2000


class TestContextTier:

    def test_enum_values(self) -> None:
        assert ContextTier.L0.value == "L0"
        assert ContextTier.L1.value == "L1"
        assert ContextTier.L2.value == "L2"
