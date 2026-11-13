// Isometric Infographic's contract, stage and kit: the facts the MCP validator
// and the render rely on. The shared cases are the ones mcp/tests/test_isometric_infographic.py runs.
import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { AREA_KINDS, COLOR_NAMES, GEOMETRY, LIMITS, PROP_NAMES, ROOMS, STACKS, TIMING, eventFrames, grouped, type IsometricData } from "./contract";
import { PROPS, drawSolid, footprint, project, tones } from "./kit";
import { pinLayout } from "./pins";
import { dropAt, projAt, quietSpans, readoutAt, viewAt, WHOLE } from "./stage";

const ROOT = path.resolve(__dirname, "../../../../../..");
const CASES = JSON.parse(fs.readFileSync(path.join(ROOT, "mcp/tests/fixtures/isometric_infographic_contract.json"), "utf8"));
const PACK = JSON.parse(fs.readFileSync(path.join(ROOT, "tubematic_core/style_packs/isometric_infographic.json"), "utf8"));

describe("the shared contract", () => {
  it("has the constants and the cases the validator uses", () => {
    expect(CASES.constants).toEqual(JSON.parse(JSON.stringify({ LIMITS, TIMING, GEOMETRY })));
    const data = CASES.data as IsometricData;
    expect(data.boards.map((b) => eventFrames(b))).toEqual(CASES.event_frames);
    expect(quietSpans(data, CASES.total)).toEqual(CASES.quiet_spans);
    for (const c of CASES.readout_at) expect(readoutAt(data, c.frame)).toEqual({ value: c.value, red: c.red, shown: c.shown });
    for (const c of CASES.footprint) expect(footprint(c.solids)).toBe(c.half);
    for (const c of CASES.view_at) expect(viewAt(data.boards[0], c.frame)).toEqual({ x: c.x, y: c.y, zoom: c.zoom });
    for (const c of CASES.grouped) expect(grouped(c.n)).toBe(c.text);
  });

  it("lists in the pack exactly what the kit draws", () => {
    expect(PACK.extra.props).toEqual(PROP_NAMES);
    expect(PACK.extra.colors).toEqual(COLOR_NAMES);
    expect(PACK.extra.areas).toEqual(AREA_KINDS);
    expect(PACK.extra.rooms).toEqual(ROOMS);
    expect(PACK.extra.stacks).toEqual(STACKS);
  });
});

