import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { useRef } from "react";

interface TerminalLine {
	text: string;
	color?: string;
	delay?: number;
}

interface TerminalSimProps {
	lines: TerminalLine[];
	title?: string;
}

export default function TerminalSim({ lines, title }: TerminalSimProps) {
	const containerRef = useRef<HTMLDivElement>(null);
	const lineRefs = useRef<(HTMLDivElement | null)[]>([]);

	useGSAP(
		() => {
			const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

			if (prefersReduced) {
				// Show all lines instantly
				for (const el of lineRefs.current) {
					if (el) gsap.set(el, { opacity: 1 });
				}
				return;
			}

			const tl = gsap.timeline({ delay: 0.6 });

			for (let i = 0; i < lineRefs.current.length; i++) {
				const el = lineRefs.current[i];
				if (!el) continue;
				const line = lines[i];
				const lineDelay = line.delay != null ? line.delay / 1000 : 0.15;

				tl.to(
					el,
					{
						opacity: 1,
						duration: 0.05,
					},
					`+=${lineDelay}`,
				);
			}
		},
		{ scope: containerRef, dependencies: [lines] },
	);

	return (
		<div
			ref={containerRef}
			className="bg-[#1e1e2e] rounded-lg border border-white/10 overflow-hidden w-full max-w-2xl"
		>
			{/* Title bar */}
			<div className="flex items-center gap-2 px-4 py-3 border-b border-white/5">
				<span className="w-3 h-3 rounded-full bg-red-500" />
				<span className="w-3 h-3 rounded-full bg-yellow-500" />
				<span className="w-3 h-3 rounded-full bg-green-500" />
				{title && <span className="ml-2 text-xs text-gray-500 font-mono">{title}</span>}
			</div>

			{/* Body */}
			<div
				className="p-4 font-mono text-xs sm:text-sm leading-relaxed overflow-x-auto"
				aria-live="polite"
			>
				{lines.map((line, i) => (
					<div
						key={`${i}-${line.text}`}
						ref={(el) => {
							lineRefs.current[i] = el;
						}}
						className={`opacity-0 ${line.color ?? "text-gray-300"}`}
					>
						{line.text}
					</div>
				))}
			</div>
		</div>
	);
}
