// Night Signal's contract, stage and library: the facts the MCP validator and
// the render rely on. The shared cases are the ones mcp/tests/test_night_signal.py runs.
import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  ANIMAL_NAMES, BUBBLES, CAMERA, CUTS, GEOMETRY, LIMITS, MARKS, OBJECT_NAMES, PEOPLE, SCENE_KINDS, SCREENS, SETTINGS, SHAPES,
  SLOTS, TIMING, TONES, eventFrames, fitFontSize, timecode, type NightSignalData,
} from "./contract";
import { clockText } from "./draw";
import { libraryShapes, shapesBox } from "./parts";
import { itemAt, pushAt, quietSpans, sceneIndexAt, tearAt } from "./stage";

const ROOT = path.resolve(__dirname, "../../../../../..");
const CASES = JSON.parse(fs.readFileSync(path.join(ROOT, "mcp/tests/fixtures/night_signal_contract.json"), "utf8"));
const PACK = JSON.parse(fs.readFileSync(path.join(ROOT, "tubematic_core/style_packs/night_signal.json"), "utf8"));
const REF = path.join(ROOT, "agent_files/skills/tubematic-night-signal/reference");
const EXAMPLE = JSON.parse(fs.readFileSync(path.join(REF, "example-config.json"), "utf8"));
const DATA: NightSignalData = EXAMPLE.scenes[0].props.nightSignal;

describe("the shared contract", () => {
  it("has the constants the validator uses", () => {
    expect(CASES.constants).toEqual(JSON.parse(JSON.stringify({ LIMITS, TIMING, CAMERA, GEOMETRY })));
  });

  it("works out events, still stretches, tears, items, timecodes and fits the way the validator does", () => {
    const data = CASES.data as NightSignalData;
    expect(data.scenes.map((s) => eventFrames(s))).toEqual(CASES.event_frames);
    expect(quietSpans(data, CASES.total)).toEqual(CASES.quiet_spans);
    for (const c of CASES.tear_at) {
      const t = tearAt(data, c.frame);
      expect(t ? [t.into, t.progress] : null, `frame ${c.frame}`).toEqual(c.tear);
    }
    const item = data.scenes[0].kind === "tableau" ? data.scenes[0].items[1] : null;
    for (const c of CASES.item_at) {
      const s = itemAt(item!, c.frame);
      expect({ frame: c.frame, visible: s.visible, x: s.x, red: s.red }).toEqual(c);
    }
    for (const c of CASES.timecode) expect(timecode(c.clock ?? undefined, c.frame, 30)).toBe(c.text);
    for (const c of CASES.fit_font_size) expect(fitFontSize(c.text, c.size)).toBe(c.fit);
  });
});

describe("the pack", () => {
  it("lists exactly what the renderer draws", () => {
    expect(PACK.extra).toEqual({
      people: [...PEOPLE], animals: [...ANIMAL_NAMES], objects: [...OBJECT_NAMES], sceneKinds: [...SCENE_KINDS],
      settings: [...SETTINGS], slots: [...SLOTS], screens: [...SCREENS], marks: [...MARKS], cuts: [...CUTS],
      bubbles: [...BUBBLES], shapes: [...SHAPES], tones: [...TONES],
    });
  });

  it("draws every library part it lists", () => {
    for (const name of [...PEOPLE, ...ANIMAL_NAMES, ...OBJECT_NAMES]) {
      if (name === "qr") continue; // drawn as itself, not from shapes
      const shapes = libraryShapes(name);
      expect(shapes, name).not.toBeNull();
      expect(shapes!.length, name).toBeGreaterThan(0);
    }
  });

  it("keeps every library part inside the box a custom part is held to, standing on the ground", () => {
    const half = LIMITS.partBox / 2;
    for (const name of [...PEOPLE, ...ANIMAL_NAMES, ...OBJECT_NAMES]) {
      if (name === "qr") continue;
      const [x0, y0, x1, y1] = shapesBox(libraryShapes(name)!);
      expect(x0, name).toBeGreaterThanOrEqual(-half - 20);
      expect(x1, name).toBeLessThanOrEqual(half + 20);
      expect(y0, name).toBeGreaterThanOrEqual(-LIMITS.partBox - 20);
      expect(y1, name).toBeLessThanOrEqual(20);
    }
  });
});

describe("the stage", () => {
  it("runs a camera clock on through its minutes and hours", () => {
    expect(clockText("03:12", 0, 30)).toBe("3:12:00 AM");
    expect(clockText("03:12", 30 * 60, 30)).toBe("3:13:00 AM");
    expect(clockText("11:59", 30 * 60, 30)).toBe("12:00:00 PM");
  });

  it("knows which scene is on screen", () => {
    expect(sceneIndexAt(DATA, 0)).toBe(0);
    expect(sceneIndexAt(DATA, DATA.scenes[2].start)).toBe(2);
    expect(sceneIndexAt(DATA, DATA.scenes[2].start - 1)).toBe(1);
  });

  it("tears into a scene around its start and not at a hard cut", () => {
    const s = DATA.scenes[1].start;
    expect(tearAt(DATA, s - TIMING.tearBefore - 1)).toBeNull();
    expect(tearAt(DATA, s)?.into).toBe(1);
    expect(tearAt(DATA, s + TIMING.tearAfter + 1)).toBeNull();
    const hard: NightSignalData = { ...DATA, scenes: DATA.scenes.map((x, i) => (i === 1 ? { ...x, cut: "hard" as const } : x)) };
    expect(tearAt(hard, s)).toBeNull();
  });

  it("pushes in slowly over a scene, never past CAMERA.push", () => {
    expect(pushAt(0, 100, 0)).toBe(1);
    expect(pushAt(0, 100, 100)).toBeCloseTo(CAMERA.push);
    expect(pushAt(0, 100, 50)).toBeGreaterThan(1);
    expect(pushAt(0, 100, 200)).toBeCloseTo(CAMERA.push);
  });

  it("pops an item in with an overshoot, walks it on its step and reddens the threat", () => {
    const item = { what: "person", slot: "left" as const, at: 10, threat: true, redAt: 20, to: { slot: "center" as const, at: 30 } };
    expect(itemAt(item, 9).visible).toBe(false);
    const popped = [...Array(TIMING.pop + 1).keys()].map((k) => itemAt(item, 10 + k).scale);
    expect(Math.max(...popped)).toBeGreaterThan(1);
    expect(itemAt(item, 10 + TIMING.pop).scale).toBeCloseTo(1);
    expect(itemAt(item, 19).red).toBe(0);
    expect(itemAt(item, 20 + TIMING.redden).red).toBe(1);
    expect(itemAt(item, 30 + TIMING.step).x).toBe(GEOMETRY.slotX.center);
    expect(itemAt({ what: "door", slot: "left", threat: false }, 0).red).toBe(0);
  });
});
