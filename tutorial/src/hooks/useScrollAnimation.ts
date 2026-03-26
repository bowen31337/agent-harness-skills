import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import type { RefObject } from "react";

gsap.registerPlugin(ScrollTrigger);

export function useScrollAnimation(
	containerRef: RefObject<HTMLElement | null>,
	animationCallback: (gsapCtx: { gsap: typeof gsap; ScrollTrigger: typeof ScrollTrigger }) => void,
	deps: unknown[] = [],
) {
	useGSAP(
		() => {
			const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
			if (prefersReduced) return;

			animationCallback({ gsap, ScrollTrigger });
		},
		{ scope: containerRef, dependencies: deps },
	);
}
