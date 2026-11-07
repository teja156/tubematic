// PROBE 2 — the DOM half of the shipped machinery. Every texture lives here
// (kit/textures.ts needs `document`), and every POSITION comes from layout()'s
// placements — this file never decides where anything goes.
import * as THREE from "three";
import { makeWater } from "../kit/Water";
import { mesh, rock, telegraphPole, tree, wire, worldBox } from "../kit/geometry";
import { makeRng, range } from "../kit/prng";
import * as T from "../kit/textures";
import { offsetSpot, type Layout, type Placed } from "./worldKit";
import { makeBuilding, makePart, makePartMaterials, type PartCtx } from "./parts";
import { makeGroundDetail, makeTerrain } from "./ground";

const lambert = (map?: THREE.Texture, color = 0xffffff, extra: THREE.MeshLambertMaterialParameters = {}) =>
  new THREE.MeshLambertMaterial({ map: map ?? null, color, ...extra });

export interface Glow {
  mat: THREE.MeshLambertMaterial;
  color: THREE.Color;
  /** how strongly it glows at full night */
  peak: number;
}
export interface Lamp {
  light: THREE.PointLight;
  peak: number;
  flicker: boolean;
}
export interface BuiltWorld {
  root: THREE.Group;
  glows: Glow[];
  lamps: Lamp[];
  /** trees, for the sway */
  trees: THREE.Object3D[];
  /** world-space smoke emitters (fires, chimneys) */
  smoke: { at: THREE.Vector3; kind: "chimney" | "fire" | "stack" }[];
  /** ruts / puddles / worn patches, tinted per frame */
  detail?: { update: (fogColor: THREE.Color, tod: number) => void };
  /** the terrain material's fog ceiling, if terrain is on */
  fogCap?: { value: number };
  /** named props (pieces with `name`), for beats to move, show, hide and act; `smoke` are the emitters the
   *  atmosphere reads (the same Vector3 objects as in `smoke`), with their part-space origin */
  props: { name: string; group: THREE.Group; placed: Extract<Placed, { kind: "prop" }>; smoke: { at: THREE.Vector3; local: THREE.Vector3 }[] }[];
}

