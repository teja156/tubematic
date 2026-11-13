// Process Cast's contract, stage and library: the facts the MCP validator and the
// render rely on. The shared cases are the ones mcp/tests/test_process_cast.py runs.
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  ACCESSORIES, BODIES, CAMERA_MOVES, CUSTOM, ENTRANCES, EVENT_TYPES, FACES, GEOMETRY, LIMITS, MARKS, PROPS, STATIONS, TIMING, TINTS,
  bodySize, cloneId, propCentre, slotCount, slotX, type ProcessCastData,
} from "./contract";
import { PROP_DRAWINGS } from "./props";
import { blinkAt, castAt, focusAt } from "./stage";
import { FURNITURE } from "./stations";

const ROOT = path.resolve(__dirname, "../../../../../..");
const CASES = JSON.parse(fs.readFileSync(path.join(ROOT, "mcp/tests/fixtures/process_cast_contract.json"), "utf8"));
const PACK = JSON.parse(fs.readFileSync(path.join(ROOT, "tubematic_core/style_packs/process_cast.json"), "utf8"));
const REF = path.join(ROOT, "agent_files/skills/tubematic-process-cast/reference");
const EXAMPLE = JSON.parse(fs.readFileSync(path.join(REF, "example-config.json"), "utf8"));
const DATA: ProcessCastData = EXAMPLE.scenes[0].props.processCast;
const at = (type: string, n = 0) => DATA.events.filter((e) => e.type === type)[n].frame;

describe("the shared contract", () => {
  it("has the constants the validator uses", () => {
    expect(CASES.constants).toEqual(JSON.parse(JSON.stringify({
      LIMITS, TIMING, GEOMETRY, BODIES, TINTS, ACCESSORIES, FACES, MARKS, ENTRANCES, CAMERA_MOVES, EVENT_TYPES, STATIONS, PROPS, CUSTOM,
    })));
  });

  it("works out sizes, slots and props the way the validator does", () => {
    for (const c of CASES.body_size) expect(bodySize(c.body, c.units)).toEqual(c.size);
    for (const c of CASES.slot_x) expect(slotX(c.index, c.kind, c.slot)).toBe(c.x);
    for (const c of CASES.slot_count) expect(slotCount(c.kind)).toBe(c.n);
    for (const c of CASES.prop_centre) expect(propCentre(c.index, c.kind, PROPS[c.prop as keyof typeof PROPS])).toEqual(c.centre);
    for (const c of CASES.clone_id) expect(cloneId(c.who, c.n)).toBe(c.id);
    for (const c of CASES.blink) expect(blinkAt(c.frame, c.seed)).toBe(c.blink);
  });

  it("is what character-tools/sync-contract.mjs writes today", () => {
    const files = ["mcp/tests/fixtures/process_cast_contract.json", "tubematic_core/style_packs/process_cast.json"];
    const before = files.map((f) => fs.readFileSync(path.join(ROOT, f), "utf8"));
    execFileSync(process.execPath, ["character-tools/sync-contract.mjs", "process_cast"], { cwd: path.join(ROOT, "renderer/remotion") });
    expect(files.map((f) => fs.readFileSync(path.join(ROOT, f), "utf8"))).toEqual(before);
  });
});

describe("the library", () => {
  it("draws every prop and every furniture kind the contract lists", () => {
    expect(Object.keys(PROP_DRAWINGS).sort()).toEqual(Object.keys(PROPS).sort());
    expect(Object.keys(PACK.extra.props).sort()).toEqual(Object.keys(PROPS).sort());
    expect(Object.keys(FURNITURE).sort()).toEqual(Object.keys(STATIONS).filter((k) => k !== "stage").sort());
  });
});

describe("the stage", () => {
  it("brings the first actor in at frame 0 at the first station, with the camera there", () => {
    const s = castAt(DATA, 0);
    expect(s.camX).toBe(0);
    expect(s.actors.map((a) => a.id)).toEqual(["bit"]);
  });

  it("splits into clones that flash as silhouettes, then merges them back", () => {
    const split = at("clone");
    const first = castAt(DATA, split);
    expect(first.actors.filter((a) => a.id.startsWith("bit")).length).toBe(3);
    expect(first.actors.find((a) => a.id === "bit2")!.silhouette).toBe(true);
    expect(castAt(DATA, split + TIMING.silhouette).actors.find((a) => a.id === "bit2")!.silhouette).toBe(false);
    const merged = castAt(DATA, at("merge") + TIMING.merge);
    expect(merged.actors.map((a) => a.id)).toEqual(["bit"]);
  });

  it("takes the clones off with their original when it exits", () => {
    const split = at("clone");
    const data: ProcessCastData = { ...DATA, events: DATA.events.filter((e) => e.frame <= split).concat([{ type: "exit" as const, frame: split + 20, who: "bit" }]) };
    expect(castAt(data, split + 20 + TIMING.enter).actors).toHaveLength(0);
  });

  it("adds the cubes up once two units bodies have joined", () => {
    const f = at("join");
    expect(castAt(DATA, f).actors.find((a) => a.id === "bit")!.units).toBe(4);
    const after = castAt(DATA, f + TIMING.merge);
    expect(after.actors.find((a) => a.id === "bit")!.units).toBe(8);
    expect(after.actors.find((a) => a.id === "more")).toBeUndefined();
  });

  it("glides the camera to the next station while the actor makes the trip", () => {
    const f = at("camera");
    const mid = castAt(DATA, f + TIMING.glide / 2);
    expect(mid.camX).toBeGreaterThan(0);
    expect(mid.camX).toBeLessThan(GEOMETRY.stationGap);
    const end = castAt(DATA, f + TIMING.trip);
    expect(end.camX).toBe(GEOMETRY.stationGap);
    expect(end.actors.find((a) => a.id === "bit")!.x).toBe(slotX(1, "desk", 1));
    expect(end.props).toHaveLength(0);
    expect(castAt(DATA, at("prop") + 1).props[0].prop).toBe("card");
  });

  it("keeps a focus until it is cleared", () => {
    const data: ProcessCastData = { ...DATA, events: [...DATA.events, { type: "focus" as const, frame: 50, who: "bit" }].sort((a, b) => a.frame - b.frame) };
    expect(focusAt(data, 49)).toBe("");
    expect(focusAt(data, 60)).toBe("bit");
  });

  it("ends a focus when its actor leaves, so the others at its station are not left shrunk", () => {
    const events = [
      { type: "enter" as const, frame: 0, who: "bit", station: DATA.stations[0].id, slot: 1 },
      { type: "enter" as const, frame: 10, who: "more", station: DATA.stations[0].id, slot: 3 },
      { type: "focus" as const, frame: 30, who: "bit" },
      { type: "exit" as const, frame: 60, who: "bit" },
    ];
    const data: ProcessCastData = { ...DATA, events };
    const more = (f: number) => castAt(data, f).actors.find((a) => a.id === "more")!.scale;
    expect(more(40)).toBeLessThan(1);
    expect(more(61)).toBe(GEOMETRY.stageScale);
  });
});
