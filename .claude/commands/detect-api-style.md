# Detect API Style

Identify whether the project uses REST, GraphQL, gRPC, or a combination — inferred from route definitions, schema files, and proto files. Produces a confidence-scored report with evidence.

## Instructions

### Step 1: Scan for gRPC signals

Look for Protocol Buffer definitions and gRPC service declarations:

```bash
# Find .proto files anywhere in the project
find . -name "*.proto" -not -path "*/node_modules/*" -not -path "*/.git/*" 2>/dev/null

# Check for gRPC library imports/deps
grep -rn "grpc\|protobuf\|grpcio\|google.protobuf\|@grpc/grpc-js\|grpc-gateway" \
  --include="*.py" --include="*.js" --include="*.ts" --include="*.go" \
  --include="*.java" --include="*.rb" --include="requirements*.txt" \
  --include="package.json" --include="go.mod" \
  -l . 2>/dev/null | grep -v node_modules | grep -v ".git"

# Scan proto files for service blocks
find . -name "*.proto" -not -path "*/node_modules/*" | xargs grep -l "^service " 2>/dev/null
```

Record:
- Number of `.proto` files found
- Whether any contain `service` blocks (confirms gRPC, not just Protobuf data types)
- Whether gRPC client/server libraries appear in dependency files

---

### Step 2: Scan for GraphQL signals

Look for schema files, resolvers, and query/mutation definitions:

```bash
# Find GraphQL schema files
find . \( -name "*.graphql" -o -name "*.gql" \) \
  -not -path "*/node_modules/*" -not -path "*/.git/*" 2>/dev/null

# Find schema.py / typedefs that use GraphQL DSL
grep -rn "graphql\|GraphQL\|gql\`\|buildSchema\|makeExecutableSchema\|strawberry\|ariadne\|graphene\|type Query\|type Mutation\|type Subscription" \
  --include="*.py" --include="*.js" --include="*.ts" --include="*.rb" \
  --include="*.graphql" --include="*.gql" \
  -l . 2>/dev/null | grep -v node_modules | grep -v ".git"

# Check for /graphql endpoint registration
grep -rn '"/graphql"\|'"'"'/graphql'"'"'\|path.*graphql\|route.*graphql' \
  --include="*.py" --include="*.js" --include="*.ts" --include="*.rb" \
  . 2>/dev/null | grep -v node_modules | grep -v ".git"
```

Record:
- Number of `.graphql`/`.gql` schema files
- Whether `type Query`, `type Mutation`, or `type Subscription` blocks are present
- Whether a `/graphql` HTTP endpoint is registered
- GraphQL libraries detected in source or deps

---

### Step 3: Scan for REST signals

Look for HTTP route/method decorators and REST framework usage:

```bash
# Python: Flask, FastAPI, Django, DRF
grep -rn "@app\.route\|@router\.\|@api_view\|APIView\|ModelViewSet\|include(.*urls\|path(\|re_path(" \
  --include="*.py" -l . 2>/dev/null | grep -v ".git"

# JS/TS: Express, Fastify, Hapi, Koa
grep -rn "app\.get\|app\.post\|app\.put\|app\.patch\|app\.delete\|router\.get\|router\.post\|fastify\.route\|server\.route" \
  --include="*.js" --include="*.ts" -l . 2>/dev/null | grep -v node_modules | grep -v ".git"

# Go: net/http, chi, gin, echo
grep -rn "http\.HandleFunc\|mux\.Handle\|r\.GET\|r\.POST\|e\.GET\|e\.POST\|\.GET(\|\.POST(" \
  --include="*.go" -l . 2>/dev/null | grep -v ".git"

# Ruby: Rails routes, Sinatra
grep -rn "get '\|post '\|put '\|delete '\|resources :\|namespace :" \
  --include="*.rb" -l . 2>/dev/null | grep -v ".git"

# OpenAPI / Swagger specs
find . \( -name "openapi.yaml" -o -name "openapi.json" -o -name "swagger.yaml" -o -name "swagger.json" \) \
  -not -path "*/node_modules/*" -not -path "*/.git/*" 2>/dev/null
```

Record:
- Number of files containing HTTP verb route registrations
- Presence of OpenAPI/Swagger spec files
- REST frameworks detected (Flask, FastAPI, Express, Gin, Rails, etc.)

---

### Step 4: Score and classify

For each style, compute a confidence level based on signals found:

| Signal type               | Points |
|---------------------------|--------|
| Schema/proto file present | +30    |
| `service` / Query block   | +25    |
| Library in deps           | +20    |
| Route registrations found | +15    |
| Endpoint URL matches      | +10    |

Map total points → confidence:
- **0** → ⬜ None detected
- **1–25** → 🟡 Low
- **26–55** → 🟠 Medium
- **56+** → 🟢 High

A project may score HIGH for more than one style (hybrid APIs are common).

---

### Step 5: Spot-check evidence files

For each style that scored Medium or High, print the most informative evidence snippet:

```bash
# gRPC: show first service block in first .proto file found
head -40 <first_proto_file>

# GraphQL: show type Query block from first schema file
grep -A 20 "^type Query" <first_schema_file>

# REST: show 10 representative route registrations
grep -rn "@app\.route\|app\.get\|router\.get\|r\.GET\|\.HandleFunc" \
  --include="*.py" --include="*.js" --include="*.ts" --include="*.go" \
  . 2>/dev/null | grep -v node_modules | head -10
```

---

### Step 6: Generate report

Emit a structured report:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  API Style Detection Report
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  🟢 REST      — High confidence (85 pts)
  🟡 GraphQL   — Low confidence (20 pts)
  ⬜ gRPC      — None detected (0 pts)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Evidence
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  REST
    Framework : FastAPI (detected via @router.get / @router.post)
    Routes    : 23 route registrations across 6 files
    Spec      : openapi.yaml present ✅
    Key files : app/routers/users.py, app/routers/items.py

  GraphQL
    Schema    : No .graphql files found
    Library   : graphene in pyproject.toml (possible legacy dep)
    Endpoint  : No /graphql route registration found

  gRPC
    Proto files : None found
    Libraries   : None detected

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Verdict: REST  (primary)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**Verdict rules:**
- If only one style scores Medium or higher → label it as **primary**
- If two or more score Medium or higher → label as **hybrid** (list both)
- If nothing scores above Low → label as **Undetermined** and suggest manual inspection

---

### Step 7: Machine-readable output (optional)

If invoked with `--json`, also emit:

```json
{
  "verdict": "REST",
  "hybrid": false,
  "styles": {
    "rest":    { "confidence": "high",   "score": 85, "framework": "FastAPI",   "route_files": 6,  "spec": "openapi.yaml" },
    "graphql": { "confidence": "low",    "score": 20, "framework": "graphene",  "schema_files": 0, "endpoint": false },
    "grpc":    { "confidence": "none",   "score": 0,  "proto_files": 0,         "services": 0 }
  },
  "scanned_at": "<ISO-8601 timestamp>"
}
```

---

### Notes

- This skill is **read-only** — it never modifies project files.
- If the repo has both a REST gateway and a gRPC backend (common in microservice setups), both will score High and the verdict will be `hybrid`.
- Proto files used only for data serialization (no `service` blocks) do **not** count as gRPC signals.
- For monorepos, run from the specific service subdirectory to get accurate per-service results.
- Related skills: `/check-code` (quality gates), `/harness:context` (broader codebase context), `/create-spec` (formalise the API contract).
