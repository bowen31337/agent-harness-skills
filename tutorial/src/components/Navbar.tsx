import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import { Link, NavLink } from "react-router-dom";
import { categories } from "../data/features";

export default function Navbar() {
	const [mobileOpen, setMobileOpen] = useState(false);

	return (
		<nav className="fixed top-0 z-50 w-full glass">
			<div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
				<div className="flex h-16 items-center justify-between">
					{/* Logo */}
					<Link to="/" className="text-lg font-bold gradient-text">
						harness-skills
					</Link>

					{/* Desktop links */}
					<ul className="hidden md:flex items-center gap-1">
						{categories.map((cat) => (
							<li key={cat.id}>
								<NavLink
									to={cat.route}
									className={({ isActive }) =>
										`px-3 py-2 rounded text-sm transition-colors ${
											isActive
												? "text-white bg-white/10"
												: "text-gray-400 hover:text-white hover:bg-white/5"
										}`
									}
								>
									{cat.name}
								</NavLink>
							</li>
						))}
					</ul>

					{/* Mobile hamburger */}
					<button
						type="button"
						className="md:hidden text-gray-400 hover:text-white p-2"
						onClick={() => setMobileOpen((prev) => !prev)}
						aria-label="Toggle menu"
					>
						<svg
							xmlns="http://www.w3.org/2000/svg"
							className="h-6 w-6"
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
						className="md:hidden overflow-hidden glass"
					>
						<ul className="px-4 py-2 space-y-1">
							{categories.map((cat) => (
								<li key={cat.id}>
									<NavLink
										to={cat.route}
										onClick={() => setMobileOpen(false)}
										className={({ isActive }) =>
											`block px-3 py-3 rounded text-sm transition-colors ${
												isActive
													? "text-white bg-white/10"
													: "text-gray-400 hover:text-white hover:bg-white/5"
											}`
										}
									>
										{cat.name}
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
