// Under the Hood's contract and stage: the facts the MCP validator and the render
// rely on. The shared cases are the ones mcp/tests/test_under_the_hood.py runs.
import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  CAMERA, POSES, TIMING, chartTextWidth, chipBox, counterFits, imageBox, leaderStart, overlaps, plateScale, projectAt,
  statBox, statText,
  type UnderTheHoodData,
} from "./contract";
import { POSE_TABLE } from "./presenter";
import { blinkAt, camAt, counterValue, mouthAt, plateIndexAt, pointAt, poseAt, poseTrack, statValue, underPlateAt } from "./stage";

const ROOT = path.resolve(__dirname, "../../../../../..");
const CASES = JSON.parse(fs.readFileSync(path.join(ROOT, "mcp/tests/fixtures/under_the_hood_contract.json"), "utf8"));
const EXAMPLE = JSON.parse(
  fs.readFileSync(path.join(ROOT, "agent_files/skills/tubematic-under-the-hood/reference/example-config.json"), "utf8"),
);
const DATA: UnderTheHoodData = EXAMPLE.scenes[0].props.underTheHood;
const close = (xs: number[]) => xs.map((v) => expect.closeTo(v, 6));

describe("the shared contract cases", () => {
  it("projects points and boxes the way the validator does", () => {
    for (const c of CASES.project_at) expect(projectAt(c.plate, c.s, c.uv[0], c.uv[1])).toEqual(close(c.point));
    for (const c of CASES.image_box) expect(imageBox(c.plate, c.s)).toEqual(close(c.box));
    for (const c of CASES.plate_scale) expect(plateScale(c.plate, c.t, c.fps)).toBeCloseTo(c.s, 9);
  });

  it("sizes chips, stats and leaders the way the validator does", () => {
    for (const c of CASES.chip_box) expect(chipBox(c.text, c.chip)).toEqual(close(c.box));
    for (const c of CASES.stat_box) expect(statBox(c.stat)).toEqual(close(c.box));
    for (const c of CASES.stat_text) expect(statText(c.value, c.decimals, c.prefix, c.suffix)).toBe(c.text);
    for (const c of CASES.leader_start) expect(leaderStart(c.box, c.target)).toEqual(close(c.point));
    for (const c of CASES.overlaps) expect(overlaps(c.a, c.b)).toBe(c.overlaps);
    for (const c of CASES.chart_text_width) expect(chartTextWidth(c.chart)).toBeCloseTo(c.width, 6);
    for (const c of CASES.counter_fits) expect(counterFits(c.values)).toBe(c.fits);
  });
});

describe("the presenter", () => {
  it("has a drawing for every pose the contract lists", () => {
    expect(Object.keys(POSE_TABLE).sort()).toEqual([...POSES].sort());
  });

  it("starts idle, swaps on the pose's frame with one dissolve frame, then holds", () => {
    const track = poseTrack(DATA);
    expect(poseAt(track, 0)).toEqual({ pose: "idle", dissolveFrom: null });
    const first = track[0];
    expect(poseAt(track, first.frame)).toEqual({ pose: first.pose, dissolveFrom: "idle" });
    expect(poseAt(track, first.frame + 1)).toEqual({ pose: first.pose, dissolveFrom: null });
  });

  it("moves the mouth only while a word is spoken, and blinks for two frames", () => {
    const words = [{ word: "glass", startFrame: 10, endFrame: 20 }];
    expect(mouthAt(words, 5)).toBe(0);
    expect(mouthAt(words, 25)).toBe(0);
    expect(new Set([10, 12, 14, 16, 18].map((f) => mouthAt(words, f))).size).toBeGreaterThan(1);
    const blinks = Array.from({ length: 300 }, (_, f) => blinkAt(f)).filter(Boolean).length;
    expect(blinks).toBeGreaterThanOrEqual(4);
    expect(blinks % 2).toBe(0);
  });
});

describe("the camera", () => {
  const fps = 30;

  it("picks the plate on screen", () => {
    expect(plateIndexAt(DATA, 0)).toBe(0);
    expect(plateIndexAt(DATA, DATA.plates[1].start - 1)).toBe(0);
    expect(plateIndexAt(DATA, DATA.plates[1].start)).toBe(1);
  });

  it("pushes in slowly and keeps a pinned point on its spot", () => {
    const p = DATA.plates[0];
    const a = camAt(DATA, 0, 10, fps), b = camAt(DATA, 0, 70, fps);
    expect(b.scale).toBeGreaterThan(a.scale);
    expect(b.scale / a.scale).toBeCloseTo((1 + (CAMERA.push * 70) / fps) / (1 + (CAMERA.push * 10) / fps), 9);
    expect(pointAt(p, a, 0.5, 0.5)).toEqual(projectAt(p, a.scale, 0.5, 0.5));
  });

  it("rushes into the through point before a zoom cut, then settles the new plate", () => {
    const next = DATA.plates[1];
    expect(next.enter).toBe("zoom");
    const out = camAt(DATA, 0, next.start - 1, fps);
    expect(out.extra).toBeGreaterThan(2);
    // the through point stays where it is while everything else rushes away from it
    const prev = DATA.plates[0];
    const tp = projectAt(prev, out.scale, next.through![0], next.through![1]);
    expect(pointAt(prev, out, next.through![0], next.through![1])).toEqual(close(tp));
    const settle = camAt(DATA, 1, next.start, fps);
    expect(settle.extra).toBeCloseTo(CAMERA.enterFrom, 6);
    expect(camAt(DATA, 1, next.start + TIMING.zoomIn, fps).extra).toBe(1);
  });

  it("draws the previous photograph under a plate only while a cut fades it in", () => {
    // a zoom-through out of a plate that itself came in by a cut must dip to black,
    // never flash the photograph two plates back
    const d: UnderTheHoodData = {
      plates: [
        { start: 0, image: "/a.png", events: [] },
        { start: 60, image: "/b.png", events: [] },
        { start: 120, image: "/c.png", enter: "zoom", through: [0.5, 0.5], events: [] },
      ],
    };
    expect(underPlateAt(d, 1, 60)).toBe(0);
    expect(underPlateAt(d, 1, 60 + TIMING.fade)).toBe(-1);
    expect(camAt(d, 1, 119, 30).opacity).toBeLessThan(1);   // the zoom's dip
    expect(underPlateAt(d, 1, 118)).toBe(-1);
    expect(underPlateAt(d, 1, 119)).toBe(-1);
    expect(underPlateAt(d, 2, 120)).toBe(-1);                // a zoom entrance has nothing under it
  });

  it("cross-fades a cut in over the fade frames", () => {
    const cut = DATA.plates.findIndex((p, i) => i > 0 && (p.enter ?? "cut") === "cut");
    const start = DATA.plates[cut].start;
    expect(camAt(DATA, cut, start, fps).opacity).toBeLessThan(1);
    expect(camAt(DATA, cut, start + TIMING.fade, fps).opacity).toBe(1);
  });
});

describe("numbers", () => {
  it("ticks counters in steps and settles them on their value", () => {
    expect(counterValue(100, 62, 0)).toBe(100);
    expect(counterValue(100, 62, TIMING.tickStep - 1)).toBe(100);
    expect(counterValue(100, 62, TIMING.tickFrames)).toBe(62);
    expect(counterValue(100, 62, 500)).toBe(62);
  });

  it("counts a stat up to exactly its value", () => {
    expect(statValue(0, 5, 0)).toBe(0);
    expect(statValue(0, 5, TIMING.statCount)).toBe(5);
    expect(statValue(0, 5, TIMING.statCount * 3)).toBe(5);
  });
});
