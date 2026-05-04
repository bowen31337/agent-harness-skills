# Tutorial Showcase Site Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an animated, interactive tutorial showcase site for harness-skills in `tutorial/` subfolder, deployed to GitHub Pages.

**Architecture:** React 19 SPA with hybrid page structure — GSAP-animated landing page with 8 category scroll sections, plus 8 deep-dive pages with interactive walkthroughs. Dark gradient glow theme. Tailwind v4 CSS-first config.

**Tech Stack:** React 19, TypeScript, Vite, Tailwind CSS v4, Motion.dev, GSAP, Shiki, Biome, Vitest

**Spec:** `docs/superpowers/specs/2026-03-26-tutorial-site-design.md`

---

## File Map

```
tutorial/
├── index.html                          # Vite HTML entry
├── package.json                        # Dependencies + scripts
├── biome.json                          # Biome lint/format config
├── vite.config.ts                      # Vite config (base path for GH Pages)
├── tsconfig.json                       # TypeScript strict config
├── public/
│   ├── favicon.svg                     # Site favicon
│   └── 404.html                        # SPA redirect for GitHub Pages
├── src/
│   ├── main.tsx                        # Entry: renders App, SPA redirect handler
│   ├── App.tsx                         # Router + Suspense + ErrorBoundary
│   ├── index.css                       # Tailwind v4 @theme + glow utilities
│   ├── data/
│   │   └── features.ts                 # 129 features + 8 categories as typed data
│   ├── hooks/
│   │   └── useScrollAnimation.ts       # GSAP ScrollTrigger reusable hook
│   ├── components/
│   │   ├── Layout.tsx                  # Dark shell: animated bg + Navbar + Outlet
│   │   ├── Navbar.tsx                  # Sticky nav with category links + mobile menu
│   │   ├── Hero.tsx                    # GSAP text reveal + terminal sim
│   │   ├── TerminalSim.tsx             # Animated terminal output (GSAP timeline)
│   │   ├── CodeBlock.tsx               # Shiki syntax highlighting
│   │   ├── ScrollReveal.tsx            # Motion.dev scroll-triggered wrapper
│   │   ├── CategoryCard.tsx            # Landing scroll section card
│   │   ├── FeatureItem.tsx             # Feature card with reveal animation
│   │   ├── GlowBadge.tsx              # Gradient-bordered count badge
│   │   ├── LoadingFallback.tsx         # Suspense spinner/skeleton
│   │   └── ErrorBoundary.tsx           # Catches render errors
│   └── pages/
│       ├── Landing.tsx                 # Hero + 8 category scroll sections + CTA
│       ├── AnalyzersPage.tsx           # Cat 1 deep-dive
│       ├── AgentsMdPage.tsx            # Cat 2 deep-dive
│       ├── ArchitecturePage.tsx        # Cat 3 deep-dive
│       ├── PrinciplesPage.tsx          # Cat 4 deep-dive
│       ├── GatesPage.tsx               # Cat 5 deep-dive
│       ├── ObservabilityPage.tsx       # Cat 6 deep-dive
│       ├── ExecPlansPage.tsx           # Cat 7 deep-dive
│       └── CliPage.tsx                 # Cat 8 deep-dive
└── tests/
    ├── data.test.ts                    # Verify 129 features, 8 categories
    └── components.test.tsx             # Component rendering smoke tests
```

Also creates:
- `.github/workflows/deploy-tutorial.yml` — GitHub Actions deployment
- `.gitignore` update — add `.superpowers/` if not present

---

### Task 1: Scaffold Vite + React + TypeScript project

**Files:**
- Create: `tutorial/package.json`
- Create: `tutorial/index.html`
- Create: `tutorial/vite.config.ts`
- Create: `tutorial/tsconfig.json`
- Create: `tutorial/biome.json`
- Create: `tutorial/src/main.tsx`
- Create: `tutorial/src/index.css`
- Create: `tutorial/src/App.tsx`
- Create: `tutorial/public/favicon.svg`
- Create: `tutorial/public/404.html`

- [ ] **Step 1: Create `tutorial/package.json`**

