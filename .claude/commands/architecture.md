# Architecture Layer Violations

Infer the dependency-layer hierarchy from the existing codebase structure and scan
for imports that violate those layers — reporting every violation as a **warning**
with an exact file and line location.

No configuration required: the skill derives the layer model directly from directory
and package naming conventions (MVC, Clean Architecture, DDD, and standard layered
patterns are all detected automatically).

---

## Usage

```bash
# Full scan — infer layers, detect violations, print warnings
/architecture

# Preview inferred layer map without scanning for violations
/architecture --layers-only

# Scan a single directory subtree
/architecture --root src/orders

# Also write violations as warning-severity principles
/architecture --write-principles

# Machine-readable JSON output
/architecture --format json

# Fail (exit 1) when any violations are found — useful in CI
/architecture --fail-on-violations

# Generate a layered architecture definition per domain (no violation scan)
/architecture --define

# Generate definition AND scan for violations
/architecture --define --fail-on-violations

# Write the definition to ARCHITECTURE.md
/architecture --define --write-architecture
```

---

## Instructions

### Step 0: Detect project language(s) and source root

```bash
# Python source tree?
find . -name "*.py" \
  -not -path "./.venv/*" -not -path "./node_modules/*" \
  -not -path "./__pycache__/*" | head -5

# TypeScript / JavaScript source tree?
find . \( -name "*.ts" -o -name "*.tsx" -o -name "*.js" \) \
  -not -path "./node_modules/*" -not -path "./dist/*" | head -5
```

Set `LANG_MODE` to `python`, `js`, or `both`.

Identify the **source root** — the directory that immediately contains domain
packages (e.g. `src/`, the top-level project directory, or the monorepo workspace
root).  Prefer `src/` when it exists; fall back to the repository root.

---

### Step 1: Infer the layer hierarchy

Scan the directory names directly beneath the source root and match them against
known layer-name vocabularies to assign a **layer rank** (lower rank = lower in the
stack; higher rank = closer to the user/API surface).

Use the following vocabulary table.  A directory qualifies for a layer if its name
**contains** any of the listed tokens (case-insensitive, hyphens/underscores treated
as word boundaries):

| Layer rank | Layer label | Matching tokens |
|---|---|---|
| 7 | `presentation` | `ui`, `view`, `views`, `page`, `pages`, `screen`, `screens`, `frontend`, `web`, `template`, `templates`, `presentation`, `component`, `components` |
| 6 | `api` | `api`, `rest`, `graphql`, `grpc`, `handler`, `handlers`, `controller`, `controllers`, `route`, `routes`, `router`, `endpoint`, `endpoints` |
| 5 | `application` | `app`, `application`, `use_case`, `use-case`, `usecase`, `interactor`, `command`, `commands`, `query`, `queries`, `workflow`, `orchestrat` |
| 4 | `service` | `service`, `services`, `business`, `logic`, `facade` |
| 3 | `domain` | `domain`, `model`, `models`, `entity`, `entities`, `aggregate`, `aggregates`, `value_object`, `value-object`, `core` |
| 2 | `repository` | `repo`, `repos`, `repository`, `repositories`, `store`, `stores`, `dao`, `gateway`, `gateways` |
| 1 | `infrastructure` | `infra`, `infrastructure`, `db`, `database`, `persistence`, `cache`, `queue`, `messaging`, `adapter`, `adapters`, `external`, `client`, `clients` |
| 0 | `util` | `util`, `utils`, `utility`, `utilities`, `helper`, `helpers`, `common`, `shared`, `lib`, `libs`, `pkg`, `config`, `settings`, `constant`, `constants` |

**Algorithm:**

