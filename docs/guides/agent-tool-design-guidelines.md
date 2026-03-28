# Agent Tool Design Guidelines
### Synthesized from "Lessons from Building Claude Code" + LangChain Harness Engineering (2026)
*Alex Chen — March 5, 2026 · Updated March 16, 2026*

---

## Core Principle: Shape Tools to Model Abilities

The #1 mistake in agent tool design is giving every model the same interface. Tools must be calibrated to the *actual* capability profile of the model running the agent. As capabilities improve, revisit every assumption — yesterday's scaffold is tomorrow's cage.

---

## Guideline 1: Prefer Structured Tools Over Free-Form Output

**Problem:** Asking models to produce structured output in plain text is unreliable. Claude will append extra sentences, use wrong formats, omit fields.

**Solution:** Create a dedicated tool that accepts structured parameters. If you need a list of questions with options, build an `AskUserQuestion` tool — not an instruction to "output a bulleted list."

**Rule:** If correctness matters, schema-enforce it. If format matters, tool-enforce it.

---

## Guideline 2: Progressive Disclosure > Context Dumping

**Problem:** Loading everything into the system prompt creates context rot — irrelevant information crowds out what the model actually needs, reducing quality on the main task.

**Solution:** Give the agent a pointer (a link, a file path, a skill name) and let it pull context on demand. Design skills/files so each can reference deeper layers the model can recurse into.

**Examples:**
- Claude Code: Link to docs → Guide subagent fetches and filters → returns only the answer
- Tiered memory: Recent daily notes → MEMORY.md → archived files (only when explicitly searched)

**Rule:** Start with the minimum viable context. Add progressive disclosure layers before adding system prompt text.

---

## Guideline 3: Update Tools as Model Capabilities Evolve

**Problem:** Tools designed for weaker models can constrain stronger ones. TodoWrite sent reminders every 5 turns — Opus 4.5 found this limiting, not helpful.

**Solution:** Maintain a small, well-chosen model set and audit your tools against their actual capabilities quarterly. Ask: "Does this tool still help the model, or does it now constrain it?"

**Rule:** Tools have a lifecycle. Provision, validate, evolve, and retire them deliberately.

**Upgrade — Trace-Driven Iteration:** Quarterly audits are the floor, not the ceiling. The fastest improvement loop is: run agent on benchmark → collect traces → spawn parallel error-analysis agents → synthesise failure patterns → make targeted harness changes → re-run. LangChain improved their coding agent 13.7 points on Terminal Bench 2.0 this way *without changing the model*. Every agent failure is a training signal for the harness.

> **⚠️ Compaction vs Reset:** As models improve, the harness should selectively use **full context resets** (not just compaction) for tasks that exhibit premature wrap-up. Compaction preserves continuity but does not cure *context anxiety* — the tendency for agents to rush through work as the context window fills. A context reset clears the window entirely and hands off to a fresh agent with a structured handoff document. Anthropic found that Claude Sonnet 4.5 exhibited context anxiety strongly enough that compaction alone was insufficient; context resets were essential. Newer models (Opus 4.5+) largely removed this behaviour, allowing compaction-only strategies. As models evolve, audit whether your tasks still need resets or whether compaction is now sufficient. See `docs/guides/context-reset-vs-compaction.md` for the full framework.

---

## Guideline 4: Let Agents Build Their Own Context

**Problem:** RAG and static context injection hand the model a pre-digested answer. This works until the index is stale, the query is fuzzy, or the context is wrong.

**Solution:** Give the model search tools (grep, file read, skill lookup) and let it build context itself. Smarter models are increasingly good at this if given the right primitives.

**Hierarchy:**
1. Static injection (fastest, stales quickly)
2. RAG (semantic, but fragile setup and indexing)
3. Grep/search tools (reliable, model-driven, slower)
4. Progressive disclosure via skill files (best for structured domain knowledge)

**Rule:** Prefer agent-driven context assembly over pre-assembled injection as model capability increases.

---

## Guideline 5: Design for Subagent Coordination Early

**Problem:** Todos and shared state primitives designed for single-agent use break under multi-agent coordination. Subagents have no visibility into each other's progress.

**Solution:** Design shared state with coordination in mind from the start. Tasks (not Todos) should support dependencies, status propagation, and cross-agent visibility.

**Rule:** If your agent might ever spawn subagents, design your state primitives for multi-agent use from day one.

---

## Guideline 6: Validate Elicitation Quality, Not Just Output Correctness

