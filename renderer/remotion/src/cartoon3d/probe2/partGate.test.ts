import { describe, expect, it } from "vitest";
import { hashOf, unpassed, type Verdicts } from "./gate/verdicts";
import { validatePartSpec, type PartSpec } from "./partGrammar";
import { partDims, RESERVED_PART_NAMES } from "./partsSpec";
import { checkParts } from "./qa";
import { layout, type WorldSpec } from "./worldKit";

// a bollard: a post on a base, both on the ground
const bollard: PartSpec = {
  name: "bollard",
  blurb: "iron mooring post on a square base",
  prims: [
    { kind: "box", size: [0.6, 0.1, 0.6], at: [0, 0.05, 0], mat: "iron" },
    { kind: "cylinder", r: 0.12, h: 0.9, at: [0, 0.55, 0], mat: "iron" },
  ],
};

describe("validatePartSpec (the deterministic half of the gate)", () => {
  it("passes a sound spec", () => {
    expect(validatePartSpec(bollard, RESERVED_PART_NAMES)).toEqual([]);
  });

  it("refuses a kit name, a bad name and an unknown material", () => {
    expect(validatePartSpec({ ...bollard, name: "crate" }, RESERVED_PART_NAMES)[0]).toMatch(/already a kit part/);
    expect(validatePartSpec({ ...bollard, name: "Big Post" })[0]).toMatch(/name must match/);
    const bad = validatePartSpec({ ...bollard, prims: [{ ...bollard.prims[0], mat: "chrome" as never }] });
    expect(bad.join("\n")).toMatch(/unknown material "chrome"/);
  });

  it("names the primitive that floats", () => {
    const floating = { ...bollard, prims: [bollard.prims[0], { ...bollard.prims[1], at: [0, 2, 0] as [number, number, number] }] };
    const errs = validatePartSpec(floating);
    expect(errs).toHaveLength(1);
    expect(errs[0]).toMatch(/primitive 1 \(cylinder .*\) floats/);
  });

  it("holds the size limits", () => {
    expect(validatePartSpec({ ...bollard, prims: [{ kind: "box", size: [1, 20, 1], at: [0, 10, 0] }] }).join("\n")).toMatch(/over 18 m/);
    expect(validatePartSpec({ ...bollard, prims: [{ kind: "box", size: [1, 0.001, 1], at: [0, 0, 0] }] }).join("\n")).toMatch(/hairline/);
  });

  it("explains a malformed primitive instead of throwing", () => {
    expect(validatePartSpec({ ...bollard, prims: [{ kind: "blob" } as never] })[0]).toMatch(/prims\[0\]: kind must be one of/);
    expect(validatePartSpec(null)).toEqual(["part must be an object"]);
  });
});

describe("a world that carries its own part", () => {
  const world: WorldSpec = {
    name: "quay",
    plan: { kind: "clearing", radius: 12, slots: 6 },
    ground: { tex: "dirt", hsl: { hue: 38, sat: 0.3, light: 0.6 }, seed: 1 },
    pieces: [{ kind: "prop", what: "bollard", at: { slot: 0 }, out: 1 }],
    marks: [{ name: "here", at: { slot: 1 }, out: 2 }],
    shots: [{ name: "wide", subject: "here", dist: 6, height: 1.5, swing: 0, fov: 50, aim: 1 }],
    fog: { near: 20, far: 80 },
    tod: [0, 0],
    parts: { bollard },
  };

  it("lays the part out with its derived footprint and catalog facts", () => {
    expect(partDims("bollard", world.parts)).toEqual({ w: 0.6, h: 1, d: 0.6 });
    const L = layout(world);
    const placed = L.placed.find((p) => p.kind === "prop" && p.what === "bollard");
    expect(placed).toBeDefined();
    if (placed?.kind !== "prop") throw new Error("not a prop");
    expect(placed.boxes[0]).toMatchObject({ w: 0.6, h: 1, d: 0.6 });
    expect(placed.solid).toBe(true);
    expect(placed.walkable).toBe(false);
    expect(checkParts(world)).toEqual([]);
  });

  it("blocks in QA when the part is unsound or misnamed", () => {
    const bad = { ...world, parts: { post: bollard } };
    const findings = checkParts(bad);
    expect(findings[0]).toMatchObject({ kind: "bad-part", gate: "block", who: "post" });
    expect(findings[0].detail).toMatch(/key and the name must match/);
    expect(() => layout({ ...world, parts: {} })).toThrow(/unknown part "bollard"/);
  });
});

describe("the verdict file the stager enforces", () => {
  it("counts only a judged PASS for the part's current spec", () => {
    const parts = { bollard, post: { ...bollard, name: "post" } };
    const judged = (hash: string, pass: boolean) => ({ at: "", hash, stage: "judge" as const, pass });
    const v: Verdicts = {
      parts: {
        bollard: { pass: true, attempts: [judged(hashOf(bollard), true)] },
        post: { pass: true, attempts: [judged("stale0000000", true), { at: "", hash: hashOf(parts.post), stage: "stills", pass: false }] },
      },
    };
    expect(unpassed(parts, v)).toEqual(["post"]);
    expect(unpassed(parts, { parts: {} })).toEqual(["bollard", "post"]);
    expect(unpassed({}, { parts: {} })).toEqual([]);
  });
});

