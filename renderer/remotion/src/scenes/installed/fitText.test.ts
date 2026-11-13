import { describe, expect, it } from "vitest";
import { estimateWidth, fitFontSize } from "./fitText";

describe("one-line text fitting", () => {
  it("counts wide letters wider than narrow ones", () => {
    expect(estimateWidth("WWWW", 40)).toBeGreaterThan(estimateWidth("iiii", 40) * 2);
  });

  it("keeps the base size when the text fits and shrinks it when it does not", () => {
    expect(fitFontSize("Oh no", 600, 44, 30)).toBe(44);
    const size = fitFontSize("W".repeat(48), 800, 34, 12);
    expect(size).toBeLessThan(34);
    expect(estimateWidth("W".repeat(48), size)).toBeLessThanOrEqual(800);
  });

  it("never goes under the minimum", () => {
    expect(fitFontSize("W".repeat(200), 300, 44, 30)).toBe(30);
  });
});
