import { useRef } from "react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { motion } from "motion/react";
import TerminalSim from "./TerminalSim";

const terminalLines = [
  { text: "$ harness create --profile standard", color: "text-gray-400" },
  {
    text: "\u2713 harness.config.yaml created (profile: standard)",
    color: "text-green-400",
  },
  { text: "$ harness lint", color: "text-gray-400" },
  {
    text: "\u2713 architecture: passed  \u2713 principles: passed",
    color: "text-green-400",
  },
  { text: "$ harness evaluate --format json", color: "text-gray-400" },
  {
    text: "\u2713 coverage: 92%  \u2713 types: passed  \u2713 security: clean",
    color: "text-green-400",
  },
];

const subtitleWords = [
  "129 features",
  " \u00b7 ",
  "8 categories",
  " \u00b7 ",
  "17 commands",
];

export default function Hero() {
  const sectionRef = useRef<HTMLElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const wordRefs = useRef<(HTMLSpanElement | null)[]>([]);

  useGSAP(
    () => {
      const prefersReduced = window.matchMedia(
        "(prefers-reduced-motion: reduce)",
      ).matches;

      if (prefersReduced) {
        if (titleRef.current) gsap.set(titleRef.current, { opacity: 1, y: 0 });
        for (const el of wordRefs.current) {
          if (el) gsap.set(el, { opacity: 1, y: 0 });
        }
        return;
      }

      const tl = gsap.timeline();

      // Title fade in
      tl.fromTo(
        titleRef.current,
        { opacity: 0, y: 30 },
        { opacity: 1, y: 0, duration: 0.8, ease: "power3.out" },
      );

      // Subtitle staggered word fade-in
      const validWordEls = wordRefs.current.filter(Boolean);
      tl.fromTo(
        validWordEls,
        { opacity: 0, y: 10 },
        {
          opacity: 1,
          y: 0,
          duration: 0.4,
          stagger: 0.1,
          ease: "power2.out",
        },
        "-=0.3",
      );
    },
    { scope: sectionRef },
  );

  return (
    <section
      ref={sectionRef}
      className="relative min-h-screen flex flex-col items-center justify-center overflow-hidden"
      style={{
        backgroundImage: [
          "linear-gradient(rgba(168,85,247,0.03) 1px, transparent 1px)",
          "linear-gradient(90deg, rgba(168,85,247,0.03) 1px, transparent 1px)",
        ].join(","),
        backgroundSize: "60px 60px",
      }}
    >
      {/* Floating glow orbs */}
      <motion.div
        className="absolute top-1/4 -left-32 w-96 h-96 rounded-full opacity-30 pointer-events-none"
        style={{
          background:
            "radial-gradient(circle, rgba(168,85,247,0.4) 0%, transparent 70%)",
        }}
        animate={{ x: [0, 30, 0], y: [0, -20, 0] }}
        transition={{ duration: 8, repeat: Number.POSITIVE_INFINITY, ease: "easeInOut" }}
      />
      <motion.div
        className="absolute bottom-1/4 -right-32 w-80 h-80 rounded-full opacity-20 pointer-events-none"
        style={{
          background:
            "radial-gradient(circle, rgba(34,211,238,0.4) 0%, transparent 70%)",
        }}
        animate={{ x: [0, -25, 0], y: [0, 15, 0] }}
        transition={{ duration: 10, repeat: Number.POSITIVE_INFINITY, ease: "easeInOut" }}
      />
      <motion.div
        className="absolute top-1/2 left-1/2 w-64 h-64 rounded-full opacity-15 pointer-events-none"
        style={{
          background:
            "radial-gradient(circle, rgba(74,222,128,0.3) 0%, transparent 70%)",
        }}
        animate={{ x: [0, 20, -10, 0], y: [0, -15, 10, 0] }}
        transition={{ duration: 12, repeat: Number.POSITIVE_INFINITY, ease: "easeInOut" }}
      />

      {/* Content */}
      <div className="relative z-10 flex flex-col items-center gap-6 px-4 text-center">
        <h1
          ref={titleRef}
          className="gradient-text text-4xl md:text-6xl lg:text-7xl font-bold tracking-tight opacity-0"
        >
          harness-skills
        </h1>

        <p className="text-gray-400 text-lg">
          {subtitleWords.map((word, i) => (
            <span
              key={`${i}-${word}`}
              ref={(el) => {
                wordRefs.current[i] = el;
              }}
              className="inline-block opacity-0"
            >
              {word}
            </span>
          ))}
        </p>

        <div className="mt-8 w-full flex justify-center">
          <TerminalSim lines={terminalLines} title="terminal" />
        </div>
      </div>

      {/* Scroll indicator */}
      <motion.div
        className="absolute bottom-8 flex flex-col items-center gap-1 text-gray-500"
        animate={{ y: [0, 8, 0] }}
        transition={{ duration: 2, repeat: Number.POSITIVE_INFINITY, ease: "easeInOut" }}
      >
        <span className="text-xs tracking-widest uppercase">Scroll</span>
        <svg
          width="20"
          height="20"
          viewBox="0 0 20 20"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M6 8l4 4 4-4" />
        </svg>
      </motion.div>
    </section>
  );
}
