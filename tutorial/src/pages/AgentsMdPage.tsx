import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import CodeBlock from "../components/CodeBlock";
import DeepDiveLayout from "../components/DeepDiveLayout";
import FeatureItem from "../components/FeatureItem";
import GlowBadge from "../components/GlowBadge";
import ScrollReveal from "../components/ScrollReveal";
import { features } from "../data/features";

const agentsMdFeatures = features.filter((f) => f.category === "agents-md");

const agentsMdStructure = `# AGENTS.md (root — L0, ~480 tokens)
## Quick Reference
- Build: \`make build\`
- Test:  \`pytest tests/ -v\`
- Lint:  \`ruff check . && mypy .\`

## Architecture Overview
3 domains: auth, billing, notifications
Dependency flow: types → config → repo → service → runtime

## Domain Links
- [auth/AGENTS.md](auth/AGENTS.md) — Authentication & sessions
- [billing/AGENTS.md](billing/AGENTS.md) — Payments & subscriptions
- [notifications/AGENTS.md](notifications/AGENTS.md) — Email & push

## Constraints
- All DB access via repository layer
- No direct imports between domains
- Structured logging required (see conventions)`;

const bloatedContext = `<!-- 50,000 tokens of raw README, every source file, old changelogs... -->
# Project README (last updated 2023)
## Getting Started
... 2,000 lines of outdated setup instructions ...
## API Reference
... 15,000 lines of auto-generated docs ...
## Changelog
... 8,000 lines going back to v0.1 ...

Total: ~50,000 tokens loaded. Agent context window: 60% consumed.
Useful signal: maybe 5%.`;

const tierData: {
	id: string;
	label: string;
	tokens: string;
	description: string;
	content: string;
}[] = [
	{
		id: "l0",
		label: "L0 — Root Overview",
		tokens: "<500 tokens",
		description:
			"Project-wide essentials: build commands, architecture overview, domain links, and hard constraints.",
		content: `# AGENTS.md (root)
## Quick Reference (<200 tokens)
- Build: make build
- Test:  pytest tests/ -v
- Lint:  ruff check . && mypy .

## Architecture
3 domains: auth, billing, notifications
Flow: types → config → repo → service → runtime

## Domain Links
- auth/AGENTS.md — Authentication & sessions
- billing/AGENTS.md — Payments & subscriptions
- notifications/AGENTS.md — Email & push

## Hard Constraints
- No cross-domain imports
- All DB access via repository layer
- Structured logging (JSON) required`,
	},
	{
		id: "l1",
		label: "L1 — Domain Detail",
		tokens: "~1,200 tokens each",
		description:
			"Per-domain docs covering purpose, key files, internal patterns, and domain-specific constraints.",
		content: `# auth/AGENTS.md (domain — L1)
## Purpose
Handles user authentication, session management,
and OAuth2 provider integrations.

## Key Files
- routes.py      — FastAPI route definitions
- service.py     — Business logic (login, register, refresh)
- repository.py  — DB queries (users, sessions tables)
- schemas.py     — Pydantic request/response models

## Internal Patterns
- All passwords hashed via argon2
- Sessions stored in Redis (TTL: 24h)
- OAuth tokens encrypted at rest

## Testing
- Fixtures: conftest.py (test_user, auth_client)
- Pattern: arrange-act-assert, async tests

## Constraints
- Never log raw tokens or passwords
- Rate limit: 5 login attempts per minute`,
	},
	{
		id: "l2",
		label: "L2 — File-Level Comments",
		tokens: "~200 tokens each",
		description:
			"Inline documentation embedded as comments in complex source files for immediate context.",
		content: `# auth/service.py — File-Level Context (L2)
#
# AGENTS: This file contains the core authentication
# business logic. Key patterns:
#
# - login_user() validates credentials then creates
#   a session via SessionRepository
# - Token refresh uses sliding window expiry
# - OAuth callback normalizes provider responses
#   into internal UserProfile format
# - All methods raise AuthError subtypes, never
#   generic exceptions
# - Logging: structured JSON with trace_id from
#   request context
#
# Dependencies: repository.py, schemas.py
# Do NOT import from billing/ or notifications/`,
	},
];

