"""
Example: Adversarial Evaluator + Pivot Tracker

Demonstrates how to use the AdversarialEvaluator and PivotTracker together
in a simulated generate → evaluate → refine/pivot loop.

This example uses pre-computed scores (no LLM calls) to show the mechanics.
In production, you would:
  1. Send evaluator.build_evaluator_prompt() to a separate LLM instance
  2. Parse the dimension scores from the LLM response
  3. Pass them to evaluator.grade()
"""

from harness_skills.evaluator import AdversarialEvaluator, Verdict
from harness_skills.pivot_tracker import PivotTracker, PivotDecision


def main():
    # Create evaluator and pivot tracker with matching thresholds
    evaluator = AdversarialEvaluator(approve_threshold=7.0)
    tracker = PivotTracker(approve_threshold=7.0)

    # Simulated iteration scores (as if returned by an LLM evaluator)
    # This simulates: improving → declining → pivot → improving → approved
    iterations = [
        {
            "output": "First attempt: basic implementation with some gaps",
            "scores": {"Correctness": 5, "Completeness": 4, "Quality": 5, "Originality": 3},
        },
        {
            "output": "Second attempt: improved correctness, added missing features",
            "scores": {"Correctness": 6, "Completeness": 6, "Quality": 6, "Originality": 4},
        },
        {
            "output": "Third attempt: minor regression, over-complicated design",
            "scores": {"Correctness": 5, "Completeness": 6, "Quality": 5, "Originality": 4},
        },
        {
            "output": "Fourth attempt: further decline, stuck in a rut",
            "scores": {"Correctness": 4, "Completeness": 5, "Quality": 4, "Originality": 3},
        },
        # After pivot — fresh approach
        {
            "output": "Fifth attempt (post-pivot): clean new approach",
            "scores": {"Correctness": 7, "Completeness": 7, "Quality": 7, "Originality": 6},
        },
        {
            "output": "Sixth attempt: refined new approach, nearly there",
            "scores": {"Correctness": 8, "Completeness": 8, "Quality": 8, "Originality": 7},
        },
    ]

    print("=" * 60)
    print("Adversarial Evaluator + Pivot Tracker Demo")
    print("=" * 60)

    for i, iteration in enumerate(iterations, 1):
        # Grade the output
        result = evaluator.grade(
            output=iteration["output"],
            task_description="Implement a rate limiter with sliding window algorithm",
            dimension_scores=iteration["scores"],
        )

        # Record score and get strategic decision
        decision = tracker.record_score(result.score)

        print(f"\n--- Iteration {i} ---")
        print(f"Output: {iteration['output']}")
        print(f"Score: {result.score}/10  |  Verdict: {result.verdict.value}")
        print(f"Dimension scores: {result.dimension_scores}")
        print(f"Decision: {decision.value}")
        print(f"Consecutive declines: {tracker.consecutive_declines}")

        if decision == PivotDecision.APPROVE:
            print("\n✅ Output APPROVED! Work is done.")
            break
        elif decision == PivotDecision.PIVOT:
            print("\n🔄 PIVOT triggered — scrapping current approach, trying new direction.")
            tracker.reset_trend()
        else:
            print(f"Feedback: {result.feedback}")

    # Print the plan entry
    print("\n" + "=" * 60)
    print("PLAN.md Entry:")
    print("=" * 60)
    print(tracker.to_plan_entry())

    # Also demonstrate the evaluator prompt builder
    print("=" * 60)
    print("Evaluator Prompt (first 500 chars):")
    print("=" * 60)
    prompt = evaluator.build_evaluator_prompt(
        output="def rate_limit(key): pass",
        task_description="Implement a rate limiter",
    )
    print(prompt[:500] + "...")


if __name__ == "__main__":
    main()
