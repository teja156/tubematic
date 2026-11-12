import { describe, expect, it } from "vitest";
import { TRANSITION_FRAMES, activeInsert, insertLook, insertProgress, transitionOf } from "./transitions";

describe("insert transitions", () => {
  it("reads an unknown or missing transition as a cut", () => {
    expect(transitionOf(undefined)).toBe("cut");
    expect(transitionOf("spin")).toBe("cut");
    expect(transitionOf("wipe")).toBe("wipe");
  });

  it("runs the way in over the first frames and the way out over the last", () => {
    const n = TRANSITION_FRAMES.dip;
    expect(insertProgress(-1, 200, n)).toBe(0);
    expect(insertProgress(0, 200, n)).toBeCloseTo(1 / n);
    expect(insertProgress(n - 1, 200, n)).toBe(1);
    expect(insertProgress(100, 200, n)).toBe(1);
    expect(insertProgress(199, 200, n)).toBeCloseTo(1 / n);
    expect(insertProgress(200, 200, n)).toBe(0);
  });

  it("shares a very short window between the way in and the way out", () => {
    expect(insertProgress(5, 10, 12)).toBe(1);
    expect(insertProgress(0, 10, 12)).toBeCloseTo(1 / 5);
  });

  it("a cut covers the frame for the whole window", () => {
    expect(insertLook("cut", insertProgress(0, 100, 0)).covers).toBe(true);
  });

  it("covers the frame only when fully in, so the main is never hidden while it shows", () => {
    for (const t of ["dip", "push", "wipe"] as const) {
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
    expect(activeInsert(120, windows, "cut")).toMatchObject({ index: 0, local: 20, progress: 1 });
    expect(activeInsert(459, windows, "cut")).toMatchObject({ index: 1 });
    expect(activeInsert(460, windows, "cut")).toBeNull();
  });
});
