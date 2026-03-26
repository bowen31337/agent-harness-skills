/**
 * Auto-generates code examples for features based on category + description.
 *
 * MAINTAINABILITY: This file derives examples from feature metadata rather than
 * hardcoding 129 snippets. When features.ts is updated, examples update automatically.
 * Only the `overrides` map below needs manual curation for high-value features.
 */
import type { CategoryId, Feature } from "./features";

export interface FeatureExample {
	code: string;
	lang: string;
	label: string;
}

// ── Category-level CLI patterns ──────────────────────────────────────────────
// Each category maps to a base command. The generator customizes per-feature.
const categoryCommand: Record<CategoryId, string> = {
	analyzers: "harness create",
	"agents-md": "harness update --agents-md",
	architecture: "harness lint --check layers",
	principles: "harness lint --check principles",
	gates: "harness evaluate",
	observability: "harness observe",
	"exec-plans": "harness plan",
	cli: "harness",
};

const categoryOutputPrefix: Record<CategoryId, string> = {
	analyzers: "Scanning project...\n",
	"agents-md": "Generating AGENTS.md...\n",
	architecture: "Checking architecture...\n",
	principles: "Checking principles...\n",
	gates: "Running evaluation gates...\n",
	observability: "Observing application...\n",
	"exec-plans": "Managing execution plan...\n",
	cli: "",
};

// ── Manual overrides for high-value features ─────────────────────────────────
// Add entries here for features that deserve richer examples.
const overrides: Record<string, FeatureExample> = {
	F151: {
		label: "Detection output",
		lang: "yaml",
		code: `$ harness create
Scanning project...

  Language:   Python 3.12
  Framework:  FastAPI 0.115
  ORM:        SQLAlchemy 2.0
  Tests:      pytest + pytest-asyncio
  Package:    pyproject.toml (PEP 621)`,
	},
	F156: {
		label: "Domain boundary detection",
		lang: "yaml",
		code: `$ harness create --verbose
Detecting domain boundaries...

  Domains found: 3
  ├── auth/     (12 modules, 847 imports)
  ├── billing/  (9 modules, 623 imports)
  └── notify/   (7 modules, 412 imports)

  Cross-domain imports: 4 (flagged for review)`,
	},
	F167: {
		label: "AGENTS.md generation",
		lang: "markdown",
		code: `# AGENTS.md (root — L0, ~480 tokens)
## Quick Reference
- Build: \`make build\`
- Test:  \`pytest tests/ -v\`
- Lint:  \`ruff check . && mypy .\`

## Architecture Overview
3 domains: auth, billing, notifications
Flow: types → config → repo → service → runtime`,
	},
	F170: {
		label: "Tiered loading",
		lang: "yaml",
		code: `# L0 (root):    ~480 tokens — project overview
# L1 (domain):  ~1,200 tokens — per-domain detail
# L2 (file):    ~200 tokens — inline comments

$ harness update --agents-md --tier L1 --domain auth
✓ auth/AGENTS.md updated (1,180 tokens)`,
	},
	F189: {
		label: "Layer definition",
		lang: "yaml",
		code: `# Generated architecture layers:
layers:
  - ui          # Views, API routes, CLI handlers
  - runtime     # Schedulers, workers, middleware
  - service     # Business logic, use cases
  - repo        # DB queries, external API clients
  - config      # Settings, feature flags
  - types       # Models, interfaces, enums

rule: each layer imports only from layers below`,
	},
	F191: {
		label: "Linter rule generation",
		lang: "python",
		code: `# Generated: .harness/rules/layer_imports.py
# Enforces: service cannot import from ui/runtime

FORBIDDEN_IMPORTS = {
    "service": ["ui", "runtime"],
    "repo":    ["ui", "runtime", "service"],
    "config":  ["ui", "runtime", "service", "repo"],
    "types":   ["ui", "runtime", "service", "repo", "config"],
}`,
	},
	F209: {
		label: "Pattern extraction",
		lang: "yaml",
		code: `$ harness lint --extract-principles
Scanning 847 source files...

  Candidate principles found: 6
  ├── P011: No magic numbers (found 23 instances)
  ├── P018: No hardcoded strings (found 18 instances)
  ├── P003: Structured errors (found 31 instances)
  └── ... 3 more in docs/candidate-principles.yaml`,
	},
	F217: {
		label: "Magic number detection",
		lang: "python",
		code: `# VIOLATION: P011 — No magic numbers
if retries > 3:           # ← magic number
    timeout = 30          # ← magic number

# FIXED:
MAX_RETRIES = 3
DEFAULT_TIMEOUT_SEC = 30
if retries > MAX_RETRIES:
    timeout = DEFAULT_TIMEOUT_SEC`,
	},
	F225: {
		label: "Evaluation gates",
		lang: "yaml",
		code: `# EVALUATION.md (generated)
gates:
  regression:  { threshold: "100% pass", severity: critical }
  coverage:    { threshold: "≥ 90%",     severity: critical }
  security:    { threshold: "0 high",    severity: critical }
  architecture: { threshold: "0 violations", severity: critical }
  principles:  { threshold: "0 critical", severity: warning }`,
	},
	F235: {
		label: "Gate evaluation output",
		lang: "bash",
		code: `$ harness evaluate --format table
  Gate               Result     Detail
  ─────────────────  ─────────  ──────────────────
  Regression Tests   ✓ passed   247/247 passed
  Coverage           ✓ passed   92.4% (≥ 90%)
  Security Scan      ✓ passed   0 vulnerabilities
  Architecture       ✓ passed   0 violations
  Overall: 8/8 gates passed ✓`,
	},
	F243: {
		label: "Structured logging config",
		lang: "python",
		code: `# Generated: logging_config.py
LOGGING = {
    "formatters": {
        "structured": {
            "fields": [
                "timestamp",  # ISO-8601 UTC
                "level",      # DEBUG/INFO/WARN/ERROR
                "domain",     # auth, billing, etc.
                "trace_id",   # W3C 32-hex-char
                "message",
            ]
        }
    }
}`,
	},
	F250: {
		label: "Log observation",
		lang: "bash",
		code: `$ harness observe --domain auth --level error
{"ts":"14:23:03","level":"ERROR","domain":"auth",
 "trace":"a1b2c3","msg":"OAuth token exchange failed"}
{"ts":"14:23:18","level":"ERROR","domain":"auth",
 "trace":"d4e5f6","msg":"Session expired: user_id=u_441"}`,
	},
	F263: {
		label: "Execution plan template",
		lang: "yaml",
		code: `# docs/exec-plans/billing-service.md
objective: Implement billing service
tasks:
  - id: T1
    name: Define models
    status: done
  - id: T2
    name: Repository layer
    depends_on: [T1]
    status: in-progress`,
	},
	F268: {
		label: "Context handoff",
		lang: "yaml",
		code: `# Context handoff protocol
search_hints:
  - grep "class Billing" src/billing/
  - read src/billing/AGENTS.md
last_commit: abc1234
last_task: T4 — Build service logic
next_task: T5 — Stripe webhook handler`,
	},
	F284: {
		label: "CLI invocation",
		lang: "bash",
		code: `$ harness create --profile standard
Scanning project... Python 3.12 + FastAPI detected
✓ Generated 14 artifacts
✓ harness.config.yaml written
✓ AGENTS.md generated (3 tiers)
✓ ARCHITECTURE.md generated`,
	},
	F298: {
		label: "Command chaining",
		lang: "bash",
		code: `$ harness create --then lint --then evaluate
[1/3] harness create  → ✓ 14 artifacts
[2/3] harness lint    → ✓ 0 violations
[3/3] harness evaluate → ✓ 8/8 gates passed

Pipeline complete in 12.4s`,
	},
};

