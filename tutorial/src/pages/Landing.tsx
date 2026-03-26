import { Link } from "react-router-dom";
import Hero from "../components/Hero";
import CategoryCard from "../components/CategoryCard";
import { categories } from "../data/features";
import AnalyzersVisual from "../components/visuals/AnalyzersVisual";
import AgentsMdVisual from "../components/visuals/AgentsMdVisual";
import ArchitectureVisual from "../components/visuals/ArchitectureVisual";
import PrinciplesVisual from "../components/visuals/PrinciplesVisual";
import GatesVisual from "../components/visuals/GatesVisual";
import ObservabilityVisual from "../components/visuals/ObservabilityVisual";
import ExecPlansVisual from "../components/visuals/ExecPlansVisual";
import CliVisual from "../components/visuals/CliVisual";

const visuals: Record<string, React.ReactNode> = {
  analyzers: <AnalyzersVisual />,
  "agents-md": <AgentsMdVisual />,
  architecture: <ArchitectureVisual />,
  principles: <PrinciplesVisual />,
  gates: <GatesVisual />,
  observability: <ObservabilityVisual />,
  "exec-plans": <ExecPlansVisual />,
  cli: <CliVisual />,
};

export default function Landing() {
  return (
    <div>
      <Hero />

      {/* Category scroll sections */}
      <section className="max-w-6xl mx-auto px-6 py-20 space-y-32">
        {categories.map((cat, i) => (
          <CategoryCard key={cat.id} category={cat} visual={visuals[cat.id]} index={i} />
        ))}
      </section>

      {/* Bottom CTA */}
      <section className="max-w-4xl mx-auto px-6 py-20 text-center">
        <h2 className="text-3xl font-bold gradient-text mb-6">Get Started</h2>
        <div className="glass rounded-lg p-6 inline-block">
          <code className="text-brand-cyan font-mono">uv add agent-harness-skills</code>
        </div>
        <div className="mt-8 flex gap-4 justify-center">
          <a
            href="https://github.com/bowen31337/agent-harness-skills"
            className="text-brand-purple hover:underline"
            target="_blank"
            rel="noopener noreferrer"
          >
            GitHub {"\u2192"}
          </a>
          <Link to="/analyzers" className="text-brand-cyan hover:underline">
            Documentation {"\u2192"}
          </Link>
        </div>
      </section>
    </div>
  );
}
