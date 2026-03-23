# Module Boundaries

Scan the codebase, identify domain packages, and generate explicit module-boundary rules
so that every domain's public API surface is declared only in its `__init__.py` (Python)
or `index.ts` / `index.js` (TypeScript / JavaScript) file.

Violations are written as **blocking** principles into `.claude/principles.yaml` so that
`/check-code` and `/review-pr` enforce them automatically on every future run.

---

## Instructions

### Step 0: Detect language(s)

```bash
# Python packages?
find . -name "__init__.py" -not -path "./.venv/*" -not -path "./node_modules/*" | head -20

# JS/TS packages?
find . -name "index.ts" -o -name "index.js" \
  | grep -v node_modules | grep -v dist | head -20
```

Set `LANG_MODE` to `python`, `js`, or `both` based on what is found.

---

### Step 1: Discover domain packages

**Python** — a *domain package* is any directory that:
- Contains an `__init__.py`, AND
- Lives at depth 1 or 2 beneath a recognised source root (`src/`, the project name dir, etc.), AND
- Is **not** a test package (`tests/`, `test_*`, `*_test`).

```bash
find . -name "__init__.py" \
  -not -path "./.venv/*" \
  -not -path "./node_modules/*" \
  -not -path "*/tests/*" \
  -not -path "*/test_*" \
  | sed 's|/__init__.py||' \
  | sort
```

**JS/TS** — a *domain package* is any directory that:
- Contains an `index.ts` or `index.js`, AND
- Lives beneath `src/`, AND
- Is **not** under `node_modules/`, `dist/`, `__tests__/`.

```bash
find src -\( -name "index.ts" -o -name "index.js" \) \
  | grep -v node_modules | grep -v dist | grep -v __tests__ \
  | sed 's|/index\.[tj]s||' \
  | sort
```

Collect the results into a list called **DOMAINS**.

---

### Step 2: Analyse each domain's current public surface

For each domain in DOMAINS:

#### 2a. Check whether `__all__` (Python) / named exports (JS/TS) are declared

**Python:**

```bash
grep -n "__all__" <domain>/__init__.py 2>/dev/null || echo "__MISSING__"
```

- If `__all__` is present → mark domain as **EXPLICIT**.
- If absent → mark domain as **IMPLICIT** (everything imported into `__init__.py` leaks out).

**JS/TS:**

```bash
grep -n "^export " <domain>/index.ts 2>/dev/null \
  || grep -n "^export " <domain>/index.js 2>/dev/null \
  || echo "__MISSING__"
```

- If named `export` statements are present → **EXPLICIT**.
- If `export * from` only → **WILDCARD** (treat as implicit for boundary purposes).
- If nothing → **IMPLICIT**.

#### 2b. Detect cross-domain deep imports (boundary violations)

Scan all files outside a domain for imports that reach *into* the domain's internals
(i.e. bypass the index / `__init__`):

**Python:**

```bash
# Example for domain "myapp/orders":
grep -rn "from myapp\.orders\." . \
  --include="*.py" \
  --exclude-dir=".venv" \
  | grep -v "^myapp/orders/"   # exclude files within the domain itself
```

**JS/TS:**

```bash
# Example for domain "src/orders":
grep -rn "from ['\"].*orders/" src \
  --include="*.ts" --include="*.tsx" --include="*.js" \
  | grep -v "^src/orders/"
```

Collect all violations as a list: `{ file, line, import_path }`.

---

### Step 3: Build the boundary report

Print a structured report:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Module Boundary Analysis
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Domain                    Init file         API surface    Violations
  ─────────────────────────────────────────────────────────────────────
  myapp/orders              __init__.py       ✅ EXPLICIT    0
  myapp/payments            __init__.py       ⚠️  IMPLICIT   3
  myapp/notifications       __init__.py       ❌ MISSING     —
  src/users                 index.ts          ✅ EXPLICIT    0
  src/billing               index.ts          🔶 WILDCARD    1

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Violations (4 total):
    myapp/payments:
      app/checkout/flow.py:18  →  from myapp.payments.internal import stripe_client
      app/checkout/flow.py:41  →  from myapp.payments.models import PaymentRecord
      app/reports/monthly.py:9 →  from myapp.payments.models import PaymentRecord
    src/billing:
      src/dashboard/Overview.tsx:7  →  import { formatInvoice } from '../billing/utils'

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Legend:
- ✅ EXPLICIT — `__all__` / named exports declared; boundary is enforceable.
- ⚠️  IMPLICIT — no `__all__`; everything bleeds out.
- 🔶 WILDCARD — `export *` only; surface is unpredictable.
- ❌ MISSING — no init/index file; package has no declared surface at all.

