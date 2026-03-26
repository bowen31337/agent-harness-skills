import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import { Link, NavLink } from "react-router-dom";
import type { CategoryId } from "../data/features";
import { categories } from "../data/features";

/** Short labels for the nav bar — full names are too long */
const navLabels: Record<CategoryId, string> = {
	analyzers: "Analyzers",
	"agents-md": "AGENTS.md",
	architecture: "Architecture",
	principles: "Principles",
	gates: "Gates",
	observability: "Observability",
	"exec-plans": "Exec Plans",
	cli: "CLI",
};

export default function Navbar() {
	const [mobileOpen, setMobileOpen] = useState(false);

	return (
		<nav className="fixed top-0 z-50 w-full glass border-b border-surface-border">
			<div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
				<div className="flex h-14 items-center justify-between">
					{/* Logo */}
					<Link to="/" className="flex items-center gap-2 shrink-0">
						<span className="text-lg font-bold gradient-text tracking-tight">harness-skills</span>
						<span className="hidden sm:inline text-[10px] font-mono text-gray-600 bg-white/5 px-1.5 py-0.5 rounded">
							tutorial
						</span>
					</Link>

					{/* Desktop links */}
					<ul className="hidden lg:flex items-center gap-0.5">
						{categories.map((cat) => (
							<li key={cat.id}>
								<NavLink
									to={cat.route}
									className={({ isActive }) =>
										`flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-[13px] font-medium whitespace-nowrap transition-all ${
											isActive
												? "text-white bg-white/10 shadow-sm"
												: "text-gray-400 hover:text-white hover:bg-white/5"
										}`
									}
								>
									<span className="text-sm" aria-hidden="true">
										{cat.icon}
									</span>
									{navLabels[cat.id]}
								</NavLink>
							</li>
						))}
					</ul>

					{/* Mobile hamburger */}
					<button
						type="button"
						className="lg:hidden text-gray-400 hover:text-white p-2 rounded-md hover:bg-white/5 transition-colors"
						onClick={() => setMobileOpen((prev) => !prev)}
						aria-label="Toggle menu"
						aria-expanded={mobileOpen}
					>
						<svg
							xmlns="http://www.w3.org/2000/svg"
							className="h-5 w-5"
							fill="none"
							viewBox="0 0 24 24"
							stroke="currentColor"
							strokeWidth={2}
						>
							{mobileOpen ? (
								<path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
							) : (
								<path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
							)}
						</svg>
					</button>
				</div>
			</div>

			{/* Mobile menu */}
			<AnimatePresence>
				{mobileOpen && (
					<motion.div
						initial={{ height: 0, opacity: 0 }}
						animate={{ height: "auto", opacity: 1 }}
						exit={{ height: 0, opacity: 0 }}
						transition={{ duration: 0.2 }}
						className="lg:hidden overflow-hidden border-t border-surface-border"
					>
						<ul className="px-4 py-3 space-y-1">
							{categories.map((cat) => (
								<li key={cat.id}>
									<NavLink
										to={cat.route}
										onClick={() => setMobileOpen(false)}
										className={({ isActive }) =>
											`flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium transition-colors ${
												isActive
													? "text-white bg-white/10"
													: "text-gray-400 hover:text-white hover:bg-white/5"
											}`
										}
									>
										<span className="text-base" aria-hidden="true">
											{cat.icon}
										</span>
										<div>
											<div>{navLabels[cat.id]}</div>
											<div className="text-[11px] font-normal text-gray-500">
												{cat.featureCount} features
											</div>
										</div>
									</NavLink>
								</li>
							))}
						</ul>
					</motion.div>
				)}
			</AnimatePresence>
		</nav>
	);
}
