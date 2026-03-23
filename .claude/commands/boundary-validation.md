# Boundary Validation

Scan the codebase, identify which layers perform data validation, and generate explicit
boundary-validation rules so that input validation and external-data parsing happen
**exclusively** at system boundaries (API route handlers, CLI argument parsers, external
service adapters) and **never** inside domain services, use-case classes, or repository
implementations.

Violations are written as **blocking** principles into `.claude/principles.yaml` (IDs
`BV001`–`BV999`) so that `/check-code` and `/review-pr` enforce them automatically on
every future run.

---

## Instructions

### Step 0: Detect project layout

Identify the source root and the layer directories present:

```bash
# Python packages?
find . -name "__init__.py" \
  -not -path "./.venv/*" \
  -not -path "./node_modules/*" \
  | head -30

# JS/TS source roots?
find . -name "tsconfig.json" -not -path "*/node_modules/*" | head -5
```

Then determine which directories correspond to which architectural layers by looking at
directory names and any existing `ARCHITECTURE.md` or layer comments:

| Layer label | Typical directory patterns |
|---|---|
| **boundary** | `api/`, `routes/`, `views/`, `controllers/`, `adapters/`, `clients/`, `consumers/`, `handlers/`, `cli/` |
| **service** | `services/`, `use_cases/`, `domain/`, `core/`, `business/` |
| **repository** | `repositories/`, `repo/`, `db/`, `persistence/`, `storage/` |
| **model** | `models/`, `schemas/`, `entities/`, `dto/` |

Record the mapping as:
```
BOUNDARY_DIRS = [...]   # e.g. ["src/api", "harness_skills/cli"]
SERVICE_DIRS  = [...]   # e.g. ["src/services"]
REPO_DIRS     = [...]   # e.g. ["src/repositories"]
```

If the project does not have a clear layered structure, note this in the report and skip
Steps 2–4 (no rules can be generated without identifiable layers).

---

### Step 1: Identify validation patterns

Collect the **validation fingerprints** this project uses.  Scan all Python and TypeScript/
JavaScript files for these patterns:

**Python — Pydantic / dataclass validation:**
```bash
grep -rn \
  --include="*.py" \
  -E "(BaseModel|model_validate|parse_obj|model_fields_set|Field\(|validator\(|field_validator\(|@validate_call)" \
  . 2>/dev/null | grep -v "\.venv/"
```

**Python — manual / defensive validation:**
```bash
grep -rn \
  --include="*.py" \
  -E "(isinstance\(|raise ValueError|raise TypeError|assert .+, ['\"])" \
  . 2>/dev/null | grep -v "\.venv/" | grep -v "test_"
```

**Python — raw dict access that implies unvalidated data:**
```bash
grep -rn \
  --include="*.py" \
  -E '(\.get\(['"'"'"](id|name|type|status|data|payload|result)['"'"'"]|request\[|body\[)' \
  . 2>/dev/null | grep -v "\.venv/"
```

**TypeScript / JavaScript — Zod / class-validator / manual validation:**
```bash
grep -rn \
  --include="*.ts" --include="*.tsx" --include="*.js" \
  -E "(z\.object\(|z\.string\(|@IsString|@IsNumber|@IsEmail|typeof .+ ===|instanceof .+Error)" \
  . 2>/dev/null | grep -v node_modules
```

Collect results into two buckets:
- **BOUNDARY_VALIDATION**: hits inside `BOUNDARY_DIRS`
- **MISPLACED_VALIDATION**: hits inside `SERVICE_DIRS` or `REPO_DIRS`

---

### Step 2: Detect HTTP-layer types leaking into business logic

HTTP-aware types (`HTTPException`, `Response`, `status_code`, `Request`, framework
decorators) must not appear outside boundary layers:

```bash
grep -rn \
  --include="*.py" \
  -E "(HTTPException|fastapi\.responses|flask\.abort|status\.HTTP_|from starlette)" \
  . 2>/dev/null \
  | grep -v "\.venv/" \
  | grep -v "test_"
```

```bash
grep -rn \
  --include="*.ts" --include="*.tsx" \
  -E "(HttpException|@HttpCode|@Res\(\)|Response\.status\(|NestFactory)" \
  . 2>/dev/null | grep -v node_modules
```

Flag any hit inside `SERVICE_DIRS` or `REPO_DIRS` as a **boundary-leak violation**.

---

### Step 3: Detect duplicate validation (same field validated at multiple layers)

Search for field names that appear in validation expressions at more than one layer.
A field name like `email` should be validated in exactly one place (the boundary schema)
and then trusted everywhere downstream:

