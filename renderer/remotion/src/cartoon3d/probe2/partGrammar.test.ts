import * as THREE from "three";
import { describe, expect, it } from "vitest";
import { compilePart } from "./partCompile";
import { deriveDims, deriveInfo, type PartSpec, type Prim } from "./partGrammar";
import type { PartCtx, PartMaterials } from "./parts";
import { PART_SPECS } from "./partSpecs";

describe("deriveDims / deriveInfo", () => {
  // a 1 x 2 x 1 box on the ground and a post off to +x, turned 90 degrees so it lies along z
  const spec: PartSpec = {
    name: "probe",
    blurb: "two primitives",
    prims: [
      { kind: "box", size: [1, 2, 1], at: [0, 1, 0], mat: "crate" },
      { kind: "cylinder", r: 0.1, h: 3, at: [1.5, 0.1, 0], rot: [90, 0, 0], mat: "iron" },
    ],
    smoke: [{ at: [0, 2, 0], kind: "chimney" }],
  };

  it("is the origin-centred box round every primitive, rotations applied", () => {
    // x reaches 1.6 (post centre 1.5 + radius), so the centred width is 3.2;
    // the post lies along z, 3 m long; the box sets the height
    expect(deriveDims(spec)).toEqual({ w: 3.2, h: 2, d: 3 });
  });

  it("takes flags as given and smoke from the attach points", () => {
    expect(deriveInfo(spec)).toEqual({ solid: true, walkable: false, lightAtNight: false, smoke: true, blurb: "two primitives" });
    expect(deriveInfo({ ...spec, smoke: undefined, solid: false, walkable: true })).toMatchObject({ solid: false, walkable: true, smoke: false });
  });
});

describe("the part specs", () => {
  it.each(Object.entries(PART_SPECS))("%s is plain JSON data named after its kind", (kind, spec) => {
    expect(spec.name).toBe(kind);
    const back = JSON.parse(JSON.stringify(spec)) as PartSpec;
    expect(back).toEqual(spec);
    expect(deriveDims(back)).toEqual(deriveDims(spec));
  });

  // The compiler and the footprint must agree. Cards need a canvas, so they are
  // left out here (the gallery renders them); every other mesh must sit inside
  // the derived box, and the box must not be loose either (polygonal
  // cylinders fall a little inside the round bound the footprint uses).
  const noCards = (ps: Prim[]): Prim[] =>
    ps.filter((p) => p.kind !== "card").map((p) => (p.kind === "group" ? { ...p, items: noCards(p.items) } : p));
  const anyMat = new Proxy({}, { get: () => new THREE.MeshBasicMaterial() }) as unknown as PartMaterials;

  it.each(Object.entries(PART_SPECS).filter(([k]) => k !== "bystander"))("%s compiles inside its derived footprint", (_kind, spec) => {
    const ctx: PartCtx = { glows: [], lamps: [], smokeLocal: [] };
    const solid = { ...spec, prims: noCards(spec.prims) };
    const g = compilePart(solid, 3, anyMat, ctx);
    const lights = g.children.filter((c) => c instanceof THREE.Light);
    lights.forEach((l) => g.remove(l));
    const box = new THREE.Box3().setFromObject(g, true);
    const d = deriveDims(spec);
    const reach = { w: 2 * Math.max(-box.min.x, box.max.x), h: box.max.y, d: 2 * Math.max(-box.min.z, box.max.z) };
    for (const k of ["w", "h", "d"] as const) {
      expect(reach[k]).toBeLessThanOrEqual(d[k] + 1e-6);
      expect(reach[k]).toBeGreaterThan(d[k] * 0.85);
    }
    expect(lights.length).toBe(spec.lamp?.length ?? 0);
    expect(ctx.lamps.length).toBe(lights.length);
    expect(((g.userData.smoke as THREE.Vector3[] | undefined) ?? []).length).toBe(spec.smoke?.length ?? 0);
  });
});
