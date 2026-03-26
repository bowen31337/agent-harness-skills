import { motion } from "motion/react";

const tiers = [
  { label: "Root Overview", tier: "L0", gradient: "from-purple-500/40 to-purple-900/20" },
  { label: "Domain Docs", tier: "L1", gradient: "from-cyan-500/40 to-cyan-900/20" },
  { label: "File-Level", tier: "L2", gradient: "from-green-500/40 to-green-900/20" },
];

export default function AgentsMdVisual() {
  return (
    <div className="relative flex flex-col items-center py-4 px-2">
      {tiers.map((t, i) => (
        <motion.div
          key={t.tier}
          className={`relative w-full max-w-[220px] rounded-lg border border-surface-border bg-gradient-to-br ${t.gradient} px-4 py-3`}
          style={{ marginTop: i === 0 ? 0 : -8, zIndex: tiers.length - i }}
          initial={{ opacity: 0, x: i * 12 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5, delay: i * 0.15 }}
        >
          <span className="text-[10px] font-mono text-gray-500">{t.tier}</span>
          <p className="text-sm font-medium text-gray-200">{t.label}</p>
        </motion.div>
      ))}
    </div>
  );
}
