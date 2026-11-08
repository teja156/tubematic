// The camera grammar a video's camAt is built from (camera.ts): the facts a shot plan relies on.
import { describe, expect, it } from "vitest";
import { dofAtOf, glide, kicksAt, keyEnd, layersAt, lin, runKeys, shotAt, type Key } from "./camera";
import type { ShotDef } from "./video";

const SHOTS: ShotDef[] = [
  { id: 1, a: 0, b: 100, light: "day", set: "street", note: "a" },
  { id: 2, a: 100, b: 200, light: "day", set: "street", note: "b" },
  { id: 3, a: 200, b: 300, light: "golden", set: "river", note: "c" },
];

describe("glides", () => {
  it("are symmetric smootherstep: 0 at the start, 1 at the end, half way at the middle", () => {
    expect(glide(0)).toBe(0);
    expect(glide(1)).toBe(1);
    expect(glide(0.5)).toBeCloseTo(0.5);
    expect(glide(2)).toBe(1);   // clamped
    expect(glide(0.25)).toBeLessThan(0.25);   // slow start
  });
  it("a key glides in from its frame over dur frames and a cut lands at once", () => {
    const keys: Key[] = [
      { f: 0, s: () => ({ pos: [0, 2, 10], look: [0, 1, 0] }) },
      { f: 50, dur: 20, s: () => ({ pos: [10, 2, 10], look: [10, 1, 0] }) },
      { f: 90, cut: true, s: () => ({ pos: [50, 2, 10], look: [50, 1, 0], fov: 30 }) },
    ];
    expect(runKeys(keys, 10).pos[0]).toBe(0);
    expect(runKeys(keys, 50).pos[0]).toBe(0);
    expect(runKeys(keys, 60).pos[0]).toBeCloseTo(5);
    expect(runKeys(keys, 70).pos[0]).toBeCloseTo(10);
    expect(runKeys(keys, 89).fov).toBe(40);   // the default lens
    expect(runKeys(keys, 90)).toMatchObject({ pos: [50, 2, 10], fov: 30, roll: 0 });
    expect(keyEnd(keys, 55)).toBe(70);
    expect(keyEnd(keys, 95)).toBe(95);
  });
});

describe("kicks", () => {
  it("start on the first frame at or after the event, flip sign every frame and die in seven", () => {
    const kicks: [number, number][] = [[1.0, 1]];
    expect(kicksAt(kicks, 0.9)).toBe(0);
    expect(kicksAt(kicks, 1.0)).toBeCloseTo(1);
    expect(kicksAt(kicks, 1 + 1 / 30)).toBeLessThan(0);
    expect(kicksAt(kicks, 1 + 2 / 30)).toBeGreaterThan(0);
    expect(kicksAt(kicks, 1 + 7 / 30)).toBe(0);
  });
});

describe("shots in time", () => {
  it("finds the shot of a frame and holds the last one past the end", () => {
    expect(shotAt(SHOTS, 0).id).toBe(1);
    expect(shotAt(SHOTS, 100).id).toBe(2);
    expect(shotAt(SHOTS, 299).id).toBe(3);
    expect(shotAt(SHOTS, 1000).id).toBe(3);
  });
  it("a crossfade draws the previous shot under the next one, centred on the boundary", () => {
    expect(layersAt(SHOTS, {}, 150)).toEqual([{ id: 2, alpha: 1 }]);
    const layers = layersAt(SHOTS, { 3: 20 }, 195);
    expect(layers.map((l) => l.id)).toEqual([2, 3]);
    expect(layers[1].alpha).toBeGreaterThan(0.2);
    expect(layers[1].alpha).toBeLessThan(0.4);
    expect(layersAt(SHOTS, { 3: 20 }, 189)).toEqual([{ id: 2, alpha: 1 }]);
    expect(layersAt(SHOTS, { 3: 20 }, 210)).toEqual([{ id: 3, alpha: 1 }]);
  });
});

describe("tables", () => {
  it("lin interpolates and clamps at both ends", () => {
    const t: [number, number][] = [[0, 0], [10, 100], [20, 100]];
    expect(lin(t, -5)).toBe(0);
    expect(lin(t, 5)).toBe(50);
    expect(lin(t, 15)).toBe(100);
    expect(lin(t, 50)).toBe(100);
  });
  it("the lens table eases cInf in from the previous entry over dur", () => {
    const d = dofAtOf([{ f: 0, cInf: 0 }, { f: 100, dur: 10, cInf: 12 }], 105);
    expect(d.cInf).toBeCloseTo(6);
    expect(dofAtOf([{ f: 0, cInf: 0 }, { f: 100, dur: 10, cInf: 12 }], 50).cInf).toBe(0);
    expect(dofAtOf([{ f: 0, cInf: 0 }, { f: 100, dur: 10, cInf: 12 }], 500).cInf).toBe(12);
  });
});
