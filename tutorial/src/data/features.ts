export type CategoryId =
	| "analyzers"
	| "agents-md"
	| "architecture"
	| "principles"
	| "gates"
	| "observability"
	| "exec-plans"
	| "cli";

export interface Feature {
	id: string;
	description: string;
	category: CategoryId;
}

export interface Category {
	id: CategoryId;
	name: string;
	featureCount: number;
	color: string;
	icon: string;
	description: string;
	route: string;
}

export const features: Feature[] = [
	// Category: Codebase Analysis & Detection (14 features)
	{
		id: "F151",
		description: "Detects primary language(s) and framework(s) from package files",
		category: "analyzers",
	},
	{
		id: "F152",
		description:
			"Detects project structure pattern (monorepo, polyrepo, single-app) from directory layout",
		category: "analyzers",
	},
	{
		id: "F153",
		description: "Identifies existing test framework and test location conventions",
		category: "analyzers",
	},
	{
		id: "F154",
		description: "Identifies existing linter/formatter configuration and extracts active rules",
		category: "analyzers",
	},
	{ id: "F155", description: "Detects CI/CD platform from config files", category: "analyzers" },
	{
		id: "F156",
		description:
			"Maps directory tree into candidate domain boundaries using heuristics and import clustering",
		category: "analyzers",
	},
	{
		id: "F157",
		description:
			"Detects existing dependency layering patterns from import graph analysis via tree-sitter AST parsing",
		category: "analyzers",
	},
	{
		id: "F158",
		description: "Identifies existing documentation files and their coverage completeness",
		category: "analyzers",
	},
	{
		id: "F159",
		description:
			"Detects database technology from config files, migration directories, and ORM definitions",
		category: "analyzers",
	},
	{
		id: "F160",
		description:
			"Identifies API style (REST, GraphQL, gRPC) from route definitions, schema files, or proto files",
		category: "analyzers",
	},
	{
		id: "F161",
		description:
			"Detects environment variable patterns from .env files, config, and source code references",
		category: "analyzers",
	},
	{
		id: "F162",
		description:
			"Produces harness_manifest.json validated against a published JSON Schema with JSONPath error locations",
		category: "analyzers",
	},
	{
		id: "F163",
		description:
			"Generates harness_manifest.schema.json alongside the manifest for independent validation",
		category: "analyzers",
	},
	{
		id: "F164",
		description: "Generates a symbol index mapping identifiers to file paths and line numbers",
		category: "analyzers",
	},

	// Category: AGENTS.md Generation (16 features)
	{
		id: "F168",
		description:
			"Generates a tiered AGENTS.md system with root overview (<500 tokens) linking to per-domain docs",
		category: "agents-md",
	},
	{
		id: "F169",
		description: "Includes detected build, test, and lint commands with exact invocation syntax",
		category: "agents-md",
	},
	{
		id: "F170",
		description: "Generates per-domain AGENTS.md files for each detected subsystem",
		category: "agents-md",
	},
	{
		id: "F171",
		description:
			"Each domain AGENTS.md includes purpose, key files, internal patterns, and constraints",
		category: "agents-md",
	},
	{
		id: "F172",
		description:
			"Includes architecture overview section mapping domain boundaries and dependency flow",
		category: "agents-md",
	},
	{
		id: "F173",
		description:
			"Includes security protocols section covering secret handling and input validation",
		category: "agents-md",
	},
	{
		id: "F174",
		description: "Includes git workflow section with branch naming, commit format, and PR process",
		category: "agents-md",
	},
	{
		id: "F175",
		description:
			"Includes code conventions section derived from existing linter config and detected patterns",
		category: "agents-md",
	},
	{
		id: "F176",
		description:
			"Includes testing conventions section with test naming, assertion style, and fixture patterns",
		category: "agents-md",
	},
	{
		id: "F177",
		description:
			"Includes error handling patterns section derived from existing codebase conventions",
		category: "agents-md",
	},
	{
		id: "F178",
		description: "Cross-links all generated documentation for navigation via relative paths",
		category: "agents-md",
	},
	{
		id: "F179",
		description: "Enforces token-budget awareness with configurable max token count per AGENTS.md",
		category: "agents-md",
	},
	{
		id: "F180",
		description:
			"Flags stale documentation risks by tracking referenced source files and reporting staleness scores",
		category: "agents-md",
	},
	{
		id: "F181",
		description: "Supports regeneration mode with three-way merge to preserve manual edits",
		category: "agents-md",
	},
	{
		id: "F182",
		description: "Generates context depth map showing L0/L1/L2 tiered structure with token budgets",
		category: "agents-md",
	},
	{
		id: "F183",
		description: "Each AGENTS.md includes a Quick Reference section (<200 tokens) at the top",
		category: "agents-md",
	},

	// Category: Architecture Documentation & Enforcement (19 features)
	{
		id: "F187",
		description: "Generates ARCHITECTURE.md with a domain map showing all detected subsystems",
		category: "architecture",
	},
	{
		id: "F188",
		description:
			"Infers dependency direction between domains and generates a text-based dependency flow diagram",
		category: "architecture",
	},
	{
		id: "F189",
		description:
			"Generates a layered architecture definition per domain (Types\u2192Config\u2192Repo\u2192Service\u2192Runtime\u2192UI)",
		category: "architecture",
	},
	{
		id: "F190",
		description: "Detects violations of inferred dependency layers and reports them as warnings",
		category: "architecture",
	},
	{
		id: "F191",
		description: "Generates linter rules that mechanically enforce dependency direction",
		category: "architecture",
	},
	{
		id: "F192",
		description:
			"Generates CI validation script that fails builds on architectural boundary violations",
		category: "architecture",
	},
	{
		id: "F193",
		description: "Generates a providers pattern definition for cross-cutting concerns",
		category: "architecture",
	},
	{
		id: "F194",
		description:
			"Documents the one-way dependency rule: each layer may only import from layers below",
		category: "architecture",
	},
	{
		id: "F195",
		description:
			"Generates file naming convention rules and linter config based on detected conventions",
		category: "architecture",
	},
	{
		id: "F196",
		description: "Generates file size limit rules to prevent monolithic files",
		category: "architecture",
	},
	{
		id: "F197",
		description: "Generates module boundary rules where public API surface is explicitly declared",
		category: "architecture",
	},
	{
		id: "F198",
		description: "Generates docs/design-docs/ directory with ADR template",
		category: "architecture",
	},
	{
		id: "F199",
		description: "Generates docs/generated/ directory for auto-derived documentation",
		category: "architecture",
	},
	{
		id: "F200",
		description:
			"Supports custom layer definitions allowing engineers to override the default layer stack",
		category: "architecture",
	},
	{
		id: "F201",
		description: "Generates a structural test suite that validates architectural invariants",
		category: "architecture",
	},
	{
		id: "F202",
		description: "Generates a harness lint command that runs all architectural checks in one pass",
		category: "architecture",
	},
	{
		id: "F203",
		description: "Embeds version identifier and generation timestamp in every generated artifact",
		category: "architecture",
	},
	{
		id: "F204",
		description: "Generates a harness audit command with per-artifact freshness scoring",
		category: "architecture",
	},
	{
		id: "F205",
		description: "Generates an artifact changelog recording what changed in each harness update",
		category: "architecture",
	},

	// Category: Golden Principles & Pattern Enforcement (13 features)
	{
		id: "F209",
		description:
			"Analyzes the codebase for recurring patterns and extracts them as candidate golden principles with frequency data",
		category: "principles",
	},
	{
		id: "F210",
		description: "Generates PRINCIPLES.md listing all mechanical rules with rationale and examples",
		category: "principles",
	},
	{
		id: "F211",
		description:
			"Generates prefer-shared-utilities rule with pointers to existing utility packages",
		category: "principles",
	},
	{
		id: "F212",
		description:
			"Generates boundary-level validation rules for data validation at system boundaries",
		category: "principles",
	},
	{
		id: "F213",
		description:
			"Generates concurrency and async patterns rule based on detected framework conventions",
		category: "principles",
	},
	{
		id: "F214",
		description:
			"Generates error handling pattern rules with structured errors and logging conventions",
		category: "principles",
	},
	{
		id: "F215",
		description: "Generates naming convention rules derived from existing codebase style analysis",
		category: "principles",
	},
	{
		id: "F216",
		description: "Generates import ordering and grouping rules matching detected conventions",
		category: "principles",
	},
	{
		id: "F217",
		description:
			"Generates no-magic-numbers and no-hardcoded-strings rule with constant extraction guidance",
		category: "principles",
	},
	{
		id: "F218",
		description:
			"Generates test writing principles covering arrange-act-assert, naming, fixtures, and mocks",
		category: "principles",
	},
	{
		id: "F219",
		description: "Supports custom principle definitions via interactive prompt or config file",
		category: "principles",
	},
	{
		id: "F220",
		description:
			"Generates background cleanup task definitions for enforcing principles across the codebase",
		category: "principles",
	},
	{
		id: "F221",
		description:
			"Generates a principle violation report command scanning for deviations with severity and location",
		category: "principles",
	},

	// Category: Evaluation Gates & Testing Harness (15 features)
	{
		id: "F225",
		description: "Generates EVALUATION.md defining all completion criteria for PRs",
		category: "gates",
	},
	{
		id: "F226",
		description: "Generates a regression test gate ensuring all existing tests pass",
		category: "gates",
	},
	{
		id: "F227",
		description: "Generates a coverage gate with configurable threshold (default 90%)",
		category: "gates",
	},
	{
		id: "F228",
		description: "Generates a security check gate covering secret scanning and dependency audit",
		category: "gates",
	},
	{
		id: "F229",
		description: "Generates a performance benchmark gate with configurable thresholds",
		category: "gates",
	},
	{
		id: "F230",
		description: "Generates an architectural compliance gate running the structural test suite",
		category: "gates",
	},
	{
		id: "F231",
		description: "Generates a golden principles compliance gate that fails on critical violations",
		category: "gates",
	},
	{
		id: "F232",
		description:
			"Generates a documentation freshness gate verifying AGENTS.md references are current",
		category: "gates",
	},
	{
		id: "F233",
		description: "Generates a type safety gate running the type checker with zero errors required",
		category: "gates",
	},
	{
		id: "F234",
		description: "Generates a lint gate with zero warnings required on changed files",
		category: "gates",
	},
	{
		id: "F235",
		description:
			"Generates harness evaluate running all gates with structured JSON/YAML/table output",
		category: "gates",
	},
	{
		id: "F236",
		description:
			"Generates per-gate configuration in harness.config.yaml with enable/disable/thresholds",
		category: "gates",
	},
	{
		id: "F237",
		description: "Generates CI pipeline integration as GitHub Actions and GitLab CI workflows",
		category: "gates",
	},
	{
		id: "F238",
		description: "Generates gate failure reports as structured JSON with severity and suggestions",
		category: "gates",
	},
	{
		id: "F239",
		description: "Supports custom evaluation gates via a plugin interface in harness.config.yaml",
		category: "gates",
	},

	// Category: Observability & Application Legibility (17 features)
	{
		id: "F243",
		description: "Generates structured logging configuration matching the detected framework",
		category: "observability",
	},
	{
		id: "F244",
		description: "Generates a logging convention document specifying required fields per log entry",
		category: "observability",
	},
	{
		id: "F245",
		description:
			"Generates log format linter rules ensuring all log statements follow the structured pattern",
		category: "observability",
	},
	{
		id: "F246",
		description: "Generates a per-worktree boot script for isolated application instances",
		category: "observability",
	},
	{
		id: "F247",
		description:
			"Generates environment isolation configuration with separate ports and databases per worktree",
		category: "observability",
	},
	{
		id: "F248",
		description: "Generates a health check endpoint specification for application verification",
		category: "observability",
	},
	{
		id: "F249",
		description:
			"Generates harness boot command that starts isolated app and waits for health check",
		category: "observability",
	},
	{
		id: "F250",
		description:
			"Generates harness observe command for tailing structured logs by domain or trace_id",
		category: "observability",
	},
	{
		id: "F251",
		description: "Generates browser automation integration config (Playwright/Puppeteer)",
		category: "observability",
	},
	{
		id: "F252",
		description:
			"Generates a DOM snapshot utility for inspecting UI state without a full browser session",
		category: "observability",
	},
	{
		id: "F253",
		description:
			"Generates performance measurement hooks for response times, memory, and startup duration",
		category: "observability",
	},
	{
		id: "F254",
		description:
			"Generates an error aggregation view grouping recent errors by domain and frequency",
		category: "observability",
	},
	{
		id: "F255",
		description:
			"Generates harness screenshot command for capturing application state as visual artifacts",
		category: "observability",
	},
	{
		id: "F256",
		description: "Generates observability stack templates for lightweight local log aggregation",
		category: "observability",
	},
	{
		id: "F257",
		description:
			"Generates telemetry hooks tracking artifact reads, CLI frequency, and gate failure patterns",
		category: "observability",
	},
	{
		id: "F258",
		description:
			"Generates harness telemetry command reporting utilization and effectiveness scores",
		category: "observability",
	},
	{
		id: "F259",
		description:
			"Generates effectiveness scoring correlating artifact usage with PR quality metrics",
		category: "observability",
	},

	// Category: Execution Plans & State Management (18 features)
	{
		id: "F263",
		description:
			"Generates docs/exec-plans/ with templates including task dependency graph and coordination metadata",
		category: "exec-plans",
	},
	{
		id: "F264",
		description:
			"Generates execution plan template with objective, approach, steps, context assembly, and progress log",
		category: "exec-plans",
	},
	{
		id: "F265",
		description:
			"Generates harness plan command to create execution plans from feature descriptions",
		category: "exec-plans",
	},
	{
		id: "F266",
		description: "Generates progress log format for timestamped entries as steps complete",
		category: "exec-plans",
	},
	{
		id: "F267",
		description:
			"Generates harness status dashboard showing all plans with dependency graph display",
		category: "exec-plans",
	},
	{
		id: "F268",
		description:
			"Generates context handoff protocol with search hints for agent-driven context rebuild",
		category: "exec-plans",
	},
	{
		id: "F269",
		description: "Generates harness resume command loading most recent plan state as agent context",
		category: "exec-plans",
	},
	{
		id: "F270",
		description: "Generates git-based checkpoint integration with agent_id and task_id metadata",
		category: "exec-plans",
	},
	{
		id: "F271",
		description: "Generates technical debt tracker for logging shortcuts and TODOs with severity",
		category: "exec-plans",
	},
	{
		id: "F272",
		description: "Generates plan-to-PR linking convention for full traceability",
		category: "exec-plans",
	},
	{
		id: "F273",
		description: "Generates stale plan detector flagging plans with no progress beyond threshold",
		category: "exec-plans",
	},
	{
		id: "F274",
		description:
			"Generates plan completion report summarizing work done, debt incurred, and follow-ups",
		category: "exec-plans",
	},
	{
		id: "F275",
		description:
			"Execution plan templates include context assembly sections with grep patterns and file globs",
		category: "exec-plans",
	},
	{
		id: "F276",
		description:
			"Generates harness context command returning minimal file paths and search patterns",
		category: "exec-plans",
	},
	{
		id: "F277",
		description:
			"Execution plans support task dependencies via depends_on with blocked/ready/in-progress status",
		category: "exec-plans",
	},
	{
		id: "F278",
		description:
			"Generates task lock protocol with agent_id, timestamp, and auto-expire for concurrency control",
		category: "exec-plans",
	},
	{
		id: "F279",
		description: "Generates shared state file for agents to publish and query intermediate results",
		category: "exec-plans",
	},
	{
		id: "F280",
		description:
			"Generates harness coordinate command for cross-agent conflict detection and task reordering",
		category: "exec-plans",
	},

	// Category: Skill Invocation & CLI Interface (17 features)
	{
		id: "F284",
		description: "Registers /harness:create for full harness generation",
		category: "cli",
	},
	{
		id: "F285",
		description:
			"Registers /harness:update for re-scanning and updating artifacts with manual edit preservation",
		category: "cli",
	},
	{
		id: "F286",
		description: "Registers /harness:lint for running all architectural and principle checks",
		category: "cli",
	},
	{
		id: "F287",
		description: "Registers /harness:evaluate for running all evaluation gates",
		category: "cli",
	},
	{
		id: "F288",
		description: "Registers /harness:boot for launching isolated application instances",
		category: "cli",
	},
	{
		id: "F289",
		description: "Registers /harness:plan for creating execution plans from descriptions",
		category: "cli",
	},
	{
		id: "F290",
		description: "Registers /harness:status for showing plan, gate, and harness health metrics",
		category: "cli",
	},
	{
		id: "F291",
		description: "Registers /harness:resume for loading plan state for context handoff",
		category: "cli",
	},
	{
		id: "F292",
		description: "Registers /harness:screenshot for capturing application state",
		category: "cli",
	},
	{
		id: "F293",
		description:
			"Generates harness.config.yaml with progressive profiles (starter, standard, advanced)",
		category: "cli",
	},
	{
		id: "F294",
		description: "Generates standalone harness init shell script for non-Claude-Code environments",
		category: "cli",
	},
	{
		id: "F295",
		description: "All CLI commands support --output-format flag with TTY auto-detection",
		category: "cli",
	},
	{
		id: "F296",
		description: "Generates typed pydantic response models for every CLI command output",
		category: "cli",
	},
	{
		id: "F297",
		description: "CLI commands support --verbosity levels (quiet, normal, verbose, debug)",
		category: "cli",
	},
	{
		id: "F298",
		description: "Supports command composition via --then chaining for single-invocation pipelines",
		category: "cli",
	},
	{
		id: "F293b",
		description: "Config profiles provide progressive complexity from starter to advanced",
		category: "cli",
	},
	{
		id: "F295b",
		description:
			"Structured output defaults to JSON when stdout is not a TTY for agent consumption",
		category: "cli",
	},
];