```json
{
  "name": "harness-skills-tutorial",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest",
    "lint": "biome check .",
    "format": "biome format --write ."
  },
  "dependencies": {
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "react-router-dom": "^7.0.0",
    "motion": "^12.0.0",
    "gsap": "^3.12.0",
    "@gsap/react": "^2.1.0",
    "shiki": "^3.0.0"
  },
  "devDependencies": {
    "@biomejs/biome": "^1.9.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "@tailwindcss/vite": "^4.0.0",
    "@testing-library/react": "^16.0.0",
    "@vitejs/plugin-react": "^4.3.0",
    "tailwindcss": "^4.0.0",
    "typescript": "^5.6.0",
    "vite": "^6.0.0",
    "vitest": "^3.0.0",
    "jsdom": "^25.0.0"
  }
}
```

- [ ] **Step 2: Create `tutorial/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Harness Skills — Agent Harness Engineering Toolkit</title>
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
  </head>
  <body class="bg-surface text-white antialiased">
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 3: Create `tutorial/vite.config.ts`**

```typescript
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  base: "/agent-harness-skills/",
  plugins: [react(), tailwindcss()],
  build: {
    target: "esnext",
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: [],
  },
});
```

- [ ] **Step 4: Create `tutorial/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "skipLibCheck": true,
    "isolatedModules": true,
    "esModuleInterop": true,
    "resolveJsonModule": true,
    "allowImportingTsExtensions": true,
    "noEmit": true
  },
  "include": ["src", "tests", "scripts"]
}
```

- [ ] **Step 5: Create `tutorial/biome.json`**

```json
{
  "$schema": "https://biomejs.dev/schemas/1.9.0/schema.json",
  "organizeImports": { "enabled": true },
  "linter": {
    "enabled": true,
    "rules": { "recommended": true }
  },
  "formatter": {
    "enabled": true,
    "indentStyle": "tab",
    "lineWidth": 100
  },
  "javascript": {
    "formatter": { "quoteStyle": "double" }
  }
}
```

- [ ] **Step 6: Create `tutorial/src/index.css`**

```css
@import "tailwindcss";

@theme {
  --color-brand-purple: #a855f7;
  --color-brand-cyan: #22d3ee;
  --color-brand-green: #4ade80;
  --color-surface: #0c0a1a;
  --color-surface-raised: #1a1035;
  --color-surface-border: rgba(168, 85, 247, 0.15);
}

html {
  scroll-behavior: smooth;
}

body {
  background-color: var(--color-surface);
}

.glow-purple { box-shadow: 0 0 20px rgba(168, 85, 247, 0.3); }
.glow-cyan { box-shadow: 0 0 20px rgba(34, 211, 238, 0.3); }
.glow-green { box-shadow: 0 0 20px rgba(74, 222, 128, 0.3); }

.glass {
  backdrop-filter: blur(12px);
  background: rgba(26, 16, 53, 0.6);
  border: 1px solid var(--color-surface-border);
}

.gradient-text {
  background: linear-gradient(135deg, var(--color-brand-purple), var(--color-brand-cyan), var(--color-brand-green));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

- [ ] **Step 7: Create `tutorial/src/main.tsx`**

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./index.css";

const basename = "/agent-harness-skills";

// SPA redirect: restore path from ?p= query param (set by 404.html)
const params = new URLSearchParams(window.location.search);
const redirectPath = params.get("p");
if (redirectPath) {
  window.history.replaceState(null, "", `${basename}/${redirectPath}`);
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter basename={basename}>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
```

- [ ] **Step 8: Create `tutorial/src/App.tsx` (minimal shell)**

```tsx
import { Route, Routes } from "react-router-dom";

function Placeholder({ name }: { name: string }) {
  return <div className="min-h-screen flex items-center justify-center text-white text-2xl">{name}</div>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Placeholder name="Landing — coming soon" />} />
      <Route path="*" element={<Placeholder name="404 — Page not found" />} />
    </Routes>
  );
}
```

- [ ] **Step 9: Create `tutorial/public/favicon.svg`**

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
  <defs>
    <linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#a855f7"/>
      <stop offset="50%" stop-color="#22d3ee"/>
      <stop offset="100%" stop-color="#4ade80"/>
    </linearGradient>
  </defs>
  <rect width="32" height="32" rx="6" fill="#0c0a1a"/>
  <text x="16" y="23" text-anchor="middle" font-size="18" font-weight="bold" fill="url(#g)" font-family="monospace">H</text>
</svg>
```

