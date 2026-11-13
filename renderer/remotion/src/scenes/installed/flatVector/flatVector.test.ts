// Flat Vector Science's contract, stage and library: the facts the MCP validator
// and the render rely on. The shared cases are the ones mcp/tests/test_flat_vector_science.py runs.
import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  BACKDROPS, CATALOGUE, CUTS, GEOMETRY, LIMITS, SHOT_KINDS, SIZES, SLOTS, TIMING, eventFrames, grouped, pillWidth, propScale,
  type FlatVectorData, type LadderShot,
} from "./contract";
import { BACKDROP } from "./draw";
import { PROPS } from "./props";
import { counterValue, depthAt, drift, itemScale, pictureAts, quietSpans, shotIndexAt, stepAt, transitionAt } from "./stage";

const ROOT = path.resolve(__dirname, "../../../../../..");
const CASES = JSON.parse(fs.readFileSync(path.join(ROOT, "mcp/tests/fixtures/flat_vector_science_contract.json"), "utf8"));
const PACK = JSON.parse(fs.readFileSync(path.join(ROOT, "tubematic_core/style_packs/flat_vector_science.json"), "utf8"));
const REF = path.join(ROOT, "agent_files/skills/tubematic-flat-vector-science/reference");
const EXAMPLE = JSON.parse(fs.readFileSync(path.join(REF, "example-config.json"), "utf8"));
const DATA: FlatVectorData = EXAMPLE.scenes[0].props.flatVector;

describe("the shared contract", () => {
  it("has the constants the validator uses", () => {
    expect(CASES.constants).toEqual(JSON.parse(JSON.stringify({ LIMITS, TIMING, GEOMETRY })));
  });

  it("works out events, still stretches, counters, steps and widths the way the validator does", () => {
    const data = CASES.data as FlatVectorData;
    expect(data.shots.map((s) => eventFrames(s))).toEqual(CASES.event_frames);
    expect(quietSpans(data, CASES.total)).toEqual(CASES.quiet_spans);
    for (const c of CASES.counter_value) expect(counterValue(data.shots[0].counter!, c.frame, 500)).toBeCloseTo(c.value);
    for (const c of CASES.step_at) expect(stepAt([210, 260], c.frame)).toEqual({ index: c.index, progress: c.progress });
    for (const c of CASES.pill_width) expect(pillWidth(c.parts)).toBe(c.width);
    for (const c of CASES.grouped) expect(grouped(c.n)).toBe(c.text);
  });
});

describe("the pack and the library", () => {
  it("lists exactly what the renderer draws", () => {
    expect(PACK.extra.props).toEqual(CATALOGUE);
    expect(PACK.extra.boxes).toEqual(Object.fromEntries(Object.entries(PROPS).map(([k, p]) => [k, p.box])));
    expect(PACK.extra.shotKinds).toEqual([...SHOT_KINDS]);
    expect(PACK.extra.backdrops).toEqual([...BACKDROPS]);
    expect(PACK.extra.slots).toEqual([...SLOTS]);
    expect(PACK.extra.sizes).toEqual([...SIZES]);
    expect(PACK.extra.cuts).toEqual([...CUTS]);
  });

  it("gives every backdrop a look and every prop a group, a box and a drawing", () => {
    for (const b of BACKDROPS) expect(BACKDROP[b]).toBeDefined();
    for (const [name, p] of Object.entries(PROPS)) {
      expect(p.box[0] * p.box[1], name).toBeGreaterThan(0);
      expect(p.draw(), name).toBeTruthy();
    }
    expect(Object.keys(PROPS).length).toBeGreaterThanOrEqual(40);
  });

  it("draws a prop's longest side at its size", () => {
    for (const c of CASES.prop_scale) expect(propScale(PROPS[c.what].box, c.size)).toBeCloseTo(c.scale);
    expect(propScale([960, 300], "l") * 960).toBeCloseTo(GEOMETRY.size.l);
  });
});

describe("the stage", () => {
  it("knows which shot is on screen and runs each transition at its own frames", () => {
    expect(shotIndexAt(DATA, 0)).toBe(0);
    const lensShot = DATA.shots.findIndex((s) => s.cut === "lens");
    const s = DATA.shots[lensShot].start;
    expect(transitionAt(DATA, s - TIMING.lens - 1)).toBeNull();
    expect(transitionAt(DATA, s - 1)).toMatchObject({ into: lensShot, kind: "lens" });
    expect(transitionAt(DATA, s)).toBeNull();
    const flashShot = DATA.shots.findIndex((x) => x.cut === "flash");
    expect(transitionAt(DATA, DATA.shots[flashShot].start)).toMatchObject({ into: flashShot, kind: "flash" });
  });

  it("opens a ladder on its first picture even before the first rung's word", () => {
    const ladder = DATA.shots.find((x) => x.kind === "ladder") as LadderShot;
    expect(pictureAts(ladder)[0]).toBe(ladder.start);
    expect(stepAt(pictureAts(ladder), ladder.start).index).toBe(0);
  });

  it("pops an item in with an overshoot, and drifts without ever standing still", () => {
    const pops = [...Array(TIMING.pop + 1).keys()].map((k) => itemScale({ what: "whale", slot: "center", size: "l", at: 10 }, 10 + k));
    expect(Math.max(...pops)).toBeGreaterThan(1);
    expect(itemScale({ what: "whale", slot: "center", size: "l", at: 10 }, 9)).toBeCloseTo(0);
    const a = drift(0, 1), b = drift(40, 1);
    expect(a.dx === b.dx && a.dy === b.dy).toBe(false);
  });

  it("rolls a descent's depth from one layer to the next", () => {
    const shot = { kind: "descent" as const, start: 0, backdrop: "ocean" as const, label: "DEPTH", unit: "m",
      layers: [{ name: "A", value: 40, at: 10 }, { name: "B", value: 2000, at: 100 }] };
    expect(depthAt(shot, 5)).toBe(0);
    expect(depthAt(shot, 10 + TIMING.rung)).toBe(40);
    expect(depthAt(shot, 100 + TIMING.rung)).toBe(2000);
  });
});
