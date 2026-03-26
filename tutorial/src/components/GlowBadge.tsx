interface GlowBadgeProps {
	text: string;
	color: "purple" | "cyan" | "green";
}

const glowClass: Record<GlowBadgeProps["color"], string> = {
	purple: "glow-purple",
	cyan: "glow-cyan",
	green: "glow-green",
};

export default function GlowBadge({ text, color }: GlowBadgeProps) {
	return (
		<span
			className={`inline-block px-3 py-1 text-xs font-medium rounded-full border border-surface-border ${glowClass[color]}`}
		>
			{text}
		</span>
	);
}
