import { describe, expect, it } from "vitest";
import * as THREE from "three";
import { Crowd } from "./crowd";
import { Burst, Debris, ramp } from "./fx";
import { box, discs, globe, room, strata } from "./diorama";
import { buildFigure, HOUSE, mulberry, randomOutfit } from "./figure";
import { FACE_NAMES, faceGeometry, setFace } from "./faces";
import { dancePose } from "./cycles";

describe("figure", () => {
  it("stands one unit tall with its feet on the floor, built from about 18 parts", () => {
    const f = buildFigure(HOUSE);
    f.root.updateMatrixWorld(true);
    const b = new THREE.Box3().setFromObject(f.root);
    expect(b.min.y).toBeGreaterThan(-0.001);
    expect(b.max.y).toBeGreaterThan(0.95);
    expect(b.max.y).toBeLessThan(1.1);
    let n = 0; f.root.traverse((o) => { if ((o as THREE.Mesh).isMesh) n++; });
    expect(n).toBeGreaterThanOrEqual(18);
    expect(n).toBeLessThanOrEqual(24);
  });
  it("a seeded outfit is the same every time", () => {
    expect(randomOutfit(mulberry(4))).toEqual(randomOutfit(mulberry(4)));
    expect(randomOutfit(mulberry(4))).not.toEqual(randomOutfit(mulberry(5)));
  });
});

describe("faces", () => {
  it("swapping a face replaces it, never stacks", () => {
    const f = buildFigure();
    setFace(f.headMount, "smile"); setFace(f.headMount, "shock"); setFace(f.headMount, "blank");
    expect(f.headMount.children.filter((c) => c.name === "face")).toHaveLength(1);
  });
  it("every face merges into one geometry for the crowd", () => {
    for (const n of FACE_NAMES) expect(faceGeometry(n).getAttribute("position").count).toBeGreaterThan(0);
  });
});

describe("crowd", () => {
  const mem = Crowd.block(6, 4, { seed: 2, outfit: randomOutfit });
  it("a block is rows by columns, seeded", () => {
    expect(mem).toHaveLength(24);
    expect(Crowd.block(6, 4, { seed: 2, outfit: randomOutfit })).toEqual(mem);
  });
  it("draws one instanced mesh per part kind, not one per figure", () => {
    const c = new Crowd(mem, (f, b) => dancePose(f + b));
    const meshes = c.root.children.filter((o) => (o as THREE.InstancedMesh).isInstancedMesh);
    expect(meshes.length).toBeLessThan(35);
    expect(meshes.length).toBeGreaterThanOrEqual(18);
  });
  it("hides the optional parts a member lacks (a bald head has no cap)", () => {
    const bald = [{ x: 0, z: 0, outfit: { ...HOUSE, hairStyle: "bald" as const } }, { x: 1, z: 0, outfit: HOUSE }];
    const c = new Crowd(bald, () => ({}));
    const caps = (c.root.children as THREE.InstancedMesh[]).filter((m) => m.count === 2);
    const m = new THREE.Matrix4(), p = new THREE.Vector3(), q = new THREE.Quaternion(), s = new THREE.Vector3();
    const scaled = caps.map((im) => { im.getMatrixAt(0, m); m.decompose(p, q, s); return s.x === 0; });
    expect(scaled.some(Boolean)).toBe(true);   // the cap, tuft, bob and jaw are off for member 0
    expect(scaled.filter(Boolean).length).toBeLessThan(scaled.length);
  });
  it("members in one bucket move together, different buckets differ", () => {
    const c = new Crowd([{ x: 0, z: 0, outfit: HOUSE, bucket: 0 }, { x: 0, z: 0, outfit: HOUSE, bucket: 1 }], (f, b) => dancePose(f + b * 5));
    c.update(2);
    const im = (c.root.children as THREE.InstancedMesh[]).find((o) => o.count === 2 && o.isInstancedMesh)!;
    const a = new THREE.Matrix4(), b = new THREE.Matrix4();
    let diff = false;
    for (const mesh of c.root.children as THREE.InstancedMesh[]) {
      if (mesh.count !== 2) continue;
      mesh.getMatrixAt(0, a); mesh.getMatrixAt(1, b);
      if (!a.equals(b)) diff = true;
    }
    expect(im).toBeTruthy();
    expect(diff).toBe(true);
  });
});

describe("fx", () => {
  it("a burst pops on its frame, holds, and is gone", () => {
    const b = new Burst(0.5, 4).at(10, [0, 0, 0]);
    b.update(9); expect(b.root.visible).toBe(false);
    b.update(10); expect(b.root.visible).toBe(true);
    b.update(15); expect(b.root.visible).toBe(true);
    b.update(16); expect(b.root.visible).toBe(false);
  });
  it("debris falls: higher at first, lower later, hidden after its life", () => {
    const d = new Debris(6, 1, 20).at(0, [0, 2, 0]);
    d.update(3); const early = d.root.children[0].position.y;
    d.update(12); const late = d.root.children[0].position.y;
    expect(late).toBeLessThan(early);
    d.update(20); expect(d.root.children[0].visible).toBe(false);
  });
  it("ramp is clamped", () => { expect(ramp(5, 10, 4)).toBe(0); expect(ramp(12, 10, 4)).toBe(0.5); expect(ramp(40, 10, 4)).toBe(1); });
});

describe("diorama", () => {
  it("a room has no front wall and a floor", () => {
    const r = room({ w: 4, d: 3, h: 2 });
    const b = new THREE.Box3().setFromObject(r.root);
    expect(b.max.y).toBeCloseTo(2, 1);
    expect(b.min.y).toBeLessThan(0);
    expect(b.max.z).toBeCloseTo(1.5, 1);
  });
  it("box sits on its base height", () => {
    const g = new THREE.Group(); const m = box(g, 1, 2, 1, "#fff", 0, 0.5, 0);
    expect(new THREE.Box3().setFromObject(m).min.y).toBeCloseTo(0.5);
  });
  it("a globe colours every facet sea or land", () => {
    const g = new THREE.Group(); const m = globe(g, 1, { seed: 2 });
    expect(m.geometry.getAttribute("color").count).toBe(m.geometry.getAttribute("position").count);
  });
  it("strata and discs build stacks", () => {
    const g = new THREE.Group();
    expect(strata(g, 2, 1, [{ h: 0.5, color: "#5a4630" }, { h: 1, color: "#888" }]).children).toHaveLength(2);
    expect(discs(g, [{ r: 1, color: "#fa0" }, { r: 0.5, color: "#f00" }]).children).toHaveLength(2);
  });
});
