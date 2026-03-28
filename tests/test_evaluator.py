"""Tests for harness_skills.evaluator — AdversarialEvaluator."""

from __future__ import annotations

import pytest

from harness_skills.evaluator import (
    DIMENSIONS,
    GOOD_REVIEW_EXAMPLE,
    BAD_REVIEW_EXAMPLE,
    AdversarialEvaluator,
    EvaluationResult,
    GradingDimension,
    Verdict,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def evaluator() -> AdversarialEvaluator:
    return AdversarialEvaluator(approve_threshold=7.0)


@pytest.fixture
def lenient_evaluator() -> AdversarialEvaluator:
    return AdversarialEvaluator(approve_threshold=5.0)


@pytest.fixture
def strict_evaluator() -> AdversarialEvaluator:
    return AdversarialEvaluator(approve_threshold=9.0)


# ---------------------------------------------------------------------------
# Basic construction
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_default_threshold(self, evaluator: AdversarialEvaluator):
        assert evaluator.approve_threshold == 7.0

    def test_custom_threshold(self):
        e = AdversarialEvaluator(approve_threshold=8.5)
        assert e.approve_threshold == 8.5

    def test_default_dimensions(self, evaluator: AdversarialEvaluator):
        assert len(evaluator.dimensions) == 4
        names = [d.name for d in evaluator.dimensions]
        assert names == ["Correctness", "Completeness", "Quality", "Originality"]

    def test_custom_dimensions(self):
        custom = [GradingDimension(name="Speed", weight=5, description="How fast")]
        e = AdversarialEvaluator(dimensions=custom)
        assert len(e.dimensions) == 1
        assert e.dimensions[0].name == "Speed"

    def test_dimension_weights(self, evaluator: AdversarialEvaluator):
        weights = {d.name: d.weight for d in evaluator.dimensions}
        assert weights["Correctness"] == 3
        assert weights["Completeness"] == 3
        assert weights["Quality"] == 2
        assert weights["Originality"] == 1


# ---------------------------------------------------------------------------
# Grading with explicit scores
# ---------------------------------------------------------------------------


class TestGrading:
    def test_approve_high_scores(self, evaluator: AdversarialEvaluator):
        result = evaluator.grade(
            output="excellent implementation",
            task_description="build something",
            dimension_scores={
                "Correctness": 9,
                "Completeness": 8,
                "Quality": 8,
                "Originality": 7,
            },
        )
        assert result.verdict == Verdict.APPROVE
        assert result.score >= 7.0

    def test_reject_low_scores(self, evaluator: AdversarialEvaluator):
        result = evaluator.grade(
            output="poor implementation",
            task_description="build something",
            dimension_scores={
                "Correctness": 3,
                "Completeness": 2,
                "Quality": 4,
                "Originality": 1,
            },
        )
        assert result.verdict == Verdict.REQUEST_CHANGES
        assert result.score < 7.0

    def test_weighted_score_calculation(self, evaluator: AdversarialEvaluator):
        """Verify the weighted average: (9*3 + 9*3 + 9*2 + 9*1) / 9 = 9.0"""
        result = evaluator.grade(
            output="uniform scores",
            task_description="test",
            dimension_scores={
                "Correctness": 9,
                "Completeness": 9,
                "Quality": 9,
                "Originality": 9,
            },
        )
        assert result.score == 9.0

    def test_weight_asymmetry(self, evaluator: AdversarialEvaluator):
        """Correctness (×3) matters more than Originality (×1)."""
        # High correctness, low originality
        r1 = evaluator.grade(
            output="a", task_description="b",
            dimension_scores={
                "Correctness": 10, "Completeness": 5, "Quality": 5, "Originality": 0,
            },
        )
        # Low correctness, high originality
        r2 = evaluator.grade(
            output="a", task_description="b",
            dimension_scores={
                "Correctness": 0, "Completeness": 5, "Quality": 5, "Originality": 10,
            },
        )
        assert r1.score > r2.score

    def test_score_clamped_to_0_10(self, evaluator: AdversarialEvaluator):
        result = evaluator.grade(
            output="a", task_description="b",
            dimension_scores={
                "Correctness": 15,  # above 10
                "Completeness": -5,  # below 0
                "Quality": 7,
                "Originality": 7,
            },
        )
        assert 0.0 <= result.score <= 10.0
        assert result.dimension_scores["Correctness"] == 10.0
        assert result.dimension_scores["Completeness"] == 0.0

    def test_exact_threshold_approves(self, evaluator: AdversarialEvaluator):
        """Score exactly at threshold should APPROVE."""
        # Total weight = 9. We need weighted_sum / 9 == 7.0 → weighted_sum = 63
        # All scores = 7.0: (7*3 + 7*3 + 7*2 + 7*1) = 63. 63/9 = 7.0
        result = evaluator.grade(
            output="a", task_description="b",
            dimension_scores={
                "Correctness": 7, "Completeness": 7, "Quality": 7, "Originality": 7,
            },
        )
        assert result.score == 7.0
        assert result.verdict == Verdict.APPROVE

    def test_just_below_threshold_rejects(self, evaluator: AdversarialEvaluator):
        result = evaluator.grade(
            output="a", task_description="b",
            dimension_scores={
                "Correctness": 6.9, "Completeness": 6.9, "Quality": 6.9, "Originality": 6.9,
            },
        )
        assert result.score < 7.0
        assert result.verdict == Verdict.REQUEST_CHANGES


# ---------------------------------------------------------------------------
# Threshold variations
# ---------------------------------------------------------------------------


class TestThresholdVariations:
    def test_lenient_approves_moderate_work(self, lenient_evaluator: AdversarialEvaluator):
        result = lenient_evaluator.grade(
            output="a", task_description="b",
            dimension_scores={
                "Correctness": 6, "Completeness": 5, "Quality": 5, "Originality": 4,
            },
        )
        assert result.verdict == Verdict.APPROVE

    def test_strict_rejects_good_work(self, strict_evaluator: AdversarialEvaluator):
        result = strict_evaluator.grade(
            output="a", task_description="b",
            dimension_scores={
                "Correctness": 8, "Completeness": 8, "Quality": 8, "Originality": 8,
            },
        )
        assert result.verdict == Verdict.REQUEST_CHANGES


# ---------------------------------------------------------------------------
# Heuristic scoring (no explicit scores provided)
# ---------------------------------------------------------------------------


class TestHeuristicScoring:
    def test_empty_output_scores_zero(self, evaluator: AdversarialEvaluator):
        result = evaluator.grade(output="", task_description="write something")
        assert result.score == 0.0
        assert result.verdict == Verdict.REQUEST_CHANGES

    def test_whitespace_output_scores_zero(self, evaluator: AdversarialEvaluator):
        result = evaluator.grade(output="   \n  ", task_description="write something")
        assert result.score == 0.0

    def test_nonempty_output_scores_above_zero(self, evaluator: AdversarialEvaluator):
        result = evaluator.grade(
            output="def add(a, b): return a + b",
            task_description="Write a function that adds two numbers",
        )
        assert result.score > 0.0

    def test_longer_output_generally_scores_higher(self, evaluator: AdversarialEvaluator):
        short = evaluator.grade(output="x = 1", task_description="build an app")
        long = evaluator.grade(
            output="class App:\n    def __init__(self):\n        self.x = 1\n" * 10,
            task_description="build an app",
        )
        assert long.score >= short.score


# ---------------------------------------------------------------------------
# Feedback generation
# ---------------------------------------------------------------------------


class TestFeedback:
    def test_custom_feedback_passed_through(self, evaluator: AdversarialEvaluator):
        result = evaluator.grade(
            output="x", task_description="y",
            dimension_scores={"Correctness": 9, "Completeness": 9, "Quality": 9, "Originality": 9},
            feedback="Custom feedback text",
        )
        assert result.feedback == "Custom feedback text"

    def test_auto_feedback_mentions_weak_dimensions(self, evaluator: AdversarialEvaluator):
        result = evaluator.grade(
            output="x", task_description="y",
            dimension_scores={"Correctness": 3, "Completeness": 9, "Quality": 3, "Originality": 9},
        )
        assert "Correctness" in result.feedback
        assert "Quality" in result.feedback

    def test_auto_feedback_mentions_strong_dimensions(self, evaluator: AdversarialEvaluator):
        result = evaluator.grade(
            output="x", task_description="y",
            dimension_scores={"Correctness": 9, "Completeness": 9, "Quality": 3, "Originality": 3},
        )
        assert "Correctness" in result.feedback or "Completeness" in result.feedback


# ---------------------------------------------------------------------------
# Evaluator prompt builder
# ---------------------------------------------------------------------------


class TestPromptBuilder:
    def test_prompt_contains_dimensions(self, evaluator: AdversarialEvaluator):
        prompt = evaluator.build_evaluator_prompt(
            output="hello world",
            task_description="greet the world",
        )
        assert "Correctness" in prompt
        assert "Completeness" in prompt
        assert "Quality" in prompt
        assert "Originality" in prompt

    def test_prompt_contains_calibration_examples(self, evaluator: AdversarialEvaluator):
        prompt = evaluator.build_evaluator_prompt(output="x", task_description="y")
        assert "rate limiter" in prompt.lower()
        assert "APPROVE" in prompt
        assert "REQUEST_CHANGES" in prompt

    def test_prompt_contains_output(self, evaluator: AdversarialEvaluator):
        prompt = evaluator.build_evaluator_prompt(
            output="def unique_function_xyz(): pass",
            task_description="something",
        )
        assert "unique_function_xyz" in prompt

    def test_prompt_contains_task(self, evaluator: AdversarialEvaluator):
        prompt = evaluator.build_evaluator_prompt(
            output="x",
            task_description="Build a time-travel machine",
        )
        assert "time-travel machine" in prompt

    def test_prompt_mentions_adversarial_role(self, evaluator: AdversarialEvaluator):
        prompt = evaluator.build_evaluator_prompt(output="x", task_description="y")
        assert "ADVERSARIAL" in prompt


# ---------------------------------------------------------------------------
# Few-shot examples
# ---------------------------------------------------------------------------


class TestFewShotExamples:
    def test_good_example_has_required_fields(self):
        assert "task" in GOOD_REVIEW_EXAMPLE
        assert "scores" in GOOD_REVIEW_EXAMPLE
        assert "feedback" in GOOD_REVIEW_EXAMPLE
        assert "verdict" in GOOD_REVIEW_EXAMPLE

    def test_bad_example_has_required_fields(self):
        assert "task" in BAD_REVIEW_EXAMPLE
        assert "scores" in BAD_REVIEW_EXAMPLE
        assert "feedback" in BAD_REVIEW_EXAMPLE
        assert "verdict" in BAD_REVIEW_EXAMPLE

    def test_good_example_scores_higher(self, evaluator: AdversarialEvaluator):
        good_result = evaluator.grade(
            output="good",
            task_description=GOOD_REVIEW_EXAMPLE["task"],
            dimension_scores=GOOD_REVIEW_EXAMPLE["scores"],
        )
        bad_result = evaluator.grade(
            output="bad",
            task_description=BAD_REVIEW_EXAMPLE["task"],
            dimension_scores=BAD_REVIEW_EXAMPLE["scores"],
        )
        assert good_result.score > bad_result.score

    def test_good_example_approves(self, evaluator: AdversarialEvaluator):
        result = evaluator.grade(
            output="good",
            task_description=GOOD_REVIEW_EXAMPLE["task"],
            dimension_scores=GOOD_REVIEW_EXAMPLE["scores"],
        )
        assert result.verdict == Verdict.APPROVE

    def test_bad_example_rejects(self, evaluator: AdversarialEvaluator):
        result = evaluator.grade(
            output="bad",
            task_description=BAD_REVIEW_EXAMPLE["task"],
            dimension_scores=BAD_REVIEW_EXAMPLE["scores"],
        )
        assert result.verdict == Verdict.REQUEST_CHANGES


# ---------------------------------------------------------------------------
# EvaluationResult structure
# ---------------------------------------------------------------------------


class TestEvaluationResult:
    def test_result_has_all_fields(self, evaluator: AdversarialEvaluator):
        result = evaluator.grade(
            output="x", task_description="y",
            dimension_scores={"Correctness": 7, "Completeness": 7, "Quality": 7, "Originality": 7},
        )
        assert isinstance(result, EvaluationResult)
        assert isinstance(result.score, float)
        assert isinstance(result.verdict, Verdict)
        assert isinstance(result.dimension_scores, dict)
        assert isinstance(result.feedback, str)
        assert isinstance(result.weighted_breakdown, dict)

    def test_weighted_breakdown_sums_to_score(self, evaluator: AdversarialEvaluator):
        result = evaluator.grade(
            output="x", task_description="y",
            dimension_scores={"Correctness": 8, "Completeness": 6, "Quality": 7, "Originality": 5},
        )
        breakdown_sum = sum(result.weighted_breakdown.values())
        # Allow small floating point tolerance
        assert abs(breakdown_sum - result.score) < 0.1
