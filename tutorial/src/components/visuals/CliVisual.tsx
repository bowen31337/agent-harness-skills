import { motion } from "motion/react";

const stages = ["create", "lint", "evaluate"];

export default function CliVisual() {
	return (
		<div className="rounded-lg border border-surface-border bg-surface-card/60 p-4 font-mono text-xs">
			<div className="mb-2 text-gray-500">$ harness create --then lint --then evaluate</div>
			<div className="flex items-center gap-2">
				{stages.map((stage, i) => (
					<motion.div
						key={stage}
						className="flex items-center gap-2"
						initial={{ opacity: 0 }}
						whileInView={{ opacity: 1 }}
						viewport={{ once: true }}
						transition={{ duration: 0.4, delay: 0.3 + i * 0.25 }}
					>
						{i > 0 && <span className="text-gray-600">{"\u2192"}</span>}
						<motion.span
							className="rounded border border-indigo-500/30 bg-indigo-950/30 px-2 py-1 text-indigo-300"
							whileInView={{ borderColor: "rgba(129,140,248,0.6)" }}
							viewport={{ once: true }}
							transition={{ duration: 0.3, delay: 0.5 + i * 0.25 }}
						>
							{stage}
						</motion.span>
					</motion.div>
				))}
			</div>
		</div>
	);
}
