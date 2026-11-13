// The Storybook Reveal contract (TMDEV-231): the shared cases mcp/storybook_reveal.py also runs,
// the reveal's timing on a page, the flood's front and the page curl's shapes.
import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { H, TIMING, W, ZONES, type Page } from "./contract";
import {
  curlShapes, curlTravel, FLOOD_SOFT, FLOOD_WAVE, floodFront, landFrame, pencilProgress, pictureBox, pushScale, pushedBox,
  titleProgress, titleSize,
} from "./stage";

const CASES = JSON.parse(
  fs.readFileSync(path.resolve(__dirname, "../../../../../../mcp/tests/fixtures/storybook_reveal_contract.json"), "utf8"),
);

describe("the shared cases", () => {
  it("sizes the title the same way", () => {
    for (const c of CASES.title_size) expect(titleSize(c.text)).toBe(c.size);
  });
  it("fits the picture in the panel the same way", () => {
    for (const c of CASES.picture_box) pictureBox(c.w, c.h).forEach((v, i) => expect(v).toBeCloseTo(c.box[i], 6));
  });
  it("pushes the picture the same way", () => {
    for (const c of CASES.push_scale) expect(pushScale(c.frame, c.land, c.end)).toBeCloseTo(c.scale, 9);
    for (const c of CASES.pushed_box) {
      pushedBox(c.box, c.scale, c.focus).forEach((v, i) => expect(v).toBeCloseTo(c.out[i], 6));
    }
  });
  it("lands the colour the same way", () => {
    for (const c of CASES.land_frame) expect(landFrame({ colourAt: c.colourAt })).toBe(c.land);
  });
});

const page = (over: Partial<Page> = {}): Page => ({
  start: 100, title: "One Stormy Night", image: "/public/v/images/a.png", pencil: "/public/v/images/treated/a.pencil.png",
  pencilAt: 110, colourAt: 140, ...over,
});

describe("the reveal", () => {
  it("wipes the title in, whole at once on the first page", () => {
    expect(titleProgress(page(), false, 100)).toBe(0);
    expect(titleProgress(page(), false, 100 + TIMING.title)).toBe(1);
    expect(titleProgress(page({ start: 0 }), true, 0)).toBe(1);
  });
  it("wipes the pencil in, whole at frame 0 on a first page that opens on it", () => {
    expect(pencilProgress(page(), false, 109)).toBe(0);
    expect(pencilProgress(page(), false, 110 + TIMING.pencil / 2)).toBe(0.5);
    expect(pencilProgress(page({ start: 0, pencilAt: 0 }), true, 0)).toBe(1);
  });
  it("holds the push until the colour has landed, and never pushes past it", () => {
    expect(pushScale(150, landFrame(page()), 300)).toBe(1);
    expect(pushScale(300, landFrame(page()), 300)).toBeCloseTo(1 + TIMING.push, 9);
    expect(pushScale(900, landFrame(page()), 300)).toBeCloseTo(1 + TIMING.push, 9);
  });
  it("fills the panel's height with a square still, whole and centred", () => {
    const [sx, sy, sw, sh] = pictureBox(1024, 1024);
    expect([sy, sw, sh]).toEqual([0, ZONES.panelHeight, ZONES.panelHeight]);
    expect(sx).toBeCloseTo((ZONES.panelWidth - ZONES.panelHeight) / 2, 9);
  });
  it("keeps a tall still whole inside the panel", () => {
    const [x, y, w, h] = pictureBox(1088, 1920);
    expect(y).toBe(0);
    expect(h).toBe(ZONES.panelHeight);
    expect(x).toBeGreaterThan(0);
    expect(x + w).toBeLessThan(ZONES.panelWidth);
  });
  it("keeps the push's focus point where it was", () => {
    const box: [number, number, number, number] = [237.5, 0, 425, 750];
    const [x, y, w, h] = pushedBox(box, 1.06, [0.3, 0.7]);
    expect(x + 0.3 * w).toBeCloseTo(237.5 + 0.3 * 425, 9);
    expect(y + 0.7 * h).toBeCloseTo(0.7 * 750, 9);
  });
});

describe("the flood and the curl", () => {
  const cw = 924, ch = 774;
  it("starts left of the panel and ends right of it, even at its softest edge", () => {
    expect(Math.max(...floodFront(0, cw, ch, 7, FLOOD_SOFT).map(([x]) => x))).toBeLessThan(0);
    expect(Math.min(...floodFront(1, cw, ch, 7).map(([x]) => x))).toBeGreaterThan(cw);
  });
  it("runs from top to bottom with a ragged edge", () => {
    const front = floodFront(0.5, cw, ch, 7);
    expect(front[0][1]).toBeLessThan(0);
    expect(front[front.length - 1][1]).toBeGreaterThan(ch);
    const xs = front.map(([x]) => x);
    expect(Math.max(...xs) - Math.min(...xs)).toBeGreaterThan(FLOOD_WAVE * 0.5);
  });
  it("turns the old page away over TIMING.curl frames from the bottom-right corner", () => {
    expect(curlTravel(100, 100)).toBe(0);
    const early = curlShapes(curlTravel(103, 100));
    expect(early.flap.length).toBeGreaterThan(2);
    expect(early.keep.some(([x, y]) => x === 0 && y === 0)).toBe(true);
    const done = curlShapes(curlTravel(100 + TIMING.curl, 100));
    expect(done.keep.length).toBe(0);
    for (const [band] of curlShapes(Math.hypot(W, H) / 2).bands) expect(band.length).toBeGreaterThan(2);
  });
  it("draws the flat page with no SVG filter, gradient or blur", () => {
    const src = fs.readFileSync(path.resolve(__dirname, "../StorybookReveal.tsx"), "utf8");
    expect(src).not.toMatch(/<filter|feGaussian|linearGradient|radial-gradient|blur\(|mixBlendMode/);
  });
});
