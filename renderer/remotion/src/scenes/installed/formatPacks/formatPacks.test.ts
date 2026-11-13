import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  APPS, BAND, CPL, FORMATS, LAYOUT, LIMITS, TICKS, TIMING, changeFrames, isFictionNumber, threadHeight, wrapLines,
} from "./contract";
import { expoOut, ringPath, underlinePath } from "./draw";

const ROOT = path.resolve(__dirname, "../../../../../..");
const CASES = JSON.parse(fs.readFileSync(path.join(ROOT, "mcp/tests/fixtures/format_packs_contract.json"), "utf8"));

describe("the shared contract", () => {
  it("has the fixture's formats, limits, timings, band and lists", () => {
    expect([...FORMATS]).toEqual(CASES.formats);
    expect({ ...LIMITS }).toEqual(CASES.limits);
    expect({ ...TIMING }).toEqual(CASES.timing);
    expect({ ...CPL }).toEqual(CASES.cpl);
    expect([BAND.top, BAND.bottom]).toEqual(CASES.band);
    expect([...TICKS]).toEqual(CASES.ticks);
    expect([...APPS]).toEqual(CASES.apps);
    for (const [k, v] of Object.entries(CASES.layout)) expect((LAYOUT as Record<string, number>)[k]).toBe(v);
  });

  it("wraps text into the fixture's line counts", () => {
    for (const c of CASES.wrap) expect(wrapLines(c.text, c.cpl)).toBe(c.lines);
  });

  it("measures a thread like the validator", () => {
    for (const c of CASES.thread_height) expect(threadHeight(c.texts)).toBe(c.height);
  });

  it("keeps the thread and the phone inside the band", () => {
    expect(LAYOUT.threadTop + LAYOUT.threadBudget).toBeLessThan(LAYOUT.phoneBottom - 100);
    expect(LAYOUT.phoneBottom).toBeLessThanOrEqual(BAND.bottom);
    expect(LAYOUT.titleY + LAYOUT.listBudget).toBeLessThanOrEqual(BAND.bottom);
  });

  it("knows the fiction phone numbers from real-looking ones", () => {
    for (const n of CASES.fiction_numbers) expect(isFictionNumber(n)).toBe(true);
    for (const n of CASES.real_numbers) expect(isFictionNumber(n)).toBe(false);
  });
});

describe("timing and drawing", () => {
  it("lists every change in order, the insert's first frame first", () => {
    expect(changeFrames({
      format: "chat", contact: { name: "Unknown number" },
      messages: [{ at: 300, from: "them", text: "a" }, { at: 340, from: "me", text: "b" }],
      marks: [{ at: 360, message: 0, match: "a", kind: "ring" }],
    }, 300)).toEqual([300, 340, 360]);
    expect(changeFrames({ format: "quiz", question: "q", options: [{ at: 320, text: "x" }, { at: 350, text: "y" }],
      answer: 1, lockAt: 400 }, 300)).toEqual([300, 320, 350, 400]);
  });

  it("eases rows on the card's curve and draws marks as single paths", () => {
    expect(expoOut(0)).toBeCloseTo(0);
    expect(expoOut(1)).toBeCloseTo(1);
    expect(expoOut(0.3)).toBeGreaterThan(0.7);
    expect(ringPath(100, 100).startsWith("M")).toBe(true);
    expect((ringPath(100, 100).match(/M/g) ?? []).length).toBe(1);
    expect((underlinePath(100).match(/M/g) ?? []).length).toBe(1);
  });
});
