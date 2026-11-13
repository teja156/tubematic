// Mid-century How-To's contract, stage and library: the facts the MCP validator and
// the render rely on. The shared cases are the ones mcp/tests/test_midcentury_howto.py runs.
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  AIM_POSES, CUSTOM, ENTRANCES, EVENT_TYPES, FACES, GEOMETRY, GROUNDS, HAIRS, LIMITS, OBJECTS, OBJECT_SCALE, OUTFITS, POSES,
  SIDES, SUMMARY_POSES, TIMING, inReach, insetBox, labelBox, objectBox, presenterBox, screenLines, type MidcenturyData,
} from "./contract";
import { DRAWINGS } from "./objects";
import { poseArm, presenterBoxFor } from "./presenter";
import { blinkAt, pressPoint, pressReach, segmentAt, stageAt } from "./stage";

const ROOT = path.resolve(__dirname, "../../../../../..");
const CASES = JSON.parse(fs.readFileSync(path.join(ROOT, "mcp/tests/fixtures/midcentury_howto_contract.json"), "utf8"));
const PACK = JSON.parse(fs.readFileSync(path.join(ROOT, "tubematic_core/style_packs/midcentury_howto.json"), "utf8"));
const REF = path.join(ROOT, "agent_files/skills/tubematic-midcentury-howto/reference");
const EXAMPLE = JSON.parse(fs.readFileSync(path.join(REF, "example-config.json"), "utf8"));
const DATA: MidcenturyData = EXAMPLE.scenes[0].props.midcenturyHowTo;
const TOTAL: number = EXAMPLE.totalFrames;

describe("the shared contract", () => {
  it("has the constants the validator uses", () => {
    expect(CASES.constants).toEqual(JSON.parse(JSON.stringify({
      LIMITS, TIMING, GEOMETRY, GROUNDS, EVENT_TYPES, POSES, SUMMARY_POSES, AIM_POSES, FACES, OUTFITS, HAIRS, SIDES, ENTRANCES,
      OBJECTS, OBJECT_SCALE, CUSTOM,
    })));
  });

  it("works out the geometry the way the validator does", () => {
    for (const c of CASES.object_box) expect(objectBox(c.object, c.x, c.y, c.scale)).toEqual(c.box);
    for (const c of CASES.label_box) expect(labelBox(c.text, c.x, c.y)).toEqual(c.box);
    for (const c of CASES.inset_box) expect(insetBox(c.x, c.y)).toEqual(c.box);
    for (const c of CASES.presenter_box) expect(presenterBox(c.side)).toEqual(c.box);
    for (const c of CASES.in_reach) expect(inReach(c.side, c.x, c.y)).toBe(c.reach);
    for (const c of CASES.screen_lines) expect(screenLines(c.text)).toEqual(c.lines);
    for (const c of CASES.blink) expect(blinkAt(c.frame, c.seed)).toBe(c.blink);
  });

  it("is what character-tools/sync-contract.mjs writes today", () => {
    // The fixture and the pack's extra are written by the sync script; a stale one fails here.
    const before = [fs.readFileSync(path.join(ROOT, "mcp/tests/fixtures/midcentury_howto_contract.json"), "utf8"),
      fs.readFileSync(path.join(ROOT, "tubematic_core/style_packs/midcentury_howto.json"), "utf8")];
    execFileSync(process.execPath, ["character-tools/sync-contract.mjs", "midcentury_howto"], { cwd: path.join(ROOT, "renderer/remotion") });
    const after = [fs.readFileSync(path.join(ROOT, "mcp/tests/fixtures/midcentury_howto_contract.json"), "utf8"),
      fs.readFileSync(path.join(ROOT, "tubematic_core/style_packs/midcentury_howto.json"), "utf8")];
    expect(after).toEqual(before);
  });
});