```python
import os, re

LAYER_VOCAB = {
    7: ["ui", "view", "views", "page", "pages", "screen", "screens",
        "frontend", "web", "template", "templates", "presentation",
        "component", "components"],
    6: ["api", "rest", "graphql", "grpc", "handler", "handlers",
        "controller", "controllers", "route", "routes", "router",
        "endpoint", "endpoints"],
    5: ["app", "application", "use_case", "use-case", "usecase",
        "interactor", "command", "commands", "query", "queries",
        "workflow", "orchestrat"],
    4: ["service", "services", "business", "logic", "facade"],
    3: ["domain", "model", "models", "entity", "entities", "aggregate",
        "aggregates", "value_object", "value-object", "core"],
    2: ["repo", "repos", "repository", "repositories", "store", "stores",
        "dao", "gateway", "gateways"],
    1: ["infra", "infrastructure", "db", "database", "persistence",
        "cache", "queue", "messaging", "adapter", "adapters",
        "external", "client", "clients"],
    0: ["util", "utils", "utility", "utilities", "helper", "helpers",
        "common", "shared", "lib", "libs", "pkg", "config", "settings",
        "constant", "constants"],
}

def rank_directory(name: str) -> tuple[int, str] | None:
    normalized = re.sub(r"[-_ ]", "_", name.lower())
    tokens = normalized.split("_")
    for rank in sorted(LAYER_VOCAB, reverse=True):
        for vocab_token in LAYER_VOCAB[rank]:
            if any(vocab_token in t or t in vocab_token for t in tokens):
                label = {7:"presentation",6:"api",5:"application",
                         4:"service",3:"domain",2:"repository",
                         1:"infrastructure",0:"util"}[rank]
                return (rank, label)
    return None  # unrecognised — skip

layers = {}  # path → (rank, label)
for entry in os.scandir(source_root):
    if entry.is_dir():
        result = rank_directory(entry.name)
        if result:
            layers[entry.path] = result
```

If fewer than **2 distinct ranks** are found, the layer model is ambiguous — emit
a warning and exit gracefully:

```
⚠️  Layer inference found fewer than 2 distinct layers.
    The directory structure may not follow conventional naming.
    Use --layers-only to inspect what was found, then add explicit
    layer mappings to .claude/architecture.yaml for better results.
```

---

### Step 2: Display the inferred layer map

Always print the inferred map before scanning, so engineers can spot misclassifications:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Inferred Layer Map — src/
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Rank  Layer           Directory
  ────  ──────────────  ─────────────────────────────
    6   api             src/api/
    5   application     src/application/
    4   service         src/services/
    3   domain          src/domain/
    2   repository      src/repositories/
    1   infrastructure  src/infra/
    0   util            src/utils/

  Rule: a directory may only import from directories at equal or lower rank.
        Importing from a directory at a higher rank is a violation.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

If `--layers-only` was passed, stop here.

---

### Step 2.5: Per-Domain Layer Definition

This step always runs (it is not gated by `--define`; the flag only controls whether violation scanning follows).

#### 2.5.1 Discover domains

Scan the source root for top-level packages — directories containing `__init__.py` (Python), `package.json` (Node/JS), `go.mod` (Go), or similar language-specific markers.  Each such top-level package is one **domain**.  If the source root has no sub-packages matching any marker, treat the source root itself as a single domain.

#### 2.5.2 Map sub-modules to layer ranks

For each domain, walk its immediate subdirectories and single-file modules.  Apply the same `rank_directory()` vocabulary from Step 1 to each name and collect the resulting `{rank → [paths]}` mapping.

**Canonical layer stack** (use these labels in all output):

| Rank | Canonical label | Aliases shown to user |
|---|---|---|
| 0 | `types / config` | types, config, constants, shared models |
| 1 | `infrastructure` | db, cache, adapters, external clients |
| 2 | `repository` | repo, store, dao, gateway |
| 3 | `domain` | domain, models, entities, aggregates |
| 4 | `service` | service, business logic, facade |
| 5 | `application` | use-cases, commands, queries, workflows |
| 6 | `runtime / api` | handlers, controllers, routes, endpoints |
| 7 | `ui / presentation` | ui, views, pages, screens, components |

#### 2.5.3 Full block output (when `--define` is passed)

