import { useState } from "react";
import CodeBlock from "../components/CodeBlock";
import DeepDiveLayout from "../components/DeepDiveLayout";
import FeatureItem from "../components/FeatureItem";
import GlowBadge from "../components/GlowBadge";
import ScrollReveal from "../components/ScrollReveal";
import { features } from "../data/features";

const archFeatures = features.filter((f) => f.category === "architecture");

const spaghettiCode = `# What happens without architectural enforcement:

ui/dashboard.py
  → imports service/billing.py     ✓ ok
  → imports repo/users.py          ✗ skips service layer!
  → imports config/secrets.py      ✗ direct secret access!

service/auth.py
  → imports ui/components.py       ✗ service imports UI!
  → imports runtime/scheduler.py   ✗ wrong direction!

repo/orders.py
  → imports service/pricing.py     ✗ repo imports service!

# Result: 6 boundary violations, untestable spaghetti`;

const layerViolation = `$ harness lint --check layers

  VIOLATION  repo/orders.py:12
  │ from service.pricing import calculate_total
  │ ─── repo layer cannot import from service layer
  │
  VIOLATION  ui/dashboard.py:8
  │ from repo.users import get_user_by_id
  │ ─── ui layer cannot skip service layer
  │
  VIOLATION  service/auth.py:3
  │ from ui.components import LoginForm
  │ ─── service layer cannot import from ui layer

  3 violations found in 2.1s
  Run \`harness lint --fix\` for suggested refactors`;

type LayerId = "types" | "config" | "repo" | "service" | "runtime" | "ui";

interface Layer {
	id: LayerId;
	label: string;
	description: string;
	idx: number;
}

const layers: Layer[] = [
	{
		id: "ui",
		label: "UI / Presentation",
		description: "Views, templates, API routes, CLI handlers",
		idx: 0,
	},
	{
		id: "runtime",
		label: "Runtime / Orchestration",
		description: "Schedulers, workers, middleware, startup",
		idx: 1,
	},
	{
		id: "service",
		label: "Service / Business Logic",
		description: "Use cases, workflows, domain rules",
		idx: 2,
	},
	{
		id: "repo",
		label: "Repository / Data Access",
		description: "Database queries, external API clients, caches",
		idx: 3,
	},
	{
		id: "config",
		label: "Config / Settings",
		description: "Environment config, feature flags, constants",
		idx: 4,
	},
	{
		id: "types",
		label: "Types / Shared Models",
		description: "Data models, interfaces, enums, schemas",
		idx: 5,
	},
];