```bash
# Find field names validated at the boundary
grep -rn --include="*.py" -oE "Field\(['\"]?[a-z_]+" \
  $(echo $BOUNDARY_DIRS | tr ' ' '\n' | xargs -I{} find {} -name "*.py" 2>/dev/null) \
  2>/dev/null | sed 's/.*Field(//' | sort | uniq

# Find the same field names validated in service/repo layers
grep -rn --include="*.py" \
  -E "isinstance\(|raise ValueError|\.get\(" \
  $(echo $SERVICE_DIRS $REPO_DIRS | tr ' ' '\n' | xargs -I{} find {} -name "*.py" 2>/dev/null) \
  2>/dev/null
```

Any field that appears in both sets is a candidate for a **duplication violation**.

---

### Step 4: Build the boundary report

Print a structured report:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Boundary Validation Analysis
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Layer             Dir(s)                     Validation hits   Status
  ──────────────────────────────────────────────────────────────────────
  boundary          harness_skills/cli/         12               ✅ correct
  service           harness_skills/gates/         3               ❌ misplaced
  repository        (none found)                 —               —

  Misplaced validation (3 hits — must move to boundary layer):
    harness_skills/gates/runner.py:142   isinstance(config, dict)
    harness_skills/gates/runner.py:201   raise ValueError("config key 'threshold' …")
    harness_skills/gates/coverage.py:88  if not isinstance(report_path, str):

  Boundary-leak violations (HTTP types in service/repo layer):
    (none found)

  Duplicate validation (same field validated at >1 layer):
    (none found)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Legend:
- ✅ correct — validation lives in the expected boundary layer.
- ❌ misplaced — validation found inside a service or repository layer.
- ⚠️  leak — HTTP-framework types appear outside the boundary layer.
- 🔶 duplicate — the same field is validated at more than one layer.

---

### Step 5: Write boundary-validation rules as principles

Load `.claude/principles.yaml` (create if missing).  Upsert principles using IDs in the
range `BV001`–`BV999`.  Re-running `/boundary-validation` updates existing `BV*`
principles in-place; it never duplicates them.

Always write the five **structural rules** (BV001–BV005) regardless of whether violations
were found — these lock in the expected design:

```yaml
# Generated by /boundary-validation — do not edit IDs manually

# ── Boundary-Layer Validation (generated by /boundary-validation) ─────────────
# IDs BV001–BV999.  Re-running /boundary-validation updates these in-place.

  - id: "BV001"
    category: "architecture"
    severity: "blocking"
    applies_to: ["review-pr", "check-code"]
    rule: >
      BOUNDARY-ONLY VALIDATION — all input parsing and validation must occur
      exclusively at system boundaries: API route functions, CLI argument
      parsers, and external-service adapter methods.  Domain service methods,
      use-case classes, and repository implementations must receive fully
      validated, typed objects and must not re-validate them.
      Prohibited patterns in service/repo layers:
        • isinstance() checks on method parameters
        • raise ValueError / raise TypeError for missing or wrong-typed fields
        • raw dict .get() calls that defend against unset keys
        • Pydantic model_validate() / parse_obj() calls
      Approved boundary patterns:
        • Pydantic BaseModel or TypedDict parsed at the route or adapter layer
        • FastAPI Depends() used to validate before the service is called
        • Adapter methods (e.g. Client.parse_response()) that return typed objects

  - id: "BV002"
    category: "architecture"
    severity: "blocking"
    applies_to: ["review-pr", "check-code"]
    rule: >
      EXTERNAL SERVICE VALIDATION — responses from external HTTP APIs, message
      queues, and file-system reads must be validated and normalised inside a
      dedicated adapter / client module before a typed domain object is
      returned to the caller.  Service methods must never receive or handle
      raw dicts, JSON strings, or bytes from external sources.
      Example: ExternalServiceClient.fetch_user() must return a typed User
      domain object, not a raw dict — all field checks happen inside
      fetch_user() before it returns.

  - id: "BV003"
    category: "architecture"
    severity: "blocking"
    applies_to: ["review-pr", "check-code"]
    rule: >
      NO DUPLICATE VALIDATION — each field or invariant must be validated in
      exactly one place: the boundary schema.  Once a value has been validated
      and typed at the boundary, every downstream layer must trust that type
      and must not re-check the same condition.
      Duplication rule: if a field is declared in a Pydantic schema with a
      validator, no other function in the call chain may re-validate the same
      constraint.  Shared validation logic must be extracted into a reusable
      validator or schema field rather than copied.

  - id: "BV004"
    category: "architecture"
    severity: "blocking"
    applies_to: ["review-pr", "check-code"]
    rule: >
      TYPED PARAMETERS — all public functions in service and repository layers
      must declare fully typed parameters using Python type annotations (or
      TypeScript type declarations).  Parameters typed as `dict`, `Any`, `object`,
      or `Optional[dict]` in a service/repo method signature are a violation
      because they imply the caller is passing unvalidated data.
      Accepted types: domain-specific dataclasses, Pydantic models, primitive
      scalars (str, int, float, bool, Enum members), and collections of the above.
      Forbidden types in service/repo signatures: `dict`, `Any`, `object`,
      `Union[str, None]` where the None implies "not yet validated".

  - id: "BV005"
    category: "architecture"
    severity: "blocking"
    applies_to: ["review-pr", "check-code"]
    rule: >
      HTTP-LAYER ISOLATION — HTTP-framework types (HTTPException, Response,
      status_code, Request objects, framework decorators) must not appear
      outside the boundary layer (routes/, api/, adapters/).  Service and
      repository layers are HTTP-agnostic: they raise domain exceptions
      (e.g. UserNotFoundError) and let the boundary layer translate them into
      HTTP error responses.
      Prohibited in service/repo layers:
        • Import or raise HTTPException, flask.abort(), or equivalent
        • Return Response / JSONResponse objects
        • Reference status.HTTP_4xx / status.HTTP_5xx constants
      If a service needs to signal an error, define a domain exception class
      and raise that; the route handler catches it and maps to HTTP status.
```

