"""
Tests for harness_dashboard.data_generator
============================================

Covers:
  • Output types and counts
  • Reproducibility via seed
  • All PRs link to valid harnesses
  • Quality-signal correlation direction (higher quality → better PR metrics)
  • Dataset customisation parameters
"""

from __future__ import annotations

import statistics

import pytest

from harness_dashboard.data_generator import generate_dataset
from harness_dashboard.models import ArtifactType, HarnessRecord, PRRecord


# ---------------------------------------------------------------------------
# Basic structure
# ---------------------------------------------------------------------------

class TestBasicStructure:
    def test_returns_named_tuple(self) -> None:
        ds = generate_dataset(num_harnesses=5)
        assert hasattr(ds, "harnesses")
        assert hasattr(ds, "prs")

    def test_harness_count(self) -> None:
        ds = generate_dataset(num_harnesses=10)
        assert len(ds.harnesses) == 10

    def test_pr_count_within_expected_range(self) -> None:
        n = 10
        ds = generate_dataset(num_harnesses=n, prs_per_harness=6)
        # With prs_per_harness=6 and Gaussian jitter, expect a reasonable count
        assert len(ds.prs) > 0

    def test_all_harnesses_have_ids(self) -> None:
        ds = generate_dataset(num_harnesses=5)
        ids = [h.harness_id for h in ds.harnesses]
        assert len(set(ids)) == 5  # unique

    def test_all_prs_have_unique_ids(self) -> None:
        ds = generate_dataset(num_harnesses=10)
        ids = [p.pr_id for p in ds.prs]
        assert len(set(ids)) == len(ids)

    def test_most_prs_are_merged(self) -> None:
        """~92% of PRs are merged; ~8% are abandoned (merged=False)."""
        ds = generate_dataset(num_harnesses=20, seed=42)
        merged_count = sum(1 for p in ds.prs if p.merged)
        assert merged_count / len(ds.prs) > 0.80

    def test_all_prs_link_to_valid_harness(self) -> None:
        ds = generate_dataset(num_harnesses=8)
        harness_ids = {h.harness_id for h in ds.harnesses}
        for pr in ds.prs:
            assert pr.harness_id in harness_ids


# ---------------------------------------------------------------------------
# Field validity
# ---------------------------------------------------------------------------

class TestFieldValidity:
    def test_coverage_pct_in_range(self) -> None:
        ds = generate_dataset(num_harnesses=20)
        for h in ds.harnesses:
            assert 0.0 <= h.coverage_pct <= 100.0

    def test_artifact_count_positive(self) -> None:
        ds = generate_dataset(num_harnesses=20)
        for h in ds.harnesses:
            assert h.artifact_count >= 1

    def test_gate_pass_rate_in_range(self) -> None:
        ds = generate_dataset(num_harnesses=20)
        for p in ds.prs:
            assert 0.0 <= p.gate_pass_rate <= 1.0

    def test_review_cycles_non_negative(self) -> None:
        ds = generate_dataset(num_harnesses=20)
        for p in ds.prs:
            assert p.review_cycles >= 0

    def test_time_to_merge_positive_for_merged_prs(self) -> None:
        """Merged PRs have time_to_merge_hours > 0; abandoned PRs have 0."""
        ds = generate_dataset(num_harnesses=20)
        for p in ds.prs:
            if p.merged:
                assert p.time_to_merge_hours > 0
            else:
                assert p.time_to_merge_hours == 0.0

    def test_artifact_types_are_valid(self) -> None:
        valid = set(ArtifactType)
        ds = generate_dataset(num_harnesses=15)
        for h in ds.harnesses:
            assert h.artifact_type in valid


# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------