Print the definition in this format for **each domain** (show all 8 canonical ranks in order from highest to lowest; mark absent ranks with `—`):

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Domain: harness_skills  (src/harness_skills/)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Rank  Layer                   Paths
  ────  ──────────────────────  ──────────────────────────────────────
    7   ui / presentation       —
    6   runtime / api           harness_skills/cli/
    5   application             —
    4   service                 —
    3   domain                  —
    2   repository              —
    1   infrastructure          —
    0   types / config          harness_skills/models/
                                harness_skills/utils/

  Flow (bottom → top):
  types/config → infrastructure → repository → domain →
  service → application → runtime/api → ui/presentation

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Repeat this block for every domain found.

After all per-domain blocks, print a cross-domain summary table:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Cross-Domain Layer Coverage
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Layer                   harness_skills  dom_snapshot  harness_dashboard  log_format_linter
  ──────────────────────  ──────────────  ────────────  ─────────────────  ─────────────────
  ui / presentation       —               —             —                  —
  runtime / api           ✅              —             —                  ✅
  application             —               —             —                  —
  service                 ✅              —             ✅                 ✅
  domain                  ✅              ✅            ✅                 ✅
  repository              —               —             —                  —
  infrastructure          —               —             —                  —
  types / config          ✅              —             ✅                 ✅

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

#### 2.5.4 Compact summary output (when `--define` is NOT passed)

When `--define` is omitted, Step 2.5 still runs but produces a compact one-line summary per domain so the output is not overwhelming for a quick violation scan:

```
  Domains detected: harness_skills (cli→api, models→types), dom_snapshot_utility (snapshot→domain), harness_dashboard (scorer→service, models→domain), log_format_linter (checker→service, models→domain)
```

---

### Step 3: Collect imports per file

For every source file in the ranked directories, extract its import statements and
resolve each import to a layer directory.

**Python — extract imports:**

```bash
# For each .py file in the source tree, find all import lines
grep -rn \
  --include="*.py" \
  -E "^(import |from )" \
  <source_root>/ \
  --exclude-dir=".venv" \
  --exclude-dir="__pycache__"
```

Map each import path to a layer by checking whether the import string starts with
(or contains) the package name of any ranked directory.

Example mappings for `src/` source root:
- `from src.services.order_service import …` → `service` (rank 4)
- `from src.domain.models import …` → `domain` (rank 3)
- `from api.routes import …` → `api` (rank 6)

**TypeScript / JavaScript — extract imports:**

```bash
# For each .ts/.tsx/.js file in the source tree, find all import lines
grep -rn \
  --include="*.ts" --include="*.tsx" --include="*.js" \
  -E "^(import |} from |require\()" \
  <source_root>/ \
  --exclude-dir="node_modules" \
  --exclude-dir="dist"
```

Resolve relative imports (`../services/…`, `./repositories/…`) to absolute paths,
then map to a layer directory as above.

Build a list of `ImportEdge` records:

```python
@dataclass
class ImportEdge:
    source_file: str   # e.g. "src/domain/order.py"
    source_layer: str  # e.g. "domain"
    source_rank: int   # e.g. 3
    target_module: str # e.g. "src.api.routes"
    target_layer: str  # e.g. "api"
    target_rank: int   # e.g. 6
    line: int          # line number of the import statement
```

---

### Step 4: Detect violations

A violation occurs when a file in layer A imports from layer B and
**`B.rank > A.rank`** (i.e., a lower-ranked layer reaches up into a higher-ranked
layer).

The `util` layer (rank 0) is exempt: it may be imported by any layer without
triggering a violation.  Cross-imports between directories **at the same rank** are
also allowed (e.g., two `service` packages may import each other).

```python
violations = []
for edge in import_edges:
    if edge.target_rank > edge.source_rank and edge.target_rank > 0:
        violations.append(edge)
```

---

### Step 5: Report violations

