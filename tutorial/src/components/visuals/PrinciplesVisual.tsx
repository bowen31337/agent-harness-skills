import { motion } from "motion/react";

export default function PrinciplesVisual() {
	return (
		<div className="flex gap-3 p-4">
			{/* Before */}
			<motion.div
				className="flex-1 rounded-lg border border-red-500/30 bg-red-950/20 p-3"
				initial={{ opacity: 0 }}
				whileInView={{ opacity: 1 }}
				viewport={{ once: true }}
				transition={{ duration: 0.5 }}
			>
				<span className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-red-400">
					Before
				</span>
				<pre className="text-xs font-mono text-gray-300">
					<span className="text-red-400">x</span> = <span className="text-red-300">42</span>
				</pre>
			</motion.div>

			{/* After */}
			<motion.div
				className="flex-1 rounded-lg border border-green-500/30 bg-green-950/20 p-3"
				initial={{ opacity: 0 }}
				whileInView={{ opacity: 1 }}
				viewport={{ once: true }}
				transition={{ duration: 0.5, delay: 0.3 }}
			>
				<span className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-green-400">
					After
				</span>
				<pre className="text-xs font-mono text-gray-300">
					<span className="text-green-400">MAX_RETRIES</span> ={" "}
					<span className="text-green-300">42</span>
				</pre>
			</motion.div>
		</div>
	);
}
