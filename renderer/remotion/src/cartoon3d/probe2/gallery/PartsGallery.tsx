// PROBE 2 parts gallery: every PartKind and a spread of building styles, laid
// out on lit display terraces in a labelled grid, for judging by eye.
// Props: { page: number; night?: boolean; hand?: boolean }. Pages 0..N-1 are parts (12 each),
// then story and building pages, then the part-grammar pages: each grammar
// part hand-built (left / front) beside its compiled spec, at the same scale.
// `hand: true` builds every grammar kind on every page hand-built instead, so a
// page rendered both ways can be diffed pixel for pixel. Each item is scaled to fit its cell; the label carries
// its true footprint, and a 1 m measuring stick (four 25 cm bands) stands at
// the same scale beside every part.
import { useFrame, useThree } from "@react-three/fiber";
import { ThreeCanvas } from "@remotion/three";
import { useRef } from "react";
import { AbsoluteFill, useVideoConfig } from "remotion";
import * as THREE from "three";
import { mesh, worldBox } from "../../kit/geometry";
import { FxFlags, InkPipeline, type Dof } from "../../kit/InkPipeline";
import { makeSky } from "../../kit/Sky";
import * as T from "../../kit/textures";
import { gradeAt, lightsAt, skyAt } from "../look";
import { makeBuilding, makeHandPart, makePart, makePartMaterials, type PartCtx } from "../parts";
import { buildingExtent, PART_DIMS, PART_KINDS, type BuildingStyle, type PartKind } from "../partsSpec";
import type { BuildingPiece } from "../worldKit";

type Bld = BuildingPiece & { style?: BuildingStyle };

export interface Item {
  label: string;
  sub: string;
  /** footprint used to fit the cell: width, height, depth, and z shift of its centre */
  size: { w: number; h: number; d: number; zc: number };
  build: (m: ReturnType<typeof makePartMaterials>, ctx: PartCtx, make: typeof makeHandPart) => THREE.Group;
  stick: boolean;
}
export interface Page {
  title: string;
  cols: number;
  rows: number;
  /** cell pitch and the size an item is fitted to */
  sx: number;
  fit: number;
  /** per-row rise and set-back (default: a grid of terraces scaled by sx) */
  dy?: number;
  dz?: number;
  /** how every item is turned on its terrace (radians; default the gallery's 3/4 view) */
  yaw?: number;
  items: Item[];
}

const partItem = (k: PartKind): Item => {
  const d = PART_DIMS[k];
  return {
    label: k,
    sub: `${d.w} x ${d.h} x ${d.d} m`,
    size: { w: d.w, h: d.h, d: d.d, zc: 0 },
    build: (m, ctx, make) => make(k, 3, m, ctx),
    stick: true,
  };
};

let bseed = 100;
const B = (label: string, b: Partial<Bld> & { w: number; h: number; d: number }): Item => {
  const piece: Bld = {
    kind: "building", at: { slot: 0 }, wall: { hue: 30, sat: 0.36, light: 0.46 }, roof: { hue: 16, sat: 0.36, light: 0.38 },
    windows: 2, seed: (bseed += 7), ...b,
  };
  const ext = buildingExtent(piece);
  const out = piece.style?.chimney && (piece.style.wall === "logs" || (typeof piece.style.chimney === "object" && piece.style.chimney.outside)) ? 1.0 : 0;
  const s = piece.style ?? {};
  const bits = [s.wall, s.roof, s.porch ? "porch" : "", s.awning ? `${s.awning.kind ?? "canvas"} awning` : "", s.chimney ? "chimney" : "", s.storeys === 2 ? "2 storey" : "", s.balcony ? "balcony" : "", s.foundation ? `${s.foundation} footing` : "", s.shutters ? "shutters" : "", s.door && s.door.open ? "open door" : ""].filter(Boolean);
  return {
    label,
    sub: bits.length ? bits.join(", ") : "no style (defaults)",
    size: { w: piece.w + 2 * out, h: ext.top, d: piece.d + ext.front, zc: (ext.front - piece.d) / 2 },
    build: (m, ctx) => makeBuilding(piece, m, ctx),
    stick: false,
  };
};

const W = (hue: number, sat: number, light: number) => ({ hue, sat, light });

