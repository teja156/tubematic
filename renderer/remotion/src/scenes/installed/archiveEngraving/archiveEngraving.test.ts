// The Archive and Engraving contract (TMDEV-230): the shared cases mcp/archive_engraving.py also runs,
// the page's moving parts, the emblems' geometry, and the footnotes no data can hide.
import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { EMBLEMS, FOOTNOTES, type ArchiveEvent } from "./contract";
import { C, FIELD_R, emblemShapes, roundelShapes, shapePoints } from "./emblems";
import {
  cleanWord, dotsAlong, magnifierOnRight, plateView, pushScale, rulerMarker, rulerScale, titleLayout, toWindow, writtenChars,
} from "./stage";
import { roman } from "../ArchiveEngraving";

const CASES = JSON.parse(
  fs.readFileSync(path.resolve(__dirname, "../../../../../../mcp/tests/fixtures/archive_engraving_contract.json"), "utf8"),
);

describe("the shared cases", () => {
  it("lays the title out the same way", () => {
    for (const c of CASES.title_layout) expect(titleLayout(c.text)).toEqual({ size: c.size, lines: c.lines });
  });
  it("pushes the plate the same way", () => {
    for (const c of CASES.push_scale) expect(pushScale(c.frame, c.start, c.end)).toBeCloseTo(c.scale, 9);
  });
  it("crops the still the same way", () => {
    for (const c of CASES.plate_view) {
      plateView(c.scale, c.focus).forEach((v, i) => expect(v).toBeCloseTo(c.view[i], 6));
    }
  });
  it("puts a still's point on the page the same way", () => {
    for (const c of CASES.to_window) {
      toWindow(plateView(c.scale, c.focus), c.point).forEach((v, i) => expect(v).toBeCloseTo(c.xy[i], 6));
    }
  });
  it("scales the ruler the same way", () => {
    for (const c of CASES.ruler_scale) {
      const r = rulerScale(c.years);
      expect(r === null ? null : [r.start, r.end, r.step]).toEqual(c.scale);
    }
    for (const c of CASES.ruler_scale_ticks) expect(rulerScale(c.years, c.max)).toBe(c.scale);
  });
  it("reads a title word the same way", () => {
    for (const c of CASES.clean_word) expect(cleanWord(c.word)).toBe(c.clean);
  });
});

describe("the page", () => {
  it("draws the footnotes the server cannot switch off", () => {
    expect(FOOTNOTES).toEqual({ plate: "Illustration", chart: "Illustration", document: "Recreation" });
    const src = fs.readFileSync(path.resolve(__dirname, "../ArchiveEngraving.tsx"), "utf8");
    expect(src).toContain("<Footnote text={FOOTNOTES[card.kind]} />");
    expect(src).toContain("{FOOTNOTES.document}");
  });
  it("has no field for a person's picture", () => {
    const src = fs.readFileSync(path.resolve(__dirname, "contract.ts"), "utf8");
    const person = src.match(/export interface Person \{([\s\S]*?)\n\}/)![1];
    expect(person).not.toMatch(/image|face|photo|portrait|src/);
  });
  it("slides the ruler's marker from one year to the next", () => {
    const events: ArchiveEvent[] = [{ at: 10, do: "timeline", from: 1944, to: 1947 }, { at: 100, do: "timeline", from: 1947, to: 1878 }];
    expect(rulerMarker(events, 5)).toBeNull();
    expect(rulerMarker(events, 10)).toBe(1944);
    expect(rulerMarker(events, 40)).toBe(1947);
    expect(rulerMarker(events, 200)).toBe(1878);
  });
  it("writes a document line on and draws a route dot by dot", () => {
    expect(writtenChars("First actual case", 10, 9, false)).toBe(0);
    expect(writtenChars("First actual case", 10, 10, false)).toBe(2);
    expect(writtenChars("First actual case", 10, 10, true)).toBe(1);
    expect(writtenChars("First actual case", 10, 99, true)).toBe(17);
    const line: [number, number][] = [[0, 0], [220, 0]];
    expect(dotsAlong(line, 0).length).toBe(1);
    expect(dotsAlong(line, 1).length).toBe(11);
  });
  it("sends the magnifier to the side away from its point", () => {
    const view = plateView(1, [0.5, 0.5]);
    expect(magnifierOnRight(view, [0.2, 0.5])).toBe(true);
    expect(magnifierOnRight(view, [0.8, 0.5])).toBe(false);
  });
  it("numbers the plates", () => {
    expect([1, 4, 9, 14, 32].map(roman)).toEqual(["I", "IV", "IX", "XIV", "XXXII"]);
  });
});

describe("the emblems", () => {
  it("draws every emblem inside the roundel's field", () => {
    for (const name of EMBLEMS) {
      const shapes = emblemShapes(name);
      expect(shapes.length, name).toBeGreaterThan(0);
      for (const s of shapes) {
        for (const [x, y] of shapePoints(s)) expect(Math.hypot(x - C, y - C), name).toBeLessThanOrEqual(FIELD_R);
      }
    }
  });
  it("keeps the ring inside its box", () => {
    for (const s of roundelShapes()) {
      for (const [x, y] of shapePoints(s)) {
        expect(x).toBeGreaterThanOrEqual(0);
        expect(y).toBeLessThanOrEqual(200);
      }
    }
  });
});