Print each violation as a **warning** with the exact file path and line number.
Group violations by source layer for readability.

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Architecture Layer Violations — 5 warnings
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  🟡 domain → api  (rank 3 → rank 6)  [illegal upward dependency]
  ─────────────────────────────────────────────────────
  🟡 src/domain/order.py:14
       from src.api.serializers import OrderSchema
       domain (rank 3) must not import from api (rank 6)

  🟡 src/domain/pricing.py:7
       from api.routes import DISCOUNT_ENDPOINT
       domain (rank 3) must not import from api (rank 6)

  🟡 infrastructure → service  (rank 1 → rank 4)  [illegal upward dependency]
  ─────────────────────────────────────────────────────
  🟡 src/infra/db/session.py:3
       from src.services.user_service import UserService
       infrastructure (rank 1) must not import from service (rank 4)

  🟡 repository → application  (rank 2 → rank 5)  [illegal upward dependency]
  ─────────────────────────────────────────────────────
  🟡 src/repositories/order_repo.py:22
       from src.application.commands import CreateOrderCommand
       repository (rank 2) must not import from application (rank 5)

  🟡 src/repositories/order_repo.py:58
       from src.application.queries import OrderQuery
       repository (rank 2) must not import from application (rank 5)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Summary
  ─────────────────────────────────────────────────────
  Directories scanned  : 7
  Files scanned        : 83
  Import edges traced  : 241
  Violations found     : 5  🟡 (warnings — not blocking)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

If **no violations** are found:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✅  Architecture Layer Violations — clean
  No upward dependencies found across 7 layers / 83 files.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

### Step 6: Optionally write principles (--write-principles)

Skip this step unless `--write-principles` was passed.

Load `.claude/principles.yaml` (create if missing).  For each unique violating
layer-pair `(source_layer → target_layer)`, upsert a `warning`-severity principle
in the `AL001`–`AL999` ID range:

```yaml
# Generated by /architecture — do not edit IDs manually
- id: "AL001"
  category: "architecture"
  severity: "warning"
  applies_to: ["review-pr", "check-code"]
  rule: >
    Layer violation: 'domain' (rank 3) must not import from 'api' (rank 6).
    Dependencies must flow downward only — higher-ranked layers depend on
    lower-ranked layers, never the reverse.
    Refactor: extract the shared symbol into a lower-ranked layer (e.g. 'domain'
    or 'util') so both layers can import it without creating an upward edge.

- id: "AL002"
  category: "architecture"
  severity: "warning"
  applies_to: ["review-pr", "check-code"]
  rule: >
    Layer violation: 'infrastructure' (rank 1) must not import from 'service' (rank 4).
    Move any cross-cutting concerns into 'util' (rank 0) or introduce a
    dependency-inversion interface in 'domain' (rank 3).
```

Rules:
- One principle per unique violating layer-pair.
- Re-running `/architecture --write-principles` updates existing `AL*` principles
  in-place; it never duplicates them.
- Principles set to `severity: warning` by default — they advise without blocking CI.
  Promote to `severity: blocking` manually in `.claude/principles.yaml` if stricter
  enforcement is desired.
- After writing, regenerate `PRINCIPLES.md` (same logic as `/define-principles`
  Step 4.5).

---

### Step 6.5: Optionally write architecture definition (--write-architecture)

Skip this step unless `--write-architecture` was passed (which also implies `--define`).

Write the full per-domain definition output from Step 2.5 to `ARCHITECTURE.md` in the project root, under the heading `## Layered Architecture — Per Domain`.

Wrap the generated block with harness auto-generated markers so it can be refreshed idempotently:

```markdown
<!-- harness:auto-generated — do not edit this block manually -->
...generated content...
<!-- /harness:auto-generated -->
```

**Idempotency rules:**

- If `ARCHITECTURE.md` already exists and contains the markers, replace only the content between the markers.
- If the markers are absent, append a new `## Layered Architecture — Per Domain` section containing the markers and generated content.
- If `ARCHITECTURE.md` does not exist, create it with the heading and generated block.

After writing, print:

```
✅  Wrote layered architecture definition to ARCHITECTURE.md
```

---

