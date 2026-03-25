"""
Tests covering the 3 uncovered lines in harness_dashboard/models.py:
  - Line 54: PRRecord._check_merged_has_time raises ValueError
  - Lines 75-76: EffectivenessMetrics.score_bar()
"""

from __future__ import annotations

import pytest

from harness_dashboard.models import (
    ArtifactType,
    EffectivenessMetrics,
    EffectivenessTier,
    PRRecord,
)


class TestPRRecordValidator:
    def test_merged_true_with_zero_ttm_raises(self):
        """Line 54: merged=True and time_to_merge_hours <= 0 raises ValueError."""
        with pytest.raises(ValueError, match="merged=True requires time_to_merge_hours > 0"):
            PRRecord(
                pr_id="PR-001",
                harness_id="hrn-001",
                gate_pass_rate=0.9,
                review_cycles=1,
                time_to_merge_hours=0.0,
                merged=True,
            )


class TestScoreBar:
    def test_score_bar_returns_string(self):
        """Lines 75-76: score_bar() should return a bracketed bar."""
        m = EffectivenessMetrics(
            harness_id="h1",
            artifact_type=ArtifactType.FIXTURE,
            artifact_count=10,
            coverage_pct=70.0,
            effectiveness_score=50.0,
        )
        bar = m.score_bar()
        assert bar.startswith("[")
        assert bar.endswith("]")
        assert len(bar) == 22  # [ + 20 chars + ]

    def test_score_bar_custom_width(self):
        m = EffectivenessMetrics(
            harness_id="h1",
            artifact_type=ArtifactType.FIXTURE,
            artifact_count=10,
            coverage_pct=70.0,
            effectiveness_score=100.0,
        )
        bar = m.score_bar(width=10)
        assert len(bar) == 12  # [ + 10 + ]
        assert bar == "[██████████]"

    def test_score_bar_zero(self):
        m = EffectivenessMetrics(
            harness_id="h1",
            artifact_type=ArtifactType.FIXTURE,
            artifact_count=10,
            coverage_pct=70.0,
            effectiveness_score=0.0,
        )
        bar = m.score_bar()
        assert "█" not in bar
        assert "░" in bar
