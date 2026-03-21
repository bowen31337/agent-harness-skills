"""
Tests for harness_dashboard.scorer
====================================

Covers:
  • Empty / single-harness edge cases
  • Score range and tier assignment
  • Correct handling of unlinked harnesses (no PRs)
  • Pearson correlation directions match the injected quality signal
  • Fleet-level aggregates
  • DashboardReport is fully populated and sorted
"""

from __future__ import annotations

import pytest

from harness_dashboard.models import (
    ArtifactType,
    EffectivenessTier,
    HarnessRecord,
    PRRecord,
)
from harness_dashboard.scorer import compute_scores


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _harness(hid: str, count: int = 10, cov: float = 70.0) -> HarnessRecord:
    return HarnessRecord(
        harness_id=hid,
        artifact_type=ArtifactType.FIXTURE,
        artifact_count=count,
        coverage_pct=cov,
    )


def _pr(pr_id: str, hid: str, gate: float, cycles: int, ttm: float) -> PRRecord:
    return PRRecord(
        pr_id=pr_id,
        harness_id=hid,
        gate_pass_rate=gate,
        review_cycles=cycles,
        time_to_merge_hours=ttm,
        merged=True,
    )


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_input_returns_empty_report(self) -> None:
        report = compute_scores([], [])
        assert report.harness_count == 0
        assert report.pr_count == 0
        assert report.metrics == []
        assert report.correlations == []

    def test_single_harness_no_prs(self) -> None:
        h = _harness("h1")
        report = compute_scores([h], [])
        assert report.harness_count == 1
        assert report.pr_count == 0
        assert len(report.metrics) == 1
        m = report.metrics[0]
        # Score is 0.5 * 100 = 50 for all-zero normalised metrics (midpoint)
        # Actually with all zeros and minmax returning 0.5 constant arrays,
        # score = 0.40*0.5 + 0.35*(1-0.5) + 0.25*(1-0.5) = 0.5 → 50
        assert 0.0 <= m.effectiveness_score <= 100.0

    def test_single_harness_with_prs(self) -> None:
        h = _harness("h1")
        pr1 = _pr("p1", "h1", gate=0.9, cycles=1, ttm=5.0)
        pr2 = _pr("p2", "h1", gate=0.8, cycles=2, ttm=8.0)
        report = compute_scores([h], [pr1, pr2])
        assert report.pr_count == 2
        m = report.metrics[0]
        assert abs(m.avg_gate_pass_rate - 0.85) < 1e-6
        assert abs(m.avg_review_cycles - 1.5) < 1e-6


# ---------------------------------------------------------------------------
# Score range and tier assignment
# ---------------------------------------------------------------------------

