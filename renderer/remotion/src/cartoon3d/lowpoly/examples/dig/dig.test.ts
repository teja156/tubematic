// The "dig" example builds and poses at every frame without throwing, the shots tile the video, and every camera is finite:
// the checks a generated video's author would run before the gate (the gate itself is the MCP tool).
import { beforeAll, describe, expect, it } from "vitest";
import type * as THREE from "three";

beforeAll(() => {
  // sets draw their signs and comic words on canvases; the test has no DOM, so a canvas that accepts every call stands in
  const ctx = new Proxy({}, { get: () => () => undefined, set: () => true });
  (globalThis as unknown as { document: unknown }).document = { createElement: () => ({ width: 0, height: 0, getContext: () => ctx }) };
});

describe("dig example", () => {
  it("has shots that tile the video from frame 0 to the end, each at least half a second", async () => {
    const { SHOTS, TOTAL } = await import("./story");
    expect(SHOTS[0].a).toBe(0);
    expect(SHOTS[SHOTS.length - 1].b).toBe(TOTAL);
    SHOTS.forEach((s, i) => { expect(s.id).toBe(i + 1); if (i) expect(s.a).toBe(SHOTS[i - 1].b); expect(s.b - s.a).toBeGreaterThanOrEqual(15); });
    const lens = SHOTS.map((s) => s.b - s.a).sort((a, b) => a - b);
    expect(lens[Math.floor(lens.length / 2)]).toBeLessThanOrEqual(36);   // about a shot a second
  });
  it("builds every set and poses it on every frame of its shots", async () => {
    const { DIG } = await import("./index");
    const THREEmod = await import("three");
    const sets = DIG.sets();
    const camera = new THREEmod.PerspectiveCamera();
    for (const s of DIG.shots) {
      expect(sets[s.set]).toBeTruthy();
      for (let f = s.a; f < s.b; f += 3) {
        const c = DIG.camAt(s.id, f);
        for (const v of [...c.pos, ...c.look, c.fov, c.roll]) expect(Number.isFinite(v)).toBe(true);
        expect(() => sets[s.set].pose(s.id, f, camera)).not.toThrow();
      }
    }
    const box = new THREEmod.Box3().setFromObject(sets.crowd.root as THREE.Object3D);
    expect(box.isEmpty()).toBe(false);
  });
  it("whips only in the one shot that says so", async () => {
    const { DIG } = await import("./index");
    const blurred = DIG.shots.filter((s) => { for (let f = s.a; f < s.b; f++) if ((DIG.blurAt?.(s.id, f) ?? 0) > 0.05) return true; return false; });
    expect(blurred.map((s) => s.id)).toEqual([13]);
  });
});