describe("the library", () => {
  it("draws every object the contract and the pack list", () => {
    expect(Object.keys(DRAWINGS).sort()).toEqual(Object.keys(OBJECTS).sort());
    expect(Object.keys(PACK.extra.objects).sort()).toEqual(Object.keys(OBJECTS).sort());
  });

  it("gives each act its own name, and a screen's rows match its text slot", () => {
    for (const [id, o] of Object.entries(OBJECTS)) expect(new Set(o.acts).size, id).toBe(o.acts.length);
    expect(OBJECTS.phone.acts).toContain("row3");
  });
});

describe("the presenter", () => {
  it("aims the point and present poses at the object", () => {
    const aimed = poseArm("point", [600, -500]).arm;
    expect(aimed.glove).toBe("point");
    expect(aimed.wrist[0]).toBeGreaterThan(200);
    expect(poseArm("stand", null).arm.wrist[1]).toBeGreaterThan(-400);
  });

  it("draws each pose in a box no larger than its reach needs", () => {
    const stand = presenterBoxFor(poseArm("stand", null).arm, "hang");
    const reach = presenterBoxFor(poseArm("point", [470, -588]).arm, "hang");
    expect(stand.width * stand.height).toBeLessThan(reach.width * reach.height);
    for (const pose of POSES) {
      const { arm, back } = poseArm(pose, [300, -600], 4);
      const b = presenterBoxFor(arm, back);
      expect(b.left).toBeLessThanOrEqual(arm.wrist[0] - 120);
      expect(b.left + b.width).toBeGreaterThanOrEqual(arm.wrist[0] + 120);
      expect(b.top).toBeLessThanOrEqual(Math.min(-880, arm.wrist[1] - 120));
    }
  });
});

describe("the stage", () => {
  it("opens on the title card, walks the steps and ends on the summary", () => {
    expect(segmentAt(DATA, 0)).toEqual({ kind: "intro" });
    expect(segmentAt(DATA, DATA.steps[1].start)).toEqual({ kind: "step", index: 1 });
    expect(segmentAt(DATA, TOTAL - 1)).toEqual({ kind: "summary" });
  });

  it("puts the presenter on the right on the summary card, and none in a close-up", () => {
    expect(stageAt(DATA, TOTAL, TOTAL - 1)!.presenter!.side).toBe("right");
    expect(stageAt(DATA, TOTAL, DATA.steps[2].start + 2)!.presenter).toBeNull();
  });

  it("lands a press on the row its act lights, from the edge when he cannot reach", () => {
    const shot = DATA.shots[1];
    const press = shot.events.find((e) => e.type === "press")!;
    const st = stageAt(DATA, TOTAL, press.frame)!;
    expect(st.presses).toHaveLength(1);
    const phone = st.objects.find((o) => o.key === "phone")!;
    expect(st.presses[0].tip).toEqual(pressPoint(phone, "row2"));
    expect(st.presses[0].hose).toBe(false);
    const keypadPress = DATA.shots[3].events.find((e) => e.type === "press")!;
    expect(stageAt(DATA, TOTAL, keypadPress.frame)!.presses[0].hose).toBe(true);
    for (const c of CASES.press_point) {
      const o = { key: c.object, object: c.object, x: 540, y: 960, scale: 1.2, since: 0, enter: "pop", text: "", act: "", actAt: -1 };
      expect(pressPoint(o, c.act)).toEqual(c.point);
    }
  });

  it("pulls the hand back before a press, holds it, then lets it go", () => {
    const p = { target: "x", at: 100, tip: [0, 0] as [number, number], hose: false, from: [0, 0] as [number, number] };
    expect(pressReach(p, 90)).toBe(0);
    expect(pressReach(p, 96)).toBeLessThan(0);
    expect(pressReach(p, 100)).toBe(1);
    expect(pressReach(p, 100 + TIMING.pressHold + TIMING.pressReturn)).toBe(0);
  });

  it("starts each shot empty: nothing carries over a cut", () => {
    const s2 = stageAt(DATA, TOTAL, DATA.steps[1].start)!;
    expect(s2.objects.every((o) => o.since >= DATA.steps[1].start)).toBe(true);
  });
});
