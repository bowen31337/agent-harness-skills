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
