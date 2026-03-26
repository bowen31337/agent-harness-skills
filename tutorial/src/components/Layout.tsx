import { useEffect, useRef } from "react";
import { Outlet, useLocation } from "react-router-dom";
import Navbar from "./Navbar";

export default function Layout() {
  const mainRef = useRef<HTMLElement>(null);
  const location = useLocation();

  useEffect(() => {
    mainRef.current?.focus();
  }, [location.pathname]);

  return (
    <div
      className="min-h-screen"
      style={{
        backgroundImage:
          "linear-gradient(rgba(168, 85, 247, 0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(168, 85, 247, 0.03) 1px, transparent 1px)",
        backgroundSize: "60px 60px",
      }}
    >
      <Navbar />
      <main ref={mainRef} tabIndex={-1} className="pt-16 outline-none">
        <Outlet />
      </main>
    </div>
  );
}
