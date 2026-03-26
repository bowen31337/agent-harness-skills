import { type ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { type CategoryId, categories, features } from "../data/features";

interface DeepDiveLayoutProps {
	categoryId: CategoryId;
	children: ReactNode;
}

/**
 * Extract a short label from a feature description.
 * Takes the first meaningful phrase (before "with", "for", "from", "via", etc.)
 * and caps it at ~40 chars.
 */
function shortLabel(description: string): string {
	// Remove leading "Generates ", "Registers ", "Supports ", "Each ", "All ", "CLI ", "Execution "
	let text = description
		.replace(/^(Generates|Registers|Supports|Each|All|CLI|Execution)\s+/i, "")
		.replace(/^(a|an|the)\s+/i, "");

	// Capitalize first letter
	text = text.charAt(0).toUpperCase() + text.slice(1);

	// Truncate at a natural break if over 40 chars
	if (text.length > 40) {
		const breakIdx = text.search(/\s+(with|for|from|via|using|based|that|by|where|covering)\s/i);
		if (breakIdx > 10 && breakIdx < 50) {
			text = text.slice(0, breakIdx);
		} else {
			// Hard truncate at word boundary
			const truncated = text.slice(0, 38);
			const lastSpace = truncated.lastIndexOf(" ");
			text = lastSpace > 10 ? truncated.slice(0, lastSpace) : truncated;
		}
	}

	return text;
}

export default function DeepDiveLayout({ categoryId, children }: DeepDiveLayoutProps) {
	const category = categories.find((c) => c.id === categoryId);
	const categoryFeatures = features.filter((f) => f.category === categoryId);
	const [activeId, setActiveId] = useState<string>(categoryFeatures[0]?.id ?? "");
	const observerRef = useRef<IntersectionObserver | null>(null);

	useEffect(() => {
		observerRef.current?.disconnect();

		const observer = new IntersectionObserver(
			(entries) => {
				for (const entry of entries) {
					if (entry.isIntersecting) {
						setActiveId(entry.target.id);
					}
				}
			},
			{ rootMargin: "-20% 0px -60% 0px", threshold: 0 },
		);

		observerRef.current = observer;

		for (const f of categoryFeatures) {
			const el = document.getElementById(f.id);
			if (el) observer.observe(el);
		}

		return () => observer.disconnect();
	}, [categoryFeatures]);

	const scrollToFeature = useCallback((id: string) => {
		const el = document.getElementById(id);
		if (el) {
			el.scrollIntoView({ behavior: "smooth", block: "start" });
		}
	}, []);

	const handleSelectChange = useCallback(
		(e: React.ChangeEvent<HTMLSelectElement>) => {
			scrollToFeature(e.target.value);
		},
		[scrollToFeature],
	);

	const handleKeyDown = useCallback(
		(e: React.KeyboardEvent<HTMLAnchorElement>, idx: number) => {
			if (e.key === "ArrowDown" || e.key === "ArrowUp") {
				e.preventDefault();
				const next = e.key === "ArrowDown" ? idx + 1 : idx - 1;
				if (next >= 0 && next < categoryFeatures.length) {
					const link = document.querySelector<HTMLAnchorElement>(`[data-sidebar-idx="${next}"]`);
					link?.focus();
				}
			}
		},
		[categoryFeatures.length],
	);

	const activeIdx = categoryFeatures.findIndex((f) => f.id === activeId);

	return (
		<div className="max-w-7xl mx-auto px-4 sm:px-6 py-16 sm:py-20">
			{/* Breadcrumb */}
			<div className="mb-8 flex items-center gap-2 text-sm text-gray-500">
				<Link to="/" className="hover:text-gray-300 transition-colors">
					Home
				</Link>
				<span aria-hidden="true">/</span>
				<span className="text-gray-300">{category?.name}</span>
			</div>

			{/* Page header */}
			<header className="mb-12">
				<div className="flex items-center gap-3 mb-4">
					<span className="text-3xl" role="img" aria-label={category?.name ?? ""}>
						{category?.icon}
					</span>
					<div>
						<h1 className="text-3xl sm:text-4xl font-bold gradient-text">{category?.name}</h1>
						<p className="text-sm text-gray-500 mt-1">{category?.featureCount} features</p>
					</div>
				</div>
				<p className="text-base text-gray-400 max-w-2xl">{category?.description}</p>
			</header>

			<div className="flex gap-8">
				{/* Desktop sidebar */}
				<aside className="hidden md:block w-52 shrink-0">
					<nav
						className="sticky top-16 max-h-[calc(100vh-5rem)] overflow-y-auto"
						aria-label="Feature navigation"
					>
						{/* Progress indicator */}
						<div className="flex items-center gap-2 mb-3 px-2">
							<div className="flex-1 h-0.5 bg-surface-raised rounded-full overflow-hidden">
								<div
									className="h-full bg-brand-purple/60 rounded-full transition-all duration-300"
									style={{
										width: `${((activeIdx + 1) / categoryFeatures.length) * 100}%`,
									}}
								/>
							</div>
							<span className="text-[10px] font-mono text-gray-600 shrink-0">
								{activeIdx + 1}/{categoryFeatures.length}
							</span>
						</div>

						{/* Feature links */}
						<ul className="space-y-px">
							{categoryFeatures.map((f, idx) => {
								const isActive = activeId === f.id;
								return (
									<li key={f.id}>
										<a
											href={`#${f.id}`}
											data-sidebar-idx={idx}
											onClick={(e) => {
												e.preventDefault();
												scrollToFeature(f.id);
											}}
											onKeyDown={(e) => handleKeyDown(e, idx)}
											className={`group flex items-start gap-2 px-2 py-1.5 rounded-md text-[12px] leading-tight transition-all focus-visible:ring-2 focus-visible:ring-brand-cyan focus-visible:outline-none ${
												isActive
													? "text-white bg-brand-purple/15"
													: "text-gray-500 hover:text-gray-300 hover:bg-white/5"
											}`}
										>
											{/* Active indicator dot */}
											<span
												className={`mt-1 w-1.5 h-1.5 rounded-full shrink-0 transition-colors ${
													isActive ? "bg-brand-purple" : "bg-transparent group-hover:bg-gray-600"
												}`}
											/>
											<span className="min-w-0">{shortLabel(f.description)}</span>
										</a>
									</li>
								);
							})}
						</ul>
					</nav>
				</aside>

				{/* Mobile dropdown */}
				<div className="md:hidden w-full mb-6">
					<p className="text-xs text-gray-500 mb-1.5">
						Feature {activeIdx + 1} of {categoryFeatures.length}
					</p>
					<select
						className="w-full bg-surface-raised text-gray-300 text-sm rounded-lg border border-surface-border px-3 py-2.5 focus-visible:ring-2 focus-visible:ring-brand-cyan focus-visible:outline-none"
						onChange={handleSelectChange}
						value={activeId}
						aria-label="Jump to feature"
					>
						{categoryFeatures.map((f, idx) => (
							<option key={f.id} value={f.id}>
								{idx + 1}. {shortLabel(f.description)}
							</option>
						))}
					</select>
				</div>

				{/* Main content */}
				<main className="flex-1 min-w-0">{children}</main>
			</div>
		</div>
	);
}
