import { useCallback, useState } from "react";
import CodeBlock from "../components/CodeBlock";
import DeepDiveLayout from "../components/DeepDiveLayout";
import FeatureItem from "../components/FeatureItem";
import GlowBadge from "../components/GlowBadge";
import ScrollReveal from "../components/ScrollReveal";
import { features } from "../data/features";

const execPlansFeatures = features.filter((f) => f.category === "exec-plans");

const contextLost = `# Agent session 1 (Tuesday 2:00 PM)
Agent: "I'll implement the billing service. Starting with models..."
Agent: "Models done. Now building the repository layer..."
Agent: "Repository tests passing. Moving to service logic..."
[context window exceeded — session ends]

# Agent session 2 (Tuesday 3:30 PM)
Agent: "I see a billing/ directory. Let me understand what's here..."
Agent: "Reading models.py... reading repository.py... reading tests..."
Agent: "Ok, I think the service layer needs to be built next..."
Agent: "Wait, is this following a specific architecture pattern?"
Agent: "Let me re-read the AGENTS.md to understand the conventions..."
# 15 minutes of re-discovery before any new work begins

# Agent session 3 (Wednesday 9:00 AM)
Agent: "What was I working on? Let me check git log..."
# The cycle repeats. Every session starts from scratch.`;

const planTemplate = `# execution-plan: billing-service
# created: 2024-12-15T14:00:00Z
# status: in-progress

## Objective
Implement billing service with Stripe integration

## Tasks
- [x] T1: Define billing models (depends: none)
- [x] T2: Build repository layer (depends: T1)
- [x] T3: Write repository tests (depends: T2)
- [ ] T4: Build service logic (depends: T2) ← IN PROGRESS
- [ ] T5: Stripe webhook handler (depends: T4)
- [ ] T6: Integration tests (depends: T4, T5)
- [ ] T7: API routes (depends: T4)
- [ ] T8: E2E tests (depends: T6, T7)

## Context Handoff
Search hints for next agent:
  - grep "class Billing" src/billing/
  - read src/billing/AGENTS.md for conventions
  - last commit: abc1234 "feat(billing): add repository layer"

## Progress Log
[14:00] Started T1 — billing models
[14:12] Completed T1 — 4 models, 2 enums
[14:15] Started T2 — repository layer
[14:28] Completed T2 — CRUD + Stripe sync queries
[14:30] Started T3 — repository tests
[14:45] Completed T3 — 12 tests passing
[14:47] Started T4 — service logic`;

const statusOutput = `$ harness status

  Plan: billing-service     Progress: ████████░░ 3/8 tasks
  Plan: auth-refactor       Progress: ██████████ 8/8 done ✓
  Plan: notification-system  Progress: ██░░░░░░░░ 1/8 tasks

  Active: billing-service
  ├── T4: Build service logic (in-progress, agent: claude-7)
  ├── T5: Stripe webhook handler (blocked by T4)
  └── T6: Integration tests (blocked by T4, T5)

  Stale plans: none
  Last checkpoint: 2024-12-15T14:47:00Z (commit: abc1234)`;

type TaskStatus = "done" | "in-progress" | "blocked";

interface TaskNode {
	id: string;
	label: string;
	status: TaskStatus;
	dependsOn: string[];
}

const initialNodes: TaskNode[] = [
	{ id: "T1", label: "Define Models", status: "done", dependsOn: [] },
	{ id: "T2", label: "Repository Layer", status: "done", dependsOn: ["T1"] },
	{ id: "T3", label: "Repo Tests", status: "done", dependsOn: ["T2"] },
	{ id: "T4", label: "Service Logic", status: "in-progress", dependsOn: ["T2"] },
	{ id: "T5", label: "Webhook Handler", status: "blocked", dependsOn: ["T4"] },
	{ id: "T6", label: "Integration Tests", status: "blocked", dependsOn: ["T4", "T5"] },
	{ id: "T7", label: "API Routes", status: "blocked", dependsOn: ["T4"] },
	{ id: "T8", label: "E2E Tests", status: "blocked", dependsOn: ["T6", "T7"] },
];

