import type { ReactNode } from "react";
import { useRef } from "react";
import { Link } from "react-router-dom";
import type { Category } from "../data/features";
import { useScrollAnimation } from "../hooks/useScrollAnimation";
import GlowBadge from "./GlowBadge";

interface CategoryCardProps {
	category: Category;
	visual: ReactNode;
	index: number;
}

export default function CategoryCard({ category, visual, index }: CategoryCardProps) {
	const ref = useRef<HTMLDivElement>(null);
	const isOdd = index % 2 === 1;

	useScrollAnimation(ref, ({ gsap, ScrollTrigger }) => {
		const el = ref.current;
		if (!el) return;

		gsap.fromTo(
			el,
			{ opacity: 0, x: isOdd ? 80 : -80 },
			{
				opacity: 1,
				x: 0,
				duration: 0.8,
				ease: "power3.out",
				scrollTrigger: {
					trigger: el,
					start: "top 80%",
					toggleActions: "play none none none",
				},
			},
		);

		// Clean up ScrollTrigger instances when component unmounts
		return () => {
			ScrollTrigger.getAll().forEach((t) => t.kill());
		};
	});

	return (
		<div
			ref={ref}
			className={`flex flex-col gap-8 opacity-0 md:flex-row md:items-center md:gap-12 ${isOdd ? "md:flex-row-reverse" : ""}`}
		>
			{/* Text column */}
			<div className="flex-[3] space-y-4">
				<div className="flex items-center gap-3">
					<span className="text-4xl">{category.icon}</span>
					<h2 className="text-3xl font-bold text-gray-100">{category.name}</h2>
				</div>
				<p className="text-gray-400 leading-relaxed">{category.description}</p>
				<div className="flex items-center gap-4">
					<GlowBadge text={`${category.featureCount} features`} color="purple" />
					<Link to={category.route} className="text-sm font-medium text-brand-cyan hover:underline">
						Deep dive {"\u2192"}
					</Link>
				</div>
			</div>

			{/* Visual column */}
			<div className="flex-[2]">{visual}</div>
		</div>
	);
}