const BUILDING_PAGES: Page[] = [
  {
    title: "Buildings: wall materials",
    cols: 2, rows: 3, sx: 5.6, fit: 3.7,
    items: [
      B("planks", { w: 5, h: 3.2, d: 4.5, style: { wall: "planks", chimney: true }, wall: W(28, 0.36, 0.42) }),
      B("clapboard", { w: 5.4, h: 3.4, d: 5, wall: { hue: 30, sat: 0.4, light: 0.45, clapboard: true, painted: { hue: 200, sat: 0.18, light: 0.62, wear: 0.3 } }, style: { wall: "clapboard", shutters: true }, roof: W(4, 0.3, 0.36) }),
      B("logs", { w: 5, h: 2.8, d: 4.4, windows: 1, style: { wall: "logs", chimney: true, porch: { depth: 1.6, rail: false } }, roof: W(30, 0.2, 0.34) }),
      B("stone", { w: 5.4, h: 3.2, d: 5, wall: W(30, 0.1, 0.58), style: { wall: "stone", roofMat: "planks", chimney: { kind: "stone" } }, roof: W(24, 0.25, 0.36) }),
      B("brick", { w: 5.6, h: 5.8, d: 5, windows: 2, wall: W(10, 0.4, 0.42), style: { wall: "brick", roof: "hip", storeys: 2, chimney: true }, roof: W(220, 0.12, 0.36) }),
      B("adobe", { w: 5.4, h: 3.0, d: 5, windows: 1, wall: W(28, 0.34, 0.64), style: { wall: "adobe", roof: "flat", door: { open: true } } }),
    ],
  },
  {
    title: "Buildings: roof kinds",
    cols: 2, rows: 3, sx: 5.6, fit: 3.7,
    items: [
      B("gable", { w: 5, h: 3.1, d: 4.6, style: { roof: "gable" } }),
      B("hip", { w: 5.4, h: 3.2, d: 6, wall: { hue: 36, sat: 0.3, light: 0.5, clapboard: true, painted: { hue: 42, sat: 0.26, light: 0.8, wear: 0.25 } }, style: { roof: "hip", wall: "clapboard", porch: {} }, roof: W(200, 0.2, 0.34) }),
      B("shed", { w: 4.6, h: 2.8, d: 4.2, windows: 1, style: { roof: "shed", wall: "planks" }, wall: W(34, 0.12, 0.52) }),
      B("flat", { w: 5.4, h: 3.4, d: 5, wall: W(14, 0.36, 0.4), style: { roof: "flat", wall: "brick", awning: { kind: "canvas" } } }),
      B("falseFront + sign", { w: 6, h: 3.8, d: 5.4, falseFront: 1.6, sign: { text: "GENERAL STORE", bg: "#2e2340", fg: "#f2e2b6" }, wall: W(40, 0.34, 0.56), style: { roof: "falseFront", awning: { kind: "wood" } } }),
      B("falseFront + porch", { w: 6, h: 3.6, d: 5, falseFront: 1.3, sign: { text: "SALOON", bg: "#3a2416", fg: "#f0d79c" }, wall: W(14, 0.32, 0.4), style: { roof: "falseFront", porch: { rail: true }, foundation: "posts" } }),
    ],
  },
  {
    title: "Buildings: porches, storeys, doors",
    cols: 2, rows: 3, sx: 5.6, fit: 3.7,
    items: [
      B("telegraph office", { w: 5.2, h: 3.3, d: 4.6, windows: 2, lit: [0], sign: { text: "TELEGRAPH", bg: "#20304a", fg: "#f2e8c8" }, wall: { hue: 30, sat: 0.4, light: 0.45, clapboard: true, painted: { hue: 36, sat: 0.3, light: 0.74, wear: 0.3 } }, style: { wall: "clapboard", shutters: { hue: 210, sat: 0.2, light: 0.36 }, chimney: { kind: "brick" }, steps: true, foundation: "posts" }, roof: W(210, 0.14, 0.32) }),
      B("hotel", { w: 6.4, h: 6.2, d: 5.4, windows: 2, falseFront: 1.4, sign: { text: "HOTEL", bg: "#2a1d3a", fg: "#f4e2b0" }, wall: { hue: 30, sat: 0.4, light: 0.45, clapboard: true, painted: { hue: 8, sat: 0.3, light: 0.46, wear: 0.3 } }, style: { wall: "clapboard", roof: "falseFront", storeys: 2, balcony: true, porch: { rail: false } } }),
      B("store, open door", { w: 5.8, h: 3.5, d: 5, windows: 2, lit: [1], wall: W(36, 0.3, 0.52), style: { awning: { kind: "canvas", stripe: W(150, 0.18, 0.4) }, door: { open: true, lit: true } } }),
      B("farmhouse", { w: 6, h: 3.2, d: 5, windows: 2, wall: { hue: 30, sat: 0.4, light: 0.45, clapboard: true, painted: { hue: 42, sat: 0.24, light: 0.84, wear: 0.2 } }, style: { wall: "clapboard", porch: { depth: 2.2 }, chimney: { kind: "brick" }, shutters: true } }),
      B("log cabin", { w: 4.6, h: 2.6, d: 4.2, windows: 1, style: { wall: "logs", chimney: { side: -1 }, foundation: "stone", door: { at: 1 } }, roof: W(28, 0.18, 0.3) }),
      B("bank (stone, hip)", { w: 6, h: 5.6, d: 5.6, windows: 2, sign: { text: "BANK", bg: "#1e2c24", fg: "#e8dcb0" }, wall: W(36, 0.1, 0.62), style: { wall: "stone", roof: "hip", storeys: 2, steps: true, foundation: "stone" }, roof: W(215, 0.1, 0.4) }),
    ],
  },
  {
    title: "Buildings: no style (round-2 pieces)",
    cols: 2, rows: 3, sx: 5.6, fit: 3.7,
    items: [
      B("shack", { w: 5, h: 3, d: 4.5, windows: 1, wall: W(26, 0.4, 0.4), roof: W(16, 0.5, 0.38) }),
      B("depot", { w: 7.4, h: 3.9, d: 6, windows: 3, lit: [1], sign: { text: "SWITCHYARD", bg: "#2a1650", fg: "#ffe9b0" }, wall: { hue: 30, sat: 0.6, light: 0.45, clapboard: true, painted: { hue: 8, sat: 0.7, light: 0.5, wear: 0.4 } }, roof: W(4, 0.7, 0.45) }),
      B("store", { w: 6.2, h: 4.4, d: 5.2, falseFront: 1.7, windows: 2, lit: [0], sign: { text: "STORE", bg: "#3a1a10", fg: "#ffe0a0" }, wall: W(44, 0.4, 0.6), roof: W(185, 0.55, 0.4) }),
      B("saloon", { w: 6, h: 3.6, d: 5, falseFront: 1.3, windows: 2, lit: [0, 1], sign: { text: "SALOON", bg: "#1a1030", fg: "#ffd27a" }, wall: W(12, 0.5, 0.42), roof: W(30, 0.5, 0.4) }),
      B("feed & seed", { w: 6.6, h: 4.0, d: 5.4, falseFront: 1.5, windows: 2, lit: [1], sign: { text: "FEED & SEED", bg: "#20301a", fg: "#f4f0c0" }, wall: W(40, 0.5, 0.55), roof: W(4, 0.5, 0.4) }),
      B("cottage, no windows", { w: 4.4, h: 2.8, d: 4, windows: 0, wall: W(22, 0.4, 0.36), roof: W(260, 0.35, 0.36) }),
    ],
  },
];

