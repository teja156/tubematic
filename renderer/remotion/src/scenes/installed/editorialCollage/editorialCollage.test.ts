// The Editorial Collage contract (TMDEV-229): the shared cases mcp/editorial_collage.py also runs, the
// desk's glide and string, and the notes no data can hide.
import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { DESK, NOTES, TIMING, ZONES, type HeadlineLayoutKind } from "./contract";
import {
  cameraAt, cleanWord, countProgress, figureText, gliding, headlineLayout, heroBox, penEllipse, stationCenter, stepped,
  stringPoints, typeFrames, typedChars, upTo,
} from "./stage";

const CASES = JSON.parse(
  fs.readFileSync(path.resolve(__dirname, "../../../../../../mcp/tests/fixtures/editorial_collage_contract.json"), "utf8"),
);

describe("the shared cases", () => {
  it("steps the pieces the same way", () => {
    for (const c of CASES.stepped) expect(stepped(c.frame)).toBeCloseTo(c.stepped, 9);
  });
  it("lays the stations out the same way", () => {
    for (const c of CASES.station_center) expect(stationCenter(c.i)).toEqual(c.xy);
  });
  it("moves the camera the same way", () => {
    for (const c of CASES.camera_at) cameraAt(c.starts, c.frame).forEach((v, i) => expect(v).toBeCloseTo(c.xy[i], 6));
  });
  it("lays the headline out the same way", () => {
    for (const c of CASES.headline_layout) {
      expect(headlineLayout(c.text, c.kind as HeadlineLayoutKind, c.kicker)).toEqual({ size: c.size, lines: c.lines, fits: c.fits });
    }
  });
  it("types an index line the same way", () => {
    for (const c of CASES.typed_chars) expect(typedChars(c.text, c.at, c.frame)).toBe(c.n);
    for (const c of CASES.type_frames) expect(typeFrames(c.text)).toBe(c.frames);
  });
  it("writes a figure the same way", () => {
    for (const c of CASES.figure_text) expect(figureText(c.value, c.prefix, c.suffix, c.k)).toBe(c.text);
  });
  it("reads a headline word the same way", () => {
    for (const c of CASES.clean_word) expect(cleanWord(c.word)).toBe(c.clean);
  });
});

describe("the desk", () => {
  it("zig-zags down the desk, a column each side", () => {
    expect(stationCenter(0)).toEqual([0, 0]);
    expect(stationCenter(1)).toEqual([DESK.dx, DESK.dy]);
    expect(stationCenter(2)).toEqual([0, 2 * DESK.dy]);
  });
  it("rests, then glides for TIMING.glide frames from a station's start, and never scales", () => {
    const starts = [0, 100];
    expect(cameraAt(starts, 99)).toEqual([0, 0]);
    expect(cameraAt(starts, 100)).toEqual([0, 0]);
    expect(cameraAt(starts, 100 + TIMING.glide)).toEqual(stationCenter(1));
    const mid = cameraAt(starts, 100 + TIMING.glide / 2);
    expect(mid[0]).toBeCloseTo(DESK.dx / 2, 6);
    expect(gliding(starts, 99)).toBe(false);
    expect(gliding(starts, 100)).toBe(true);
    expect(gliding(starts, 100 + TIMING.glide)).toBe(false);
    const src = fs.readFileSync(path.resolve(__dirname, "../EditorialCollage.tsx"), "utf8");
    expect(src).not.toMatch(/scale\(\$\{[^}]*cam/);
  });
  it("moves the pieces on twelve steps a second", () => {
    expect(new Set([0, 1, 2].map(stepped)).size).toBe(1);
    expect(stepped(3)).toBe(2.5);
  });
  it("sags the string below the straight line between its pins", () => {
    const pts = stringPoints([0, 0], [600, 200]);
    expect(pts[0]).toEqual([0, 0]);
    expect(pts[pts.length - 1][0]).toBeCloseTo(600, 6);
    expect(pts[20][1]).toBeGreaterThan(100);
    expect(upTo(pts, 0)).toEqual([]);
    expect(upTo(pts, 1)).toHaveLength(pts.length);
  });
  it("draws the pen ellipse as an unclosed stroke of points", () => {
    const pts = penEllipse(500, 900, 300, 200, 1);
    const [a, b] = [pts[0], pts[pts.length - 1]];
    expect(Math.hypot(a[0] - b[0], a[1] - b[1])).toBeGreaterThan(5);
  });
  it("counts a figure up from zero over TIMING.count frames", () => {
    expect(countProgress(50, 49)).toBe(0);
    expect(countProgress(50, 50)).toBe(0);
    expect(countProgress(50, 50 + TIMING.count)).toBe(1);
    expect(figureText(4, "", "hours", 0)).toBe("0 hours");
  });
  it("keeps every hero inside the station's zones", () => {
    const heroes = [
      { kind: "print" as const, image: "a", caption: "x" },
      { kind: "sticker" as const, image: "b" },
      { kind: "index" as const, lines: [1, 2, 3, 4].map((n) => ({ text: "x".repeat(34), at: n })) },
      { kind: "figure" as const, value: 999999999.99, prefix: "$", suffix: "x".repeat(10), label: "x", countAt: 0 },
      { kind: "stack" as const, items: [{ image: "a" }, { image: "b" }, { image: "a" }] },
    ];
    for (const aspect of [9 / 16, 1, 16 / 9]) {
      for (const h of heroes) {
        const [x, y, w, hh] = heroBox(h, { a: aspect, b: aspect });
        expect(x, h.kind).toBeGreaterThanOrEqual(ZONES.left - 1);
        expect(x + w, h.kind).toBeLessThanOrEqual(ZONES.right + 1);
        expect(y, h.kind).toBeGreaterThanOrEqual(ZONES.heroTop - 1);
        expect(y + hh, h.kind).toBeLessThanOrEqual(ZONES.heroBottom + 1);
      }
    }
  });
});

describe("the notes", () => {
  it("paints the notes the server cannot switch off", () => {
    expect(NOTES).toEqual({ print: "Illustration", recreation: "Recreation" });
    const paint = fs.readFileSync(path.resolve(__dirname, "paint.ts"), "utf8");
    expect(paint).toContain("note(g, NOTES.print,");
    expect(paint).toContain("g.fillText(NOTES.recreation,");
  });
  it("has no field for a person's face", () => {
    const src = fs.readFileSync(path.resolve(__dirname, "contract.ts"), "utf8");
    const fields = src.slice(src.indexOf("export interface Headline")).replace(/\/\/.*/g, "");
    expect(fields).not.toMatch(/\b(face|portrait|person|likeness|photo)\b/);
  });
});