**Problem:** A tool that produces correct output but is never called by the model is useless. Model affinity for tools matters — some tool signatures Claude naturally reaches for, others it ignores.

**Solution:** Measure call frequency and output quality separately. If a tool is underutilized, the issue may be the name, the parameter schema, or the prompt guidance — not the implementation.

**Practical test:** Run the agent on 20 diverse tasks. Check tool call logs. Any tool called <10% of expected frequency needs redesign.

**Rule:** Instrument your agent's tool calls. Optimize for both correctness *and* model affinity.

---

## Guideline 7: Minimize Tool Count, Maximize Tool Depth

**Problem:** 50 tools = 50 options the model has to reason about. Decision overhead degrades performance on the actual task.

**Solution:** Maintain a high bar for adding new tools. Before adding a tool, ask:
- Can progressive disclosure handle this? (Often yes)
- Can an existing tool be extended? (Preferred)
- Does this use case come up >10% of runs? (If not, it's a subagent's job)

**Claude Code target:** ~20 tools. That's the ceiling for a production agent system.

**Rule:** Every tool you add costs reasoning budget. Make each one earn its place.

---

---

## Guideline 8: Force Agents to Verify Their Own Work Before Exiting

**Problem:** Agents are biased toward their first plausible solution. The most common failure pattern is: write code → re-read it → "looks right" → exit. They never run tests, never compare output against the original spec. They validate against their own implementation rather than the task requirements.

**Solution:** Add a pre-completion hook that intercepts the agent before it exits and forces a verification pass. This is not optional guidance in a system prompt — it must be mechanically enforced by the harness:

1. **Plan:** Read the task spec, identify how success will be verified
2. **Build:** Implement with testing in mind
3. **Verify:** Run tests, compare output against the *original spec* (not your own code)
4. **Fix:** If anything fails, return to Build — do not skip to exit

The hook should only allow exit once verification has been attempted. A `hasRunVerification` flag in agent state prevents double-triggering.

**Why it works:** Models are exceptional self-improvement machines *when given a concrete signal to improve against*. Tests provide that signal. Without them, the agent has no feedback loop within the run.

**Rule:** Verification is not a suggestion. Make it structurally impossible for the agent to exit without attempting it.