const PER = 12;
const PART_PAGES: Page[] = [];
for (let i = 0; i < PART_KINDS.length; i += PER) {
  PART_PAGES.push({ title: `Parts ${i + 1}-${Math.min(PART_KINDS.length, i + PER)} of ${PART_KINDS.length}`, cols: 3, rows: 4, sx: 3.4, fit: 2.5, items: PART_KINDS.slice(i, i + PER).map(partItem) });
}

// story parts are too long for the 12-up grid: one column, shown in context
// (rolling stock on railTrack, water with a boat on it, figures in a row)
const compose = (label: string, sub: string, size: Item["size"], parts: { kind: PartKind; seed: number; at?: [number, number, number] }[]): Item => ({
  label,
  sub,
  size,
  build: (m, ctx, make) => {
    const g = new THREE.Group();
    for (const p of parts) {
      const o = make(p.kind, p.seed, m, ctx);
      if (p.at) o.position.set(...p.at);
      g.add(o);
    }
    return g;
  },
  stick: true,
});
const track = (n: number) => Array.from({ length: n }, (_, i) => ({ kind: "railTrack" as PartKind, seed: 3 + i, at: [(i - (n - 1) / 2) * 4, 0, 0] as [number, number, number] }));
const STORY_PAGES: Page[] = [
  {
    title: "Story: rolling stock on railTrack",
    cols: 1, rows: 2, sx: 10.5, fit: 8.4, dy: 3.2, dz: 8,
    items: [
      compose("locomotive", "9 x 4.2 x 2.6 m on 3 railTrack", { w: 12, h: 4.2, d: 2.8, zc: 0 }, [...track(3), { kind: "locomotive", seed: 3 }]),
      compose("passengerCar", "8 x 3.7 x 2.6 m on 2 railTrack", { w: 8, h: 3.7, d: 2.8, zc: 0 }, [...track(2), { kind: "passengerCar", seed: 3 }]),
    ],
  },
  {
    title: "Story: people and water",
    cols: 1, rows: 4, sx: 8, fit: 5.6, dy: 2.0, dz: 6,
    items: [
      compose("horse x5", "2.3 x 1.9 x 0.8 m each, seeds 0-4 (bay, chestnut, grey, black, palomino)", { w: 7.8, h: 1.9, d: 2.2, zc: 0 }, [0, 1, 2, 3, 4].map((sd) => ({ kind: "horse" as PartKind, seed: sd, at: [sd < 3 ? (sd - 1) * 2.6 : (sd - 3.5) * 2.6, 0, sd < 3 ? 0.7 : -0.8] as [number, number, number] }))),
      compose("crowd", "5 x 1.9 x 2.2 m, seed 3", { w: 5, h: 1.9, d: 2.2, zc: 0 }, [{ kind: "crowd", seed: 3 }]),
      compose("bystander x6", "0.7 x 1.75 x 0.3 m each, seeds 1-6", { w: 5.4, h: 1.8, d: 0.3, zc: 0 }, [1, 2, 3, 4, 5, 6].map((sd) => ({ kind: "bystander" as PartKind, seed: sd, at: [(sd - 3.5) * 0.9, 0, 0] as [number, number, number] }))),
      compose("riverWater x2 + rowboat", "6 x 4 m each, chained along x", { w: 12, h: 0.6, d: 4, zc: 0 }, [{ kind: "riverWater", seed: 3, at: [-3, 0, 0] }, { kind: "riverWater", seed: 4, at: [3, 0, 0] }, { kind: "rowboat", seed: 3, at: [1.5, 0, 0.3] }]),
    ],
  },
];
// part grammar: the hand-built original beside the compiled spec, same size so same scale
const pair = (kind: PartKind, seeds: number[], spread: number, onTrack = 0): Item[] => {
  const d = PART_DIMS[kind];
  const w = d.w + spread * (seeds.length - 1) + (onTrack ? 2 : 0);
  return (["hand-built", "compiled"] as const).map((how) => ({
    label: `${kind} ${how}`,
    sub: how === "compiled" ? `derived ${d.w} x ${d.h} x ${d.d} m` : seeds.length > 1 ? `seeds ${seeds.join(", ")}` : `seed ${seeds[0]}`,
    size: { w, h: d.h, d: d.d, zc: 0 },
    build: (m, ctx) => {
      const g = new THREE.Group();
      for (let i = 0; i < onTrack; i++) {
        const t = makePart("railTrack", 3 + i, m, ctx);
        t.position.x = (i - (onTrack - 1) / 2) * 4;
        g.add(t);
      }
      seeds.forEach((sd, i) => {
        const o = (how === "compiled" ? makePart : makeHandPart)(kind, sd, m, ctx);
        o.position.x = (i - (seeds.length - 1) / 2) * spread;
        g.add(o);
      });
      return g;
    },
    stick: true,
  }));
};
const GRAMMAR_PAGES: Page[] = [
  { title: "Grammar: crate, tent, pineTree", cols: 2, rows: 3, sx: 3.4, fit: 2.5, items: [...pair("crate", [3], 0), ...pair("tent", [3], 0), ...pair("pineTree", [3, 4], 2.6)] },
  { title: "Grammar: waterTower, bystander", cols: 2, rows: 2, sx: 4.4, fit: 3.4, items: [...pair("waterTower", [3], 0), ...pair("bystander", [1, 2, 3], 0.9)] },
  { title: "Grammar: locomotive (hand-built in front)", cols: 1, rows: 2, sx: 10.5, fit: 8.4, dy: 3.2, dz: 8, items: [...pair("locomotive", [3], 0, 3)] },
];
export const GALLERY_PAGES: Page[] = [...PART_PAGES, ...STORY_PAGES, ...BUILDING_PAGES, ...GRAMMAR_PAGES];

