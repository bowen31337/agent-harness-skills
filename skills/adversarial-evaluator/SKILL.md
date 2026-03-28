# Adversarial Evaluator Skill

## Description

Implements **separate adversarial evaluation** for agent outputs — a key
finding from Anthropic's harness design research. Self-evaluation is
fundamentally lenient (models praise their own mediocre work); separating the
evaluator from the generator and tuning it to be skeptical is far more
tractable.

## When to Use

- After a generator agent produces output (code, design, text)
- When quality assessment requires more than binary pass/fail
- In iterative generation loops where feedback drives improvement
- When you need weighted, multi-dimensional grading

## Components

### `harness_skills/evaluator.py`

- **`AdversarialEvaluator`** — Main class
  - `grade(output, task_description, dimension_scores?, feedback?)` → `EvaluationResult`
  - `build_evaluator_prompt(output, task_description)` → prompt string for LLM
- **`EvaluationResult`** — score, verdict (APPROVE/REQUEST_CHANGES), dimension_scores, feedback
- **`Verdict`** — enum: APPROVE, REQUEST_CHANGES
- **`DIMENSIONS`** — 4 weighted grading dimensions
- **`GOOD_REVIEW_EXAMPLE`** / **`BAD_REVIEW_EXAMPLE`** — few-shot calibration

### `harness_skills/pivot_tracker.py`

- **`PivotTracker`** — monitors score trends across iterations
  - `record_score(score)` → `PivotDecision` (REFINE / PIVOT / APPROVE)
  - `to_plan_entry()` → markdown summary for PLAN.md
- **`PivotDecision`** — enum: REFINE, PIVOT, APPROVE

## Grading Dimensions

| Dimension | Weight | Focus |
|-----------|--------|-------|
| Correctness | ×3 | Does it satisfy the task requirements? |
| Completeness | ×3 | Are all features/aspects addressed? |
| Quality | ×2 | Clean, well-structured, idiomatic? |
| Originality | ×1 | Creative, non-obvious design choices? |

Weights emphasise correctness and completeness (must-haves) while rewarding
quality and originality (differentiators).

## Usage

### Basic Grading (with pre-computed scores)

```python
from harness_skills.evaluator import AdversarialEvaluator

evaluator = AdversarialEvaluator(approve_threshold=7.0)
result = evaluator.grade(
    output="def add(a, b): return a + b",
    task_description="Write a function that adds two numbers",
    dimension_scores={
        "Correctness": 9,
        "Completeness": 8,
        "Quality": 7,
        "Originality": 5,
    },
    feedback="Correct and complete. Code is clean. Nothing creative.",
)
print(result.verdict)  # APPROVE
print(result.score)    # ~7.89
```

### LLM-Based Evaluation

```python
evaluator = AdversarialEvaluator()
prompt = evaluator.build_evaluator_prompt(
    output=generator_output,
    task_description="Build a rate limiter",
)
# Send prompt to a SEPARATE model instance, parse the response,
# then call evaluator.grade() with the parsed dimension_scores.
```

### With Pivot Tracking

```python
from harness_skills.pivot_tracker import PivotTracker, PivotDecision

tracker = PivotTracker(approve_threshold=7.0)

for iteration in range(max_iterations):
    output = generator.generate(task, feedback=prev_feedback)
    result = evaluator.grade(output, task)
    decision = tracker.record_score(result.score)

    if decision == PivotDecision.APPROVE:
        break
    elif decision == PivotDecision.PIVOT:
        generator.reset_approach()
        tracker.reset_trend()
    # REFINE: continue with evaluator feedback
    prev_feedback = result.feedback
```

## References

- [Anthropic: Harness Design for Long-Running Apps](https://www.anthropic.com/engineering/harness-design-long-running-apps)
- `docs/guides/context-reset-vs-compaction.md` — when to use resets vs compaction
- `docs/guides/agent-tool-design-guidelines.md` — Guideline 8 (Separate Generator and Evaluator Roles)