const statusBorder: Record<TaskStatus, string> = {
	done: "border-green-500 bg-green-500/10",
	"in-progress": "border-yellow-500 bg-yellow-500/10 ring-1 ring-yellow-500/30",
	blocked: "border-red-500/40 bg-red-500/5 opacity-60",
};

const statusIcon: Record<TaskStatus, string> = {
	done: "\u2705",
	"in-progress": "\u{1F7E1}",
	blocked: "\u{1F534}",
};

export default function ExecPlansPage() {
	const [nodes, setNodes] = useState<TaskNode[]>(initialNodes);

	const stepForward = useCallback(() => {
		setNodes((prev) => {
			const next = prev.map((n) => ({ ...n }));
			// Find the first in-progress node and complete it
			const inProgress = next.find((n) => n.status === "in-progress");
			if (inProgress) {
				inProgress.status = "done";
				// Unblock nodes whose dependencies are now all done
				for (const node of next) {
					if (
						node.status === "blocked" &&
						node.dependsOn.every((dep) => {
							const depNode = next.find((n) => n.id === dep);
							return depNode?.status === "done";
						})
					) {
						node.status = "in-progress";
						break; // Only advance one blocked node to in-progress per step
					}
				}
			}
			return next;
		});
	}, []);

	const resetGraph = useCallback(() => {
		setNodes(initialNodes);
	}, []);

	const allDone = nodes.every((n) => n.status === "done");
	const hasInProgress = nodes.some((n) => n.status === "in-progress");

	return (
		<DeepDiveLayout categoryId="exec-plans">
			{/* Act 1: The Problem */}
			<section className="mb-20">
				<ScrollReveal>
					<GlowBadge text="The Problem" color="purple" />
					<h2 className="text-2xl font-bold text-white mt-4 mb-3">
						Context lost between sessions — every agent starts from scratch
					</h2>
					<p className="text-gray-400 mb-8 max-w-2xl">
						When an agent's context window fills up or a session ends, all the work context
						vanishes. The next agent spends its first 15 minutes rediscovering what was already
						known, re-reading files, and reconstructing the plan.
					</p>
				</ScrollReveal>
				<ScrollReveal delay={0.2}>
					<CodeBlock code={contextLost} lang="bash" filename="agent-session-history.log" />
				</ScrollReveal>
			</section>

			{/* Act 2: The Solution */}
			<section className="mb-20">
				<ScrollReveal>
					<GlowBadge text="The Solution" color="cyan" />
					<h2 className="text-2xl font-bold text-white mt-4 mb-3">
						18 features for persistent plans, checkpoints, and context handoff
					</h2>
					<p className="text-gray-400 mb-8 max-w-2xl">
						Harness generates execution plans with task dependencies, progress logs, context handoff
						protocols, and git-based checkpoints. Each agent session picks up exactly where the last
						one left off.
					</p>
				</ScrollReveal>

				<div className="grid gap-3 mb-8">
					{execPlansFeatures.map((f) => (
						<div key={f.id} id={f.id}>
							<FeatureItem feature={f} />
						</div>
					))}
				</div>

				<ScrollReveal delay={0.1}>
					<div className="space-y-6">
						<CodeBlock code={planTemplate} lang="yaml" filename="exec-plans/billing-service.md" />
						<CodeBlock code={statusOutput} lang="bash" filename="harness status" />
					</div>
				</ScrollReveal>
			</section>

			{/* Act 3: See It In Action */}
			<section className="mb-20">
				<ScrollReveal>
					<GlowBadge text="See It In Action" color="green" />
					<h2 className="text-2xl font-bold text-white mt-4 mb-3">
						Task dependency graph with live status
					</h2>
					<p className="text-gray-400 mb-8 max-w-2xl">
						Click "Step Forward" to simulate task progression. Watch how completing a task
						automatically unblocks its dependents — just like{" "}
						<code className="text-brand-cyan">harness coordinate</code> manages it.
					</p>
				</ScrollReveal>

				<ScrollReveal delay={0.1}>
					<div className="glass rounded-lg p-6">
						{/* Controls */}
						<div className="flex gap-3 mb-6">
							<button
								type="button"
								onClick={stepForward}
								disabled={allDone || !hasInProgress}
								className="px-4 py-2 rounded-lg text-sm font-medium bg-brand-cyan/20 text-brand-cyan border border-brand-cyan/30 hover:bg-brand-cyan/30 disabled:opacity-50 disabled:cursor-not-allowed transition-colors focus-visible:ring-2 focus-visible:ring-brand-cyan focus-visible:outline-none"
							>
								Step Forward
							</button>
							{nodes !== initialNodes && (
								<button
									type="button"
									onClick={resetGraph}
									className="px-4 py-2 rounded-lg text-sm font-medium bg-surface-raised text-gray-400 border border-surface-border hover:text-gray-300 transition-colors focus-visible:ring-2 focus-visible:ring-brand-cyan focus-visible:outline-none"
								>
									Reset
								</button>
							)}
						</div>

						{/* Legend */}
						<div className="flex gap-6 mb-6 text-xs text-gray-400">
							<span className="flex items-center gap-1.5">
								<span className="w-3 h-3 rounded border-2 border-green-500 bg-green-500/10" />
								Done
							</span>
							<span className="flex items-center gap-1.5">
								<span className="w-3 h-3 rounded border-2 border-yellow-500 bg-yellow-500/10" />
								In Progress
							</span>
							<span className="flex items-center gap-1.5">
								<span className="w-3 h-3 rounded border-2 border-red-500/40 bg-red-500/5" />
								Blocked
							</span>
						</div>

						{/* Task graph */}
						<div className="space-y-3">
							{nodes.map((node) => (
								<div key={node.id} className="flex items-center gap-3">
									{/* Dependency indicator */}
									<div className="w-20 shrink-0 text-right">
										{node.dependsOn.length > 0 && (
											<span className="text-[10px] font-mono text-gray-600">
												{node.dependsOn.join(", ")} {"\u2192"}
											</span>
										)}
									</div>

									{/* Node card */}
									<div
										className={`flex-1 flex items-center justify-between px-4 py-3 rounded-lg border-2 transition-all duration-300 ${statusBorder[node.status]}`}
									>
										<div className="flex items-center gap-3">
											<span className="text-sm" aria-hidden="true">
												{statusIcon[node.status]}
											</span>
											<div>
												<span className="text-xs font-mono text-gray-500 mr-2">{node.id}</span>
												<span
													className={`text-sm font-medium ${
														node.status === "blocked" ? "text-gray-500" : "text-white"
													}`}
												>
													{node.label}
												</span>
											</div>
										</div>
										<span
											className={`text-[10px] font-mono px-2 py-0.5 rounded ${
												node.status === "done"
													? "text-green-400 bg-green-500/10"
													: node.status === "in-progress"
														? "text-yellow-400 bg-yellow-500/10"
														: "text-red-400 bg-red-500/10"
											}`}
										>
											{node.status}
										</span>
									</div>
								</div>
							))}
						</div>

						{/* Progress summary */}
						<div className="mt-6 pt-4 border-t border-surface-border">
							<div className="flex items-center justify-between text-sm">
								<span className="text-gray-400">
									{nodes.filter((n) => n.status === "done").length}/{nodes.length} tasks complete
								</span>
								{allDone && (
									<span className="text-brand-green font-semibold">
										Plan complete — ready for PR
									</span>
								)}
							</div>
							<div className="mt-2 h-1 bg-surface-raised rounded-full overflow-hidden">
								<div
									className="h-full bg-brand-green rounded-full transition-all duration-300"
									style={{
										width: `${(nodes.filter((n) => n.status === "done").length / nodes.length) * 100}%`,
									}}
								/>
							</div>
						</div>
					</div>
				</ScrollReveal>
			</section>
		</DeepDiveLayout>
	);
}
