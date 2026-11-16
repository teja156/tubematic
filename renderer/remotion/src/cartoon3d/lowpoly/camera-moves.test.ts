import { describe, expect, it } from "vitest";
import { joltAt, JOLT_FRAMES, jolted, whip, type Cam } from "../camera";

const cam = (x: number): Cam => ({ pos: [x, 2, 10], look: [x, 1, 0], fov: 40, roll: 0 });

describe("jolt", () => {
  it("starts up on the hit, rings and is gone after JOLT_FRAMES", () => {
    expect(joltAt([10], 9)).toBe(0);
    expect(joltAt([10], 10)).toBeGreaterThan(0.9);
    expect(joltAt([10], 12)).toBeLessThan(0);   // the swing goes through zero
    expect(joltAt([10], 10 + JOLT_FRAMES)).toBe(0);
  });
  it("hits add, so footsteps 11 frames apart do not overlap but a double hit does", () => {
    expect(joltAt([10, 21], 21)).toBeCloseTo(joltAt([10], 10));
    expect(joltAt([10, 10], 10)).toBeCloseTo(2 * joltAt([10], 10));
  });
  it("moves the camera and its look point up and down together, so the view does not tilt", () => {
    const c = jolted(cam(0), 1);
    expect(c.pos[1]).toBeGreaterThan(2);
    expect(c.pos[1] - 2).toBeCloseTo(c.look[1] - 1);
    expect(jolted(cam(0), 0)).toEqual(cam(0));
  });
});

describe("whip", () => {
  it("holds before, lands after, and is fastest (most blurred) in the middle", () => {
    const a = cam(0), b = cam(10);
    expect(whip(a, b, 5, 10).cam.pos[0]).toBe(0);
    expect(whip(a, b, 5, 10).blur).toBe(0);
    expect(whip(a, b, 22, 10).cam.pos[0]).toBe(10);
    expect(whip(a, b, 22, 10).blur).toBe(0);
    expect(whip(a, b, 16, 10).blur).toBeGreaterThan(0.95);
    expect(whip(a, b, 16, 10).cam.pos[0]).toBeCloseTo(5);
    expect(whip(a, b, 11, 10).blur).toBeLessThan(0.1);
  });
});