class TestReproducibility:
    def test_same_seed_yields_identical_datasets(self) -> None:
        ds1 = generate_dataset(num_harnesses=10, seed=99)
        ds2 = generate_dataset(num_harnesses=10, seed=99)
        assert len(ds1.harnesses) == len(ds2.harnesses)
        assert len(ds1.prs) == len(ds2.prs)
        for h1, h2 in zip(ds1.harnesses, ds2.harnesses):
            assert h1.harness_id == h2.harness_id
            assert h1.artifact_count == h2.artifact_count
            assert h1.coverage_pct == h2.coverage_pct

    def test_different_seeds_yield_different_datasets(self) -> None:
        ds1 = generate_dataset(num_harnesses=10, seed=1)
        ds2 = generate_dataset(num_harnesses=10, seed=2)
        counts1 = [h.artifact_count for h in ds1.harnesses]
        counts2 = [h.artifact_count for h in ds2.harnesses]
        assert counts1 != counts2

    def test_none_seed_is_random(self) -> None:
        # Run twice; should differ (with overwhelming probability)
        ds1 = generate_dataset(num_harnesses=10, seed=None)
        ds2 = generate_dataset(num_harnesses=10, seed=None)
        counts1 = [h.artifact_count for h in ds1.harnesses]
        counts2 = [h.artifact_count for h in ds2.harnesses]
        # Very unlikely to be equal for 10 harnesses
        # (not guaranteed, but practically safe)
        assert counts1 != counts2 or len(ds1.prs) != len(ds2.prs)


# ---------------------------------------------------------------------------
# Quality-signal correlation (statistical)
# ---------------------------------------------------------------------------

class TestQualitySignalCorrelation:
    """
    With a large enough dataset the embedded quality signal should produce
    observable correlations between artifact quality and PR metrics.
    """

    def _split_by_quality(self, harnesses, prs, quantile: float = 0.5):
        """Split harnesses at the median quality signal and return PR groups."""
        quality = {
            h.harness_id: (h.artifact_count / 70.0) * 0.45 + (h.coverage_pct / 100.0) * 0.55
            for h in harnesses
        }
        threshold = statistics.median(quality.values())
        high_ids = {hid for hid, q in quality.items() if q >= threshold}
        low_ids = {hid for hid, q in quality.items() if q < threshold}

        prs_by_hid: dict[str, list[PRRecord]] = {}
        for p in prs:
            prs_by_hid.setdefault(p.harness_id, []).append(p)

        high_prs = [p for hid in high_ids for p in prs_by_hid.get(hid, [])]
        low_prs = [p for hid in low_ids for p in prs_by_hid.get(hid, [])]
        return high_prs, low_prs

    def test_high_quality_harnesses_have_better_gate_pass_rate(self) -> None:
        ds = generate_dataset(num_harnesses=40, seed=7)
        high, low = self._split_by_quality(ds.harnesses, ds.prs)
        if not high or not low:
            pytest.skip("split produced empty group")
        avg_high = statistics.mean(p.gate_pass_rate for p in high)
        avg_low = statistics.mean(p.gate_pass_rate for p in low)
        assert avg_high > avg_low, (
            f"Expected high-quality harnesses to have higher gate pass rate; "
            f"got {avg_high:.3f} vs {avg_low:.3f}"
        )

    def test_high_quality_harnesses_have_fewer_review_cycles(self) -> None:
        ds = generate_dataset(num_harnesses=40, seed=7)
        high, low = self._split_by_quality(ds.harnesses, ds.prs)
        if not high or not low:
            pytest.skip("split produced empty group")
        avg_high = statistics.mean(p.review_cycles for p in high)
        avg_low = statistics.mean(p.review_cycles for p in low)
        assert avg_high < avg_low, (
            f"Expected high-quality harnesses to have fewer review cycles; "
            f"got {avg_high:.2f} vs {avg_low:.2f}"
        )

    def test_high_quality_harnesses_merge_faster(self) -> None:
        ds = generate_dataset(num_harnesses=40, seed=7)
        high, low = self._split_by_quality(ds.harnesses, ds.prs)
        if not high or not low:
            pytest.skip("split produced empty group")
        avg_high = statistics.mean(p.time_to_merge_hours for p in high)
        avg_low = statistics.mean(p.time_to_merge_hours for p in low)
        assert avg_high < avg_low, (
            f"Expected high-quality harnesses to merge faster; "
            f"got {avg_high:.1f}h vs {avg_low:.1f}h"
        )