export const categories: Category[] = [
	{
		id: "analyzers",
		name: "Codebase Analysis & Detection",
		featureCount: 14,
		color: "#a855f7",
		icon: "\uD83D\uDD0D",
		description:
			"Detects languages, frameworks, domains, dependencies, and project structure from package files and AST analysis across 6 languages.",
		route: "/analyzers",
	},
	{
		id: "agents-md",
		name: "AGENTS.md Generation",
		featureCount: 16,
		color: "#22d3ee",
		icon: "\uD83D\uDCC4",
		description:
			"Generates tiered, token-budget-aware AGENTS.md files with three-way merge regeneration and cross-linked documentation.",
		route: "/agents-md",
	},
	{
		id: "architecture",
		name: "Architecture Documentation & Enforcement",
		featureCount: 19,
		color: "#4ade80",
		icon: "\uD83C\uDFD7\uFE0F",
		description:
			"Generates ARCHITECTURE.md, layered definitions (5 presets), linter rules, structural tests, and CI validation for boundary enforcement.",
		route: "/architecture",
	},
	{
		id: "principles",
		name: "Golden Principles & Pattern Enforcement",
		featureCount: 13,
		color: "#facc15",
		icon: "\u2696\uFE0F",
		description:
			"Extracts recurring patterns, generates PRINCIPLES.md with mechanical rules, and provides 7 built-in scanners for automated enforcement.",
		route: "/principles",
	},
	{
		id: "gates",
		name: "Evaluation Gates & Testing Harness",
		featureCount: 15,
		color: "#3b82f6",
		icon: "\uD83D\uDEA6",
		description:
			"9 quality gates (coverage, security, types, architecture, principles, etc.) with structured JSON reports and CI pipeline integration.",
		route: "/gates",
	},
	{
		id: "observability",
		name: "Observability & Application Legibility",
		featureCount: 17,
		color: "#f97316",
		icon: "\uD83D\uDC41\uFE0F",
		description:
			"Structured logging, boot scripts, health checks, browser automation, telemetry, and effectiveness scoring for agent-driven development.",
		route: "/observability",
	},
	{
		id: "exec-plans",
		name: "Execution Plans & State Management",
		featureCount: 18,
		color: "#ec4899",
		icon: "\uD83D\uDCCB",
		description:
			"Execution plan templates, task dependencies, lock protocols, shared state, context handoff, and multi-agent coordination.",
		route: "/exec-plans",
	},
	{
		id: "cli",
		name: "Skill Invocation & CLI Interface",
		featureCount: 17,
		color: "#818cf8",
		icon: "\u2328\uFE0F",
		description:
			"17 commands with --then composition, --output-format auto-detection, --verbosity levels, and config profiles (starter/standard/advanced).",
		route: "/cli",
	},
];
