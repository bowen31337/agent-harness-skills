"""Tests for harness_skills.pivot_tracker — PivotTracker."""

from __future__ import annotations

import pytest

from harness_skills.pivot_tracker import PivotDecision, PivotTracker


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tracker() -> PivotTracker:
    return PivotTracker(approve_threshold=7.0)


@pytest.fixture
def sensitive_tracker() -> PivotTracker:
    """Pivot after just 1 consecutive decline."""
    return PivotTracker(approve_threshold=7.0, decline_count_to_pivot=1)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_default_threshold(self, tracker: PivotTracker):
        assert tracker.approve_threshold == 7.0

    def test_default_decline_count(self, tracker: PivotTracker):
        assert tracker.decline_count_to_pivot == 2

    def test_custom_parameters(self):
        t = PivotTracker(approve_threshold=8.0, decline_count_to_pivot=3)
        assert t.approve_threshold == 8.0
        assert t.decline_count_to_pivot == 3

    def test_initial_state_empty(self, tracker: PivotTracker):
        assert tracker.scores == []
        assert tracker.decisions == []
        assert tracker.consecutive_declines == 0
        assert tracker.latest_score is None
        assert tracker.latest_decision is None


# ---------------------------------------------------------------------------
# APPROVE decision
# ---------------------------------------------------------------------------


class TestApproveDecision:
    def test_score_at_threshold_approves(self, tracker: PivotTracker):
        decision = tracker.record_score(7.0)
        assert decision == PivotDecision.APPROVE

    def test_score_above_threshold_approves(self, tracker: PivotTracker):
        decision = tracker.record_score(9.5)
        assert decision == PivotDecision.APPROVE

    def test_approve_resets_decline_counter(self, tracker: PivotTracker):
        tracker.record_score(5.0)
        tracker.record_score(4.0)  # one decline
        assert tracker.consecutive_declines == 1
        tracker.record_score(8.0)  # approve
        assert tracker.consecutive_declines == 0

    def test_approve_on_first_score(self, tracker: PivotTracker):
        decision = tracker.record_score(7.5)
        assert decision == PivotDecision.APPROVE


# ---------------------------------------------------------------------------
# REFINE decision
# ---------------------------------------------------------------------------


class TestRefineDecision:
    def test_first_score_below_threshold_refines(self, tracker: PivotTracker):
        decision = tracker.record_score(5.0)
        assert decision == PivotDecision.REFINE

    def test_improving_scores_refine(self, tracker: PivotTracker):
        tracker.record_score(4.0)
        decision = tracker.record_score(5.0)
        assert decision == PivotDecision.REFINE

    def test_stable_scores_refine(self, tracker: PivotTracker):
        tracker.record_score(5.0)
        decision = tracker.record_score(5.0)
        assert decision == PivotDecision.REFINE

    def test_single_decline_still_refines(self, tracker: PivotTracker):
        tracker.record_score(5.0)
        decision = tracker.record_score(4.5)
        assert decision == PivotDecision.REFINE
        assert tracker.consecutive_declines == 1


# ---------------------------------------------------------------------------
# PIVOT decision
# ---------------------------------------------------------------------------


class TestPivotDecision:
    def test_two_consecutive_declines_trigger_pivot(self, tracker: PivotTracker):
        tracker.record_score(5.0)
        tracker.record_score(4.5)  # decline 1
        decision = tracker.record_score(4.0)  # decline 2
        assert decision == PivotDecision.PIVOT

    def test_interrupted_decline_resets_counter(self, tracker: PivotTracker):
        tracker.record_score(5.0)
        tracker.record_score(4.5)  # decline 1
        tracker.record_score(5.0)  # improvement — resets counter
        decision = tracker.record_score(4.5)  # decline 1 again
        assert decision == PivotDecision.REFINE
        assert tracker.consecutive_declines == 1

    def test_three_consecutive_declines_still_pivot(self, tracker: PivotTracker):
        tracker.record_score(6.0)
        tracker.record_score(5.5)
        tracker.record_score(5.0)
        decision = tracker.record_score(4.5)
        assert decision == PivotDecision.PIVOT

    def test_sensitive_tracker_pivots_on_single_decline(self, sensitive_tracker: PivotTracker):
        sensitive_tracker.record_score(5.0)
        decision = sensitive_tracker.record_score(4.0)
        assert decision == PivotDecision.PIVOT


# ---------------------------------------------------------------------------
# Score tracking
# ---------------------------------------------------------------------------