- [ ] **Step 10: Create `tutorial/public/404.html`**

```html
<!DOCTYPE html>
<html>
<head>
  <script>
    var path = window.location.pathname;
    window.location.replace(
      window.location.origin + '/agent-harness-skills/?p=' +
      encodeURIComponent(path.replace('/agent-harness-skills/', ''))
    );
  </script>
</head>
</html>
```

- [ ] **Step 11: Install dependencies and verify dev server starts**

```bash
cd tutorial && npm install && npm run dev
```

Expected: Vite dev server starts, browser shows "Landing — coming soon" on dark background.

- [ ] **Step 12: Commit**

```bash
git add tutorial/
git commit -m "feat(tutorial): scaffold Vite + React + Tailwind v4 + Biome project"
```

---

### Task 2: Data layer — features.ts with all 129 features

**Files:**
- Create: `tutorial/src/data/features.ts`
- Create: `tutorial/tests/data.test.ts`

- [ ] **Step 1: Write the data test**

```typescript
import { describe, expect, it } from "vitest";
import { categories, features } from "../src/data/features";

describe("features data", () => {
  it("has exactly 129 features", () => {
    expect(features).toHaveLength(129);
  });

  it("has exactly 8 categories", () => {
    expect(categories).toHaveLength(8);
  });

  it("every feature belongs to a valid category", () => {
    const categoryIds = new Set(categories.map((c) => c.id));
    for (const f of features) {
      expect(categoryIds.has(f.category)).toBe(true);
    }
  });

  it("category feature counts match", () => {
    for (const cat of categories) {
      const count = features.filter((f) => f.category === cat.id).length;
      expect(count).toBe(cat.featureCount);
    }
  });

  it("every feature has a non-empty description", () => {
    for (const f of features) {
      expect(f.description.length).toBeGreaterThan(0);
    }
  });
});
```

- [ ] **Step 2: Run test — verify it fails**

```bash
cd tutorial && npx vitest run tests/data.test.ts
```

Expected: FAIL — `features` module not found.

- [ ] **Step 3: Create `tutorial/src/data/features.ts`**

Write the complete typed data file with:
- `CategoryId` union type (8 values)
- `Feature` interface (`id`, `description`, `category`)
- `Category` interface (`id`, `name`, `featureCount`, `color`, `icon`, `description`, `features` computed, `route`)
- `features` array: all 129 features extracted from `spec/app_spec.txt` lines 151-298
- `categories` array: 8 categories with correct feature counts. Count by parsing spec lines 150-299 — each `- Skill ...` or `- Each ...` or `- Execution plan ...` or `- All CLI ...` or `- CLI ...` line is one feature:
  - `analyzers` (14), `agents-md` (16), `architecture` (19), `principles` (13), `gates` (15), `observability` (17), `exec-plans` (18), `cli` (16) — total 128.
  - The spec header says "Features: 129" — the 129th feature is the `--then` composition line (spec line 298) which is part of the `cli` category, making cli=17, total=129. Count carefully when authoring.
- Color assignments: analyzers=purple, agents-md=cyan, architecture=green, principles=yellow, gates=blue, observability=orange, exec-plans=pink, cli=indigo

The `features` array must be manually authored from the spec. Each feature `id` follows `F{spec_line}` (e.g., `F151`). Each `description` is the spec bullet text (cleaned up, no XML entities).

- [ ] **Step 4: Run test — verify it passes**

```bash
cd tutorial && npx vitest run tests/data.test.ts
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tutorial/src/data/ tutorial/tests/
git commit -m "feat(tutorial): add typed features data layer (129 features, 8 categories)"
```

---

### Task 3: Shared components — Layout, Navbar, utility components

**Files:**
- Create: `tutorial/src/components/Layout.tsx`
- Create: `tutorial/src/components/Navbar.tsx`
- Create: `tutorial/src/components/GlowBadge.tsx`
- Create: `tutorial/src/components/ScrollReveal.tsx`
- Create: `tutorial/src/components/LoadingFallback.tsx`
- Create: `tutorial/src/components/ErrorBoundary.tsx`
- Create: `tutorial/src/hooks/useScrollAnimation.ts`
- Modify: `tutorial/src/App.tsx`

- [ ] **Step 1: Create `ErrorBoundary.tsx`**