### Step 7: Next steps

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Next Steps
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Fix violations
  ──────────────
  For each 🟡 warning, choose one of:

  (a) Move the shared symbol down to a layer both files can import:
      e.g. extract to 'domain' or 'util' so 'infrastructure' can reach it
      without depending on 'service'.

  (b) Introduce a dependency-inversion interface:
      Define an abstract class / protocol in a lower-ranked layer and have
      the higher-ranked layer provide the concrete implementation.

  (c) Adjust the layer classification in .claude/architecture.yaml if the
      inferred rank for a directory is wrong for your project.

  Enforce going forward
  ──────────────────────
  Run /architecture --write-principles to codify the layer rules as AL* entries
  in .claude/principles.yaml — they are then enforced automatically by
  /check-code and /review-pr on every future run.

  Optionally promote any AL* warning to severity: blocking to make violations
  fail CI rather than just advise.

  Generate architecture definition
  ────────────────────────────────
  Run /architecture --define to produce a canonical layer definition per domain.
  Run /architecture --define --write-architecture to persist it to ARCHITECTURE.md.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Optional: .claude/architecture.yaml override

When automatic inference is wrong or incomplete, create `.claude/architecture.yaml`
to pin the layer map explicitly.  The skill reads this file **before** running Step 1
and skips inference for any directory listed here:

```yaml
# .claude/architecture.yaml
# Manual layer overrides — takes precedence over name-based inference.
source_root: src/

layers:
  - path: src/api
    rank: 6
    label: api
  - path: src/core          # would be inferred as 'domain'; override to application
    rank: 5
    label: application
  - path: src/shared        # explicitly mark as utility — exempt from violation checks
    rank: 0
    label: util

# Additional paths to ignore entirely (e.g. generated code, migrations)
ignore:
  - src/generated/
  - src/migrations/
```

---

## Flags

| Flag | Behaviour |
|---|---|
| `--layers-only` | Print the inferred layer map and exit; do not scan for violations |
| `--root <path>` | Scan only the given directory subtree (default: source root) |
| `--write-principles` | Write `AL*` warning principles to `.claude/principles.yaml` |
| `--fail-on-violations` | Exit with code `1` when any violations are found (for CI) |
| `--format json` | Emit the full report as machine-readable JSON |
| `--ignore <glob>` | Additional glob pattern to exclude from scanning |
| `--no-util-exemption` | Disable the automatic exemption for `util`-ranked directories |
| `--define` | Generate per-domain layer definitions and print them; skip violation scan unless combined with `--fail-on-violations` |
| `--write-architecture` | Write the per-domain layer definition to `ARCHITECTURE.md` (implies `--define`) |

---

## Exit codes

| Outcome | Exit code |
|---|---|
| No violations found | `0` |
| Violations found, `--fail-on-violations` not set | `0` (warnings printed) |
| Violations found, `--fail-on-violations` set | `1` |
| Fewer than 2 layers inferred | `0` (warning printed, no scan performed) |
| Internal error | `2` |

---

## When to use this skill

| Scenario | Recommended skill |
|---|---|
| Detect upward layer dependencies in existing code | **`/architecture`** ← you are here |
| Generate a canonical layer definition per domain | **`/architecture --define`** ← new |
| Enforce explicit public API surfaces per module | `/module-boundaries` |
| Codify golden rules and enforce on PRs | `/define-principles` + `/harness:principles-gate` |
| Full quality gate before merge | `/harness:evaluate` |
| Run all principles in advisory mode | `/check-code` |

---

## Notes

- **Read-only by default** — the skill never modifies source files.  Use
  `--write-principles` to opt in to writing `.claude/principles.yaml`.
- **Static analysis only** — import edges are detected by `grep`/text scanning;
  no code is executed and no AST is built.  Dynamic imports (`importlib`,
  `require()` with variables) are not detected.
- **Inferred layers are a heuristic** — if the inferred map looks wrong, inspect
  the output of `--layers-only` and add overrides to `.claude/architecture.yaml`.
- **Util exemption** — the `util` / `shared` / `common` layer (rank 0) is exempt
  from upward-dependency rules because utilities are designed to be imported by
  every layer.  Disable with `--no-util-exemption` if your project convention
  differs.
- **Safe to re-run** — idempotent; `AL*` principles are upserted, never duplicated.
- **Does not commit** — stage and commit any changes with `/checkpoint` or manually.