// ------------------------------------------------------------------ layout

const ROW_DZ = (p: Page) => p.dz ?? p.sx * 1.08;
const ROW_DY = (p: Page) => p.dy ?? p.sx * 0.95;
const YAW = -0.45;

const cellOf = (p: Page, i: number) => {
  const c = i % p.cols;
  const r = Math.floor(i / p.cols);
  return {
    x: (c - (p.cols - 1) / 2) * p.sx,
    y: r * ROW_DY(p),
    z: -r * ROW_DZ(p),
  };
};

const cameraFor = (p: Page) => {
  const fov = 20;
  const cam = new THREE.PerspectiveCamera(fov, 1080 / 1920, 0.5, 900);
  const depth = (p.rows - 1) * ROW_DZ(p);
  const top = (p.rows - 1) * ROW_DY(p);
  const target = new THREE.Vector3(0, top * 0.5 + p.fit * 0.4, -depth * 0.5);
  const half = Math.tan(((fov / 2) * Math.PI) / 180) * (1080 / 1920);
  const dist = (p.cols * p.sx + 0.6) / (2 * half) + depth * 0.5;
  cam.position.set(0, target.y + dist * 0.26, target.z + dist);
  cam.lookAt(target);
  cam.updateMatrixWorld(true);
  cam.updateProjectionMatrix();
  return cam;
};

