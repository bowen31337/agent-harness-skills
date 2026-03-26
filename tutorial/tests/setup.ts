// Polyfill window.matchMedia for jsdom (required by GSAP ScrollTrigger)
Object.defineProperty(window, "matchMedia", {
	writable: true,
	value: (query: string) => ({
		matches: false,
		media: query,
		onchange: null,
		addListener: () => {},
		removeListener: () => {},
		addEventListener: () => {},
		removeEventListener: () => {},
		dispatchEvent: () => false,
	}),
});

// Polyfill IntersectionObserver for jsdom (required by Motion.dev whileInView)
class MockIntersectionObserver {
	readonly root: Element | null = null;
	readonly rootMargin: string = "";
	readonly thresholds: ReadonlyArray<number> = [];
	observe() {}
	unobserve() {}
	disconnect() {}
	takeRecords(): IntersectionObserverEntry[] {
		return [];
	}
}
Object.defineProperty(window, "IntersectionObserver", {
	writable: true,
	value: MockIntersectionObserver,
});

// Polyfill ResizeObserver for jsdom
class MockResizeObserver {
	observe() {}
	unobserve() {}
	disconnect() {}
}
Object.defineProperty(window, "ResizeObserver", {
	writable: true,
	value: MockResizeObserver,
});

// Polyfill scrollTo for jsdom
window.scrollTo = () => {};
Element.prototype.scrollIntoView = () => {};
