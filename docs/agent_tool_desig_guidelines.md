# Agent Tool Design Guidelines
### Synthesized from "Lessons from Building Claude Code"
*Alex Chen — March 5, 2026*

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

## Summary: The Agent Design Checklist

Before shipping any tool or skill change:

- [ ] Is the tool shaped to what this model can actually do?
- [ ] Does it schema-enforce structured output where correctness matters?
- [ ] Is context loaded progressively, not dumped upfront?
- [ ] Does it support multi-agent coordination if needed?
- [ ] Have you measured model affinity (call frequency) in addition to output quality?
- [ ] Is the total tool count still at or below your ceiling?
- [ ] Do you have a plan to revisit this tool as model capabilities change?

---

*Based on: @trq212's "Lessons from Building Claude Code"*
*Author: Alex Chen*