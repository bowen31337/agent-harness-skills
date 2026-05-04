# Tutorial Showcase Site — Design Spec

## Overview

An animated, interactive tutorial site for the `harness-skills` toolkit, built as a `tutorial/` subfolder in the existing repo. Deployed to GitHub Pages via GitHub Actions.

**Stack:** React 19, TypeScript, Tailwind CSS v4, Vite, Motion.dev, GSAP, Biome
**Deploy:** GitHub Pages at `bowen31337.github.io/agent-harness-skills/`
**Visual style:** Dark + gradient glow (purple/cyan/green palette, Stripe/Raycast aesthetic)

## Architecture

### Page Structure: Hybrid

- **Landing page** — full-page scroll-animated showcase (GSAP ScrollTrigger) with hero + 8 category preview sections
- **8 category deep-dive pages** — interactive walkthroughs with problem → solution → demo flow
- **React Router** with `AnimatePresence` page transitions

### Project Structure

```
tutorial/
├── index.html
├── package.json
├── biome.json
├── vite.config.ts
├── tsconfig.json
├── public/
│   ├── favicon.svg
│   └── 404.html           # SPA redirect for GitHub Pages
└── src/
    ├── main.tsx
    ├── App.tsx                 # Router setup with Suspense boundaries
    ├── index.css               # Tailwind v4 @theme config + glow utilities
    ├── components/
    │   ├── Layout.tsx          # Dark shell with nav + animated background
    │   ├── Navbar.tsx          # Sticky nav with category links
    │   ├── Hero.tsx            # GSAP text reveal + terminal simulation
    │   ├── CategoryCard.tsx    # Animated card for landing page sections
    │   ├── FeatureItem.tsx     # Individual feature with scroll reveal
    │   ├── CodeBlock.tsx       # Shiki syntax highlighting + typing effect
    │   ├── TerminalSim.tsx     # Simulated terminal output (GSAP timeline)
    │   ├── ScrollReveal.tsx    # Motion.dev scroll-triggered reveal wrapper
    │   ├── GlowBadge.tsx      # Gradient-bordered badge
    │   ├── LoadingFallback.tsx # Suspense fallback for code-split pages
    │   └── ErrorBoundary.tsx   # Catches render errors gracefully
    ├── pages/
    │   ├── Landing.tsx         # Hero + 8 scroll-animated category sections
    │   ├── AnalyzersPage.tsx   # Category 1: Codebase Analysis & Detection
    │   ├── AgentsMdPage.tsx    # Category 2: AGENTS.md Generation
    │   ├── ArchitecturePage.tsx # Category 3: Architecture Documentation & Enforcement
    │   ├── PrinciplesPage.tsx  # Category 4: Golden Principles & Pattern Enforcement
    │   ├── GatesPage.tsx       # Category 5: Evaluation Gates & Testing Harness
    │   ├── ObservabilityPage.tsx # Category 6: Observability & Application Legibility
    │   ├── ExecPlansPage.tsx   # Category 7: Execution Plans & State Management
    │   └── CliPage.tsx         # Category 8: Skill Invocation & CLI Interface
    ├── data/
    │   └── features.ts         # All 129 features as typed data (generated from spec)
    └── hooks/
        └── useScrollAnimation.ts  # GSAP ScrollTrigger hook
```

### Dependencies

**Runtime:**
- `react` 19 + `react-dom` + `react-router-dom`
- `motion` (Motion.dev — declarative animations)
- `gsap` + `@gsap/react` (GSAP — scroll animations, timelines; free tier, suitable for non-commercial showcase)
- `shiki` (syntax highlighting — static, low bundle impact, excellent dark themes)

**Build:**
- `vite`
- `tailwindcss` + `@tailwindcss/vite` (v4 — CSS-first config, no JS config file)
- `typescript`

**Dev:**
- `@biomejs/biome` (lint + format)
- `vitest` + `@testing-library/react` (component tests)

## Tailwind v4 Configuration

Tailwind v4 uses CSS-first configuration via `@theme` directives in `src/index.css` — no `tailwind.config.ts` file.

