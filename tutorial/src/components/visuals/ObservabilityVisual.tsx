import { motion } from "motion/react";

const logLines = [
  { level: "INFO", color: "text-green-400", msg: '{"svc":"api","trace":"a3f1","msg":"boot ok","ms":42}' },
  { level: "INFO", color: "text-green-400", msg: '{"svc":"api","trace":"a3f1","msg":"health check passed"}' },
  { level: "WARN", color: "text-yellow-400", msg: '{"svc":"worker","trace":"b7c2","msg":"retry 2/3"}' },
  { level: "ERROR", color: "text-red-400", msg: '{"svc":"worker","trace":"b7c2","msg":"timeout","code":504}' },
  { level: "INFO", color: "text-green-400", msg: '{"svc":"api","trace":"d9e4","msg":"req /users","ms":18}' },
];

export default function ObservabilityVisual() {
  return (
    <div className="rounded-lg border border-surface-border bg-surface-card/60 p-3 font-mono text-[10px] leading-relaxed overflow-hidden">
      {logLines.map((line, i) => (
        <motion.div
          key={i}
          className="whitespace-nowrap"
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 0.9 }}
          viewport={{ once: true }}
          transition={{ duration: 0.4, delay: i * 0.12 }}
        >
          <span className={line.color}>[{line.level}]</span>{" "}
          <span className="text-gray-500">{line.msg}</span>
        </motion.div>
      ))}
    </div>
  );
}
