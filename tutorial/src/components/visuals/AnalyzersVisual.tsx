import { motion } from "motion/react";

const languages = [
  { name: "Python", color: "#3572A5" },
  { name: "TypeScript", color: "#3178C6" },
  { name: "Go", color: "#00ADD8" },
  { name: "Rust", color: "#DEA584" },
  { name: "Java", color: "#B07219" },
  { name: "C#", color: "#178600" },
];

export default function AnalyzersVisual() {
  return (
    <div className="grid grid-cols-2 gap-3 p-4">
      {languages.map((lang, i) => (
        <motion.div
          key={lang.name}
          className="flex items-center gap-2 rounded-lg border border-surface-border bg-surface-card/50 px-3 py-2"
          initial={{ opacity: 0, y: 10 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.4, delay: i * 0.08 }}
        >
          <span
            className="inline-block h-2.5 w-2.5 rounded-full"
            style={{ backgroundColor: lang.color }}
          />
          <span className="text-sm text-gray-300">{lang.name}</span>
        </motion.div>
      ))}
    </div>
  );
}