export default function AgentsMdPage() {
	const [expandedTier, setExpandedTier] = useState<string | null>(null);

	const toggleTier = (id: string) => {
		setExpandedTier((prev) => (prev === id ? null : id));
	};

	return (
		<DeepDiveLayout categoryId="agents-md">
			{/* Act 1: The Problem */}
			<section className="mb-20">
				<ScrollReveal>
					<GlowBadge text="The Problem" color="purple" />
					<h2 className="text-2xl font-bold text-white mt-4 mb-3">
						Agents load 50,000 tokens of context... or none at all
					</h2>
					<p className="text-gray-400 mb-8 max-w-2xl">
						Without structured documentation, agents either consume your entire context window with
						raw files and outdated READMEs, or start with zero knowledge and spend turns
						rediscovering your project from scratch.
					</p>
				</ScrollReveal>
				<ScrollReveal delay={0.2}>
					<CodeBlock code={bloatedContext} lang="bash" filename="typical-agent-context.log" />
				</ScrollReveal>
			</section>

			{/* Act 2: The Solution */}
			<section className="mb-20">
				<ScrollReveal>
					<GlowBadge text="The Solution" color="cyan" />
					<h2 className="text-2xl font-bold text-white mt-4 mb-3">
						Tiered, token-budget-aware AGENTS.md generation
					</h2>
					<p className="text-gray-400 mb-8 max-w-2xl">
						Harness generates a three-tier documentation system: a root overview under 500 tokens,
						per-domain docs with internal patterns, and file-level inline comments -- all
						cross-linked and regeneratable with manual edit preservation.
					</p>
				</ScrollReveal>

				<div className="grid gap-3 mb-8">
					{agentsMdFeatures.map((f) => (
						<div key={f.id} id={f.id}>
							<FeatureItem feature={f} />
						</div>
					))}
				</div>

				<ScrollReveal delay={0.1}>
					<CodeBlock code={agentsMdStructure} lang="yaml" filename="AGENTS.md (generated)" />
				</ScrollReveal>
			</section>

			{/* Act 3: See It In Action */}
			<section className="mb-20">
				<ScrollReveal>
					<GlowBadge text="See It In Action" color="green" />
					<h2 className="text-2xl font-bold text-white mt-4 mb-6">
						Explore the three-tier context system
					</h2>
					<p className="text-gray-400 mb-8 max-w-2xl">
						Click each tier to see what content it generates. Each level provides progressively
						deeper context, so agents load only what they need.
					</p>
				</ScrollReveal>

				<div className="space-y-4">
					{tierData.map((tier) => (
						<ScrollReveal key={tier.id} delay={0.05}>
							<div className="glass rounded-lg overflow-hidden">
								<button
									type="button"
									onClick={() => toggleTier(tier.id)}
									aria-expanded={expandedTier === tier.id}
									aria-controls={`tier-panel-${tier.id}`}
									className="w-full text-left px-6 py-4 flex items-center justify-between gap-4 focus-visible:ring-2 focus-visible:ring-brand-cyan focus-visible:outline-none"
								>
									<div className="min-w-0">
										<div className="flex items-center gap-3 mb-1">
											<h3 className="text-lg font-semibold text-white">{tier.label}</h3>
											<span className="text-xs font-mono text-brand-cyan bg-brand-cyan/10 px-2 py-0.5 rounded">
												{tier.tokens}
											</span>
										</div>
										<p className="text-sm text-gray-400">{tier.description}</p>
									</div>
									<span
										className={`text-gray-500 transition-transform shrink-0 ${
											expandedTier === tier.id ? "rotate-180" : ""
										}`}
										aria-hidden="true"
									>
										&#9660;
									</span>
								</button>

								<AnimatePresence>
									{expandedTier === tier.id && (
										<motion.div
											id={`tier-panel-${tier.id}`}
											role="region"
											aria-label={tier.label}
											initial={{ height: 0, opacity: 0 }}
											animate={{ height: "auto", opacity: 1 }}
											exit={{ height: 0, opacity: 0 }}
											transition={{ duration: 0.3 }}
											className="overflow-hidden"
										>
											<div className="px-6 pb-4">
												<CodeBlock code={tier.content} lang="yaml" filename={`${tier.label}`} />
											</div>
										</motion.div>
									)}
								</AnimatePresence>
							</div>
						</ScrollReveal>
					))}
				</div>
			</section>
		</DeepDiveLayout>
	);
}
