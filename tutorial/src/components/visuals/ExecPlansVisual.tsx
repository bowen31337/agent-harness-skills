import { motion } from "motion/react";

const nodes = [
	{ id: "TASK-1", cx: 80, cy: 10 },
	{ id: "TASK-2", cx: 20, cy: 50 },
	{ id: "TASK-3", cx: 140, cy: 50 },
	{ id: "TASK-4", cx: 80, cy: 90 },
];

const edges = [
	{ x1: 80, y1: 22, x2: 28, y2: 42 },
	{ x1: 80, y1: 22, x2: 132, y2: 42 },
	{ x1: 28, y1: 62, x2: 80, y2: 82 },
	{ x1: 132, y1: 62, x2: 80, y2: 82 },
];

export default function ExecPlansVisual() {
	return (
		<div className="flex justify-center p-4">
			<svg viewBox="0 0 160 100" className="w-full max-w-[240px]">
				{edges.map((e, i) => (
					<motion.line
						key={i}
						x1={e.x1}
						y1={e.y1}
						x2={e.x2}
						y2={e.y2}
						stroke="#6b7280"
						strokeWidth="1"
						initial={{ opacity: 0 }}
						whileInView={{ opacity: 0.6 }}
						viewport={{ once: true }}
						transition={{ duration: 0.5, delay: 0.3 + i * 0.1 }}
					/>
				))}
				{nodes.map((n, i) => (
					<motion.g
						key={n.id}
						initial={{ opacity: 0, scale: 0.5 }}
						whileInView={{ opacity: 1, scale: 1 }}
						viewport={{ once: true }}
						transition={{ duration: 0.4, delay: i * 0.1 }}
					>
						<circle cx={n.cx} cy={n.cy} r="10" fill="#1e1e2e" stroke="#ec4899" strokeWidth="1.5" />
						<text
							x={n.cx}
							y={n.cy + 1}
							textAnchor="middle"
							dominantBaseline="middle"
							fill="#e5e7eb"
							fontSize="5"
							fontFamily="monospace"
						>
							{n.id}
						</text>
					</motion.g>
				))}
			</svg>
		</div>
	);
}
