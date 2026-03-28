"""
Adversarial Evaluator — separate generator from evaluator.

Inspired by Anthropic's harness design for long-running applications:
https://www.anthropic.com/engineering/harness-design-long-running-apps

Key insight: self-evaluation is fundamentally lenient — models confidently
praise their own mediocre work.  Separating the evaluator from the generator
and tuning it to be skeptical is far more tractable than making a generator
self-critical.

The ``AdversarialEvaluator`` grades outputs along four weighted dimensions:

- **Correctness** (weight ×3): Does the output satisfy the task requirements?
- **Completeness** (weight ×3): Are all requested features / aspects present?
- **Quality** (weight ×2): Is the implementation clean, well-structured, idiomatic?
- **Originality** (weight ×1): Are there creative or non-obvious design choices?

Weights emphasise correctness and completeness (must-haves) while still
rewarding quality and originality (differentiators).

Few-shot calibration examples (GOOD_REVIEW_EXAMPLE and BAD_REVIEW_EXAMPLE)
anchor the evaluator's scoring, preventing drift across iterations.

Usage
-----
::

    from harness_skills.evaluator import AdversarialEvaluator

    evaluator = AdversarialEvaluator(approve_threshold=7.0)
    result = evaluator.grade(
        output="def add(a, b): return a + b",
        task_description="Write a function that adds two numbers",
    )
    print(result.verdict)          # APPROVE or REQUEST_CHANGES
    print(result.score)            # weighted score 0-10
    print(result.dimension_scores) # per-dimension breakdown
    print(result.feedback)         # actionable critique
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Verdict enum
# ---------------------------------------------------------------------------


class Verdict(str, Enum):
    """Evaluation verdict."""

    APPROVE = "APPROVE"
    REQUEST_CHANGES = "REQUEST_CHANGES"


# ---------------------------------------------------------------------------
# Grading dimensions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GradingDimension:
    """A named dimension with a weight and description."""

    name: str
    weight: int
    description: str


#: The four grading dimensions used by the adversarial evaluator.
#: Weights are inspired by Anthropic's harness design — correctness and
#: completeness are weighted higher because they are non-negotiable
#: (the output must work and be complete), while quality and originality
#: are differentiators.
DIMENSIONS: list[GradingDimension] = [
    GradingDimension(
        name="Correctness",
        weight=3,
        description=(
            "Does the output satisfy the task requirements? Are there bugs, "
            "logical errors, or misunderstandings of the spec?"
        ),
    ),
    GradingDimension(
        name="Completeness",
        weight=3,
        description=(
            "Are all requested features, aspects, and edge cases addressed? "
            "Is anything missing or stubbed out?"
        ),
    ),
    GradingDimension(
        name="Quality",
        weight=2,
        description=(
            "Is the implementation clean, well-structured, and idiomatic? "
            "Does it follow best practices for the language / domain?"
        ),
    ),
    GradingDimension(
        name="Originality",
        weight=1,
        description=(
            "Are there creative, non-obvious, or elegant design choices? "
            "Does the output go beyond a boilerplate template solution?"
        ),
    ),
]


# ---------------------------------------------------------------------------
# Few-shot calibration examples
# ---------------------------------------------------------------------------

#: A good review example — the evaluator should score this ≈8.5–9.5.
GOOD_REVIEW_EXAMPLE: dict[str, Any] = {
    "task": "Implement a rate limiter with sliding window algorithm",
    "output_summary": (
        "Clean sliding-window implementation using a sorted set of timestamps. "
        "Handles edge cases (empty window, concurrent access via threading lock). "
        "Includes docstrings, type hints, and unit tests. Uses dataclass for config."
    ),
    "scores": {
        "Correctness": 9,
        "Completeness": 9,
        "Quality": 9,
        "Originality": 7,
    },
    "feedback": (
        "Solid implementation. The sliding window correctly evicts stale entries. "
        "Thread safety via Lock is appropriate. Minor improvement: could use a "
        "more memory-efficient structure (deque) instead of sorted set for "
        "high-throughput scenarios. Originality is adequate but not exceptional — "
        "this is a well-known algorithm implemented competently."
    ),
    "verdict": "APPROVE",
}

#: A bad review example — the evaluator should score this ≈3.0–4.5.
BAD_REVIEW_EXAMPLE: dict[str, Any] = {
    "task": "Implement a rate limiter with sliding window algorithm",
    "output_summary": (
        "Uses a simple counter reset every 60 seconds (fixed window, not sliding). "
        "No thread safety. No docstrings or type hints. Tests are absent. "
        "The counter resets allow burst traffic at window boundaries."
    ),
    "scores": {
        "Correctness": 3,
        "Completeness": 4,
        "Quality": 4,
        "Originality": 2,
    },
    "feedback": (
        "The implementation uses a fixed window, not a sliding window as specified — "
        "this is a fundamental correctness issue. Burst traffic at window boundaries "
        "means the rate limiter can allow 2x the configured rate. No thread safety "
        "makes this unsafe for concurrent use. Missing tests and documentation. "
        "The approach is the simplest possible counter — no creative choices."
    ),
    "verdict": "REQUEST_CHANGES",
}


# ---------------------------------------------------------------------------
# Evaluation result
# ---------------------------------------------------------------------------


@dataclass
class EvaluationResult:
    """Result of grading an output against a task description."""

    score: float
    """Weighted score on a 0–10 scale."""

    verdict: Verdict
    """APPROVE if score >= approve_threshold, else REQUEST_CHANGES."""

    dimension_scores: dict[str, float]
    """Per-dimension raw scores (0–10 each)."""

    feedback: str
    """Actionable critique explaining the scores."""

    weighted_breakdown: dict[str, float] = field(default_factory=dict)
    """Per-dimension weighted contribution to the final score."""


# ---------------------------------------------------------------------------
# Adversarial Evaluator
# ---------------------------------------------------------------------------


class AdversarialEvaluator:
    """Separate adversarial evaluator for agent outputs.

    The evaluator is designed to be run as a *different* agent from the
    generator — separation is what makes adversarial grading tractable.
    Tuning a standalone evaluator to be skeptical is far easier than making
    a generator self-critical.

    Parameters
    ----------
    approve_threshold:
        Minimum weighted score (0–10) to approve the output.  Default: 7.0.
    dimensions:
        Grading dimensions to use.  Defaults to the standard four
        (Correctness ×3, Completeness ×3, Quality ×2, Originality ×1).
    """

    def __init__(
        self,
        approve_threshold: float = 7.0,
        dimensions: list[GradingDimension] | None = None,
    ) -> None:
        self.approve_threshold = approve_threshold
        self.dimensions = dimensions or list(DIMENSIONS)
        self._total_weight = sum(d.weight for d in self.dimensions)

    def grade(
        self,
        output: str,
        task_description: str,
        dimension_scores: dict[str, float] | None = None,
        feedback: str = "",
    ) -> EvaluationResult:
        """Grade an output against the task description.

        In production use, the ``dimension_scores`` and ``feedback`` are
        produced by prompting an LLM evaluator agent with the task, output,
        grading dimensions, and few-shot calibration examples.  This method
        accepts pre-computed scores for deterministic testing and for
        integration with any LLM backend.

        If ``dimension_scores`` is not provided, a heuristic scorer is used
        (suitable for testing; production should always provide LLM scores).

        Parameters
        ----------
        output:
            The generator's output to evaluate.
        task_description:
            What the generator was asked to do.
        dimension_scores:
            Optional dict of dimension_name → score (0–10).  When provided,
            these are used directly.  When absent, a simple heuristic scorer
            is applied.
        feedback:
            Optional pre-written feedback string.  When absent, feedback is
            auto-generated from dimension scores.

        Returns
        -------
        EvaluationResult
            Contains the weighted score, verdict, per-dimension breakdown,
            and actionable feedback.
        """
        if dimension_scores is None:
            dimension_scores = self._heuristic_score(output, task_description)

        # Compute weighted score
        weighted_breakdown: dict[str, float] = {}
        weighted_sum = 0.0
        for dim in self.dimensions:
            raw = float(dimension_scores.get(dim.name, 0.0))
            # Clamp to 0–10
            raw = max(0.0, min(10.0, raw))
            contribution = raw * dim.weight
            weighted_breakdown[dim.name] = round(contribution / self._total_weight, 2)
            weighted_sum += contribution

        score = round(weighted_sum / self._total_weight, 2) if self._total_weight > 0 else 0.0

        # Determine verdict
        verdict = Verdict.APPROVE if score >= self.approve_threshold else Verdict.REQUEST_CHANGES

        # Generate feedback if not provided
        if not feedback:
            feedback = self._generate_feedback(dimension_scores, score, verdict)

        return EvaluationResult(
            score=score,
            verdict=verdict,
            dimension_scores={
                dim.name: round(max(0.0, min(10.0, float(dimension_scores.get(dim.name, 0.0)))), 1)
                for dim in self.dimensions
            },
            feedback=feedback,
            weighted_breakdown=weighted_breakdown,
        )

    def build_evaluator_prompt(
        self,
        output: str,
        task_description: str,
    ) -> str:
        """Build the prompt to send to an LLM evaluator agent.

        This prompt includes the grading dimensions, few-shot calibration
        examples, and the actual output to evaluate.  Send this to a
        *separate* model instance from the generator.

        Returns
        -------
        str
            A complete prompt string for the evaluator LLM.
        """
        dim_block = "\n".join(
            f"- **{d.name}** (weight ×{d.weight}): {d.description}"
            for d in self.dimensions
        )

        good = GOOD_REVIEW_EXAMPLE
        bad = BAD_REVIEW_EXAMPLE

        return f"""\
