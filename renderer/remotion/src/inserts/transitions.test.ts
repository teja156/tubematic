import { describe, expect, it } from "vitest";
import { TRANSITION_FRAMES, activeInsert, glitchBands, heldFrame, insertLook, insertProgress, transitionOf } from "./transitions";

describe("insert transitions", () => {
  it("reads an unknown or missing transition as a cut", () => {
    expect(transitionOf(undefined)).toBe("cut");
    expect(transitionOf("spin")).toBe("cut");
    expect(transitionOf("wipe")).toBe("wipe");
    expect(transitionOf("glitch")).toBe("glitch");
  });

  it("runs the way in before the window and the way out after it, so the whole window is fully in", () => {
    const n = TRANSITION_FRAMES.push;
    expect(insertProgress(-n - 1, 200, n)).toBe(0);
    expect(insertProgress(-n, 200, n)).toBeCloseTo(1 / (n + 1));
    expect(insertProgress(-1, 200, n)).toBeCloseTo(n / (n + 1));
    expect(insertProgress(0, 200, n)).toBe(1);
    expect(insertProgress(199, 200, n)).toBe(1);
    expect(insertProgress(200, 200, n)).toBeCloseTo(n / (n + 1));
    expect(insertProgress(200 + n - 1, 200, n)).toBeCloseTo(1 / (n + 1));
    expect(insertProgress(200 + n, 200, n)).toBe(0);
  });

  it("a cut shows the insert for exactly its window", () => {
    expect(insertProgress(-1, 60, 0)).toBe(0);
    expect(insertProgress(0, 60, 0)).toBe(1);
    expect(insertProgress(59, 60, 0)).toBe(1);
    expect(insertProgress(60, 60, 0)).toBe(0);
  });

  it("a cut covers the frame for the whole window", () => {
    expect(insertLook("cut", insertProgress(0, 100, 0)).covers).toBe(true);
  });

  it("covers the frame only when fully in, so the main is never hidden while it shows", () => {
    for (const t of ["dip", "push", "wipe", "glitch"] as const) {
      expect(insertLook(t, 0.5).covers).toBe(false);
      expect(insertLook(t, 1).covers).toBe(true);
      expect(insertLook(t, 0).insertOpacity).toBe(0);
    }
  });

  it("dips to the canvas before the insert fades up", () => {
    expect(insertLook("dip", 0.25)).toMatchObject({ veilOpacity: 0.5, insertOpacity: 0 });
    expect(insertLook("dip", 0.75)).toMatchObject({ veilOpacity: 1, insertOpacity: 0.5 });
  });

  it("pushes the main out as the insert comes in, and wipes from the right", () => {
    const half = insertLook("push", 0.5);
    expect(half.insertShiftX).toBeCloseTo(540);
    expect(half.mainShiftX).toBeCloseTo(-540);
    expect(insertLook("wipe", 0.5).insertClipLeft).toBeCloseTo(540);
  });

  it("finds the window a frame falls in", () => {
    const windows = [{ startFrame: 100, durationInFrames: 50 }, { startFrame: 400, durationInFrames: 60 }];
    expect(activeInsert(99, windows, "cut")).toBeNull();
    // A wipe starts its way in 12 frames before the window and ends 12 after.
    expect(activeInsert(88, windows, "wipe")).toMatchObject({ index: 0, local: -12 });
    expect(activeInsert(87, windows, "wipe")).toBeNull();
    expect(activeInsert(161, windows, "wipe")).toMatchObject({ index: 0, local: 61 });
    expect(activeInsert(120, windows, "cut")).toMatchObject({ index: 0, local: 20, progress: 1 });
    expect(activeInsert(459, windows, "cut")).toMatchObject({ index: 1 });
    expect(activeInsert(460, windows, "cut")).toBeNull();
  });

  it("tears the insert in over a few frames, more bands each frame, the same way every render", () => {
    expect(TRANSITION_FRAMES.glitch).toBe(4);
    const area = (p: number, frame: number) => {
      const g = glitchBands(p, frame);
      return g.path ? (g.path.match(/M /g) ?? []).length : 0;
    };
    // Deterministic: the same frame gives the same bands.
    expect(glitchBands(0.6, 123)).toEqual(glitchBands(0.6, 123));
    // More of the insert shows each frame: a later frame never shows fewer bands than an earlier one.
    let prev = 0;
    for (const [p, frame] of [[0.1, 10], [0.3, 11], [0.5, 12], [0.7, 13], [0.9, 14]] as const) {
      expect(area(p, frame)).toBeGreaterThanOrEqual(prev);
      prev = area(p, frame);
    }
    expect(area(0.9, 14)).toBeGreaterThan(area(0.1, 10));
    const look = insertLook("glitch", 0.6, 1080, 200);
    expect(look.covers).toBe(false);
    expect(look.mainShiftX).toBe(-look.insertShiftX);
    if (look.insertOpacity > 0) expect(look.insertClipPath).toMatch(/^path\("M /);
    expect(insertLook("glitch", 1, 1080, 200).covers).toBe(true);
  });
});

describe("the held first frame", () => {
  it("holds the frame the first element settles on, through the way in", () => {
    expect(heldFrame(8, 16, 240)).toBe(24);
    expect(heldFrame(12, 0, 240)).toBe(12);
    expect(heldFrame(0, undefined, 240)).toBe(0);
  });
  it("never holds past the window or before the way in ends", () => {
    expect(heldFrame(8, 500, 60)).toBe(8 + 59);
    expect(heldFrame(8, -5, 60)).toBe(8);
  });
  it("holds the first frame for a value that is not a number", () => {
    expect(heldFrame(8, "abc", 60)).toBe(8);
    expect(heldFrame(8, Number.NaN, 60)).toBe(8);
    expect(heldFrame(8, "16", 60)).toBe(24);
  });
});