```css
@import "tailwindcss";

@theme {
  --color-brand-purple: #a855f7;
  --color-brand-cyan: #22d3ee;
  --color-brand-green: #4ade80;
  --color-surface: #0c0a1a;
  --color-surface-raised: #1a1035;
}

/* Custom glow utilities */
.glow-purple { box-shadow: 0 0 20px rgba(168, 85, 247, 0.3); }
.glow-cyan { box-shadow: 0 0 20px rgba(34, 211, 238, 0.3); }
.glow-green { box-shadow: 0 0 20px rgba(74, 222, 128, 0.3); }

/* Glassmorphism panels */
.glass {
  backdrop-filter: blur(12px);
  background: rgba(26, 16, 53, 0.6);
  border: 1px solid rgba(168, 85, 247, 0.15);
}
```

Dark mode is the only mode — no toggle needed.

## Landing Page

### Hero Section
- Full-viewport dark gradient background with subtle animated grid (GSAP)
- `harness-skills` title: gradient text reveal animation (purple → cyan → green)
- Subtitle `129 features · 8 categories · 17 commands` with staggered fade-in
- Terminal simulation: `harness create --then lint --then evaluate` with line-by-line output (GSAP timeline)
- Floating glow orbs in background (Motion.dev)

### Scroll Sections (8 categories)
Each section triggered by GSAP ScrollTrigger:
- Left: category title + description + feature count GlowBadge
- Right: category-specific visual element:

