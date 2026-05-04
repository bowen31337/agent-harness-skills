"""Tests for harness_skills.effectiveness_stats — statistics engine."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

np = pytest.importorskip("numpy", reason="numpy required (install with: pip install -e '.[dashboard]')")

from harness_skills.effectiveness_stats import (
    ArtifactStats,
    _safe_pointbiserial,
    compute_all_stats,
    compute_artifact_combination_effects,
    compute_artifact_stats,
    compute_correlation_matrix,
    stats_to_dict,
    stats_to_json_summary,
)
from harness_skills.pr_effectiveness import (
    ArtifactType,
    HarnessArtifact,
    PRRecord,
    generate_sample_prs,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pr(
    pr_id: str = "PR-0001",
    artifacts: list[ArtifactType] | None = None,
    gate_pass_rate: float = 0.8,
    review_cycles: int = 1,
    time_to_merge_hours: float | None = 24.0,
    merged: bool = True,
) -> PRRecord:
    arts = [
        HarnessArtifact(artifact_type=a, passed=True, execution_time_seconds=10.0)
        for a in (artifacts or [])
    ]
    return PRRecord(
        pr_id=pr_id,
        repo="test-repo",
        author="tester",
        created_at=datetime(2025, 10, 1, tzinfo=timezone.utc),
        artifacts=arts,
        gate_pass_rate=gate_pass_rate,
        review_cycles=review_cycles,
        time_to_merge_hours=time_to_merge_hours,
        merged=merged,
    )


# ---------------------------------------------------------------------------
# _safe_pointbiserial
# ---------------------------------------------------------------------------


class TestSafePointbiserial:
    def test_all_zeros_returns_default(self):
        r, p = _safe_pointbiserial(np.array([0, 0, 0]), np.array([1.0, 2.0, 3.0]))
        assert r == 0.0
        assert p == 1.0

    def test_all_ones_returns_default(self):
        r, p = _safe_pointbiserial(np.array([1, 1, 1]), np.array([1.0, 2.0, 3.0]))
        assert r == 0.0
        assert p == 1.0

    def test_valid_data(self):
        binary = np.array([0, 0, 0, 1, 1, 1])
        continuous = np.array([1.0, 2.0, 1.5, 5.0, 6.0, 5.5])
        r, p = _safe_pointbiserial(binary, continuous)
        assert r > 0.0  # positive correlation
        assert 0.0 <= p <= 1.0

    def test_constant_continuous_returns_default(self):
        # When continuous values are constant, scipy may raise or return nan
        binary = np.array([0, 1, 0, 1])
        continuous = np.array([5.0, 5.0, 5.0, 5.0])
        r, p = _safe_pointbiserial(binary, continuous)
        # Should gracefully handle (returns 0.0, 1.0 on exception or nan)
        assert isinstance(r, float)
        assert isinstance(p, float)

    def test_exception_in_pointbiserialr(self):
        """Force the except branch by making pointbiserialr raise."""
        binary = np.array([0, 1, 0, 1])
        continuous = np.array([1.0, 2.0, 3.0, 4.0])
        with patch("harness_skills.effectiveness_stats.sp_stats.pointbiserialr", side_effect=ValueError("boom")):
            r, p = _safe_pointbiserial(binary, continuous)
        assert r == 0.0
        assert p == 1.0


# ---------------------------------------------------------------------------
# compute_artifact_stats
# ---------------------------------------------------------------------------


class TestComputeArtifactStats:
    def test_basic(self):
        prs = [
            _make_pr("PR-1", [ArtifactType.BUILD], gate_pass_rate=0.9, review_cycles=1, time_to_merge_hours=10.0),
            _make_pr("PR-2", [ArtifactType.BUILD], gate_pass_rate=0.85, review_cycles=2, time_to_merge_hours=15.0),
            _make_pr("PR-3", [], gate_pass_rate=0.5, review_cycles=3, time_to_merge_hours=40.0),
            _make_pr("PR-4", [], gate_pass_rate=0.6, review_cycles=4, time_to_merge_hours=35.0),
        ]
        stats = compute_artifact_stats(prs, ArtifactType.BUILD)
        assert stats.artifact_type == "build"
        assert stats.n_total == 4
        assert stats.n_with == 2
        assert stats.n_without == 2
        assert stats.usage_rate == 0.5
        assert stats.gate_pass_delta > 0  # build users have higher pass rate
        assert stats.review_delta < 0  # build users have fewer review cycles

    def test_all_with_artifact(self):
        prs = [
            _make_pr("PR-1", [ArtifactType.LINT], gate_pass_rate=0.9, review_cycles=1),
            _make_pr("PR-2", [ArtifactType.LINT], gate_pass_rate=0.8, review_cycles=2),
        ]
        stats = compute_artifact_stats(prs, ArtifactType.LINT)
        assert stats.n_with == 2
        assert stats.n_without == 0
        assert stats.gate_pass_without == 0.0
        assert stats.gate_pass_correlation == 0.0  # all same binary value

    def test_none_with_artifact(self):
        prs = [
            _make_pr("PR-1", [], gate_pass_rate=0.5, review_cycles=3),
            _make_pr("PR-2", [], gate_pass_rate=0.6, review_cycles=2),
        ]
        stats = compute_artifact_stats(prs, ArtifactType.E2E_TESTS)
        assert stats.n_with == 0
        assert stats.n_without == 2
        assert stats.gate_pass_with == 0.0

    def test_merge_time_none_when_not_merged(self):
        prs = [
            _make_pr("PR-1", [ArtifactType.BUILD], time_to_merge_hours=None, merged=False),
            _make_pr("PR-2", [], time_to_merge_hours=None, merged=False),
        ]
        stats = compute_artifact_stats(prs, ArtifactType.BUILD)
        assert stats.merge_time_with is None
        assert stats.merge_time_without is None
        assert stats.merge_time_delta is None
        assert stats.merge_time_correlation is None
        assert stats.merge_time_pvalue is None

    def test_merge_time_correlation_needs_min_10(self):
        # Only 4 merged PRs - should not compute merge_time_correlation
        prs = [
            _make_pr(f"PR-{i}", [ArtifactType.BUILD] if i % 2 == 0 else [], time_to_merge_hours=float(10 + i))
            for i in range(4)
        ]
        stats = compute_artifact_stats(prs, ArtifactType.BUILD)
        assert stats.merge_time_correlation is None

    def test_merge_time_correlation_with_enough_data(self):
        prs = [
            _make_pr(f"PR-{i}", [ArtifactType.BUILD] if i % 2 == 0 else [], time_to_merge_hours=float(10 + i))
            for i in range(20)
        ]
        stats = compute_artifact_stats(prs, ArtifactType.BUILD)
        assert stats.merge_time_correlation is not None
        assert stats.merge_time_pvalue is not None

    def test_merge_time_delta_partial(self):
        # All merged but only some have the artifact
        prs = [
            _make_pr("PR-1", [ArtifactType.BUILD], time_to_merge_hours=10.0),
            _make_pr("PR-2", [], time_to_merge_hours=30.0),
        ]
        stats = compute_artifact_stats(prs, ArtifactType.BUILD)
        assert stats.merge_time_with == 10.0
        assert stats.merge_time_without == 30.0
        assert stats.merge_time_delta == -20.0


# ---------------------------------------------------------------------------
# compute_all_stats
# ---------------------------------------------------------------------------


class TestComputeAllStats:
    def test_returns_all_artifact_types(self):
        prs = generate_sample_prs(n=50, seed=42)
        all_stats = compute_all_stats(prs)
        assert set(all_stats.keys()) == {a.value for a in ArtifactType}
        for key, stats in all_stats.items():
            assert isinstance(stats, ArtifactStats)
            assert stats.artifact_type == key


# ---------------------------------------------------------------------------
# compute_correlation_matrix
# ---------------------------------------------------------------------------


class TestComputeCorrelationMatrix:
    def test_diagonal_is_one(self):
        prs = generate_sample_prs(n=50, seed=42)
        matrix = compute_correlation_matrix(prs)
        for art in ArtifactType:
            assert matrix[art.value][art.value] == 1.0

    def test_symmetry(self):
        prs = generate_sample_prs(n=50, seed=42)
        matrix = compute_correlation_matrix(prs)
        types = list(ArtifactType)
        for a1 in types:
            for a2 in types:
                assert matrix[a1.value][a2.value] == matrix[a2.value][a1.value]

    def test_all_keys_present(self):
        prs = generate_sample_prs(n=30, seed=1)
        matrix = compute_correlation_matrix(prs)
        assert len(matrix) == len(ArtifactType)
        for row in matrix.values():
            assert len(row) == len(ArtifactType)

    def test_pearsonr_exception_fallback(self):
        """Force the except branch in compute_correlation_matrix."""
        prs = generate_sample_prs(n=30, seed=1)
        with patch("harness_skills.effectiveness_stats.sp_stats.pearsonr", side_effect=ValueError("boom")):
            matrix = compute_correlation_matrix(prs)
        # Diagonal should still be 1.0, off-diagonal should be 0.0
        for art in ArtifactType:
            assert matrix[art.value][art.value] == 1.0
            for art2 in ArtifactType:
                if art != art2:
                    assert matrix[art.value][art2.value] == 0.0


# ---------------------------------------------------------------------------
# compute_artifact_combination_effects
# ---------------------------------------------------------------------------


class TestComputeArtifactCombinationEffects:
    def test_returns_list(self):
        prs = generate_sample_prs(n=250, seed=42)
        effects = compute_artifact_combination_effects(prs)
        assert isinstance(effects, list)
        assert len(effects) <= 15

    def test_min_5_prs_per_cluster(self):
        prs = generate_sample_prs(n=250, seed=42)
        effects = compute_artifact_combination_effects(prs)
        for item in effects:
            assert item["n_prs"] >= 5

    def test_sorted_by_gate_pass_rate_desc(self):
        prs = generate_sample_prs(n=250, seed=42)
        effects = compute_artifact_combination_effects(prs)
        if len(effects) > 1:
            rates = [e["avg_gate_pass_rate"] for e in effects]
            assert rates == sorted(rates, reverse=True)

    def test_small_dataset_no_clusters(self):
        # Fewer than 5 PRs for any combo -> empty
        prs = [_make_pr(f"PR-{i}", [ArtifactType.BUILD]) for i in range(3)]
        effects = compute_artifact_combination_effects(prs)
        assert effects == []

    def test_cluster_fields(self):
        prs = generate_sample_prs(n=250, seed=42)
        effects = compute_artifact_combination_effects(prs)
        if effects:
            item = effects[0]
            assert "artifacts" in item
            assert "n_prs" in item
            assert "avg_gate_pass_rate" in item
            assert "avg_review_cycles" in item
            assert "avg_merge_time_hrs" in item

    def test_merge_time_none_when_no_merged(self):
        prs = [
            _make_pr(f"PR-{i}", [ArtifactType.BUILD], time_to_merge_hours=None, merged=False)
            for i in range(10)
        ]
        effects = compute_artifact_combination_effects(prs)
        for item in effects:
            assert item["avg_merge_time_hrs"] is None


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------


class TestSerialisation:
    def test_stats_to_dict(self):
        prs = generate_sample_prs(n=30, seed=42)
        stats = compute_artifact_stats(prs, ArtifactType.BUILD)
        d = stats_to_dict(stats)
        assert isinstance(d, dict)
        assert d["artifact_type"] == "build"
        assert "n_total" in d
        assert "gate_pass_correlation" in d

    def test_stats_to_json_summary(self):
        prs = generate_sample_prs(n=30, seed=42)
        all_stats = compute_all_stats(prs)
        json_str = stats_to_json_summary(all_stats)
        parsed = json.loads(json_str)
        assert isinstance(parsed, dict)
        # Should have all artifact types
        assert set(parsed.keys()) == {a.value for a in ArtifactType}

    def test_json_summary_fields(self):
        prs = generate_sample_prs(n=30, seed=42)
        all_stats = compute_all_stats(prs)
        json_str = stats_to_json_summary(all_stats)
        parsed = json.loads(json_str)
        for art_key, data in parsed.items():
            assert "n_with" in data
            assert "usage_rate" in data
            assert "gate_pass_delta" in data
            assert "gate_pass_significant" in data
            assert "review_significant" in data
            assert "merge_time_significant" in data

    def test_merge_time_significant_false_when_none(self):
        prs = [
            _make_pr(f"PR-{i}", [ArtifactType.BUILD] if i < 2 else [], time_to_merge_hours=None, merged=False)
            for i in range(10)
        ]
        all_stats = compute_all_stats(prs)
        json_str = stats_to_json_summary(all_stats)
        parsed = json.loads(json_str)
        for data in parsed.values():
            if data["merge_time_pvalue"] is None:
                assert data["merge_time_significant"] is False