const fitScale = (p: Page, it: Item) => {
  const s = Math.max(it.size.w * 0.9, it.size.d * 0.75, it.size.h * 0.85);
  return Math.min(2.6, p.fit / Math.max(0.2, s));
};

// ------------------------------------------------------------------ scene

const buildScene = (p: Page, night: boolean, hand: boolean) => {
  const scene = new THREE.Scene();
  const tod = night ? 0.96 : 0.12;
  const sky = makeSky();
  const sk = skyAt(tod, {});
  const u = sky.uniforms;
  u.zenith.value.copy(sk.zenith);
  u.horizon.value.copy(sk.horizon);
  u.ground.value.copy(sk.ground);
  u.cloudColor.value.copy(sk.cloud);
  u.sunColor.value.copy(sk.sun);
  u.sunDir.value.set(-1, sk.sunElevation, 0.25).normalize();
  u.stars.value = sk.stars;
  scene.add(sky.sky);

  const li = lightsAt(tod, {});
  const key = new THREE.DirectionalLight(li.keyColor, li.keyIntensity);
  const depth = (p.rows - 1) * ROW_DZ(p);
  const centre = new THREE.Vector3(0, 0, -depth / 2);
  key.position.copy(centre).add(new THREE.Vector3(li.keyDir.r, li.keyDir.g, li.keyDir.b).normalize().multiplyScalar(60));
  key.target.position.copy(centre);
  key.castShadow = true;
  key.shadow.mapSize.set(4096, 4096);
  const ext = Math.max(p.cols * p.sx, depth) * 0.75 + 4;
  Object.assign(key.shadow.camera, { left: -ext, right: ext, top: ext, bottom: -ext, near: 1, far: 140 });
  key.shadow.bias = -0.0006;
  key.shadow.normalBias = 0.03;
  scene.add(key, key.target, new THREE.HemisphereLight(li.hemiSky, li.hemiGround, li.hemiIntensity));

  // terraces: one raised dirt shelf per row
  const dirt = new THREE.MeshLambertMaterial({ map: T.dirt(51, 34, 0.26, 0.56) });
  const edge = new THREE.MeshLambertMaterial({ map: T.planks({ seed: 52, planks: 3, hue: 26, sat: 0.3, light: 0.36 }) });
  const wide = p.cols * p.sx + 2;
  for (let r = 0; r < p.rows; r++) {
    const y = r * ROW_DY(p);
    const z = -r * ROW_DZ(p);
    const h = y + 0.3;
    scene.add(mesh(worldBox(wide, h, ROW_DZ(p), 3), [edge, edge, dirt, dirt, edge, edge], [0, y - h / 2, z]));
  }
  const floor = mesh(worldBox(400, 0.2, 400, 6), dirt, [0, -0.4, -150]);
  scene.add(floor);

  const m = makePartMaterials();
  const ctx: PartCtx = { glows: [], lamps: [], smokeLocal: [] };
  const stick = [new THREE.MeshLambertMaterial({ color: 0x3a2c40 }), new THREE.MeshLambertMaterial({ color: 0xe8dcc4 })];
  const smokeMarker = new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.85 });
  p.items.forEach((it, i) => {
    const c = cellOf(p, i);
    const s = fitScale(p, it);
    const g = it.build(m, ctx, hand ? makeHandPart : makePart);
    const holder = new THREE.Group();
    holder.position.set(c.x, c.y, c.z - it.size.zc * s * Math.cos(YAW));
    holder.rotation.y = p.yaw ?? YAW;
    holder.scale.setScalar(s);
    holder.add(g);
    scene.add(holder);
    // smoke emitters: a small white marker so the point can be checked by eye
    holder.updateMatrixWorld(true);
    for (const pt of (g.userData.smoke as THREE.Vector3[] | undefined) ?? []) {
      const dot = new THREE.Mesh(new THREE.SphereGeometry(0.09 * s, 8, 6), smokeMarker);
      dot.position.copy(pt.clone().applyMatrix4(g.matrixWorld));
      dot.userData.noInk = true;
      scene.add(dot);
    }
    if (it.stick) {
      for (let k = 0; k < 4; k++) {
        const band = mesh(new THREE.CylinderGeometry(0.018 * s, 0.018 * s, 0.25 * s, 6), stick[k % 2], [0, 0, 0]);
        band.position.set(c.x - p.sx * 0.42, c.y + (k + 0.5) * 0.25 * s, c.z + p.sx * 0.3);
        scene.add(band);
      }
    }
  });
  for (const gl of ctx.glows) gl.mat.emissive.copy(gl.color).multiplyScalar(night ? gl.peak : 0);
  for (const l of ctx.lamps) l.light.intensity = night ? l.peak : 0;

  const camera = cameraFor(p);
  sky.sky.position.copy(camera.position);
  return { scene, camera, grade: gradeAt(tod, {}) };
};

