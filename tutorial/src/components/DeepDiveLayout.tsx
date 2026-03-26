import { type ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { type CategoryId, categories, features } from "../data/features";

interface DeepDiveLayoutProps {
	categoryId: CategoryId;
	children: ReactNode;
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

	return (
		<div className="max-w-7xl mx-auto px-6 py-20">
			{/* Page header */}
			<header className="mb-12">
				<span className="text-4xl mb-4 block" role="img" aria-label={category?.name ?? ""}>
					{category?.icon}
				</span>
				<h1 className="text-4xl font-bold gradient-text mb-3">{category?.name}</h1>
				<p className="text-lg text-gray-400 max-w-2xl">{category?.description}</p>
			</header>

			<div className="flex gap-8">
				{/* Desktop sidebar */}
				<aside className="hidden md:block w-64 shrink-0">
					<nav className="sticky top-20 space-y-1 max-h-[80vh] overflow-y-auto pr-2">
						{categoryFeatures.map((f, idx) => (
							<a
								key={f.id}
								href={`#${f.id}`}
								data-sidebar-idx={idx}
								onClick={(e) => {
									e.preventDefault();
									scrollToFeature(f.id);
								}}
								onKeyDown={(e) => handleKeyDown(e, idx)}
								className={`block text-xs px-3 py-2 rounded transition-colors focus-visible:ring-2 focus-visible:ring-brand-cyan focus-visible:outline-none ${
									activeId === f.id
										? "bg-brand-purple/20 text-brand-purple border-l-2 border-brand-purple"
										: "text-gray-500 hover:text-gray-300 hover:bg-white/5"
								}`}
							>
								<span className="font-mono text-[10px] text-gray-600 mr-1">{f.id}</span>
								{f.description.slice(0, 60)}
								{f.description.length > 60 ? "..." : ""}
							</a>
						))}
					</nav>
				</aside>

				{/* Mobile dropdown */}
				<div className="md:hidden w-full mb-6">
					<select
						className="w-full bg-surface-raised text-gray-300 text-sm rounded-lg border border-surface-border px-3 py-2 focus-visible:ring-2 focus-visible:ring-brand-cyan focus-visible:outline-none"
						onChange={handleSelectChange}
						value={activeId}
						aria-label="Jump to feature"
					>
						{categoryFeatures.map((f) => (
							<option key={f.id} value={f.id}>
								{f.id}: {f.description.slice(0, 50)}...
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
