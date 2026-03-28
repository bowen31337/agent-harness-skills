# Context Reset vs Compaction

## The Problem: Context Anxiety

As an agent's context window fills during a long-running task, many models
exhibit **context anxiety** — they begin wrapping up work prematurely because
they believe they are running out of room. This manifests as:

- Rushing to produce a "good enough" output instead of iterating
- Skipping planned features or tasks
- Producing shorter, less thorough outputs toward the end of a session
- Explicitly stating "I'm running low on context" and trying to finish

Anthropic observed this strongly in Claude Sonnet 4.5, where compaction alone
was not sufficient to enable strong long-task performance.

> *"Some models also exhibit 'context anxiety,' in which they begin wrapping up
> work prematurely as they approach what they believe is their context limit."*
> — [Anthropic: Harness Design for Long-Running Apps](https://www.anthropic.com/engineering/harness-design-long-running-apps)

## Two Strategies

### Compaction (Summarise In-Place)

**What it does:** Earlier parts of the conversation are summarised so the same
agent continues on a shortened history.

**Pros:**
- Preserves conversational continuity
- Lower orchestration overhead — no need to spawn a new agent
- The agent retains "muscle memory" of its approach

**Cons:**
- Does **not** give the agent a clean slate
- Context anxiety can persist because the agent still perceives itself as deep
  into a long session
- Summarisation may lose important detail

**When to use:** Short-to-medium tasks (< 80 tool calls), tasks where
continuity matters more than freshness, models that don't exhibit context
anxiety.

### Context Reset (Clean Slate + Handoff)

**What it does:** Clears the context window entirely and starts a fresh agent.
A structured handoff document carries the previous agent's state, accomplished
work, and next steps.

**Pros:**
- Eliminates context anxiety entirely — the new agent has a fresh context
- Forces explicit documentation of state (the handoff artifact)
- The new agent verifies context with its own tools instead of relying on
  stale in-context information

**Cons:**
- Orchestration overhead — need to manage agent lifecycle
- Token overhead — the handoff document uses tokens
- Latency — spinning up a new agent takes time
- Risk of information loss if the handoff is incomplete

**When to use:** Long-running tasks (≥ 80 tool calls), tasks where the model
exhibits premature wrap-up, tasks split across natural phase boundaries.

## The Reset Threshold

The `HandoffProtocol` includes a `reset_threshold` parameter (default: 80 tool
calls) that signals when the harness should trigger a full context reset
instead of compaction.

```python
from harness_skills.handoff import HandoffProtocol

# Default: reset after 80 tool calls
protocol = HandoffProtocol(reset_threshold=80)

# Check if we should reset
if protocol.should_reset(tool_call_count=current_count):
    # Trigger context reset: write handoff, spawn fresh agent
    ...
else:
    # Compaction is fine for now
    ...
```

### Choosing the Right Threshold

| Scenario | Suggested Threshold | Rationale |
|----------|-------------------|-----------|
| Simple feature implementation | 120+ or disabled | Short task, anxiety unlikely |
| Multi-file refactoring | 80 (default) | Medium-length, natural break points |
| Full application build | 50–60 | Long task, reset at phase boundaries |
| Model known to exhibit anxiety | 40–60 | Lower threshold compensates for model behaviour |
| Model that handles long context well | 120+ | Model doesn't need frequent resets |

## Model-Specific Considerations

Different models exhibit context anxiety at different rates:

- **Claude Sonnet 4.5:** Exhibited context anxiety strongly enough that
  compaction alone was insufficient. Context resets were essential.
- **Claude Opus 4.5+:** Largely removed context anxiety on its own, allowing
  compaction-only strategies with automatic context management.

As models improve, the reset threshold can be raised or resets can be removed
entirely. This is consistent with the broader harness design principle:
*every component encodes an assumption about what the model can't do on its
own, and those assumptions should be stress-tested as models improve.*

## Example: Phased Application Build

```
Phase 1: Planning (Planner Agent)
  └─ Writes PLAN.md + handoff document
  └─ Context reset → spawn Generator

Phase 2: Implementation Sprint 1 (Generator Agent)
  └─ Builds features 1–4
  └─ After 80 tool calls → context reset
  └─ Writes handoff: "Features 1–4 done, next: features 5–8"
  └─ Context reset → spawn fresh Generator

Phase 3: Implementation Sprint 2 (Generator Agent)
  └─ Reads handoff, builds features 5–8
  └─ Writes handoff → context reset → spawn Evaluator

Phase 4: Evaluation (Evaluator Agent)
  └─ Reviews all work against the plan
  └─ Grades with weighted dimensions
  └─ Either APPROVE or send back to Generator with feedback
```

## Integration with the Adversarial Evaluator

Context resets pair naturally with the adversarial evaluator pattern. After
each reset:

1. The fresh agent reads the handoff document
2. It verifies context using its own tools (Read, Grep, Glob)
3. It continues from the next steps in the handoff
4. At the end of its session, the evaluator grades the work
5. The `PivotTracker` monitors score trends to decide REFINE vs PIVOT

This creates a virtuous cycle: the agent gets a clean context (eliminating
anxiety), the evaluator catches quality issues (eliminating self-evaluation
bias), and the pivot tracker prevents diminishing-returns iteration loops.
