import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import App from "../src/App";

describe("App", () => {
	it("renders landing page at /", async () => {
		render(
			<MemoryRouter initialEntries={["/"]}>
				<App />
			</MemoryRouter>,
		);
		// Multiple elements contain "harness-skills" (navbar + hero title)
		const elements = await screen.findAllByText(/harness-skills/i);
		expect(elements.length).toBeGreaterThanOrEqual(1);
	});

	it("renders 404 for unknown routes", async () => {
		render(
			<MemoryRouter initialEntries={["/nonexistent"]}>
				<App />
			</MemoryRouter>,
		);
		expect(await screen.findByText(/not found/i)).toBeTruthy();
	});
});
