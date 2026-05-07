# Design Docs & Architectural Decision Records (ADRs)

This directory contains architectural decision records (ADRs) and broader design documents for the **agent-harness-skills** project.

## What is an ADR?

An ADR captures a significant architectural decision made during the development of this project — including the **context**, the **decision**, the **alternatives considered**, and the **consequences**. They are lightweight, immutable (once accepted), and stored alongside the code they describe.

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
