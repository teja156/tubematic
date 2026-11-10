// Bean Explainer's contract, stage and rig: the facts the MCP validator and the
// render rely on. The shared cases are the ones mcp/tests/test_bean_explainer.py runs.
import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { POSES as POSE_TABLE, blendedPose, blinkAt, headPlace, ik, squashAt } from "./bean";
import { POSES, PROPS, TIMING, beanBox, labelBox, propBox, wrapLabel, type BeanExplainerData, type PropId } from "./contract";
import { DRAWINGS, WHOLE_PROP_ACTS, wholePropMotion } from "./props";
import { settled, stageAt, sectionContentStart } from "./stage";

const ROOT = path.resolve(__dirname, "../../../../../..");
const CASES = JSON.parse(fs.readFileSync(path.join(ROOT, "mcp/tests/fixtures/bean_explainer_contract.json"), "utf8"));
const EXAMPLE = JSON.parse(
  fs.readFileSync(path.join(ROOT, "agent_files/skills/tubematic-bean-explainer/reference/example-config.json"), "utf8"),
);
const DATA: BeanExplainerData = EXAMPLE.scenes[0].props.beanExplainer;
const TOTAL: number = EXAMPLE.totalFrames;

describe("the shared contract cases", () => {
  it("wraps labels the way the validator does", () => {
    for (const c of CASES.wrap_label) expect(wrapLabel(c.text), c.text).toEqual(c.lines);
  });

  it("computes boxes the way the validator does", () => {
    for (const c of CASES.prop_box) expect(propBox(c.prop, c.x, c.y, c.scale)).toEqual(c.box.map((v: number) => expect.closeTo(v, 6)));
    for (const c of CASES.label_box) expect(labelBox(c.text, c.x, c.y)).toEqual(c.box.map((v: number) => expect.closeTo(v, 6)));
    for (const c of CASES.bean_box) expect(beanBox(c.x, c.scale)).toEqual(c.box.map((v: number) => expect.closeTo(v, 6)));
  });
});

describe("the library", () => {
  it("draws every prop the contract lists, and nothing else", () => {
    expect(Object.keys(DRAWINGS).sort()).toEqual(Object.keys(PROPS).sort());
  });

  it("has a pose spec for every pose", () => {
    expect(Object.keys(POSE_TABLE).sort()).toEqual([...POSES].sort());
  });

  it("brings every whole-prop act back to rest after it plays", () => {
    for (const act of WHOLE_PROP_ACTS) {
      const [dx, dy, , s] = wholePropMotion(act, TIMING.actFrames, 300);
      if (act === "swing") continue; // a damped swing is a fixed small angle by then, not a moving one
      expect([dx, dy, s], act).toEqual([0, 0, 1]);
    }
  });
});

describe("the stage", () => {
  it("builds additively inside a shot and starts empty at a cut", () => {
    const early = stageAt(DATA, TOTAL, 130)!;
    const late = stageAt(DATA, TOTAL, 280)!;
    expect(early.props.map((p) => p.key)).toEqual(["phone"]);
    expect(late.props.map((p) => p.key)).toEqual(["phone", "cursor"]);
    expect(late.labels).toHaveLength(1);
    const cut = stageAt(DATA, TOTAL, 330)!;
    expect(cut.props).toHaveLength(0);
  });

  it("plays the carousel at a list section change, and holds content until it ends", () => {
    const s = stageAt(DATA, TOTAL, 300)!;
    expect(s.carousel).toEqual({ from: 0, to: 1, t: 12 });
    expect(stageAt(DATA, TOTAL, 330)!.carousel).toBeNull();
    expect(sectionContentStart(DATA, 1)).toBe(288 + TIMING.carousel);
    expect(sectionContentStart(DATA, 0)).toBe(78);
  });

  it("swaps a pose in a two-frame snap and keeps the latest face", () => {
    const at = (f: number) => stageAt(DATA, TOTAL, f)!.beans[0];
    expect(at(232)).toMatchObject({ pose: "panic", prevPose: "stand", poseT: 0, face: "shocked" });
    expect(at(233).poseT).toBe(0.5);
    expect(at(234).poseT).toBe(1);
  });

  it("clears a bean's marks at its next pose", () => {
    expect(stageAt(DATA, TOTAL, 240)!.beans[0].marks.map((m) => m.type)).toEqual(["sweat", "alarm"]);
    expect(stageAt(DATA, TOTAL, 260)!.beans[0].marks).toEqual([]);
  });
});

describe("the rig", () => {
  it("never reaches past the arm's length", () => {
    const [, hand] = ik([0, 0], [1000, 0], 120, 114, 1);
    expect(Math.hypot(hand[0], hand[1])).toBeLessThan(234);
  });

  it("is still between swaps: no squash after the snap, a settled spring is exactly 1", () => {
    expect(squashAt(100, 80)).toEqual([1, 1]);
    expect(settled(0.9993, TIMING.settle)).toBe(1);
    expect(settled(0.5, 3)).toBe(0.5);
  });

  it("blinks briefly and rarely", () => {
    let closed = 0;
    for (let f = 0; f < 900; f++) if (blinkAt(f, 3) > 0) closed++;
    expect(closed).toBeGreaterThan(20);
    expect(closed).toBeLessThan(70);
  });

  it("places the head where the drawing does", () => {
    const pose = blendedPose({ pose: "stand", prevPose: "stand", poseT: 1, frame: 0 });
    expect(headPlace(pose)).toEqual({ at: [0, -578], rot: 0 });
  });
});

it("keeps every library prop's text slot within the validator's limits", () => {
  for (const [id, p] of Object.entries(PROPS) as [PropId, (typeof PROPS)[PropId]][]) {
    expect(p.text, id).toBeGreaterThanOrEqual(0);
    expect(p.w * p.h, id).toBeGreaterThan(0);
  }
});
