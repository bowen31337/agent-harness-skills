import { motion, useReducedMotion } from "motion/react";
import type { ReactNode } from "react";

interface ScrollRevealProps {
	children: ReactNode;
	delay?: number;
}

export default function ScrollReveal({ children, delay = 0 }: ScrollRevealProps) {
	const prefersReduced = useReducedMotion();

	if (prefersReduced) {
		return <>{children}</>;
	}

	return (
		<motion.div
			initial={{ opacity: 0, y: 40 }}
			whileInView={{ opacity: 1, y: 0 }}
			viewport={{ once: true, margin: "-100px" }}
			transition={{ duration: 0.6, delay }}
		>
			{children}
		</motion.div>
	);
}