describe("the kit and the stage", () => {
  it("starts a camera move from the view on screen, so a move during another never jumps", () => {
    const b = { start: 0, props: [{ id: "a", what: "house", at: [2, 2] }, { id: "b", what: "house", at: [8, 8] }],
      camera: [{ at: 10, focus: "a" }, { at: 20, focus: "b" }] } as unknown as IsometricData["boards"][number];
    for (const f of [19, 20, 21]) {
      const a = viewAt(b, f), c = viewAt(b, f + 1);
      expect(Math.abs(a.x - c.x) + Math.abs(a.y - c.y)).toBeLessThan(0.6);
    }
  });

  it("projects true isometric and shades three tones from one colour", () => {
    const pr = { k: 60, cx: 540, cy: 650 };
    expect(project(pr, 0, 0)).toEqual([540, 650]);
    const [x, y] = project(pr, 1, 0);
    expect(y - 650).toBeCloseTo(30);
    expect(x - 540).toBeCloseTo(60 * Math.cos(Math.PI / 6));
    const t = tones("#CF5140");
    expect(t.left).toBe("#CF5140");
    expect(t.top).not.toBe(t.right);
  });

  it("shades a custom solid coloured with a palette name", () => {
    const fills: string[] = [];
    const ctx = new Proxy({}, {
      get: (_t, k) => (k === "fillStyle" ? "" : () => undefined),
      set: (_t, k, v) => { if (k === "fillStyle") fills.push(String(v)); return true; },
    }) as unknown as CanvasRenderingContext2D;
    const look = { main: "#CF5140", accent: "#3E4A5C", fade: 0, spread: 0 };
    drawSolid(ctx, { k: 60, cx: 540, cy: 650 }, { s: "box", x: 0, y: 0, w: 0.5, d: 0.5, h: 0.5, c: "gold" }, 1, 1, 0, 1, look);
    expect(fills.length).toBeGreaterThan(0);
    for (const f of fills) expect(f).toMatch(/^#[0-9a-f]{6}$/i);
  });

  it("keeps the whole board in view at zoom 1 and every prop's solids on its footprint", () => {
    expect(projAt(WHOLE)).toEqual({ k: GEOMETRY.k, cx: GEOMETRY.cx, cy: GEOMETRY.cy });
    for (const [name, p] of Object.entries(PROPS)) {
      expect(p.solids.length, name).toBeGreaterThan(0);
      for (const s of p.solids) expect(Math.abs(s.x) <= 0.8 && Math.abs(s.y) <= 0.8, name).toBe(true);
    }
    expect(PROP_NAMES.length).toBeGreaterThanOrEqual(40);
  });

  it("drops a prop in from above with a squash, and leaves one with no enter alone", () => {
    expect(dropAt({ id: "a", what: "house", at: [1, 1] }, 0)).toEqual({ lift: 0, squash: 0, visible: true });
    const p = { id: "a", what: "house", at: [1, 1] as [number, number], enter: 50 };
    expect(dropAt(p, 50 - TIMING.drop - 1).visible).toBe(false);
    expect(dropAt(p, 50 - TIMING.drop).lift).toBeGreaterThan(2);
    expect(dropAt(p, 50).lift).toBe(0);
    expect(dropAt(p, 51).squash).not.toBe(0);
  });
});

describe("the pin layout", () => {
  const pin = (on: string, label: string, extra: object = {}) => ({ on, label, at: 100, ...extra });
  const data = (props: [string, string, [number, number]][], pins: object[]) => ({
    title: "T", boards: [{ start: 0, areas: [], props: props.map(([id, what, at]) => ({ id, what, at })), pins }],
  }) as unknown as IsometricData;

  it("keeps a lone pin at its default place", () => {
    const d = data([["a", "house", [3, 3]]], [pin("a", "Home")]);
    expect(pinLayout(d, d.boards[0])).toEqual([{ right: true, lane: 0 }]);
  });

  it("never lets two stacked pins' labels overlap: the second takes the other side or rises", () => {
    // two props one tile apart, so their anchors are about 60 px apart on screen
    const d = data([["hub", "warehouse", [4, 4]], ["depot", "house", [5, 4.4]]], [pin("hub", "Regional hub", { value: "3", unit: "h" }), pin("depot", "Local depot", { value: "4", unit: "h" })]);
    const slots = pinLayout(d, d.boards[0]);
    expect(slots[0]).toEqual({ right: true, lane: 0 });
    expect(slots[1].right !== slots[0].right || slots[1].lane > 0).toBe(true);
  });

  it("rises when the other side is fixed by `side`", () => {
    const d = data([["a", "warehouse", [4, 4]], ["b", "house", [4.4, 4.4]]], [pin("a", "North hub", { side: "right" }), pin("b", "South depot", { side: "right" })]);
    const [first, second] = pinLayout(d, d.boards[0]);
    expect(first).toEqual({ right: true, lane: 0 });
    expect(second).toEqual({ right: true, lane: expect.any(Number) });
    expect(second.lane).toBeGreaterThan(0);
  });

  it("is the same whatever frame it is asked at", () => {
    const d = data([["a", "warehouse", [4, 4]], ["b", "house", [4.5, 4.5]]], [pin("a", "Hub"), pin("b", "Depot")]);
    expect(pinLayout(d, d.boards[0])).toEqual(pinLayout(d, d.boards[0]));
  });

  it("never moves a label out of the frame: near the right edge the second pin rises instead of flipping right", () => {
    const d = data([["a", "warehouse", [9, 1]], ["b", "house", [8.6, 1.4]]], [pin("a", "Far east hub", { value: "3", unit: "h" }), pin("b", "Far east depot", { value: "4", unit: "h" })]);
    const [first, second] = pinLayout(d, d.boards[0]);
    expect(first.right).toBe(false); // too far right for a label on its right
    expect(second.right).toBe(false);
    expect(second.lane).toBeGreaterThan(0);
  });

  it("near the left edge a clash rises on the same side: a label never starts left of the safe margin", () => {
    const d = data([["a", "warehouse", [2, 7]], ["b", "house", [2.4, 7.4]]], [pin("a", "West hub"), pin("b", "West depot")]);
    const [first, second] = pinLayout(d, d.boards[0]);
    expect(first).toEqual({ right: true, lane: 0 });
    expect(second.right).toBe(true);
    expect(second.lane).toBeGreaterThan(0);
  });

  it("leaves pins that are far apart where they are", () => {
    const d = data([["a", "house", [1, 1]], ["b", "house", [8, 8]]], [pin("a", "Start"), pin("b", "End")]);
    expect(pinLayout(d, d.boards[0]).every((s) => s.lane === 0)).toBe(true);
  });
});
