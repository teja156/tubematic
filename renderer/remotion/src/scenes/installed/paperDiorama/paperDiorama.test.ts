// The Paper Diorama contract (TMDEV-228): the shared cases mcp/paper_diorama.py also runs, the
// stage's poses, the painter's outlines, and the shipped props' pieces.
import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { COLORS, LIMITS, ROOMS, type PaperSet, type PropDef } from "./contract";
import { CRITTER_H, CRITTER_W, critterDef } from "./critter";
import { outline, pieceBox, roughen } from "./paint";
import { critterPose, itemPose, popScale, ringPoints, slotBox, stageScale, tearReveal } from "./stage";
import { bannerFontSize } from "../PaperDiorama";
import LIBRARY from "./props.json";

const CASES = JSON.parse(
  fs.readFileSync(path.resolve(__dirname, "../../../../../../mcp/tests/fixtures/paper_diorama_contract.json"), "utf8"),
);
const set = (over: Partial<PaperSet> = {}): PaperSet => ({ start: 0, room: "diner", banner: "Hello", ...over });

describe("the shared cases", () => {
  it("pops the same way", () => {
    for (const c of CASES.pop_scale) expect(popScale(c.age)).toBeCloseTo(c.scale, 5);
  });
  it("puts a prop in a slot the same way", () => {
    for (const c of CASES.slot_box) expect(slotBox(set({ room: c.room }), c.slot, c.level, c.w, c.h)).toEqual(c.box);
  });
  it("scales the stage the same way", () => {
    for (const c of CASES.stage_scale) {
      const s = set({ events: c.zooms.map((at: number) => ({ at, do: "zoom" as const })) });
      expect(stageScale(s, c.frame)).toBeCloseTo(c.scale, 5);
    }
  });
  it("sizes the banner the same way", () => {
    for (const c of CASES.banner_font_size) expect(bannerFontSize(c.text)).toBe(c.size);
  });
  it("has the critter's box the server measures", () => {
    expect(CRITTER_W).toBeCloseTo(CASES.critter.w, 6);
    expect(CRITTER_H).toBeCloseTo(CASES.critter.h, 6);
  });
});

describe("the stage", () => {
  const s = set({
    items: [{ id: "a", prop: "laptop", slot: "c", at: 10 }],
    critter: { slot: "l" },
    events: [
      { at: 30, do: "move", target: "a", to: "r" },
      { at: 60, do: "swap", target: "a", prop: "envelope" },
      { at: 80, do: "exit", target: "a" },
      { at: 40, do: "expr", target: "critter", value: "shock" },
    ],
  });
  it("shows an item from its frame, moves it, swaps it and takes it off", () => {
    expect(itemPose(s, s.items![0], 9).visible).toBe(false);
    expect(itemPose(s, s.items![0], 10).scale).toBeCloseTo(0.6);
    expect(itemPose(s, s.items![0], 29).x).toBe(540);
    expect(itemPose(s, s.items![0], 42).x).toBe(890);
    expect(itemPose(s, s.items![0], 60).prop).toBe("envelope");
    expect(itemPose(s, s.items![0], 86).visible).toBe(false);
  });
  it("changes the critter's face on its event", () => {
    expect(critterPose(s, 39, 0).expr).toBe("idle");
    expect(critterPose(s, 40, 0).expr).toBe("shock");
  });
  it("tears the next set in and draws a ring around a box", () => {
    expect(tearReveal(0, 0)).toBe(0);
    expect(tearReveal(12, 0)).toBe(1);
    expect(ringPoints([100, 100, 300, 200], 0.5, 1).length).toBeLessThan(ringPoints([100, 100, 300, 200], 1, 1).length);
  });
});

describe("the painter and the props", () => {
  it("walks a rounded rect's outline inside its box, and roughens it by a pixel or so", () => {
    const pts = outline({ shape: "rect", fill: "ink", x: 10, y: 20, w: 100, h: 50, r: 8 });
    for (const [x, y] of pts) {
      expect(x).toBeGreaterThanOrEqual(10 - 1e-6);
      expect(x).toBeLessThanOrEqual(110 + 1e-6);
      expect(y).toBeGreaterThanOrEqual(20 - 1e-6);
      expect(y).toBeLessThanOrEqual(70 + 1e-6);
    }
    const rough = roughen(pts, 3);
    rough.forEach(([x, y], i) => expect(Math.hypot(x - pts[i][0], y - pts[i][1])).toBeLessThan(2));
    expect(roughen(pts, 3)).toEqual(rough);
  });

  const all = Object.entries(LIBRARY as unknown as Record<string, PropDef>);
  it("ships props whose pieces use the palette and stay inside their boxes", () => {
    expect(all.length).toBeGreaterThan(0);
    for (const [name, def] of all) {
      expect(def.pieces.length, name).toBeLessThanOrEqual(LIMITS.maxPieces);
      expect(def.w, name).toBeLessThanOrEqual(LIMITS.maxPropW);
      expect(def.h, name).toBeLessThanOrEqual(LIMITS.maxPropH);
      for (const p of def.pieces) {
        for (const c of [p.fill, p.shade, p.hi]) if (c !== undefined) expect(COLORS, `${name}: ${c}`).toHaveProperty(c);
        const [l, t, r, b] = pieceBox(p);
        expect(l >= -1 && t >= -1 && r <= def.w + 1 && b <= def.h + 1, `${name}: a piece outside its box`).toBe(true);
      }
    }
  });
  it("draws the critter inside its own box in every expression", () => {
    for (const ex of ["idle", "happy", "shock", "worried", "squint", "sleep", "blink"] as const) {
      const def = critterDef("hero", "hardhat", ex);
      for (const p of def.pieces) {
        const [l, t, r, b] = pieceBox(p);
        expect(l >= -1 && t >= -1 && r <= def.w + 1 && b <= def.h + 1, ex).toBe(true);
      }
    }
  });
  it("ships a picture for every room", () => {
    for (const room of Object.keys(ROOMS)) {
      expect(fs.existsSync(path.resolve(__dirname, `../../../../public/paperDiorama/rooms/${room}.jpg`)), room).toBe(true);
    }
  });
});