export const buildWorld = (L: Layout): BuiltWorld => {
  const { spec, placed } = L;
  const root = new THREE.Group();
  const namedProps: BuiltWorld["props"] = [];
  const glows: Glow[] = [];
  const lamps: Lamp[] = [];

  const trees: THREE.Object3D[] = [];
  const smoke: BuiltWorld["smoke"] = [];
  let detail: BuiltWorld["detail"];
  let fogCap: BuiltWorld["fogCap"];
  if (spec.terrain) {
    const ground = makeTerrain(spec.terrain, { kind: spec.ground.tex, ...spec.ground.hsl, seed: spec.ground.seed });
    fogCap = (ground.userData.fogCap as { value: number } | undefined) ?? undefined;
    root.add(ground);
  }
  if (spec.detail) {
    const d = makeGroundDetail({ seed: spec.ground.seed + 7, ...spec.detail });
    root.add(d.group);
    detail = d;
  }
  // ground (flat plane, only when there is no terrain)
  const gtex =
    spec.ground.tex === "cobbles"
      ? T.cobbles(spec.ground.seed)
      : spec.ground.tex === "stone"
        ? T.stoneBlocks(spec.ground.seed)
        : T.dirt(spec.ground.seed, spec.ground.hsl.hue, spec.ground.hsl.sat, spec.ground.hsl.light);
  const groundGeo = new THREE.PlaneGeometry(600, 600);
  groundGeo.rotateX(-Math.PI / 2);
  const uv = groundGeo.getAttribute("uv") as THREE.BufferAttribute;
  for (let i = 0; i < uv.count; i++) uv.setXY(i, uv.getX(i) * 150, uv.getY(i) * 150);
  if (!spec.terrain) root.add(mesh(groundGeo, lambert(gtex), [0, 0, 0], { cast: false }));

  const glass = lambert(undefined, 0x3fe0c0, { emissive: new THREE.Color(0x0a4a40) });
  const wireMat = lambert(undefined, 0x2a1d44);
  const poleWood = lambert(T.bark(21, 25, 0.42));
  const trunk = lambert(T.bark(31, 20, 0.35));
  const rockMat = lambert(T.stoneBlocks(9), 0xd8c0ff);
  const leafCache = new Map<number, THREE.MeshLambertMaterial>();
  const leaf = (hue: number) => {
    if (!leafCache.has(hue)) leafCache.set(hue, lambert(T.foliage(41 + hue, hue)));
    return leafCache.get(hue)!;
  };
  const pm = makePartMaterials();
  const ctx: PartCtx = { glows, lamps, smokeLocal: [], water: makeWater };
  // water sheets (kit/Water.ts): coloured by distance and the light each frame, no ink, not solid
  for (const wp of spec.water ?? []) {
    const spot = wp.pos ? { x: wp.pos[0], z: wp.pos[1], yaw: 0 } : wp.at ? (() => { const sp = offsetSpot(spec.plan, wp.at!, wp.out ?? 0, wp.along ?? 0); return { x: sp.pos.x, z: sp.pos.z, yaw: sp.yaw }; })() : { x: 0, z: 0, yaw: 0 };
    const w = makeWater(wp.w, wp.d, { flow: wp.flow, marks: wp.marks });
    w.position.set(spot.x, wp.y ?? 0.06, spot.z);
    w.rotation.y = wp.yaw !== undefined ? (wp.yaw * Math.PI) / 180 : spot.yaw;
    root.add(w);
  }
  // parts and buildings declare smoke points in their own frame; grammar parts
  // also say each point's kind (userData.smokeKinds)
  type SmokeKind = "chimney" | "fire" | "stack";
  const collectSmoke = (g: THREE.Object3D, kind: SmokeKind = "chimney") => {
    g.updateMatrixWorld(true);
    const kinds = g.userData.smokeKinds as SmokeKind[] | undefined;
    const out: { at: THREE.Vector3; local: THREE.Vector3 }[] = [];
    ((g.userData.smoke as THREE.Vector3[] | undefined) ?? []).forEach((v, i) => {
      const at = v.clone().applyMatrix4(g.matrixWorld);
      smoke.push({ at, kind: kinds?.[i] ?? kind });
      out.push({ at, local: v.clone() });
    });
    return out;
  };
  const tuftMat = lambert(T.foliage(77, 95));

  const runs = new Map<number, THREE.Vector3[][]>();

  for (const p of placed) {
    if (p.kind === "building") {
      const g = makeBuilding(p.piece, pm, ctx);
      g.position.copy(p.pos);
      g.rotation.y = p.yaw;
      root.add(g);
      collectSmoke(g);
    } else if (p.kind === "platform") {
      const b = p.piece;
      const g = new THREE.Group();
      g.position.copy(p.pos);
      g.rotation.y = p.yaw;
      g.add(mesh(worldBox(b.w, b.h, b.d, 2.4), lambert(T.planks({ seed: 11, planks: 6, hue: b.wood.hue, sat: b.wood.sat, light: b.wood.light })), [0, b.h / 2, 0]));
      root.add(g);
    } else if (p.kind === "path") {
      const b = p.boxes[0];
      const tex = T.dirt(97, p.piece.hsl.hue, p.piece.hsl.sat, p.piece.hsl.light);
      const geo = new THREE.PlaneGeometry(b.w, b.d);
      geo.rotateX(-Math.PI / 2);
      const pu = geo.getAttribute("uv") as THREE.BufferAttribute;
      for (let i = 0; i < pu.count; i++) pu.setXY(i, (pu.getX(i) * b.w) / 4, (pu.getY(i) * b.d) / 4);
      const mat = lambert(tex, 0xffffff, { polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1 });
      const plane = mesh(geo, mat, [b.cx, 0.005, b.cz], { cast: false });
      plane.userData.noInk = true; // a flat decal has no silhouette to ink
      root.add(plane);
    } else if (p.kind === "pole") {
      const { group, tips } = telegraphPole(p.pos, p.height, poleWood, glass, p.yaw);
      root.add(group);
      if (!runs.has(p.run)) runs.set(p.run, []);
      runs.get(p.run)!.push(tips);
    } else if (p.kind === "tree") {
      const t = tree(p.pos, p.scale, trunk, leaf(p.leafHue), p.seed);
      trees.push(t);
      root.add(t);
    } else if (p.kind === "rock") {
      root.add(rock(p.pos, p.scale, rockMat, p.seed));
    } else if (p.kind === "tuft") {
      const rng = makeRng(p.seed);
      const g = new THREE.Group();
      g.position.copy(p.pos);
      for (let k = 0; k < 4; k++) {
        const c = mesh(new THREE.ConeGeometry(0.07 * p.scale, 0.42 * p.scale, 5), tuftMat, [range(rng, -0.14, 0.14), 0.2 * p.scale, range(rng, -0.14, 0.14)], { cast: false });
        c.rotation.set(range(rng, -0.3, 0.3), 0, range(rng, -0.3, 0.3));
        g.add(c);
      }
      root.add(g);
    } else if (p.kind === "prop") {
      const g = makePart(p.what, p.seed, pm, ctx, L.spec.parts);
      g.position.copy(p.pos);
      g.rotation.y = p.yaw;
      g.scale.setScalar(p.scale);
      root.add(g);
      const sm = collectSmoke(g, p.what === "firepit" || p.what === "campfire" ? "fire" : p.what === "locomotive" ? "stack" : "chimney");
      if (p.name) {
        namedProps.push({ name: p.name, group: g, placed: p, smoke: sm });
        g.visible = !p.hidden;
        if (p.hidden) for (const e of sm) e.at.set(0, -500, 0);
      }
    } else if (p.kind === "fence") {
      const g = new THREE.Group();
      g.position.copy(p.pos);
      g.rotation.y = p.yaw;
      const posts = Math.max(2, Math.round(p.length / 2) + 1);
      for (let i = 0; i < posts; i++) {
        g.add(mesh(worldBox(0.12, 1.1, 0.12, 1), pm.darkWood, [(i / (posts - 1)) * p.length, 0.55, 0]));
      }
      for (const y of [0.45, 0.88]) g.add(mesh(worldBox(p.length, 0.08, 0.05, 1), pm.lightWood, [p.length / 2, y, 0]));
      root.add(g);
    }
  }

  for (const tipsList of runs.values()) {
    for (let i = 1; i < tipsList.length; i++) {
      for (let k = 0; k < tipsList[i].length; k++) {
        root.add(new THREE.Mesh(wire(tipsList[i - 1][k], tipsList[i][k], 0.9 + 0.1 * k), wireMat));
      }
    }
  }

  return { root, glows, lamps, trees, smoke, detail, fogCap, props: namedProps };
};
