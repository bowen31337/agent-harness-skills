"""Tests for harness_skills.pr_effectiveness — data models + sample generator."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from harness_skills.pr_effectiveness import (
    ArtifactEffectivenessScore,
    ArtifactType,
    HarnessArtifact,
    HarnessEffectivenessReport,
    PRRecord,
    generate_sample_prs,
)


# ---------------------------------------------------------------------------
# ArtifactType enum
# ---------------------------------------------------------------------------


class TestArtifactType:
    def test_enum_values(self):
        assert ArtifactType.BUILD == "build"
        assert ArtifactType.LINT == "lint"
        assert ArtifactType.UNIT_TESTS == "unit_tests"
        assert ArtifactType.E2E_TESTS == "e2e_tests"
        assert ArtifactType.MUTATION_TESTS == "mutation_tests"

    def test_all_members(self):
        assert len(ArtifactType) == 11


# ---------------------------------------------------------------------------
# HarnessArtifact
# ---------------------------------------------------------------------------


class TestHarnessArtifact:
    def test_basic_creation(self):
        a = HarnessArtifact(
            artifact_type=ArtifactType.BUILD,
            passed=True,
            execution_time_seconds=12.5,
        )
        assert a.artifact_type == ArtifactType.BUILD
        assert a.passed is True
        assert a.coverage_pct is None
        assert a.issues_found == 0

    def test_with_coverage(self):
        a = HarnessArtifact(
            artifact_type=ArtifactType.COVERAGE_REPORT,
            passed=True,
            execution_time_seconds=30.0,
            coverage_pct=85.5,
            issues_found=2,
        )
        assert a.coverage_pct == 85.5
        assert a.issues_found == 2


# ---------------------------------------------------------------------------
# PRRecord
# ---------------------------------------------------------------------------


class TestPRRecord:
    @pytest.fixture()
    def sample_pr(self):
        return PRRecord(
            pr_id="PR-0001",
            repo="api-gateway",
            author="dev-01",
            created_at=datetime(2025, 10, 1, tzinfo=timezone.utc),
            artifacts=[
                HarnessArtifact(
                    artifact_type=ArtifactType.BUILD,
                    passed=True,
                    execution_time_seconds=10.0,
                ),
                HarnessArtifact(
                    artifact_type=ArtifactType.LINT,
                    passed=True,
                    execution_time_seconds=5.0,
                ),
            ],
            gate_pass_rate=0.9,
            review_cycles=1,
            time_to_merge_hours=24.0,
            merged=True,
            merged_at=datetime(2025, 10, 2, tzinfo=timezone.utc),
        )

    def test_artifact_types_used(self, sample_pr):
        assert sample_pr.artifact_types_used == {ArtifactType.BUILD, ArtifactType.LINT}

    def test_artifact_count(self, sample_pr):
        assert sample_pr.artifact_count == 2

    def test_defaults(self):
        pr = PRRecord(
            pr_id="PR-X",
            repo="r",
            author="a",
            created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            gate_pass_rate=0.5,
            review_cycles=0,
        )
        assert pr.merged is False
        assert pr.merged_at is None
        assert pr.time_to_merge_hours is None
        assert pr.post_merge_incidents == 0
        assert pr.artifacts == []
        assert pr.artifact_types_used == set()
        assert pr.artifact_count == 0


# ---------------------------------------------------------------------------
# ArtifactEffectivenessScore
# ---------------------------------------------------------------------------


class TestArtifactEffectivenessScore:
    def test_creation(self):
        score = ArtifactEffectivenessScore(
            artifact_type="build",
            effectiveness_score=75.0,
            gate_pass_impact=0.15,
            review_cycle_impact=-0.3,
            merge_time_impact=-2.0,
            usage_rate=0.9,
            confidence=0.85,
            priority="high",
            key_insight="Build runs correlate with higher gate pass rates.",
            recommendation="Ensure all PRs run the build step.",
        )
        assert score.effectiveness_score == 75.0
        assert score.priority == "high"

    def test_validation_bounds(self):
        with pytest.raises(Exception):
            ArtifactEffectivenessScore(
                artifact_type="x",
                effectiveness_score=200.0,  # out of range
                gate_pass_impact=0,
                review_cycle_impact=0,
                merge_time_impact=0,
                usage_rate=0.5,
                confidence=0.5,
                priority="low",
                key_insight="x",
                recommendation="x",
            )


# ---------------------------------------------------------------------------
# HarnessEffectivenessReport
# ---------------------------------------------------------------------------


class TestHarnessEffectivenessReport:
    def test_creation(self):
        report = HarnessEffectivenessReport(
            analysis_timestamp="2025-10-01T00:00:00Z",
            total_prs_analyzed=100,
            date_range="2025-09-01 to 2025-10-01",
            overall_harness_health_score=80.0,
            coverage_score=70.0,
            effectiveness_score=90.0,
            artifact_scores=[],
            critical_gaps=["Missing e2e tests"],
            top_recommendations=["Add e2e tests"],
            executive_summary="Good overall.",
            methodology_note="Point-biserial correlations.",
        )
        assert report.total_prs_analyzed == 100
        assert report.critical_gaps == ["Missing e2e tests"]


# ---------------------------------------------------------------------------
# generate_sample_prs
# ---------------------------------------------------------------------------


class TestGenerateSamplePRs:
    def test_default_count(self):
        prs = generate_sample_prs()
        assert len(prs) == 250

    def test_custom_count(self):
        prs = generate_sample_prs(n=10, seed=123)
        assert len(prs) == 10

    def test_deterministic(self):
        a = generate_sample_prs(n=20, seed=99)
        b = generate_sample_prs(n=20, seed=99)
        assert [p.pr_id for p in a] == [p.pr_id for p in b]
        assert [p.gate_pass_rate for p in a] == [p.gate_pass_rate for p in b]

    def test_pr_ids_sequential(self):
        prs = generate_sample_prs(n=5, seed=1)
        assert [p.pr_id for p in prs] == [
            "PR-0001", "PR-0002", "PR-0003", "PR-0004", "PR-0005",
        ]

    def test_repos_and_authors(self):
        prs = generate_sample_prs(n=50, seed=42)
        repos = {p.repo for p in prs}
        authors = {p.author for p in prs}
        assert len(repos) >= 2
        assert len(authors) >= 2

    def test_merged_prs_have_merge_time(self):
        prs = generate_sample_prs(n=100, seed=42)
        for pr in prs:
            if pr.merged:
                assert pr.time_to_merge_hours is not None
                assert pr.merged_at is not None
            else:
                assert pr.time_to_merge_hours is None
                assert pr.merged_at is None

    def test_gate_pass_rate_bounds(self):
        prs = generate_sample_prs(n=200, seed=42)
        for pr in prs:
            assert 0.0 <= pr.gate_pass_rate <= 1.0

    def test_artifacts_present(self):
        prs = generate_sample_prs(n=100, seed=42)
        total_artifacts = sum(p.artifact_count for p in prs)
        assert total_artifacts > 0

    def test_coverage_pct_only_on_coverage_report(self):
        prs = generate_sample_prs(n=100, seed=42)
        for pr in prs:
            for a in pr.artifacts:
                if a.artifact_type == ArtifactType.COVERAGE_REPORT:
                    assert a.coverage_pct is not None
                else:
                    assert a.coverage_pct is None