React class component that catches render errors, shows a "Something went wrong" message with a retry button. Dark-themed to match the site.

- [ ] **Step 2: Create `LoadingFallback.tsx`**

Simple centered spinner/pulse animation using Tailwind's `animate-pulse`. Shows "Loading..." text with the gradient-text class.

- [ ] **Step 3: Create `GlowBadge.tsx`**

Props: `text: string`, `color: 'purple' | 'cyan' | 'green'`. Renders a pill badge with gradient border and glow effect. Uses the `.glow-{color}` utilities.

- [ ] **Step 4: Create `ScrollReveal.tsx`**

Wraps children in a Motion.dev `motion.div` with `initial={{ opacity: 0, y: 40 }}`, `whileInView={{ opacity: 1, y: 0 }}`, `viewport={{ once: true, margin: "-100px" }}`. Respects `prefers-reduced-motion` via a `useReducedMotion()` check.

**Note:** Motion.dev v12 uses `motion/react` import path, NOT `framer-motion`:
```tsx
import { motion, useReducedMotion } from "motion/react";
```

- [ ] **Step 5: Create `useScrollAnimation.ts` hook**

Wraps GSAP `useGSAP` + `ScrollTrigger.create()`. Takes a ref and animation config, returns cleanup. Skips animation when `prefers-reduced-motion` is set.

**Important:** Must register GSAP plugins at module scope:
```typescript
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);
```
This registration is required for all scroll animations to work. Without it, ScrollTrigger silently fails.

- [ ] **Step 6: Create `Navbar.tsx`**

Sticky top nav with: logo text "harness-skills" (gradient), category links as horizontal list (desktop), hamburger menu (mobile). Uses `glass` class for backdrop blur. Links use `react-router-dom` `NavLink` with active state highlighting.

- [ ] **Step 7: Create `Layout.tsx`**

Renders: animated dark background (subtle grid pattern via CSS), `<Navbar />`, `<Outlet />` from react-router. The background uses a CSS grid pattern animated with a subtle GSAP opacity pulse.

**Accessibility: focus management on route change.** Use `useLocation` + `useEffect` to move focus to the main content area (`<main>` with `tabIndex={-1}`) whenever the route changes. This ensures screen readers announce the new page content:

```tsx
const location = useLocation();
const mainRef = useRef<HTMLElement>(null);
useEffect(() => { mainRef.current?.focus(); }, [location.pathname]);
```

- [ ] **Step 8: Create stub page files for all 8 categories**

Each stub is a minimal placeholder so lazy imports resolve without errors. Create 8 files in `tutorial/src/pages/`:

```tsx
// AnalyzersPage.tsx (and same pattern for all 8)
export default function AnalyzersPage() {
  return <div className="min-h-screen p-8 text-white"><h1>Codebase Analysis & Detection</h1><p>Coming soon...</p></div>;
}
```

Files to create: `AnalyzersPage.tsx`, `AgentsMdPage.tsx`, `ArchitecturePage.tsx`, `PrinciplesPage.tsx`, `GatesPage.tsx`, `ObservabilityPage.tsx`, `ExecPlansPage.tsx`, `CliPage.tsx`.

- [ ] **Step 9: Update `App.tsx` to use Layout + lazy-loaded pages**

```tsx
import { Suspense, lazy } from "react";
import { Route, Routes, useLocation } from "react-router-dom";
import { AnimatePresence } from "motion/react";
import ErrorBoundary from "./components/ErrorBoundary";
import Layout from "./components/Layout";
import LoadingFallback from "./components/LoadingFallback";

const Landing = lazy(() => import("./pages/Landing"));
const AnalyzersPage = lazy(() => import("./pages/AnalyzersPage"));
const AgentsMdPage = lazy(() => import("./pages/AgentsMdPage"));
const ArchitecturePage = lazy(() => import("./pages/ArchitecturePage"));
const PrinciplesPage = lazy(() => import("./pages/PrinciplesPage"));
const GatesPage = lazy(() => import("./pages/GatesPage"));
const ObservabilityPage = lazy(() => import("./pages/ObservabilityPage"));
const ExecPlansPage = lazy(() => import("./pages/ExecPlansPage"));
const CliPage = lazy(() => import("./pages/CliPage"));

function NotFound() {
  return <div className="min-h-screen flex items-center justify-center text-white text-2xl">404 — Page not found</div>;
}

export default function App() {
  return (
    <ErrorBoundary>
      <Suspense fallback={<LoadingFallback />}>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Landing />} />
            <Route path="analyzers" element={<AnalyzersPage />} />
            <Route path="agents-md" element={<AgentsMdPage />} />
            <Route path="architecture" element={<ArchitecturePage />} />
            <Route path="principles" element={<PrinciplesPage />} />
            <Route path="gates" element={<GatesPage />} />
            <Route path="observability" element={<ObservabilityPage />} />
            <Route path="exec-plans" element={<ExecPlansPage />} />
            <Route path="cli" element={<CliPage />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </Suspense>
    </ErrorBoundary>
  );
}
```

