// Part compiler — the DOM half of the part grammar (partGrammar.ts). Builds a
// THREE.Group from a PartSpec with the same meshes, materials and userData the
// hand-built parts in parts.ts produce:
// - solids cast and receive shadows and get ink; `noInk` primitives are decals
// - glowing materials are registered in ctx.glows, lamps are PointLights in ctx.lamps
// - smoke points go on userData.smoke (local frame), their kinds on userData.smokeKinds
// - figure cards are alpha-tested in the colour, shadow and ink passes
// Every mesh is added straight to the returned group with its full placement.
import * as THREE from "three";
import { worldBox } from "../kit/geometry";
import { cutoutNormalMaterial } from "../kit/InkPipeline";
import { makeRng } from "../kit/prng";
import { figureTex, plateTex } from "./cardDraw";
import { cardSize, pickBySeed, walk, type CardDraw, type Leaf, type MatRef, type PartSpec, type V3 } from "./partGrammar";
import type { PartCtx, PartMaterials } from "./parts";

const col = (h: number, s: number, l: number) => new THREE.Color().setHSL((((h % 360) + 360) % 360) / 360, s, l, THREE.SRGBColorSpace);
const UP = new THREE.Vector3(0, 1, 0);

/** what each card drawing is: its texture, and whether it is a cut-out figure or an opaque print */
const CARDS: Record<CardDraw, { tex: (seed: number, text?: string) => THREE.Texture; cutout: boolean }> = {
  figure: { tex: (seed) => figureTex(seed), cutout: true },
  plate: { tex: (_seed, text) => plateTex(text ?? "", "#1a1424", "#e8c870"), cutout: false },
};

/** a thin flat panel cut from a 2D outline, UVs spanning its bounds (as parts.ts shapeGeo) */
const flatShape = (pts: [number, number][]) => {
  const s = new THREE.Shape();
  pts.forEach(([x, y], i) => (i === 0 ? s.moveTo(x, y) : s.lineTo(x, y)));
  const geo = new THREE.ShapeGeometry(s);
  const bb = new THREE.Box3().setFromBufferAttribute(geo.getAttribute("position") as THREE.BufferAttribute);
  const uv = geo.getAttribute("uv") as THREE.BufferAttribute;
  const p = geo.getAttribute("position") as THREE.BufferAttribute;
  for (let i = 0; i < uv.count; i++) {
    uv.setXY(i, (p.getX(i) - bb.min.x) / Math.max(0.01, bb.max.x - bb.min.x), (p.getY(i) - bb.min.y) / Math.max(0.01, bb.max.y - bb.min.y));
  }
  return geo;
};

const geometry = (p: Exclude<Leaf, { kind: "rod" | "card" }>): THREE.BufferGeometry => {
  switch (p.kind) {
    case "box":
      return worldBox(p.size[0], p.size[1], p.size[2], 1);
    case "cylinder":
      return new THREE.CylinderGeometry(p.rTop ?? p.r, p.r, p.h, p.seg ?? 10, 1, !!p.open);
    case "sphere":
      return new THREE.SphereGeometry(1, p.seg?.[0] ?? 12, p.seg?.[1] ?? 8);
    case "torus":
      return new THREE.TorusGeometry(p.r, p.tube, p.seg?.[0] ?? 6, p.seg?.[1] ?? 24);
    case "lathe":
      return new THREE.LatheGeometry(p.points.map(([r, y]) => new THREE.Vector2(r, y)), p.seg ?? 16);
    case "shape": {
      if (!p.depth) return flatShape(p.points);
      const s = new THREE.Shape();
      p.points.forEach(([x, y], i) => (i === 0 ? s.moveTo(x, y) : s.lineTo(x, y)));
      s.closePath();
      const g = new THREE.ExtrudeGeometry(s, { depth: p.depth, bevelEnabled: false });
      g.translate(0, 0, -p.depth / 2);
      return g;
    }
    case "plane":
      return new THREE.PlaneGeometry(p.size[0], p.size[1]);
  }
};

