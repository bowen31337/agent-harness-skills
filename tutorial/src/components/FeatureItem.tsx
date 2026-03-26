import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import { getFeatureExample } from "../data/featureExamples";
import type { Feature } from "../data/features";
import CodeBlock from "./CodeBlock";
import ScrollReveal from "./ScrollReveal";

interface FeatureItemProps {
	feature: Feature;
}

export default function FeatureItem({ feature }: FeatureItemProps) {
	const [expanded, setExpanded] = useState(false);
	const example = getFeatureExample(feature);

	return (
		<ScrollReveal>
			<div className="glass rounded-lg overflow-hidden">
				{/* Header — always visible */}
				<button
					type="button"
					onClick={() => setExpanded((prev) => !prev)}
					aria-expanded={expanded}
					aria-controls={`example-${feature.id}`}
					className="w-full text-left px-4 py-3 flex items-start gap-3 hover:bg-white/5 transition-colors focus-visible:ring-2 focus-visible:ring-brand-cyan focus-visible:outline-none"
				>
					{/* Feature info */}
					<div className="flex-1 min-w-0">
						<p className="text-sm text-gray-200 leading-relaxed">{feature.description}</p>
						<div className="flex items-center gap-2 mt-1.5">
							<span className="text-[10px] font-mono text-gray-600">{feature.id}</span>
							<span className="text-[10px] text-gray-600">·</span>
							<span className="text-[10px] text-brand-cyan/70">{example.label}</span>
						</div>
					</div>

					{/* Expand chevron */}
					<span
						className={`mt-1 text-gray-500 transition-transform shrink-0 text-xs ${expanded ? "rotate-180" : ""}`}
						aria-hidden="true"
					>
						&#9660;
					</span>
				</button>

				{/* Collapsible code example */}
				<AnimatePresence>
					{expanded && (
						<motion.div
							id={`example-${feature.id}`}
							initial={{ height: 0, opacity: 0 }}
							animate={{ height: "auto", opacity: 1 }}
							exit={{ height: 0, opacity: 0 }}
							transition={{ duration: 0.2 }}
							className="overflow-hidden"
						>
							<div className="px-4 pb-3">
								<CodeBlock code={example.code} lang={example.lang} filename={example.label} />
							</div>
						</motion.div>
					)}
				</AnimatePresence>
			</div>
		</ScrollReveal>
	);
}
