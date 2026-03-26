import { motion } from "motion/react";

const layers = [
	{ name: "ui", shade: "#bbf7d0", width: "100%" },
	{ name: "runtime", shade: "#86efac", width: "92%" },
	{ name: "service", shade: "#4ade80", width: "84%" },
	{ name: "repo", shade: "#22c55e", width: "76%" },
	{ name: "config", shade: "#16a34a", width: "68%" },
	{ name: "types", shade: "#15803d", width: "60%" },
];

export default function ArchitectureVisual() {
	return (
		<div className="flex flex-col-reverse gap-1.5 p-4">
			{layers.map((layer, i) => (
				<motion.div
					key={layer.name}
					className="flex items-center justify-center rounded py-1.5 text-xs font-mono font-medium text-gray-900"
					style={{ width: layer.width, backgroundColor: layer.shade }}
					initial={{ opacity: 0, scaleX: 0.3 }}
					whileInView={{ opacity: 1, scaleX: 1 }}
					viewport={{ once: true }}
					transition={{ duration: 0.4, delay: i * 0.1, ease: "easeOut" }}
				>
					{layer.name}
				</motion.div>
			))}
		</div>
	);
}