You are an ADVERSARIAL EVALUATOR. Your job is to find flaws, not to praise.
You are evaluating work produced by a DIFFERENT agent — you owe it no charity.

## Grading Dimensions (score each 0–10)

{dim_block}

## Calibration Examples

### Example A — Strong Output (≈8.5 weighted)
Task: {good["task"]}
Summary: {good["output_summary"]}
Scores: {good["scores"]}
Feedback: {good["feedback"]}

### Example B — Weak Output (≈3.5 weighted)
Task: {bad["task"]}
Summary: {bad["output_summary"]}
Scores: {bad["scores"]}
Feedback: {bad["feedback"]}

## Your Task

**Task Description:** {task_description}

**Output to Evaluate:**
```
{output}
```

Grade each dimension 0–10, then write specific, actionable feedback.
Be skeptical. If something looks wrong, it probably is.
Approval threshold: {self.approve_threshold}/10.

Respond in this exact format:
Correctness: <score>
Completeness: <score>
Quality: <score>
Originality: <score>
Verdict: APPROVE | REQUEST_CHANGES
Feedback: <your detailed, actionable critique>
"""

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _heuristic_score(
        self,
        output: str,
        task_description: str,
    ) -> dict[str, float]:
        """Simple heuristic scorer for testing.

        This is NOT a substitute for LLM evaluation — it provides basic
        signal based on output length, structure, and keyword overlap.
        """
        scores: dict[str, float] = {}

        # Length-based baseline (very rough)
        length = len(output.strip())
        if length == 0:
            return {d.name: 0.0 for d in self.dimensions}

        base = min(7.0, 3.0 + (length / 200))  # longer = somewhat better, caps at 7

        # Keyword overlap with task description
        task_words = set(task_description.lower().split())
        output_words = set(output.lower().split())
        overlap = len(task_words & output_words) / max(len(task_words), 1)
        correctness_bonus = overlap * 3.0

        scores["Correctness"] = min(10.0, base + correctness_bonus)
        scores["Completeness"] = min(10.0, base + overlap * 2.0)
        scores["Quality"] = min(10.0, base + (1.0 if "def " in output or "class " in output else 0.0))
        scores["Originality"] = min(10.0, max(2.0, base - 1.5))

        return scores

    def _generate_feedback(
        self,
        dimension_scores: dict[str, float],
        score: float,
        verdict: Verdict,
    ) -> str:
        """Auto-generate feedback from dimension scores."""
        lines: list[str] = []

        weak_dims = [
            d.name
            for d in self.dimensions
            if dimension_scores.get(d.name, 0.0) < 6.0
        ]
        strong_dims = [
            d.name
            for d in self.dimensions
            if dimension_scores.get(d.name, 0.0) >= 8.0
        ]

        if strong_dims:
            lines.append(f"Strong: {', '.join(strong_dims)}.")
        if weak_dims:
            lines.append(f"Needs improvement: {', '.join(weak_dims)}.")

        lines.append(f"Weighted score: {score}/10.")

        if verdict == Verdict.APPROVE:
            lines.append("Output meets the approval threshold.")
        else:
            lines.append(
                f"Output falls below the approval threshold ({self.approve_threshold}). "
                "Address the weak dimensions before resubmitting."
            )

        return " ".join(lines)
