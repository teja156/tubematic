// Footprint and budget of a code part, measured from what it builds. Works in the browser and in Node (with
// domShim.ts installed first). parts.ts registers the builder at load, which keeps this module free of the
// parts.ts -> partsSpec.ts -> here cycle.
import * as THREE from "three";
import { CODE_PARTS } from "./index";

export interface Measured { w: number; h: number; d: number; minY: number; tris: number; empty: boolean }

type Builder = (name: string, seed: number) => THREE.Group;
let builder: Builder | null = null;
export const registerCodeBuilder = (b: Builder) => { builder = b; };

const cache = new Map<string, Measured>();
const r2 = (x: number) => Math.round(x * 100) / 100;

export const measureCodePart = (name: string): Measured => {
  const hit = cache.get(name);
  if (hit) return hit;
  if (!CODE_PARTS[name]) throw new Error(`unknown code part "${name}"`);
  if (!builder) throw new Error("code parts cannot be measured here: import parts.ts first (it registers the builder)");
  const g = builder(name, 1);
  g.updateMatrixWorld(true);
  const box = new THREE.Box3();
  let tris = 0;
  let any = false;
  g.traverse((o) => {
    const m = o as THREE.Mesh;
    if (!m.isMesh || !m.geometry) return;
    if (o.userData.noInk && (o as THREE.Mesh).material && ((o as THREE.Mesh).material as THREE.Material).depthWrite === false) return; // decals
    any = true;
    const geo = m.geometry as THREE.BufferGeometry;
    if (!geo.boundingBox) geo.computeBoundingBox();
    const b = geo.boundingBox!.clone().applyMatrix4(m.matrixWorld);
    box.union(b);
    const n = geo.index ? geo.index.count : geo.getAttribute("position")?.count ?? 0;
    const inst = (m as THREE.InstancedMesh).isInstancedMesh ? (m as THREE.InstancedMesh).count : 1;
    tris += (n / 3) * inst;
  });
  const out: Measured = any
    ? { w: r2(box.max.x - box.min.x), h: r2(box.max.y), d: r2(box.max.z - box.min.z), minY: r2(box.min.y), tris: Math.round(tris), empty: false }
    : { w: 0, h: 0, d: 0, minY: 0, tris: 0, empty: true };
  cache.set(name, out);
  return out;
};

/** the deterministic half of the gate for a code part: what no judge should have to look at */
export const CODE_LIMITS = { maxH: 60, maxWD: 90, minSize: 0.05, maxTris: 400_000, belowGround: 0.03 } as const;
export const validateCodePart = (name: string, reserved: readonly string[] = []): string[] => {
  const errs: string[] = [];
  if (!/^[a-z][A-Za-z0-9]{1,31}$/.test(name)) errs.push(`name "${name}" must match ^[a-z][A-Za-z0-9]{1,31}$`);
  if (reserved.includes(name)) errs.push(`"${name}" is already a kit part`);
  const p = CODE_PARTS[name];
  if (!p) return [...errs, `no code part "${name}" in partSpecs/code/index.ts`];
  if (!p.blurb || p.blurb.length > 200) errs.push("blurb must be 1-200 characters");
  if (typeof p.build !== "function") errs.push("build must be a function (m, ctx, seed) => THREE.Group");
  if (errs.length) return errs;
  let m: Measured;
  try {
    m = measureCodePart(name);
  } catch (e) {
    return [`build() threw: ${(e as Error).message}`];
  }
  if (m.empty) errs.push("build() made no meshes");
  if (m.h > CODE_LIMITS.maxH) errs.push(`${m.h} m tall, over ${CODE_LIMITS.maxH} m`);
  if (Math.max(m.w, m.d) > CODE_LIMITS.maxWD) errs.push(`${m.w} x ${m.d} m footprint, over ${CODE_LIMITS.maxWD} m`);
  if (!m.empty && Math.min(m.w, m.h, m.d) < CODE_LIMITS.minSize) errs.push(`hairline: ${m.w} x ${m.h} x ${m.d} m`);
  if (m.minY < -CODE_LIMITS.belowGround) errs.push(`reaches ${m.minY} m below the ground (a part stands on y = 0)`);
  if (m.tris > CODE_LIMITS.maxTris) errs.push(`${m.tris} triangles, over ${CODE_LIMITS.maxTris}`);
  return errs;
};