export default function ArchitecturePage() {
	const [selectedLayer, setSelectedLayer] = useState<LayerId | null>(null);

	const getLayerColor = (layer: Layer): string => {
		if (!selectedLayer) return "border-surface-border bg-surface-raised";
		const selectedIdx = layers.find((l) => l.id === selectedLayer)?.idx ?? -1;

		if (layer.id === selectedLayer) {
			return "border-brand-cyan bg-brand-cyan/10 ring-2 ring-brand-cyan";
		}
		// Layers below (higher idx) = allowed imports (green)
		if (layer.idx > selectedIdx) {
			return "border-green-500/50 bg-green-500/10";
		}
		// Layers above (lower idx) = forbidden imports (red)
		if (layer.idx < selectedIdx) {
			return "border-red-500/50 bg-red-500/10";
		}
		return "border-surface-border bg-surface-raised";
	};

	const getLayerLabel = (layer: Layer): string | null => {
		if (!selectedLayer || layer.id === selectedLayer) return null;
		const selectedIdx = layers.find((l) => l.id === selectedLayer)?.idx ?? -1;
		if (layer.idx > selectedIdx) return "allowed";
		if (layer.idx < selectedIdx) return "forbidden";
		return null;
	};

	return (
		<DeepDiveLayout categoryId="architecture">
			{/* Act 1: The Problem */}
			<section className="mb-20">
				<ScrollReveal>
					<GlowBadge text="The Problem" color="purple" />
					<h2 className="text-2xl font-bold text-white mt-4 mb-3">
						Import spaghetti -- every module imports everything
					</h2>
					<p className="text-gray-400 mb-8 max-w-2xl">
						Without enforced boundaries, dependencies flow in every direction. Services import UI
						components, repositories call business logic, and the codebase becomes an untestable,
						unreviewable tangle.
					</p>
				</ScrollReveal>
				<ScrollReveal delay={0.2}>
					<CodeBlock code={spaghettiCode} lang="bash" filename="dependency-chaos.log" />
				</ScrollReveal>
			</section>

			{/* Act 2: The Solution */}
			<section className="mb-20">
				<ScrollReveal>
					<GlowBadge text="The Solution" color="cyan" />
					<h2 className="text-2xl font-bold text-white mt-4 mb-3">
						Layered architecture with mechanical enforcement
					</h2>
					<p className="text-gray-400 mb-8 max-w-2xl">
						Harness generates a 6-layer architecture definition, linter rules, structural tests, and
						CI validation scripts. Every import is checked against the one-way dependency rule:
						layers may only import from layers below.
					</p>
				</ScrollReveal>

				<div className="grid gap-3 mb-8">
					{archFeatures.map((f) => (
						<div key={f.id} id={f.id}>
							<FeatureItem feature={f} />
						</div>
					))}
				</div>

				<ScrollReveal delay={0.1}>
					<CodeBlock code={layerViolation} lang="bash" filename="harness lint --check layers" />
				</ScrollReveal>
			</section>

			{/* Act 3: See It In Action */}
			<section className="mb-20">
				<ScrollReveal>
					<GlowBadge text="See It In Action" color="green" />
					<h2 className="text-2xl font-bold text-white mt-4 mb-3">
						Interactive layer dependency diagram
					</h2>
					<p className="text-gray-400 mb-8 max-w-2xl">
						Click any layer to see which imports are allowed (green) and which are forbidden (red).
						Each layer may only import from layers below it.
					</p>
				</ScrollReveal>

				<ScrollReveal delay={0.1}>
					<div className="glass rounded-lg p-6">
						{/* Legend */}
						<div className="flex gap-6 mb-6 text-xs text-gray-400">
							<span className="flex items-center gap-2">
								<span className="w-3 h-3 rounded bg-brand-cyan/30 border border-brand-cyan" />
								Selected layer
							</span>
							<span className="flex items-center gap-2">
								<span className="w-3 h-3 rounded bg-green-500/20 border border-green-500/50" />
								Can import from
							</span>
							<span className="flex items-center gap-2">
								<span className="w-3 h-3 rounded bg-red-500/20 border border-red-500/50" />
								Cannot import from
							</span>
						</div>

						{/* Layer stack */}
						<div className="space-y-2">
							{layers.map((layer) => {
								const label = getLayerLabel(layer);
								return (
									<button
										key={layer.id}
										type="button"
										onClick={() =>
											setSelectedLayer((prev) => (prev === layer.id ? null : layer.id))
										}
										aria-pressed={selectedLayer === layer.id}
										className={`w-full text-left px-5 py-4 rounded-lg border transition-all duration-200 focus-visible:ring-2 focus-visible:ring-brand-cyan focus-visible:outline-none ${getLayerColor(layer)}`}
									>
										<div className="flex items-center justify-between">
											<div>
												<div className="font-semibold text-white text-sm">{layer.label}</div>
												<div className="text-xs text-gray-400 mt-0.5">{layer.description}</div>
											</div>
											<div className="flex items-center gap-2">
												{label && (
													<span
														className={`text-[10px] font-mono px-2 py-0.5 rounded ${
															label === "allowed"
																? "text-green-400 bg-green-500/10"
																: "text-red-400 bg-red-500/10"
														}`}
													>
														{label === "allowed" ? "import ok" : "import blocked"}
													</span>
												)}
												{selectedLayer === layer.id && (
													<span className="text-[10px] font-mono text-brand-cyan bg-brand-cyan/10 px-2 py-0.5 rounded">
														selected
													</span>
												)}
											</div>
										</div>
									</button>
								);
							})}
						</div>

						{/* Direction arrow */}
						<div className="mt-4 flex items-center justify-center gap-2 text-xs text-gray-500">
							<span>imports flow downward only</span>
							<span aria-hidden="true">&#8595;</span>
						</div>
					</div>
				</ScrollReveal>
			</section>
		</DeepDiveLayout>
	);
}