| Category | Visual |
|----------|--------|
| Codebase Analysis | Language icons (Python/TS/Go/Rust/Java/C#) with orbit animation |
| AGENTS.md Generation | Tiered document preview (L0→L1→L2) with zoom |
| Architecture Enforcement | Layer diagram building up on scroll |
| Golden Principles | Code diff: "before violation" → "after fix" with highlight |
| Evaluation Gates | Progress bars filling (coverage 92%, types pass, etc.) |
| Observability | Simulated log stream with colored entries |
| Execution Plans | Task dependency graph with animated connecting edges |
| CLI Interface | Terminal with `--then` pipeline chaining demo |

Each has a "Deep dive →" link to the category page.

### Bottom CTA
- "Get Started" with copyable `uv add agent-harness-skills` command
- Links to GitHub repo, MkDocs docs

## Category Deep-Dive Pages

### Layout
- Sticky sidebar nav listing features in the category (highlights on scroll)
- Main content with walkthrough flow
- **Mobile:** sidebar collapses to a top dropdown menu; sections stack vertically

### Walkthrough Structure (3 acts)

1. **The Problem** — what developers face without this feature. Animated "before" state. Motion.dev fade-in.

2. **The Solution** — features as scroll-reveal cards, each with:
   - Feature name + description
   - `CodeBlock` with Shiki syntax highlighting
   - `TerminalSim` showing command output (GSAP typing)

3. **See It In Action** — interactive demo per category:

| Category | Demo |
|----------|------|
| Codebase Analysis | Tabs switching between language analysis outputs |
| AGENTS.md Generation | Live preview with expandable sections |
| Architecture Enforcement | Interactive layer diagram (click to see import rules) |
| Golden Principles | Toggle violations on/off in code sample |
| Evaluation Gates | Simulated `harness evaluate` with gates passing in sequence |
| Observability | Animated log stream with domain/trace_id filter |
| Execution Plans | Animated task dependency visualization |
| CLI Interface | Interactive terminal with animated command output |

### Page Transitions
Motion.dev `AnimatePresence` with fade+slide between routes.

## Animation Strategy

### Library Responsibilities

| Animation | Library | Reason |
|-----------|---------|--------|
| Hero text reveal, terminal typing, parallax | **GSAP** | Timeline sequencing, ScrollTrigger |
| Page transitions, hover effects, scroll-reveal | **Motion.dev** | Declarative React, `AnimatePresence` |
| Background grid/particles | **GSAP** | Raw perf for continuous animation |
| Click/hover/expand responses | **Motion.dev** | `layout` animations, spring physics |

### Performance
- GPU-composited properties only (transform, opacity)
- `prefers-reduced-motion` respected — instant fallback
- Vite code-splits each category page via `React.lazy()`
- Lazy-load images below fold
- `will-change: transform` applied dynamically (add before animation, remove after) — not static in CSS

## Responsive Design

- **Landing hero:** stacks vertically on mobile; terminal simulation scales to fit
- **Landing scroll sections:** two-column → single-column stack below `md` breakpoint
- **Deep-dive sidebar:** collapses to a top dropdown/hamburger on mobile
- **Terminal simulations:** use `overflow-x: auto` with horizontal scroll on narrow screens
- **Touch targets:** minimum 44px for interactive elements

## SPA Routing on GitHub Pages

**`public/404.html`** — GitHub Pages serves this for unknown paths. It encodes the path into a query parameter and redirects to `index.html`:

```html
<!DOCTYPE html>
<html>
<head>
  <script>
    // Redirect path to query param for SPA client-side routing
    var path = window.location.pathname;
    window.location.replace(
      window.location.origin + '/agent-harness-skills/?p=' +
      encodeURIComponent(path.replace('/agent-harness-skills/', ''))
    );
  </script>
</head>
</html>
```

**`src/main.tsx`** — on load, reads `?p=` and calls `router.navigate()` to restore the route.

## Accessibility

- **Color contrast:** all text meets WCAG AA minimum (4.5:1 for body, 3:1 for large text). Purple/cyan/green on dark backgrounds tested.
- **Keyboard navigation:** all interactive demos operable via keyboard (Tab, Enter, Arrow keys)
- **Focus management:** focus moves to page content on route change via `useEffect`
- **Screen readers:** `TerminalSim` uses `aria-live="polite"` for output lines; `CodeBlock` uses `role="code"`
- **`prefers-reduced-motion`:** all GSAP/Motion animations disabled; content appears instantly

## Testing

- **Vitest** + `@testing-library/react` for component unit tests
- **Data layer tests:** verify all 129 features present, all 8 categories have correct feature counts
- **CI runs tests before deploy** (added `npm test` step to workflow)
- **No Playwright e2e** — out of scope for initial build; can be added later

## GitHub Actions Deployment

**Workflow:** `.github/workflows/deploy-tutorial.yml`

```yaml
name: Deploy Tutorial
on:
  push:
    branches: [main]
    paths: ['tutorial/**']
  workflow_dispatch:

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    permissions:
      pages: write
      id-token: write
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - run: npm ci
        working-directory: tutorial
      - run: npx biome check .
        working-directory: tutorial
      - run: npm test -- --run
        working-directory: tutorial
      - run: npm run build
        working-directory: tutorial
      - uses: actions/upload-pages-artifact@v3
        with: { path: tutorial/dist }
      - id: deployment
        uses: actions/deploy-pages@v4
```

**Vite:** `base: '/agent-harness-skills/'`
**Router:** `basename="/agent-harness-skills"`

## Data Model

```typescript
interface Feature {
  id: string;          // e.g. "F151"
  description: string; // spec text
  category: CategoryId;
}

type CategoryId =
  | 'analyzers' | 'agents-md' | 'architecture'
  | 'principles' | 'gates' | 'observability'
  | 'exec-plans' | 'cli';

interface Category {
  id: CategoryId;
  name: string;
  featureCount: number;
  color: string;       // gradient accent color
  icon: string;        // emoji or SVG
  description: string;
  features: Feature[];
  route: string;       // e.g. '/analyzers'
}
```

**Data generation:** `features.ts` should be generated from `spec/app_spec.txt` via a build script to prevent drift between the toolkit and the tutorial. A simple Node script parses the XML-like spec and outputs typed TS.

## Success Criteria

- Landing page loads in <2s on 3G throttle
- All 129 features represented in the data layer
- GSAP ScrollTrigger animates all 8 landing sections smoothly
- All 8 deep-dive pages render with interactive demos
- Biome passes with zero errors
- Vitest tests pass
- GitHub Actions deploys to Pages on push to main
- `prefers-reduced-motion` disables animations gracefully
- WCAG AA color contrast met
- Works on mobile (responsive Tailwind layout, sidebar collapses)