export const compilePart = (spec: PartSpec, seed: number, m: PartMaterials, ctx: PartCtx): THREE.Group => {
  const g = new THREE.Group();
  // the same stream makePart seeds for a hand-built kind of this name
  const rng = makeRng(seed * 7919 + spec.name.length * 131);
  const made = new Map<string, THREE.Material>();

  const material = (ref: MatRef | undefined): THREE.Material | THREE.Material[] => {
    if (ref === undefined) throw new Error(`part ${spec.name}: a primitive has no mat`);
    if (Array.isArray(ref)) return ref.map((r) => material(r) as THREE.Material);
    if (typeof ref === "string") {
      const k = m[ref];
      if (!(k instanceof THREE.Material)) throw new Error(`part ${spec.name}: no kit material "${ref}"`);
      return k;
    }
    const key = JSON.stringify(ref);
    let mat = made.get(key);
    if (!mat) {
      const base = col(...ref.hsl);
      if (ref.glow) {
        const lm = new THREE.MeshLambertMaterial({ color: base, emissive: new THREE.Color(0x000000) });
        ctx.glows.push({ mat: lm, color: new THREE.Color(...ref.glow.rgb), peak: ref.glow.peak });
        mat = lm;
      } else mat = new THREE.MeshLambertMaterial({ color: base });
      made.set(key, mat);
    }
    return mat;
  };
  const glows = (ref: MatRef | undefined) => typeof ref === "object" && !Array.isArray(ref) && !!ref.glow;

  const cardMat = (draw: CardDraw, text?: string) => {
    const key = `card:${draw}:${text ?? ""}`;
    let mat = made.get(key);
    if (!mat) {
      const tex = CARDS[draw].tex(seed, text);
      mat = CARDS[draw].cutout
        ? new THREE.MeshLambertMaterial({ map: tex, alphaTest: 0.5, side: THREE.DoubleSide, emissiveMap: tex, emissive: new THREE.Color(0.22, 0.22, 0.22) })
        : new THREE.MeshLambertMaterial({ map: tex });
      made.set(key, mat);
    }
    return mat as THREE.MeshLambertMaterial;
  };

  for (const { prim: p, m: place } of walk(spec.prims, rng)) {
    let o: THREE.Mesh;
    if (p.kind === "rod") {
      // endpoints in the part frame, then the cylinder spans them (as parts.ts rod)
      const a = new THREE.Vector3(...p.from).applyMatrix4(place);
      const b = new THREE.Vector3(...p.to).applyMatrix4(place);
      o = new THREE.Mesh(new THREE.CylinderGeometry(p.rTop ?? p.r, p.r, a.distanceTo(b), p.seg ?? 6), material(p.mat));
      o.position.copy(a).add(b).multiplyScalar(0.5);
      o.quaternion.setFromUnitVectors(UP, b.clone().sub(a).normalize());
    } else if (p.kind === "card") {
      const { w, h } = cardSize(p, seed);
      const geo = new THREE.PlaneGeometry(w, h);
      geo.translate(0, h / 2, 0);
      const mat = cardMat(p.draw, p.text ? pickBySeed(seed, p.text) : undefined);
      o = new THREE.Mesh(geo, mat);
      place.decompose(o.position, o.quaternion, o.scale);
      if (CARDS[p.draw].cutout) {
        o.customDepthMaterial = new THREE.MeshDepthMaterial({ depthPacking: THREE.RGBADepthPacking, map: mat.map, alphaTest: 0.5, side: THREE.DoubleSide });
        o.userData.normalMaterial = cutoutNormalMaterial(mat.map!);
      }
    } else {
      const geo = geometry(p);
      o = new THREE.Mesh(geo, material(p.mat));
      const s: V3 = p.kind === "sphere" ? (typeof p.r === "number" ? [p.r, p.r, p.r] : p.r) : [1, 1, 1];
      place.clone().multiply(new THREE.Matrix4().makeScale(...s)).decompose(o.position, o.quaternion, o.scale);
    }
    if (p.uv) {
      const uv = o.geometry.getAttribute("uv") as THREE.BufferAttribute;
      for (let i = 0; i < uv.count; i++) uv.setXY(i, uv.getX(i) * p.uv[0], uv.getY(i) * p.uv[1]);
    }
    o.castShadow = !p.noInk && !glows(p.mat);
    o.receiveShadow = !(p.kind === "card" && CARDS[p.draw].cutout);
    if (p.noInk) o.userData.noInk = true;
    g.add(o);
  }

  for (const l of spec.lamp ?? []) {
    const light = new THREE.PointLight(l.colour ? col(...l.colour) : 0xffd090, 0, 8, 2);
    light.castShadow = false;
    light.position.set(...l.at);
    ctx.lamps.push({ light, peak: 3, flicker: false });
    g.add(light);
  }
  if (spec.smoke?.length) {
    g.userData.smoke = spec.smoke.map((s) => new THREE.Vector3(...s.at));
    g.userData.smokeKinds = spec.smoke.map((s) => s.kind);
  }
  return g;
};
