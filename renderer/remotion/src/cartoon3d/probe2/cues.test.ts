// Gesture cues timed inside a beat (worldKit gestureAt) and the checker's refusal of cues and gestures the drawers
// cannot make: an unknown gesture name is a crash in the middle of a render, so it is caught on the data.
import { describe, expect, it } from "vitest";
import { checkBeats, checkWorld } from "./qa";
import { gestureAt, type BeatSpec, type WorldSpec } from "./worldKit";

const LEAD = 2;
const role = (over: Partial<BeatSpec["cast"][number]> = {}): BeatSpec["cast"][number] => ({ who: "operator", mark: "a", action: "idle", gesture: "talk", headTurn: 0.5, ...over });

describe("gestureAt", () => {
  it("holds the beat's gesture and head turn when there are no cues", () => {
    expect(gestureAt(role(), 100, LEAD)).toEqual({ gesture: "talk", from: "talk", headTurn: 0.5, headFrom: 0.5, since: -Infinity });
  });

  it("switches at a cue's frame, LEAD frames early, remembering what it blends from", () => {
    const r = role({ cues: [{ frame: 250, gesture: "point", headTurn: -1 }] });
    expect(gestureAt(r, 247, LEAD).gesture).toBe("talk");
    expect(gestureAt(r, 248, LEAD)).toEqual({ gesture: "point", from: "talk", headTurn: -1, headFrom: 0.5, since: 250 });
  });

  it("carries the previous head turn through a cue that only changes the gesture, and the reverse", () => {
    const r = role({ cues: [{ frame: 250, gesture: "wave" }, { frame: 300, headTurn: 1 }] });
    expect(gestureAt(r, 260, LEAD)).toMatchObject({ gesture: "wave", headTurn: 0.5, since: 250 });
    expect(gestureAt(r, 320, LEAD)).toMatchObject({ gesture: "wave", from: "wave", headTurn: 1, headFrom: 0.5, since: 300 });
  });
});

describe("the checker on the beat sheet", () => {
  const sheetOf = (ranges: [number, number][]): BeatSpec[] => ranges.map(([start, end]) => ({ start, end, shot: "w", cast: [] }));
  const details = (ranges: [number, number][], total?: number) => checkBeats(sheetOf(ranges), total).map((f) => f.detail);

  it("accepts ordered, contiguous beats from frame 0 to the last frame", () => {
    expect(details([[0, 59], [60, 119]], 120)).toEqual([]);
    expect(details([[0, 59]])).toEqual([]);   // length unknown: only the tiling is checked
  });

  it("blocks a gap, an overlap, a late start, an empty sheet and a sheet shorter than the video", () => {
    expect(details([[0, 59], [61, 119]], 120)[0]).toMatch(/frame 60 is the first not yet covered/);
    expect(details([[0, 59], [50, 119]], 120)[0]).toMatch(/frame 60 is the first not yet covered/);
    expect(details([[5, 119]], 120)[0]).toMatch(/starts at frame 5/);
    expect(details([], 120)[0]).toMatch(/empty/);
    expect(details([[0, 99]], 120)[0]).toMatch(/must end at frame 119/);
    expect(checkBeats(sheetOf([[0, 99]]), 120)[0]).toMatchObject({ kind: "bad-beats", gate: "block" });
  });
});

describe("the checker on gestures and cues", () => {
  const world: WorldSpec = {
    name: "cues", plan: { kind: "clearing", radius: 12, slots: 6 }, ground: { tex: "dirt", hsl: { hue: 38, sat: 0.3, light: 0.6 }, seed: 1 },
    pieces: [], marks: [{ name: "a", at: { slot: 1 }, out: 2 }], shots: [{ name: "w", subject: "a", dist: 6, height: 1.5, swing: 0, fov: 50, aim: 1 }],
    fog: { near: 20, far: 80 }, tod: [0, 0],
    cast: { clerk: { blurb: "a telegraph clerk", jacket: "#5d7a3a", pants: "#3b3f52", boots: "#4a3426", skin: 1 } },
  };
  const sheet = (cast: BeatSpec["cast"]): BeatSpec[] => [{ start: 0, end: 59, shot: "w", cast }];
  const blocks = (cast: BeatSpec["cast"]) => checkWorld(world, sheet(cast), {}).findings.filter((f) => f.kind === "bad-part").map((f) => f.detail);

  it("accepts cues in order inside the beat with gestures the cast member can make", () => {
    expect(blocks([role({ cues: [{ frame: 10, gesture: "wave" }, { frame: 40, headTurn: -1 }] })])).toEqual([]);
    expect(blocks([{ who: "newsboy", mark: "a", action: "idle", cues: [{ frame: 10, gesture: "cheer" }] }])).toEqual([]);
    expect(blocks([{ who: "clerk", mark: "a", action: "idle", cues: [{ frame: 10, gesture: "shrug" }] }])).toEqual([]);
  });

  it("refuses a gesture the drawer does not know, on the beat or in a cue", () => {
    expect(blocks([role({ gesture: "salute" as never })]).join("\n")).toMatch(/gesture "salute" is not one operator can make/);
    expect(blocks([{ who: "newsboy", mark: "a", action: "idle", cues: [{ frame: 10, gesture: "armsCrossed" }] }]).join("\n")).toMatch(/cue 0: gesture "armsCrossed" is not one newsboy can make/);
  });

  it("refuses cues outside the beat, out of order, or that change nothing", () => {
    expect(blocks([role({ cues: [{ frame: 70, gesture: "wave" }] })]).join("\n")).toMatch(/cue 0 at frame 70 is outside the beat \(frames 0-59\)/);
    expect(blocks([role({ cues: [{ frame: 40, gesture: "wave" }, { frame: 20, gesture: "point" }] })]).join("\n")).toMatch(/cue 1 at frame 20 is not after cue 0/);
    expect(blocks([role({ cues: [{ frame: 20 }] })]).join("\n")).toMatch(/cue 0 changes nothing/);
  });
});