- [ ] **Step 9: Verify dev server renders Layout with Navbar**

```bash
cd tutorial && npm run dev
```

Expected: dark background, sticky navbar, "Landing — coming soon" placeholder.

- [ ] **Step 10: Commit**

```bash
git add tutorial/src/
git commit -m "feat(tutorial): add Layout, Navbar, utility components, lazy routing"
```

---

### Task 4: Hero section with GSAP animations

**Files:**
- Create: `tutorial/src/components/Hero.tsx`
- Create: `tutorial/src/components/TerminalSim.tsx`

- [ ] **Step 1: Create `TerminalSim.tsx`**

Props: `lines: { text: string; color?: string; delay?: number }[]`. Uses GSAP timeline to type out each line character-by-character in a simulated terminal window. Terminal has: dark rounded container, green/cyan/red dots in the header bar, monospace font, `aria-live="polite"` for accessibility. Respects `prefers-reduced-motion` — shows all lines instantly.

- [ ] **Step 2: Create `Hero.tsx`**

Full-viewport section with:
- Animated grid background (CSS `background-image` with grid lines, GSAP opacity pulse)
- `harness-skills` title using `gradient-text` class, revealed with GSAP `fromTo` (clipPath or y-translate)
- Subtitle `129 features · 8 categories · 17 commands` — staggered word fade-in via GSAP timeline
- `<TerminalSim>` below with lines:
  ```
  $ harness create --profile standard
  ✓ harness.config.yaml created (profile: standard)
  $ harness lint
  ✓ architecture: passed  ✓ principles: passed
  $ harness evaluate --format json
  ✓ coverage: 92%  ✓ types: passed  ✓ security: clean
  ```
- Floating glow orbs: 2-3 absolutely positioned divs with radial gradients, animated with Motion.dev `animate` (slow x/y drift)

- [ ] **Step 3: Create placeholder `Landing.tsx`**

Renders `<Hero />` plus a spacer div so the page scrolls. Verify Hero animations play.

- [ ] **Step 4: Test in browser**

```bash
cd tutorial && npm run dev
```

Expected: hero text animates in, terminal types out, glow orbs float. On `prefers-reduced-motion`: everything appears instantly.

- [ ] **Step 5: Commit**

```bash
git add tutorial/src/
git commit -m "feat(tutorial): add Hero with GSAP text reveal + TerminalSim"
```

---

### Task 5: CodeBlock component with Shiki

**Files:**
- Create: `tutorial/src/components/CodeBlock.tsx`

- [ ] **Step 1: Create `CodeBlock.tsx`**

Props: `code: string`, `lang: string`, `filename?: string`. Uses Shiki with `createHighlighter` (lazy-initialized, cached). Theme: `vitesse-dark` or `github-dark`. Renders highlighted HTML in a dark rounded container with optional filename tab. Includes a "Copy" button. Uses `role="code"` for accessibility.

Since Shiki is async, use `useState` + `useEffect` to load the highlighter on mount, showing a plain `<pre>` fallback until ready.

- [ ] **Step 2: Verify rendering**

Add a test CodeBlock to Landing.tsx temporarily:

```tsx
<CodeBlock code="harness evaluate --format json" lang="bash" filename="terminal" />
```

Expected: syntax-highlighted code block with dark theme.

- [ ] **Step 3: Commit**

```bash
git add tutorial/src/components/CodeBlock.tsx
git commit -m "feat(tutorial): add CodeBlock with Shiki syntax highlighting"
```

---

### Task 6: CategoryCard + Landing page scroll sections

