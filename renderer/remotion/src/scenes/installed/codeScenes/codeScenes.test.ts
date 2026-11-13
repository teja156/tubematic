import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  BAND, LANGS, LIMITS, LAYOUT, TIMING, codeLines, fontSizeFor, lineHeightFor, outputAt, typeFrames,
  type CodeScenesData,
} from "./contract";
import { matchPieces, morphAt } from "./morph";
import { tokenize } from "./tokens";

const ROOT = path.resolve(__dirname, "../../../../../..");
const CASES = JSON.parse(fs.readFileSync(path.join(ROOT, "mcp/tests/fixtures/code_scenes_contract.json"), "utf8"));

describe("the shared contract", () => {
  it("has the fixture's languages, limits, timings and band", () => {
    expect([...LANGS]).toEqual(CASES.langs);
    expect({ ...LIMITS }).toEqual(CASES.limits);
    expect({ ...TIMING }).toEqual(CASES.timing);
    expect([BAND.top, BAND.bottom]).toEqual(CASES.band);
  });

  it("picks the fixture's font size for each block of code", () => {
    for (const c of CASES.font_sizes) expect(fontSizeFor(c.lines, c.cols)).toBe(c.size);
  });

  it("fits the largest code, a callout and a full output pane inside the band", () => {
    for (let lines = 1; lines <= LIMITS.maxLines; lines++) {
      const fs = fontSizeFor(lines, LIMITS.maxCols);
      expect(fs).toBeGreaterThanOrEqual(32);
      const card = LAYOUT.titleH + 2 * LAYOUT.codePad + lines * lineHeightFor(fs) + LAYOUT.calloutH;
      const pane = LAYOUT.paneHeadH + LIMITS.outputLines * LAYOUT.paneLineH + LAYOUT.panePad;
      expect(LAYOUT.cardY + card + LAYOUT.paneGap + pane).toBeLessThanOrEqual(BAND.bottom);
      expect(LIMITS.maxCols * fs * 0.6).toBeLessThanOrEqual(LAYOUT.textWidth);
    }
  });

  it("types a first step in the fixture's frames", () => {
    for (const c of CASES.type_frames) expect(typeFrames(c.code)).toBe(c.frames);
  });

  it("shows each step the fixture's output pane", () => {
    for (const c of CASES.output_at) {
      const data: CodeScenesData = { lang: "python", steps: c.steps.map((s: object, i: number) => ({ at: i * 60, ...s })) };
      expect(c.steps.map((_: unknown, i: number) => outputAt(data, i)?.from ?? null)).toEqual(c.from);
    }
  });

  it("drops trailing blank lines", () => {
    expect(codeLines("a\nb\n\n")).toEqual(["a", "b"]);
    expect(codeLines("")).toEqual([""]);
  });
});

describe("tokens and the morph", () => {
  it("colours every language without throwing and keeps the columns", () => {
    for (const lang of LANGS) {
      const pieces = tokenize("x = 1\n  y", lang, "dark");
      expect(pieces.length).toBeGreaterThan(0);
    }
    const p = tokenize('name = input("Name: ")', "python", "dark");
    expect(p.map((t) => t.text)).toEqual(["name", "=", "input", "(", '"', "Name", ":", '"', ")"]);
    expect(p.find((t) => t.text === "input")!.col).toBe(7);
  });

  it("colours keywords differently from names", () => {
    const p = tokenize("for row in cur:", "python", "dark");
    expect(p.find((t) => t.text === "for")!.color).not.toBe(p.find((t) => t.text === "row")!.color);
  });

  it("keeps unchanged pieces still and moves the ones a new line pushes down", () => {
    const a = tokenize("a = 1\nprint(a)", "python", "dark");
    const b = tokenize("a = 1\nb = 2\nprint(a)", "python", "dark");
    const pairs = matchPieces(a, b);
    const kept = pairs.filter((p) => p.from && p.to);
    expect(kept.length).toBe(a.length);
    const mid = morphAt(pairs, 0.5);
    const first = mid.find((d) => d.text === "a" && d.row === 0)!;
    expect(first.col).toBe(0);
    const printPiece = mid.find((d) => d.text === "print")!;
    expect(printPiece.row).toBeGreaterThan(1);
    expect(printPiece.row).toBeLessThan(2);
    const added = morphAt(pairs, 0).filter((d) => d.key.startsWith("a"));
    expect(added.every((d) => d.opacity === 0)).toBe(true);
    expect(morphAt(pairs, 1).every((d) => d.key.startsWith("r") ? d.opacity === 0 : d.opacity === 1)).toBe(true);
  });
});