const Runner: React.FC<{ page: Page; night: boolean; hand: boolean }> = ({ page, night, hand }) => {
  const { gl } = useThree();
  const state = useRef<{ s: ReturnType<typeof buildScene>; pipe: InkPipeline } | null>(null);
  const flags: FxFlags = { shadows: true, ink: true, grade: true, dof: false };
  useFrame(() => {
    if (!state.current) {
      state.current = { s: buildScene(page, night, hand), pipe: new InkPipeline(gl, flags, 0) };
    }
    const { s, pipe } = state.current;
    const dof: Dof = { focus: 30, strength: 0, maxRadius: 1 };
    pipe.render(gl, s.scene, s.camera, s.grade, dof);
  }, 1);
  return null;
};

export const PartsGallery: React.FC<Record<string, unknown>> = (props) => {
  const n = GALLERY_PAGES.length;
  const page = GALLERY_PAGES[((Number(props.page ?? 0) % n) + n) % n];
  return <GalleryView page={page} night={!!props.night} hand={!!props.hand} />;
};

/** one gallery page on its lit terraces, with the title and the item labels */
export const GalleryView: React.FC<{ page: Page; night: boolean; hand?: boolean }> = ({ page, night, hand = false }) => {
  const { width, height } = useVideoConfig();
  const dpr = typeof window !== "undefined" ? window.devicePixelRatio : 1;
  const cam = cameraFor(page);
  const labels = page.items.map((it, i) => {
    const c = cellOf(page, i);
    const v = new THREE.Vector3(c.x, c.y + 0.02, c.z + ROW_DZ(page) * 0.4).project(cam);
    return { it, x: ((v.x + 1) / 2) * width, y: ((1 - v.y) / 2) * height };
  });
  return (
    <AbsoluteFill style={{ backgroundColor: "#1a1440" }}>
      <ThreeCanvas
        width={width}
        height={height}
        dpr={dpr}
        flat
        linear
        shadows={{ enabled: true, type: THREE.PCFShadowMap }}
        gl={{ antialias: false, alpha: false, powerPreference: "high-performance" }}
      >
        <Runner page={page} night={night} hand={hand} />
      </ThreeCanvas>
      <div style={{ position: "absolute", left: 0, right: 0, top: 36, textAlign: "center", font: "700 40px system-ui, sans-serif", color: "#2b2238", textShadow: "0 1px 0 #fff8" }}>
        {page.title}
        {night ? " (night)" : ""}
      </div>
      {labels.map(({ it, x, y }) => (
        <div
          key={it.label}
          style={{
            position: "absolute", left: x - 170, top: y, width: 340, textAlign: "center",
            font: "700 25px system-ui, sans-serif", color: "#2b2238",
          }}
        >
          <span style={{ background: "#f6eedfdd", padding: "2px 10px", borderRadius: 8 }}>{it.label}</span>
          <div style={{ font: "500 18px system-ui, sans-serif", marginTop: 4, color: "#3d3350" }}>
            <span style={{ background: "#f6eedfaa", padding: "1px 6px", borderRadius: 6 }}>{it.sub}</span>
          </div>
        </div>
      ))}
    </AbsoluteFill>
  );
};
