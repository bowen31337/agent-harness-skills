import { motion } from "motion/react";

const gates = [
  { name: "coverage", pct: 92, color: "#4ade80" },
  { name: "types", pct: 100, color: "#22d3ee" },
  { name: "security", pct: 100, color: "#a855f7" },
  { name: "principles", pct: 85, color: "#facc15" },
  { name: "docs", pct: 78, color: "#f97316" },
];

export default function GatesVisual() {
  return (
    <div className="flex flex-col gap-2.5 p-4">
      {gates.map((g, i) => (
        <div key={g.name} className="flex items-center gap-2">
          <span className="w-20 text-right text-xs font-mono text-gray-400">{g.name}</span>
          <div className="flex-1 h-3 rounded-full bg-surface-card overflow-hidden">
            <motion.div
              className="h-full rounded-full"
              style={{ backgroundColor: g.color }}
              initial={{ width: 0 }}
              whileInView={{ width: `${g.pct}%` }}
              viewport={{ once: true }}
              transition={{ duration: 0.8, delay: i * 0.1, ease: "easeOut" }}
            />
          </div>
          <span className="w-8 text-xs font-mono text-gray-500">{g.pct}%</span>
        </div>
      ))}
    </div>
  );
}