class TestScoreTracking:
    def test_scores_accumulate(self, tracker: PivotTracker):
        tracker.record_score(3.0)
        tracker.record_score(4.0)
        tracker.record_score(5.0)
        assert tracker.scores == [3.0, 4.0, 5.0]

    def test_latest_score(self, tracker: PivotTracker):
        tracker.record_score(3.0)
        tracker.record_score(5.0)
        assert tracker.latest_score == 5.0

    def test_decisions_accumulate(self, tracker: PivotTracker):
        tracker.record_score(3.0)
        tracker.record_score(4.0)
        assert len(tracker.decisions) == 2
        assert all(isinstance(d, PivotDecision) for d in tracker.decisions)

    def test_latest_decision(self, tracker: PivotTracker):
        tracker.record_score(8.0)
        assert tracker.latest_decision == PivotDecision.APPROVE


# ---------------------------------------------------------------------------
# reset_trend()
# ---------------------------------------------------------------------------


class TestResetTrend:
    def test_reset_clears_decline_counter(self, tracker: PivotTracker):
        tracker.record_score(5.0)
        tracker.record_score(4.0)
        assert tracker.consecutive_declines == 1
        tracker.reset_trend()
        assert tracker.consecutive_declines == 0

    def test_reset_preserves_score_history(self, tracker: PivotTracker):
        tracker.record_score(5.0)
        tracker.record_score(4.0)
        tracker.reset_trend()
        assert tracker.scores == [5.0, 4.0]

    def test_post_pivot_fresh_start(self, tracker: PivotTracker):
        """After a pivot + reset, a single decline doesn't trigger another pivot."""
        tracker.record_score(5.0)
        tracker.record_score(4.5)
        tracker.record_score(4.0)  # PIVOT
        tracker.reset_trend()
        tracker.record_score(6.0)
        decision = tracker.record_score(5.5)  # one decline
        assert decision == PivotDecision.REFINE


# ---------------------------------------------------------------------------
# to_plan_entry()
# ---------------------------------------------------------------------------


class TestPlanEntry:
    def test_plan_entry_contains_header(self, tracker: PivotTracker):
        tracker.record_score(5.0)
        entry = tracker.to_plan_entry()
        assert "Pivot Tracker Status" in entry

    def test_plan_entry_contains_threshold(self, tracker: PivotTracker):
        entry = tracker.to_plan_entry()
        assert "7.0" in entry

    def test_plan_entry_shows_latest_score(self, tracker: PivotTracker):
        tracker.record_score(5.5)
        entry = tracker.to_plan_entry()
        assert "5.5" in entry

    def test_plan_entry_shows_score_trend(self, tracker: PivotTracker):
        tracker.record_score(3.0)
        tracker.record_score(4.0)
        tracker.record_score(5.0)
        entry = tracker.to_plan_entry()
        assert "3.0" in entry
        assert "4.0" in entry
        assert "5.0" in entry
        assert "→" in entry

    def test_plan_entry_shows_decision(self, tracker: PivotTracker):
        tracker.record_score(8.0)
        entry = tracker.to_plan_entry()
        assert "APPROVE" in entry

    def test_empty_tracker_plan_entry(self, tracker: PivotTracker):
        entry = tracker.to_plan_entry()
        assert "Total iterations" in entry
        assert "0" in entry


# ---------------------------------------------------------------------------
# Full scenario: generate → evaluate → refine/pivot loop
# ---------------------------------------------------------------------------


class TestFullScenario:
    def test_improving_then_approve(self, tracker: PivotTracker):
        """Steadily improving scores → eventually approved."""
        decisions = []
        for s in [4.0, 5.0, 6.0, 6.5, 7.0]:
            decisions.append(tracker.record_score(s))
        assert PivotDecision.APPROVE in decisions
        assert PivotDecision.PIVOT not in decisions

    def test_declining_triggers_pivot(self, tracker: PivotTracker):
        """Declining scores → pivot triggered."""
        d1 = tracker.record_score(5.0)
        d2 = tracker.record_score(4.5)
        d3 = tracker.record_score(4.0)
        assert d1 == PivotDecision.REFINE
        assert d2 == PivotDecision.REFINE
        assert d3 == PivotDecision.PIVOT

    def test_pivot_then_improve_then_approve(self, tracker: PivotTracker):
        """Decline → pivot → fresh approach → approve."""
        tracker.record_score(5.0)
        tracker.record_score(4.5)
        d = tracker.record_score(4.0)
        assert d == PivotDecision.PIVOT

        tracker.reset_trend()
        tracker.record_score(6.0)
        d = tracker.record_score(7.5)
        assert d == PivotDecision.APPROVE