**Files:**
- Create: `tutorial/src/components/CategoryCard.tsx`
- Create: `tutorial/src/components/FeatureItem.tsx`
- Modify: `tutorial/src/pages/Landing.tsx`

- [ ] **Step 1: Create `CategoryCard.tsx`**

Props: `category: Category`, `visual: ReactNode`, `index: number`. Two-column layout (text left, visual right). Uses `useScrollAnimation` hook for GSAP ScrollTrigger entrance (slide in from left/right alternating based on index). Contains: category name (h2), description, `GlowBadge` with feature count, "Deep dive →" `Link`.

- [ ] **Step 2: Create `FeatureItem.tsx`**

Props: `feature: Feature`. Small card with feature description wrapped in `ScrollReveal`. Used in deep-dive pages (built now for reuse).

- [ ] **Step 3: Create category-specific visual components**

For each of the 8 categories, create a small inline visual component within `Landing.tsx` (or extract to `components/visuals/`):

1. **Analyzers**: 6 language icon circles arranged in a ring, rotating slowly (GSAP rotation)
2. **AGENTS.md**: Three stacked document cards (L0, L1, L2) with z-offset, zooming on scroll
3. **Architecture**: Horizontal layer bars stacking up one by one (types → config → repo → service → runtime → ui)
4. **Principles**: Two code blocks side by side — "before" (red highlight) → "after" (green highlight)
5. **Gates**: Vertical list of gate names with progress bars that fill to different percentages
6. **Observability**: Scrolling log lines in a mini terminal (colored by level)
7. **Exec Plans**: Nodes (circles) with connecting lines that draw in via GSAP `drawSVG` or stroke-dashoffset
8. **CLI**: Mini terminal showing `--then` chaining with pipeline arrow animations

Each visual is ~30-60 lines. Keep them focused — they're teasers, not full demos.

- [ ] **Step 4: Build full `Landing.tsx`**

Compose: `<Hero />`, then 8x `<CategoryCard>` with data from `categories` array + matching visual component, then a bottom CTA section with copyable install command and GitHub/docs links.

- [ ] **Step 5: Test scroll animations in browser**

```bash
cd tutorial && npm run dev
```

Expected: scrolling reveals each category section with slide-in animation. Each visual element animates. "Deep dive →" links navigate to placeholder pages.

- [ ] **Step 6: Commit**

```bash
git add tutorial/src/
git commit -m "feat(tutorial): add Landing page with 8 scroll-animated category sections"
```

---

### Task 7: Deep-dive page template + first 4 category pages

**Files:**
- Create: `tutorial/src/pages/AnalyzersPage.tsx`
- Create: `tutorial/src/pages/AgentsMdPage.tsx`
- Create: `tutorial/src/pages/ArchitecturePage.tsx`
- Create: `tutorial/src/pages/PrinciplesPage.tsx`

- [ ] **Step 1: Build reusable deep-dive page layout**

Create a shared layout pattern (either a component or just a consistent structure) for deep-dive pages:
- Sticky sidebar (desktop): lists feature names from the category, highlights current on scroll via Intersection Observer
- Mobile: sidebar collapses to a dropdown at top
- Main content: 3-act walkthrough structure

**Accessibility: keyboard navigation for all interactive demos.** All interactive elements (tabs, toggles, clickable diagram nodes) must be keyboard-operable:
- Use `<button>` or `role="tab"` with `tabIndex={0}` for clickable items
- Arrow keys navigate between tabs/options
- Enter/Space activates the focused element
- Visible focus ring (Tailwind `focus-visible:ring-2 focus-visible:ring-brand-cyan`)

- [ ] **Step 2: Build `AnalyzersPage.tsx`**

**The Problem:** "Agents waste turns guessing your stack." Show a confused-agent terminal animation.
**The Solution:** Features F151-F164 as scroll-reveal cards with code examples:
- `harness create` detecting Python + FastAPI
- Symbol index lookup via `harness search`
**See It In Action:** Tab component switching between Python/TS/Go/Rust/Java/C# analysis output in `TerminalSim` components.

- [ ] **Step 3: Build `AgentsMdPage.tsx`**

**The Problem:** "Agents load everything or nothing." Show a bloated context dump.
**The Solution:** Features F167-F182 with tiered loading demo.
**See It In Action:** Interactive AGENTS.md preview — click L0/L1/L2 tabs to see different detail levels expanding.