**References:** LangChain `PreCompletionChecklistMiddleware`; [Ralph Wiggum Loop](https://ghuntley.com/loop/)

---

## Guideline 9: Onboard Agents Into Their Environment at Boot

**Problem:** Agents waste significant early turns on environment discovery — finding file paths, checking which tools are installed, mapping directory structure. This is error-prone (search tools fail, paths are wrong) and burns context budget on work that could be done once at startup.

**Solution:** Inject environment context at agent boot via a startup hook, not through the system prompt:

- **Directory map:** Current working directory + key subdirectories + file counts
- **Available tools:** Which CLIs are installed and their versions (python, node, cargo, go, etc.)
- **Constraints:** Timeouts, memory limits, evaluation criteria, testing framework in use
- **Task context:** How the work will be scored or verified (especially important for benchmark-style tasks)

The more agents know about their environment *before* they start, the fewer early-turn errors. LangChain's `LocalContextMiddleware` reduced their "context discovery failure" rate significantly — agents that know their environment from step 1 don't waste 10 turns figuring out where things are.

**Important:** This is context *delivery*, not context *dumping*. Inject structured, factual environment data — not prose guidance, which belongs in the system prompt.

**Rule:** Boot-time environment injection is cheap and high-leverage. Do it before the first model call, not after the first failure.

---

## Guideline 10: Detect and Break Doom Loops

**Problem:** Agents get stuck making small variations to the same broken approach — sometimes 10+ times on the same file. They are myopic once committed to a plan: each iteration feels like progress ("I fixed the indentation") when the fundamental approach is wrong. This burns tokens, time, and produces no progress.

**Solution:** Track per-resource edit counts and inject reconsidering context after a threshold is crossed:

```
You have edited 'src/parser.ts' 6 times. Consider stepping back:
is your fundamental approach correct? Review the original spec
and try a different strategy rather than making further small edits.
```

Triggers to track:
| Signal | Threshold | Intervention |
|--------|-----------|-------------|
| Same file edited N times | 5 (configurable) | Suggest reconsidering approach |
| Same tool called with identical args | 3 consecutive | Flag repetition, suggest alternative |
| Same error message seen | 3 times | Prompt root cause analysis, not patch |

**Design note:** This is a guardrail for *today's* models. As models improve, doom loops will become rarer and this hook can be retired. Build it as a modular, removable component — not baked into core agent logic. The goal is correct behaviour now without coupling future architecture to current model limitations.

**Rule:** A loop detector doesn't fix the underlying problem — it creates an opening for the agent to escape. Make the intervention prompt Socratic, not prescriptive.

---

## Guideline 11: Separate Generator and Evaluator Roles

**Problem:** When asked to evaluate their own work, agents consistently praise it — even when, to a human observer, the quality is obviously mediocre. This is most visible on subjective tasks (design, writing, UX) but also affects verifiable tasks (code, tests). The core issue is that self-evaluation is fundamentally lenient: the same model that generated the output is inclined to be generous when judging it.

**Solution:** Separate the agent doing the work (generator) from the agent judging it (evaluator). This creates a feedback loop where the generator has concrete, external criticism to iterate against.

Key engineering insights from Anthropic's harness research:

1. **Self-evaluation is fundamentally lenient — and this is not fixable by prompting alone.** Models confidently praise their own mediocre work. The separation between generator and evaluator doesn't immediately eliminate leniency, but tuning a standalone evaluator to be skeptical is **far more tractable** than making a generator self-critical.

2. **Weighted grading dimensions turn subjective judgment into concrete scores.** Rather than asking "is this good?", define specific dimensions (e.g., Correctness ×3, Completeness ×3, Quality ×2, Originality ×1) that encode what "good" means. Weight them to prioritise must-haves over nice-to-haves. This gives both the generator and evaluator a shared vocabulary.

3. **Few-shot calibration examples prevent score drift.** Provide the evaluator with detailed score breakdowns for known-good and known-bad outputs. This anchors judgment and ensures consistency across iterations.

4. **Score trend detection enables strategic pivots.** Monitor evaluation scores across iterations. If scores are trending up → **refine** the current approach. If 2+ consecutive scores decline → **pivot** to an entirely different approach. Anthropic observed that some generations refined incrementally while others took sharp creative turns between iterations — the pivot decision should be data-driven, not left to intuition.

**Architecture:**

```
Planner → Generator → Evaluator → [REFINE/PIVOT/APPROVE]
              ↑                          |
              └──── feedback loop ───────┘
```

The evaluator grades each iteration using the weighted dimensions + few-shot calibration. The PivotTracker monitors the score trend and decides the next action. On APPROVE, the work is done. On REFINE, the feedback goes back to the generator. On PIVOT, the generator scraps its approach and tries something fundamentally different.

**Implementation:** See `harness_skills/evaluator.py` (AdversarialEvaluator), `harness_skills/pivot_tracker.py` (PivotTracker), and `skills/adversarial-evaluator/SKILL.md`.

**Rule:** Never let an agent grade its own work. Separate generation from evaluation, calibrate the evaluator with examples, and use score trends to decide when to persist vs pivot.

**Reference:** [Anthropic: Harness Design for Long-Running Application Development](https://www.anthropic.com/engineering/harness-design-long-running-apps)

---

## Summary: The Agent Design Checklist

Before shipping any tool or skill change:

- [ ] Is the tool shaped to what this model can actually do?
- [ ] Does it schema-enforce structured output where correctness matters?
- [ ] Is context loaded progressively, not dumped upfront?
- [ ] Does it support multi-agent coordination if needed?
- [ ] Have you measured model affinity (call frequency) in addition to output quality?
- [ ] Is the total tool count still at or below your ceiling?
- [ ] Do you have a plan to revisit this tool as model capabilities change?
- [ ] Does the harness force a verification pass before the agent exits? (G8)
- [ ] Is environment context injected at boot, not discovered at runtime? (G9)
- [ ] Is there a loop detector to break repeated-edit doom loops? (G10)
- [ ] Are agent traces collected and feeding back into harness improvements? (G3 upgrade)
- [ ] Is the evaluator separate from the generator? (G11)
- [ ] Does the evaluator use weighted grading dimensions with few-shot calibration? (G11)
- [ ] Is there a pivot tracker monitoring score trends across iterations? (G11)
- [ ] Are context resets used for long-running tasks that exhibit premature wrap-up? (G3 callout)

---

*Based on: @trq212's "Lessons from Building Claude Code"*
*Updated with: LangChain ["Improving Deep Agents with Harness Engineering"](https://blog.langchain.com/improving-deep-agents-with-harness-engineering/) (2026)*
*Author: Alex Chen*