import { useState } from "react";
import DeepDiveLayout from "../components/DeepDiveLayout";
import ScrollReveal from "../components/ScrollReveal";
import CodeBlock from "../components/CodeBlock";
import TerminalSim from "../components/TerminalSim";
import FeatureItem from "../components/FeatureItem";
import GlowBadge from "../components/GlowBadge";
import { features } from "../data/features";

const analyzerFeatures = features.filter((f) => f.category === "analyzers");

const failedGuessLines = [
  { text: "$ agent: What framework is this project using?", color: "text-brand-cyan" },
  { text: "> Checking for Angular... not found", color: "text-red-400", delay: 400 },
  { text: "> Checking for Vue.js... not found", color: "text-red-400", delay: 400 },
  { text: "> Checking for Express... not found", color: "text-red-400", delay: 400 },
  { text: "> Checking for Django... not found", color: "text-red-400", delay: 400 },
  { text: "> Checking for Rails... not found", color: "text-red-400", delay: 400 },
  { text: "> Maybe it's Flask? ...not found", color: "text-red-400", delay: 400 },
  { text: "> ...still guessing after 10 turns", color: "text-yellow-400", delay: 600 },
  { text: "", delay: 200 },
  { text: "# Meanwhile, harness detected FastAPI + SQLAlchemy in 0.3s", color: "text-brand-green", delay: 800 },
];

const createDetectCode = `$ harness create
Scanning project...

  Language:   Python 3.12
  Framework:  FastAPI 0.115
  ORM:        SQLAlchemy 2.0
  Tests:      pytest + pytest-asyncio
  CI:         GitHub Actions
  Structure:  monorepo (3 services)
  API style:  REST (OpenAPI 3.1)

Generated harness_manifest.json (14 analyzers passed)`;

const searchCode = `$ harness search GateRunner --format json
{
  "results": [
    {
      "symbol": "GateRunner",
      "kind": "class",
      "file": "src/gates/runner.py",
      "line": 42,
      "references": 8
    },
    {
      "symbol": "GateRunnerConfig",
      "kind": "interface",
      "file": "src/gates/types.py",
      "line": 15,
      "references": 3
    }
  ]
}`;

const languageTabs = [
  {
    label: "Python",
    code: `Language:   Python 3.12
Framework:  FastAPI 0.115
ORM:        SQLAlchemy 2.0
Tests:      pytest + pytest-asyncio
Package:    pyproject.toml (PEP 621)
Linter:     ruff 0.8.x (189 rules active)
CI:         GitHub Actions
Structure:  monorepo (3 domains detected)
DB:         PostgreSQL (Alembic migrations)
API:        REST via OpenAPI 3.1`,
  },
  {
    label: "TypeScript",
    code: `Language:   TypeScript 5.7
Framework:  Next.js 15 (App Router)
ORM:        Prisma 6.1
Tests:      vitest + @testing-library/react
Package:    package.json (pnpm workspace)
Linter:     biome 1.9 (224 rules active)
CI:         GitHub Actions
Structure:  monorepo (turborepo, 5 packages)
DB:         PostgreSQL (Prisma migrations)
API:        tRPC + REST fallback`,
  },
  {
    label: "Go",
    code: `Language:   Go 1.23
Framework:  Chi v5 (net/http compatible)
ORM:        sqlc + pgx
Tests:      go test + testify
Package:    go.mod (workspace)
Linter:     golangci-lint 1.62 (38 linters)
CI:         GitLab CI
Structure:  monorepo (cmd/ + internal/)
DB:         PostgreSQL (golang-migrate)
API:        REST (OpenAPI generated)`,
  },
  {
    label: "Rust",
    code: `Language:   Rust 1.83 (2024 edition)
Framework:  Axum 0.8
ORM:        SQLx 0.8 (compile-time checked)
Tests:      cargo test + proptest
Package:    Cargo.toml (workspace)
Linter:     clippy (all warnings denied)
CI:         GitHub Actions
Structure:  workspace (6 crates)
DB:         PostgreSQL (sqlx migrations)
API:        REST via utoipa (OpenAPI)`,
  },
  {
    label: "Java",
    code: `Language:   Java 21 (LTS)
Framework:  Spring Boot 3.4
ORM:        Spring Data JPA + Hibernate 6
Tests:      JUnit 5 + Mockito + Testcontainers
Package:    Maven (multi-module POM)
Linter:     Checkstyle + SpotBugs
CI:         Jenkins Pipeline
Structure:  multi-module (7 modules)
DB:         PostgreSQL (Flyway migrations)
API:        REST (SpringDoc OpenAPI)`,
  },
  {
    label: "C#",
    code: `Language:   C# 12 (.NET 9)
Framework:  ASP.NET Core Minimal APIs
ORM:        Entity Framework Core 9
Tests:      xUnit + NSubstitute + Verify
Package:    Directory.Build.props (solution)
Linter:     dotnet format + Roslyn analyzers
CI:         Azure Pipelines
Structure:  solution (Clean Architecture)
DB:         SQL Server (EF migrations)
API:        REST (Swashbuckle OpenAPI)`,
  },
];

