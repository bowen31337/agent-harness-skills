import { describe, expect, it } from "vitest";
import { categories, features } from "../src/data/features";

describe("features data", () => {
  it("has exactly 129 features", () => {
    expect(features).toHaveLength(129);
  });

  it("has exactly 8 categories", () => {
    expect(categories).toHaveLength(8);
  });

  it("every feature belongs to a valid category", () => {
    const categoryIds = new Set(categories.map((c) => c.id));
    for (const f of features) {
      expect(categoryIds.has(f.category)).toBe(true);
    }
  });

  it("category feature counts match", () => {
    for (const cat of categories) {
      const count = features.filter((f) => f.category === cat.id).length;
      expect(count).toBe(cat.featureCount);
    }
  });

  it("every feature has a non-empty description", () => {
    for (const f of features) {
      expect(f.description.length).toBeGreaterThan(0);
    }
  });
});
