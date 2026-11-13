import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { estimateWidth, fitFontSize, wrapCount } from "./fitText";

const ROOT = path.resolve(__dirname, "../../../../..");
const CASES = JSON.parse(fs.readFileSync(path.join(ROOT, "mcp/tests/fixtures/text_fit_contract.json"), "utf8"));

describe("the shared cases with mcp/text_fit.py", () => {
  it("estimates the fixture's widths", () => {
    for (const c of CASES.widths) expect(estimateWidth(c.text, c.size, c.spacing)).toBeCloseTo(c.width, 3);
  });
  it("picks the fixture's sizes", () => {
    for (const c of CASES.fits) expect(fitFontSize(c.text, c.max, c.base, c.min, c.spacing)).toBe(c.size);
  });
  it("counts the fixture's wrapped lines", () => {
    for (const c of CASES.wraps) expect(wrapCount(c.text, c.size, c.max)).toBe(c.lines);
  });
});

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