describe("code parts and prop cues", () => {
  it("measures a code part's footprint headlessly and validates it", async () => {
    const { installDomShim } = await import("./domShim");
    installDomShim();
    const { ensureCodeBuilder } = await import("./parts");
    ensureCodeBuilder();
    const { measureCodePart, validateCodePart } = await import("./partSpecs/code/measure");
    const m = measureCodePart("telegraphKey");
    expect(m.empty).toBe(false);
    expect(m.h).toBeGreaterThan(0.9);
    expect(m.minY).toBeGreaterThanOrEqual(-0.03);
    expect(validateCodePart("telegraphKey")).toEqual([]);
    expect(validateCodePart("nope")[0]).toMatch(/no code part/);
    expect(partDims("telegraphKey")).toEqual({ w: m.w, h: m.h, d: m.d });
  });

  it("moves, shows and hides a named prop by its beats' cues", async () => {
    const { propPoseAt } = await import("./worldKit");
    const world: WorldSpec = {
      name: "cues",
      plan: { kind: "clearing", radius: 12, slots: 6 },
      ground: { tex: "dirt", hsl: { hue: 38, sat: 0.3, light: 0.6 }, seed: 1 },
      pieces: [{ kind: "prop", what: "crate", at: { slot: 0 }, out: 1, name: "box", hidden: true }],
      marks: [{ name: "a", at: { slot: 1 }, out: 2 }, { name: "b", at: { slot: 4 }, out: 2 }],
      shots: [{ name: "wide", subject: "a", dist: 6, height: 1.5, swing: 0, fov: 50, aim: 1 }],
      fog: { near: 20, far: 80 },
      tod: [0, 0],
    };
    const sheet = [
      { start: 0, end: 29, shot: "wide", cast: [] },
      { start: 30, end: 59, shot: "wide", cast: [], props: [{ name: "box", visible: true, from: "a", to: "b", ease: "linear" as const }] },
      { start: 60, end: 89, shot: "wide", cast: [] },
    ];
    const L = layout(world);
    const box = L.placed.find((p) => p.kind === "prop" && p.name === "box");
    if (!box || box.kind !== "prop") throw new Error("no box");
    expect(propPoseAt(L, sheet, box, 10).visible).toBe(false);
    const a = L.markAt("a"), b = L.markAt("b");
    const p30 = propPoseAt(L, sheet, box, 30), p45 = propPoseAt(L, sheet, box, 45), p80 = propPoseAt(L, sheet, box, 80);
    expect(p30.visible).toBe(true);
    expect(p30.pos.distanceTo(a)).toBeLessThan(0.05);
    expect(p45.pos.distanceTo(a.clone().lerp(b, 15 / 29))).toBeLessThan(0.05);
    expect(p80.pos.distanceTo(b)).toBeLessThan(0.05); // stays where the cue left it
    expect(p45.speed).toBeGreaterThan(0);
    expect(checkParts(world)).toEqual([]);
  });
});

describe("the cast grammar", () => {
  it("validates a figure and knows its height", async () => {
    const { validateFigure } = await import("../kit/figureCheck");
    const { castHeight } = await import("./worldKit");
    const captain = { blurb: "a riverboat captain in a navy coat", jacket: "#1f2d57", pants: "#2b2f3e", boots: "#1a1410", hat: "cap" as const, build: "stout" as const, skin: 1 };
    expect(validateFigure("captain", captain)).toEqual([]);
    expect(validateFigure("newsboy", captain)[0]).toMatch(/fixed cast/);
    expect(validateFigure("paperboy", { ...captain, holds: "bundle", coat: "tails", heldColor: "#f1ead8" })).toEqual([]);
    expect(validateFigure("paperboy", { ...captain, holds: "umbrella" } as never)[0]).toMatch(/holds/);
    expect(validateFigure("x", { ...captain, hat: "fez" as never }).join("\n")).toMatch(/hat: one of/);
    expect(validateFigure("x", { ...captain, jacket: "navy" }).join("\n")).toMatch(/jacket: a #rrggbb/);
    const world = {
      name: "c", plan: { kind: "clearing" as const, radius: 12, slots: 6 }, ground: { tex: "dirt" as const, hsl: { hue: 38, sat: 0.3, light: 0.6 }, seed: 1 },
      pieces: [], marks: [{ name: "a", at: { slot: 1 }, out: 2 }], shots: [{ name: "w", subject: "a", dist: 6, height: 1.5, swing: 0, fov: 50, aim: 1 }],
      fog: { near: 20, far: 80 }, tod: [0, 0] as [number, number], cast: { captain },
    };
    expect(castHeight(world, "captain")).toBe(1.7);
    expect(castHeight(world, "newsboy")).toBe(1.26);
    expect(() => castHeight(world, "ghost")).toThrow(/unknown cast member/);
    const bad = checkParts({ ...world, cast: { captain: { ...captain, build: "giant" as never } } });
    expect(bad).toEqual([]); // parts are fine; the cast check is separate
    const { checkCast } = await import("./qa");
    expect(checkCast({ ...world, cast: { captain: { ...captain, build: "giant" as never } } })[0].detail).toMatch(/build: one of/);
  });
});
