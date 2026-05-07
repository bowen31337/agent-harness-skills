# Design Docs

Scaffold the `docs/design-docs/` directory structure for Architectural Decision Records (ADRs)
and broader design documents. Safe to re-run — existing files are never overwritten.

---

## When to use

- Bootstrapping a new project that needs a formal ADR process.
- Adding ADR support to an existing project that has none.
- Verifying the expected directory layout is in place before writing a new ADR.

---

## Instructions

### Step 1: Check for an existing structure

```bash
ls docs/design-docs/ 2>/dev/null && echo "__EXISTS__" || echo "__MISSING__"
```

If `docs/design-docs/` already exists, print:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  docs/design-docs/ already present — skipping scaffold.
  Run with --force to overwrite existing files.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

…and stop (unless `--force` was passed, in which case continue to Step 2 but skip
files that already exist unless `--force` was passed).

---

### Step 2: Create the directory skeleton

```bash
mkdir -p docs/design-docs/adr
mkdir -p docs/design-docs/drafts
```

---

### Step 3: Write `docs/design-docs/README.md`

Create the file with this exact content (substitute `<PROJECT_NAME>` with the name
found in `pyproject.toml`, `package.json`, or the repository root directory name):

```markdown
# Design Docs & Architectural Decision Records (ADRs)

This directory contains architectural decision records (ADRs) and broader design
documents for the **<PROJECT_NAME>** project.

## What is an ADR?

An ADR captures a significant architectural decision made during the development of
this project — including the **context**, the **decision**, the **alternatives
considered**, and the **consequences**. They are lightweight, immutable (once
accepted), and stored alongside the code they describe.

## Directory Structure

```
docs/design-docs/
├── README.md               ← You are here
├── template.md             ← Copy this to start a new ADR
├── adr/                    ← Accepted/superseded ADRs (numbered)
│   └── 0001-example.md
└── drafts/                 ← Work-in-progress ADRs
    └── .gitkeep
```

## Lifecycle

```
Draft → Proposed → Accepted → Deprecated / Superseded
```

| Status       | Meaning                                            |
|--------------|----------------------------------------------------|
| Draft        | Being written, not yet ready for review            |
| Proposed     | Ready for team review                              |
| Accepted     | Decision ratified and in effect                    |
| Deprecated   | No longer relevant, but kept for historical record |
| Superseded   | Replaced by a later ADR (link to successor)        |

## How to Add a New ADR

1. Copy `template.md` into `adr/` with the next sequential number and a short slug:
   ```bash
   cp docs/design-docs/template.md docs/design-docs/adr/0002-my-decision.md
   ```
2. Fill in every section of the template.
3. Set **Status** to `Draft`, then `Proposed` when ready for review.
4. After team sign-off, change **Status** to `Accepted` and open a PR.

## Conventions

- File names: `NNNN-short-lowercase-slug.md` (four-digit zero-padded number).
- One decision per ADR — keep them focused and small.
- Never edit an accepted ADR's decision; instead create a superseding ADR.
- Reference related ADRs with relative links: `[ADR-0001](adr/0001-example.md)`.
```

---

### Step 4: Write `docs/design-docs/template.md`

Create the file with this exact content:

```markdown
# ADR-NNNN: [Short Title of the Decision]

> **Status:** Draft | Proposed | Accepted | Deprecated | Superseded by [ADR-XXXX](adr/XXXX-successor.md)
> **Date:** YYYY-MM-DD
> **Deciders:** <!-- list names or roles, e.g. "Backend team", "@alice, @bob" -->
> **Tags:** <!-- optional: e.g. testing, infrastructure, api-design -->

---

## Context

<!--
Describe the situation, problem, or requirement that forced this decision.
Include relevant constraints (time, team size, existing tech, compliance, etc.).
Keep it factual — no opinions yet.
-->

## Decision

<!--
State the decision clearly in one or two sentences.
Start with: "We will …" or "We decided to …"
-->

## Alternatives Considered

<!--
List the options that were evaluated. For each:
- What it is
- Why it was considered
- Why it was rejected (or why it wasn't chosen)
-->

### Option A — [Name]

**Description:** …

**Pros:**
- …

**Cons:**
- …

**Why rejected:** …

---

### Option B — [Name] *(chosen)*

**Description:** …

**Pros:**
- …

**Cons:**
- …

---

### Option C — [Name]

**Description:** …

**Pros:**
- …

**Cons:**
- …

**Why rejected:** …

## Consequences

<!--
What becomes easier or harder as a result of this decision?
Include positive, negative, and neutral outcomes.
-->

**Positive:**
- …

**Negative / Trade-offs:**
- …

**Neutral:**
- …

## Implementation Notes

<!--
Optional. Any guidance for how to implement the decision:
- Affected files / modules
- Migration steps if replacing something existing
- Links to related PRs, issues, or tickets
-->

## References

<!--
Optional. External links, RFCs, papers, prior art, related ADRs.
-->

- [Related ADR](adr/NNNN-related.md)
- [Relevant issue / PR](#)
```

---

### Step 5: Create placeholder files for empty directories

Git does not track empty directories. Add a `.gitkeep` to each:

```bash
touch docs/design-docs/adr/.gitkeep
touch docs/design-docs/drafts/.gitkeep
```

> **Note:** If `docs/design-docs/adr/` already contains at least one `.md` file,
> skip creating `.gitkeep` there.

---

### Step 6: Stage the new files

```bash
git add docs/design-docs/
```

Do **not** commit automatically — let the engineer review and commit with their
preferred message or via `/checkpoint`.

---

### Step 7: Print a confirmation summary

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✅ docs/design-docs/ scaffolded
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Created:
    docs/design-docs/README.md      ← ADR process overview & conventions
    docs/design-docs/template.md    ← Copy this for every new ADR
    docs/design-docs/adr/           ← Accepted & superseded decisions live here
    docs/design-docs/drafts/        ← Work-in-progress ADRs live here

  Next steps:
    1. Write your first ADR:
         cp docs/design-docs/template.md docs/design-docs/adr/0001-<slug>.md
    2. Fill in every section, then set Status → Proposed.
    3. After team review, set Status → Accepted and open a PR.

  Re-run any time:   /design-docs
  Force overwrite:   /design-docs --force
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Flags

| Flag      | Behaviour                                                      |
|-----------|----------------------------------------------------------------|
| `--force` | Overwrite `README.md` and `template.md` even if they exist     |
| `--dry-run` | Print what would be created without writing any files        |

---

## Notes

- This skill is **idempotent** — re-running without `--force` never overwrites files
  that already exist.
- It does **not** commit. Stage and commit with `/checkpoint` or manually.
- ADR numbering starts at `0001`. The four-digit zero-padded format keeps directory
  listings sorted chronologically.
- Keep each ADR small and focused on **one** decision. If a decision has many
  sub-parts, split it into multiple ADRs and cross-reference them.