- [ ] **Step 4: Build `ArchitecturePage.tsx`**

**The Problem:** "Import spaghetti." Show tangled dependency lines.
**The Solution:** Features F186-F204 with layer diagrams.
**See It In Action:** Interactive layer diagram — click a layer to highlight what it can/cannot import. Built with divs + CSS, animated with Motion.dev layout transitions.

- [ ] **Step 5: Build `PrinciplesPage.tsx`**

**The Problem:** "Same code review comments, every PR." Show repeated review comments.
**The Solution:** Features F208-F220 with scanner examples.
**See It In Action:** Code sample with toggleable violations — click to enable/disable P011 (magic numbers), P018 (hardcoded strings) scanners. Violations highlight in-line.

- [ ] **Step 6: Verify all 4 pages render and navigate correctly**

```bash
cd tutorial && npm run dev
```

Test: landing → click "Deep dive" → page loads with sidebar + content + interactive demo. Back button works.

- [ ] **Step 7: Commit**

```bash
git add tutorial/src/pages/
git commit -m "feat(tutorial): add deep-dive pages for Analyzers, AGENTS.md, Architecture, Principles"
```

---

### Task 8: Remaining 4 category deep-dive pages

**Files:**
- Create: `tutorial/src/pages/GatesPage.tsx`
- Create: `tutorial/src/pages/ObservabilityPage.tsx`
- Create: `tutorial/src/pages/ExecPlansPage.tsx`
- Create: `tutorial/src/pages/CliPage.tsx`

- [ ] **Step 1: Build `GatesPage.tsx`**

**Problem:** "Ship and pray." **Solution:** Features F224-F238. **Demo:** Simulated `harness evaluate` run — gates appear one by one with pass/fail animations (green checkmark / red X), progress bar fills. Uses GSAP timeline with staggered delays.

- [ ] **Step 2: Build `ObservabilityPage.tsx`**

**Problem:** "printf debugging in production." **Solution:** Features F242-F258. **Demo:** Animated structured log stream — NDJSON lines scroll up in a terminal, color-coded by level (green=INFO, yellow=WARN, red=ERROR). Filter buttons for domain and trace_id.

- [ ] **Step 3: Build `ExecPlansPage.tsx`**

**Problem:** "Context lost between sessions." **Solution:** Features F262-F279. **Demo:** Task dependency graph — SVG nodes with animated connecting edges drawn via stroke-dashoffset. Nodes show status (done=green, in-progress=yellow, blocked=red).

- [ ] **Step 4: Build `CliPage.tsx`**

**Problem:** "20 separate commands to remember." **Solution:** Features F283-F298. **Demo:** Interactive terminal — `TerminalSim` with typed `harness create --then lint --then evaluate` showing pipeline stages executing in sequence. Display the 17 commands in a grid with icons.

- [ ] **Step 5: Verify all 8 deep-dive pages work**

```bash
cd tutorial && npm run dev
```

Navigate to each of the 8 pages. Verify sidebar, content, and interactive demos render correctly.

- [ ] **Step 6: Commit**

```bash
git add tutorial/src/pages/
git commit -m "feat(tutorial): add deep-dive pages for Gates, Observability, ExecPlans, CLI"
```

---

### Task 9: Page transitions + responsive polish

**Files:**
- Modify: `tutorial/src/App.tsx`
- Modify: `tutorial/src/components/Navbar.tsx`
- Modify: various page files for responsive tweaks

- [ ] **Step 1: Add AnimatePresence page transitions**

Wrap `<Routes>` in Motion.dev `AnimatePresence`. Each page's root element gets `motion.div` with `initial={{ opacity: 0, x: 20 }}`, `animate={{ opacity: 1, x: 0 }}`, `exit={{ opacity: 0, x: -20 }}`. Use `useLocation` as key.

- [ ] **Step 2: Mobile navbar hamburger menu**

Add a hamburger button (visible below `md` breakpoint) that toggles a slide-down menu with all category links. Uses Motion.dev for open/close animation.

- [ ] **Step 3: Mobile deep-dive sidebar → dropdown**

On mobile, the sticky sidebar becomes a `<select>` dropdown or a collapsible section at the top of the page. Feature list scrolls to the selected section on change.

