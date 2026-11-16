// The paper styles' caption looks (TMDEV-228/229/230): the "tags" look's seeded tags and their pop,
// the "highlight" look's marker wipe, and the "karaoke" look's word colour (TMDEV-250).
import { describe, expect, it } from "vitest";
import { KARAOKE_ACCENT, karaokeWordColor, markerReach, tagScale, tagSeed, tornPolygon } from "./Subtitles";

describe("tags", () => {
  it("gives a word the same tilt and torn edge on every frame and render", () => {
    expect(tagSeed(120, 1)).toBe(tagSeed(120, 1));
    expect(tornPolygon(120)).toBe(tornPolygon(120));
    expect(tornPolygon(120)).not.toBe(tornPolygon(121));
    for (let f = 0; f < 400; f += 7) {
      const v = tagSeed(f, 3);
      expect(v).toBeGreaterThanOrEqual(0);
      expect(v).toBeLessThan(1);
    }
  });

  it("pops from 0.6 past 1 and settles, so a still tag repaints nothing", () => {
    expect(tagScale(0)).toBeCloseTo(0.6);
    expect(Math.max(tagScale(1), tagScale(2), tagScale(3))).toBeGreaterThan(1);
    expect(tagScale(4)).toBe(1);
    expect(tagScale(40)).toBe(1);
  });

  it("tears only the top and bottom edges, inside the tag's box", () => {
    const pts = tornPolygon(77).slice("polygon(".length, -1).split(", ");
    for (const p of pts) {
      const [x, y] = p.split(" ").map((v) => parseFloat(v));
      expect(x).toBeGreaterThanOrEqual(0);
      expect(x).toBeLessThanOrEqual(100);
      expect(y).toBeGreaterThanOrEqual(0);
      expect(y).toBeLessThanOrEqual(100);
    }
  });
});

describe("highlight", () => {
  it("wipes the marker in over a few frames from the word's start, and holds", () => {
    expect(markerReach(9, 10)).toBe(0);
    expect(markerReach(14, 10)).toBeGreaterThan(0);
    expect(markerReach(14, 10)).toBeLessThan(1);
    expect(markerReach(18, 10)).toBe(1);
    expect(markerReach(300, 10)).toBe(1);
  });
});

describe("karaoke", () => {
  it("keeps the text colour until the word's frame, then turns to the accent for good", () => {
    expect(karaokeWordColor(9, 10, "#ffffff", null)).toBe("#ffffff");
    expect(karaokeWordColor(10, 10, "#ffffff", null)).toBe(KARAOKE_ACCENT);
    expect(karaokeWordColor(500, 10, "#ffffff", null)).toBe(KARAOKE_ACCENT);
  });
  it("takes the accent a config names", () => {
    expect(karaokeWordColor(20, 10, "#ffffff", "#ff0000")).toBe("#ff0000");
    expect(KARAOKE_ACCENT).toBe("#FFD221");
  });
});