If the analysis in Steps 1–3 found specific violations, also write per-file rules
(BV010 and above) naming the exact files that must be refactored:

```yaml
  - id: "BV010"
    category: "architecture"
    severity: "blocking"
    applies_to: ["review-pr", "check-code"]
    rule: >
      harness_skills/gates/runner.py — the isinstance() checks on lines 142
      and the raise ValueError on line 201 must be moved to the CLI layer
      (harness_skills/cli/) or to a Pydantic config schema so that runner.py
      receives already-validated objects.
```

---

### Step 6: Regenerate PRINCIPLES.md

After writing `.claude/principles.yaml`, regenerate `PRINCIPLES.md` using the same
logic as `/define-principles` Step 4.5.  Specifically:

1. Preserve all existing sections in `PRINCIPLES.md` that are outside the
   `Boundary Validation Rules` section.
2. Add or replace a section titled `## <N>. Boundary Validation Rules` (where N is
   the next available section number) with the BV principles formatted the same way
   as existing sections.
3. Stage the file with `git add PRINCIPLES.md` but do **not** auto-commit.

---

### Step 7: Summary and next steps

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✅ Boundary Validation — Done
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  <N> layers identified
  <M> misplaced validation hits — fix in: <list of files>
  5 structural boundary principles written  →  .claude/principles.yaml (BV001–BV005)
  <K> per-file remediation principles written  →  (BV010–BV0KK)

  Enforcement active in:
    • /check-code  — scans staged files against BV* principles
    • /review-pr   — flags boundary violations in PR diffs
    • /harness:lint — runs the principles gate which includes BV* rules

  Re-run any time:  /boundary-validation
  Skip principle write:  /boundary-validation --no-principles
  Report only:  /boundary-validation --dry-run
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Flags

| Flag | Behaviour |
|---|---|
| `--dry-run` | Report only — no files written, no principles updated |
| `--layer boundary=<path>` | Override the detected boundary directory (repeatable) |
| `--layer service=<path>` | Override the detected service directory (repeatable) |
| `--fix` | Auto-apply all principle writes without interactive confirmation |
| `--no-principles` | Skip Step 5 (don't write to `.claude/principles.yaml`) |
| `--format json` | Emit the full violation list as JSON instead of the human-readable report |

---

## Notes

- **Safe to re-run** — existing `BV*` principles are updated in-place, never duplicated.
- **No file contents are modified** — only `.claude/principles.yaml` and `PRINCIPLES.md`
  are written; source files are not auto-fixed.
- **Static analysis only** — detection uses grep patterns, not AST execution.
  False positives in test helpers are expected; review the report before accepting.
- **Complement to /module-boundaries** — that skill enforces *who* may import *what*;
  this skill enforces *where* validation logic must live.  Run both on greenfield setups.
- **Integrate with CI** — after running this skill, the `principles` gate in
  `harness evaluate` will flag any new code that violates BV001–BV005 automatically.
- Do **not** commit changes directly — stage and commit with `/checkpoint` or manually.