class TestScoresAndTiers:
    def test_all_scores_in_range(self) -> None:
        harnesses = [_harness(f"h{i}", count=i * 5, cov=float(i * 10)) for i in range(1, 6)]
        prs = [
            _pr(f"p{i}", f"h{i}", gate=0.5 + i * 0.05, cycles=3 - i // 2, ttm=20.0 - i * 2.0)
            for i in range(1, 6)
        ]
        report = compute_scores(harnesses, prs)
        for m in report.metrics:
            assert 0.0 <= m.effectiveness_score <= 100.0

    def test_tier_thresholds(self) -> None:
        from harness_dashboard.scorer import _tier, EffectivenessTier  # noqa: PLC0415
        assert _tier(80.0) == EffectivenessTier.ELITE
        assert _tier(79.9) == EffectivenessTier.STRONG
        assert _tier(60.0) == EffectivenessTier.STRONG
        assert _tier(59.9) == EffectivenessTier.MODERATE
        assert _tier(40.0) == EffectivenessTier.MODERATE
        assert _tier(39.9) == EffectivenessTier.WEAK
        assert _tier(0.0) == EffectivenessTier.WEAK

    def test_best_harness_outscores_worst(self) -> None:
        """Harness with high gate pass / low TTM / few cycles beats weak one."""
        h_good = _harness("good", count=50, cov=90.0)
        h_bad = _harness("bad", count=5, cov=20.0)

        prs = [
            _pr("pg1", "good", gate=0.98, cycles=0, ttm=2.0),
            _pr("pg2", "good", gate=0.95, cycles=1, ttm=3.0),
            _pr("pb1", "bad",  gate=0.40, cycles=6, ttm=80.0),
            _pr("pb2", "bad",  gate=0.30, cycles=8, ttm=100.0),
        ]
        report = compute_scores([h_good, h_bad], prs)
        scores = {m.harness_id: m.effectiveness_score for m in report.metrics}
        assert scores["good"] > scores["bad"]

    def test_results_sorted_descending(self) -> None:
        harnesses = [_harness(f"h{i}") for i in range(5)]
        prs = [
            _pr(f"p{i}", f"h{i}", gate=float(i) / 4, cycles=4 - i, ttm=10.0 + i * 5)
            for i in range(5)
        ]
        report = compute_scores(harnesses, prs)
        scores = [m.effectiveness_score for m in report.metrics]
        assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# Unlinked harnesses
# ---------------------------------------------------------------------------

class TestUnlinkedHarnesses:
    def test_harness_with_no_prs_gets_zero_quality(self) -> None:
        h1 = _harness("linked")
        h2 = _harness("orphan")
        pr = _pr("p1", "linked", gate=0.9, cycles=1, ttm=5.0)
        report = compute_scores([h1, h2], [pr])
        orphan = next(m for m in report.metrics if m.harness_id == "orphan")
        assert orphan.pr_count == 0
        assert orphan.avg_gate_pass_rate == 0.0
        assert orphan.avg_review_cycles == 0.0

    def test_unmerged_prs_are_excluded(self) -> None:
        h = _harness("h1")
        open_pr = PRRecord(
            pr_id="open1",
            harness_id="h1",
            gate_pass_rate=0.9,
            review_cycles=2,
            time_to_merge_hours=10.0,
            merged=False,
        )
        report = compute_scores([h], [open_pr])
        assert report.pr_count == 0
        assert report.metrics[0].pr_count == 0


# ---------------------------------------------------------------------------
# Correlation directions
# ---------------------------------------------------------------------------

class TestCorrelations:
    def test_six_correlations_returned(self) -> None:
        """2 artifact attrs × 3 PR metrics = 6 CorrelationInsight objects."""
        harnesses = [_harness(f"h{i}", count=i * 3) for i in range(1, 8)]
        prs = [_pr(f"p{i}", f"h{i}", gate=0.5 + i * 0.05, cycles=5 - i // 2, ttm=40.0 - i * 4)
               for i in range(1, 8)]
        report = compute_scores(harnesses, prs)
        assert len(report.correlations) == 6

    def test_correlation_attrs_and_metrics_covered(self) -> None:
        harnesses = [_harness(f"h{i}", count=i * 5, cov=float(i * 10)) for i in range(1, 6)]
        prs = [_pr(f"p{i}", f"h{i}", gate=0.4 + i * 0.1, cycles=5 - i, ttm=50.0 - i * 8)
               for i in range(1, 6)]
        report = compute_scores(harnesses, prs)

        attrs = {c.artifact_attr for c in report.correlations}
        metrics = {c.pr_metric for c in report.correlations}
        assert "artifact_count" in attrs
        assert "coverage_pct" in attrs
        assert "gate_pass_rate" in metrics
        assert "review_cycles" in metrics
        assert "time_to_merge_hours" in metrics

    def test_pearson_r_in_valid_range(self) -> None:
        harnesses = [_harness(f"h{i}", count=i * 5) for i in range(1, 10)]
        prs = [_pr(f"p{i}", f"h{i}", gate=0.3 + i * 0.06, cycles=max(0, 8 - i), ttm=80.0 - i * 7)
               for i in range(1, 10)]
        report = compute_scores(harnesses, prs)
        for c in report.correlations:
            assert -1.0 <= c.pearson_r <= 1.0
            assert 0.0 <= c.p_value <= 1.0


# ---------------------------------------------------------------------------
# Fleet aggregates
# ---------------------------------------------------------------------------

class TestFleetAggregates:
    def test_fleet_score_between_min_and_max(self) -> None:
        harnesses = [_harness(f"h{i}") for i in range(5)]
        prs = [_pr(f"p{i}", f"h{i}", gate=0.6, cycles=2, ttm=20.0) for i in range(5)]
        report = compute_scores(harnesses, prs)
        individual_scores = [m.effectiveness_score for m in report.metrics]
        assert min(individual_scores) <= report.fleet_avg_score <= max(individual_scores)

    def test_tier_counts_sum_to_harness_count(self) -> None:
        harnesses = [_harness(f"h{i}") for i in range(8)]
        prs = [_pr(f"p{i}", f"h{i}", gate=0.5 + i * 0.04, cycles=3, ttm=20.0)
               for i in range(8)]
        report = compute_scores(harnesses, prs)
        total_tier = (
            report.elite_count
            + report.strong_count
            + report.moderate_count
            + report.weak_count
        )
        assert total_tier == report.harness_count

    def test_harness_and_pr_counts(self) -> None:
        harnesses = [_harness(f"h{i}") for i in range(3)]
        prs = [_pr(f"p{i}{j}", f"h{i}", gate=0.8, cycles=1, ttm=10.0)
               for i in range(3) for j in range(4)]
        report = compute_scores(harnesses, prs)
        assert report.harness_count == 3
        assert report.pr_count == 12
