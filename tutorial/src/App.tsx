import { Suspense, lazy } from "react";
import { Route, Routes } from "react-router-dom";
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
  return (
    <div className="min-h-screen flex items-center justify-center text-white text-2xl">
      404 — Page not found
    </div>
  );
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