export default function AnalyzersPage() {
  const [activeTab, setActiveTab] = useState(0);

  const handleTabKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>, idx: number) => {
    let next = idx;
    if (e.key === "ArrowRight") next = (idx + 1) % languageTabs.length;
    else if (e.key === "ArrowLeft") next = (idx - 1 + languageTabs.length) % languageTabs.length;
    else return;
    e.preventDefault();
    setActiveTab(next);
    const btn = document.querySelector<HTMLButtonElement>(`[data-tab-idx="${next}"]`);
    btn?.focus();
  };

  return (
    <DeepDiveLayout categoryId="analyzers">
      {/* Act 1: The Problem */}
      <section className="mb-20">
        <ScrollReveal>
          <GlowBadge text="The Problem" color="purple" />
          <h2 className="text-2xl font-bold text-white mt-4 mb-3">
            Agents waste their first 10 turns guessing your stack
          </h2>
          <p className="text-gray-400 mb-8 max-w-2xl">
            Without codebase analysis, AI agents spend their initial context window
            probing for languages, frameworks, and project structure -- burning tokens
            and time before doing any real work.
          </p>
        </ScrollReveal>
        <ScrollReveal delay={0.2}>
          <TerminalSim lines={failedGuessLines} title="agent-session.log" />
        </ScrollReveal>
      </section>

      {/* Act 2: The Solution */}
      <section className="mb-20">
        <ScrollReveal>
          <GlowBadge text="The Solution" color="cyan" />
          <h2 className="text-2xl font-bold text-white mt-4 mb-3">
            14 analyzers detect everything in one pass
          </h2>
          <p className="text-gray-400 mb-8 max-w-2xl">
            Harness runs 14 targeted analyzers that inspect package files, AST structure,
            directory layout, and config files to build a complete project manifest
            in under a second.
          </p>
        </ScrollReveal>

        <div className="grid gap-3 mb-8">
          {analyzerFeatures.map((f) => (
            <div key={f.id} id={f.id}>
              <FeatureItem feature={f} />
            </div>
          ))}
        </div>

        <ScrollReveal delay={0.1}>
          <div className="space-y-6">
            <CodeBlock code={createDetectCode} lang="bash" filename="harness create" />
            <CodeBlock code={searchCode} lang="json" filename="harness search" />
          </div>
        </ScrollReveal>
      </section>

      {/* Act 3: See It In Action */}
      <section className="mb-20">
        <ScrollReveal>
          <GlowBadge text="See It In Action" color="green" />
          <h2 className="text-2xl font-bold text-white mt-4 mb-6">
            Detection output across 6 languages
          </h2>
        </ScrollReveal>

        <ScrollReveal delay={0.1}>
          <div
            className="glass rounded-lg overflow-hidden"
            role="tablist"
            aria-label="Language detection examples"
          >
            {/* Tab buttons */}
            <div className="flex border-b border-surface-border overflow-x-auto">
              {languageTabs.map((tab, idx) => (
                <button
                  key={tab.label}
                  type="button"
                  role="tab"
                  data-tab-idx={idx}
                  aria-selected={activeTab === idx}
                  tabIndex={activeTab === idx ? 0 : -1}
                  onClick={() => setActiveTab(idx)}
                  onKeyDown={(e) => handleTabKeyDown(e, idx)}
                  className={`px-4 py-3 text-sm font-medium whitespace-nowrap transition-colors focus-visible:ring-2 focus-visible:ring-brand-cyan focus-visible:outline-none ${
                    activeTab === idx
                      ? "text-brand-cyan border-b-2 border-brand-cyan bg-white/5"
                      : "text-gray-500 hover:text-gray-300 hover:bg-white/5"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Tab panel */}
            <div role="tabpanel" aria-label={languageTabs[activeTab].label} className="p-0">
              <CodeBlock
                code={languageTabs[activeTab].code}
                lang="yaml"
                filename={`harness_manifest.json — ${languageTabs[activeTab].label} project`}
              />
            </div>
          </div>
        </ScrollReveal>
      </section>
    </DeepDiveLayout>
  );
}