// ── Generator function ───────────────────────────────────────────────────────

/** Extract key terms from a description for generating contextual examples */
function extractTerms(desc: string): string[] {
	const lower = desc.toLowerCase();
	const terms: string[] = [];

	if (lower.includes("generat")) terms.push("generates");
	if (lower.includes("detect")) terms.push("detects");
	if (lower.includes("lint") || lower.includes("check")) terms.push("lint");
	if (lower.includes("test")) terms.push("test");
	if (lower.includes("config")) terms.push("config");
	if (lower.includes("command") || lower.includes("register")) terms.push("command");
	if (lower.includes("ci") || lower.includes("pipeline")) terms.push("ci");
	if (lower.includes("report")) terms.push("report");
	if (lower.includes("gate")) terms.push("gate");
	if (lower.includes("log")) terms.push("log");
	if (lower.includes("plan")) terms.push("plan");
	if (lower.includes("agent")) terms.push("agent");

	return terms;
}

/** Generate a code example for any feature based on its metadata */
function generateExample(feature: Feature): FeatureExample {
	const cmd = categoryCommand[feature.category];
	const prefix = categoryOutputPrefix[feature.category];
	const terms = extractTerms(feature.description);

	// Clean description for use in output
	const shortDesc = feature.description
		.replace(/^(Generates|Registers|Supports|Each|All|CLI|Execution)\s+/i, "")
		.replace(/^(a|an|the)\s+/i, "");

	if (terms.includes("command")) {
		const cmdName =
			feature.description.match(/harness\s+(\w+)/)?.[1] ?? feature.category.replace("-", " ");
		return {
			label: "CLI usage",
			lang: "bash",
			code: `$ harness ${cmdName} --help\nUsage: harness ${cmdName} [options]\n\n${shortDesc}`,
		};
	}

	if (terms.includes("generates") && terms.includes("config")) {
		return {
			label: "Generated config",
			lang: "yaml",
			code: `# harness.config.yaml (generated)\n${feature.category}:\n  enabled: true\n  # ${shortDesc}`,
		};
	}

	if (terms.includes("generates") && terms.includes("ci")) {
		return {
			label: "CI integration",
			lang: "yaml",
			code: `# .github/workflows/harness.yml\n- name: ${shortDesc.slice(0, 50)}\n  run: ${cmd}\n  working-directory: .`,
		};
	}

	if (terms.includes("lint") || terms.includes("report")) {
		return {
			label: "Lint output",
			lang: "bash",
			code: `$ ${cmd}\n${prefix}  ✓ ${shortDesc}`,
		};
	}

	if (terms.includes("gate")) {
		return {
			label: "Gate result",
			lang: "bash",
			code: `$ harness evaluate\n  ${shortDesc.slice(0, 60).padEnd(60)} ✓ passed`,
		};
	}

	if (terms.includes("log")) {
		return {
			label: "Log output",
			lang: "json",
			code: `{"ts":"2024-12-15T14:23:01Z","level":"INFO",\n "domain":"${feature.category}","msg":"${shortDesc.slice(0, 50)}"}`,
		};
	}

	if (terms.includes("plan")) {
		return {
			label: "Plan output",
			lang: "yaml",
			code: `$ harness plan\n# ${shortDesc}`,
		};
	}

	// Default: show as CLI output
	return {
		label: "Output",
		lang: "bash",
		code: `$ ${cmd}\n${prefix}  ✓ ${shortDesc}`,
	};
}

/**
 * Get a code example for a feature.
 * Returns a curated override if available, otherwise auto-generates one.
 */
export function getFeatureExample(feature: Feature): FeatureExample {
	return overrides[feature.id] ?? generateExample(feature);
}
