import type { Feature } from "../data/features";
import ScrollReveal from "./ScrollReveal";

interface FeatureItemProps {
  feature: Feature;
}

export default function FeatureItem({ feature }: FeatureItemProps) {
  return (
    <ScrollReveal>
      <div className="glass rounded-lg p-4 space-y-2">
        <p className="text-sm text-gray-300 leading-relaxed">{feature.description}</p>
        <span className="inline-block text-[10px] font-mono text-gray-600">{feature.id}</span>
      </div>
    </ScrollReveal>
  );
}