- [ ] **Step 4: Responsive tweaks**

- Landing scroll sections: `flex-col` below `md`, `flex-row` above
- Terminal simulations: `overflow-x-auto` + `text-sm` on mobile
- Touch targets: buttons and links minimum `p-3` (44px)
- Hero title: `text-4xl md:text-6xl lg:text-7xl`

- [ ] **Step 5: Test on mobile viewport**

Open Chrome DevTools, test at 375px and 768px widths. Verify navbar, landing sections, and deep-dive pages all render correctly.

- [ ] **Step 6: Commit**

```bash
git add tutorial/src/
git commit -m "feat(tutorial): add page transitions, mobile nav, responsive layout"
```

---

### Task 10: Tests + Biome lint + build verification

**Files:**
- Create: `tutorial/tests/components.test.tsx`
- Modify: `tutorial/tests/data.test.ts` (if needed)

- [ ] **Step 1: Write component smoke tests**

```typescript
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import App from "../src/App";

describe("App", () => {
  it("renders landing page at /", () => {
    render(<MemoryRouter initialEntries={["/"]}><App /></MemoryRouter>);
    expect(screen.getByText(/harness-skills/i)).toBeTruthy();
  });

  it("renders 404 for unknown routes", () => {
    render(<MemoryRouter initialEntries={["/nonexistent"]}><App /></MemoryRouter>);
    expect(screen.getByText(/not found/i)).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run tests**

```bash
cd tutorial && npx vitest run
```

Expected: all tests pass (data tests + component tests).

- [ ] **Step 3: Run Biome lint**

```bash
cd tutorial && npx biome check .
```

Fix any lint errors. Expected: zero errors.

- [ ] **Step 4: Run production build**

```bash
cd tutorial && npm run build
```

Expected: builds successfully to `tutorial/dist/`. Verify `dist/index.html` exists, `dist/assets/` contains JS/CSS chunks.

- [ ] **Step 5: Preview production build**

```bash
cd tutorial && npm run preview
```

Open the preview URL. Verify: landing page loads, navigation works, animations play.

- [ ] **Step 6: Commit**

```bash
git add tutorial/
git commit -m "test(tutorial): add component tests, verify lint + build pass"
```

---

### Task 11: GitHub Actions deployment workflow

**Files:**
- Create: `.github/workflows/deploy-tutorial.yml`

- [ ] **Step 1: Create the workflow file**

```yaml
name: Deploy Tutorial

on:
  push:
    branches: [main]
    paths: ['tutorial/**']
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: false

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: npm
          cache-dependency-path: tutorial/package-lock.json

      - name: Install dependencies
        run: npm ci
        working-directory: tutorial

      - name: Lint (Biome)
        run: npx biome check .
        working-directory: tutorial

      - name: Test (Vitest)
        run: npm test -- --run
        working-directory: tutorial

      - name: Build
        run: npm run build
        working-directory: tutorial

      - name: Setup Pages
        uses: actions/configure-pages@v5

      - name: Upload artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: tutorial/dist

      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
```

- [ ] **Step 2: Verify workflow YAML is valid**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/deploy-tutorial.yml'))"
```

Expected: no errors.

- [ ] **Step 3: Commit and push**

```bash
git add .github/workflows/deploy-tutorial.yml tutorial/
git commit -m "ci: add GitHub Actions workflow for tutorial deployment to Pages"
git push origin main
```

Expected: GitHub Actions triggers, builds tutorial, deploys to Pages.

- [ ] **Step 4: Verify deployment**

Visit `https://bowen31337.github.io/agent-harness-skills/` and confirm the site loads.

---

## Execution Summary

| Task | What | Est. Size |
|------|------|-----------|
| 1 | Scaffold (Vite + React + TW4 + Biome) | Small |
| 2 | Data layer (129 features) | Medium |
| 3 | Shared components (Layout, Navbar, utilities) | Medium |
| 4 | Hero + TerminalSim | Medium |
| 5 | CodeBlock with Shiki | Small |
| 6 | Landing page (8 scroll sections + visuals) | Large |
| 7 | Deep-dive pages 1-4 | Large |
| 8 | Deep-dive pages 5-8 | Large |
| 9 | Page transitions + responsive | Medium |
| 10 | Tests + lint + build | Small |
| 11 | GitHub Actions deployment | Small |