---

### Step 4: Auto-fix — add `__all__` or named exports where missing

For every domain marked **IMPLICIT** or **MISSING**, offer to generate a minimal
public-API declaration based on the *current* exports visible to callers.

**Python — generate `__all__`:**

```python
# Inspect what names callers currently import from this package, then write:
__all__ = [
    "OrderService",
    "OrderStatus",
    # ... (names actually used by callers, discovered in Step 2b)
]
```

Insert this block at the top of `<domain>/__init__.py`, after any existing docstring.
If the file doesn't exist, create it with only `__all__ = []` and a `# TODO:` comment.

**JS/TS — generate named exports:**

Replace `export * from './...'` lines with explicit re-exports:

```ts
// index.ts — generated by /module-boundaries
export { UserService } from './UserService';
export type { User, UserRole } from './types';
// TODO: review and remove any symbols that should stay internal
```

Only write files when the engineer confirms.  Print a diff preview first:

```
  [Preview] myapp/payments/__init__.py
  + __all__ = ["PaymentService", "PaymentStatus"]
  Apply? [y/N]
```

Do NOT auto-write if run with `--dry-run`.

---

### Step 5: Write boundary rules as principles

Load `.claude/principles.yaml` (create if missing).  For each domain, upsert a
principle that enforces the rule going forward.  Use IDs in the range `MB001`–`MB999`
so they don't collide with hand-written principles.

```yaml
# Generated by /module-boundaries — do not edit IDs manually
- id: "MB001"
  category: "architecture"
  severity: "blocking"
  applies_to: ["review-pr", "check-code"]
  rule: >
    myapp/orders: all imports must go through myapp.orders (the package root).
    Never import from myapp.orders.<submodule> directly.

- id: "MB002"
  category: "architecture"
  severity: "blocking"
  applies_to: ["review-pr", "check-code"]
  rule: >
    myapp/payments: __all__ must be kept up-to-date in __init__.py.
    Never add a symbol to __all__ without a matching implementation in the package.
```

Rules:
- One principle per domain that has at least one violation **or** is IMPLICIT/MISSING.
- Domains with zero violations and EXPLICIT status get a principle too (to lock the
  boundary so regressions are caught).
- Re-running `/module-boundaries` updates existing `MB*` principles in-place; it never
  duplicates them.
- After writing, also regenerate `docs/PRINCIPLES.md` (same logic as `/define-principles`
  Step 4.5).

---

### Step 6: Summary and next steps

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✅ Module Boundaries — Done
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  5 domains scanned
  3 boundary principles written  →  .claude/principles.yaml (MB001–MB003)
  2 __init__.py files updated with __all__
  4 deep-import violations found  →  fix manually or re-run after refactoring

  Enforcement active in:
    • /check-code  — scans staged files against MB* principles
    • /review-pr   — flags deep imports in PR diffs

  Re-run any time:  /module-boundaries
  Skip auto-fix:    /module-boundaries --dry-run
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Flags

| Flag | Behaviour |
|---|---|
| `--dry-run` | Report only — no files written, no principles updated |
| `--domain <path>` | Analyse a single domain instead of the whole project |
| `--fix` | Apply all auto-fixes without interactive confirmation |
| `--no-principles` | Skip Step 5 (don't write to `.claude/principles.yaml`) |

---

## Notes

- This skill is **safe to re-run**: it is idempotent.  Existing `__all__` entries and
  `MB*` principles are updated, never duplicated.
- It does **not** commit any changes.  Stage and commit with `/checkpoint` or manually.
- For monorepos with many packages, use `--domain` to focus on one at a time.
- Deep-import detection uses static grep; it does not execute any code.
