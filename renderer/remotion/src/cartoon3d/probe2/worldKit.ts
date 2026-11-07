// PROBE 2 (throwaway, TMDEV-179 Level-3 question): can an agent compose two
// genuinely different worlds out of ONE pool of parts, emitting data only?
//
// This file is PURE — three.js math and the seeded RNG only, never a texture,
// never `document`. That is load-bearing: the headless QA check imports it, so
// it must run in Node. The DOM half (materials, meshes) is worldBuild.ts.
//
// Round 2 rule, learned the hard way: `placements()` is the ONE place any
// position is computed. The renderer and the checker both consume it. Round 1's
// checker re-implemented the scatter with a different RNG and silently tested
// trees and rocks at positions that were never rendered.
import * as THREE from "three";
import type { Beat, Pose } from "../kit/cameraPath";
import { makeRng, range, smooth } from "../kit/prng";
import type { Look } from "./look";
import type { AtmosphereOpts } from "./atmosphere";
import type { GroundDetail } from "./ground";
import { terrainHeight, type TerrainSpec } from "./groundSpec";
import type { BoyGesture } from "../carrington/newsboy";
import type { PartSpec } from "./partGrammar";
import { figureHeight, type FigureSpec } from "../kit/Figure";
import { buildingExtent, partDims, partInfo, resolveStyle, type BuildingStyle, type PartKind, type PropName } from "./partsSpec";
import type { OpGesture } from "../carrington/operator";

// ------------------------------------------------------------- rig limits
// Shared by the renderer (how the walk is drawn) and the checker (what speed
// the walk can physically show). One definition, so they cannot disagree.
export const FPS = 30;
/** canvas design units per metre of stride (calibrated in spike 2's walk) */
export const STRIDE_PER_M = 800;
/** widest step the newsboy's legs can draw without breaking the figure */
export const MAX_STRIDE = 330; // round 3: the figure now draws a brisk walk cleanly (was 170)
/** one cycle = two steps. 20 frames = 3 steps/s = 10 frames per step, inside
 *  the reference's measured 9-12 (spike 2 sat at 12.5 and read as a stroll) */
export const WALK_CYCLE_FRAMES = 20;
export const STEPS_PER_S = (2 * FPS) / WALK_CYCLE_FRAMES;
/** fastest a character can move before its feet visibly slide */
export const MAX_WALK_MPS = (MAX_STRIDE / STRIDE_PER_M) * STEPS_PER_S;
/** walks finish this far into their beat, so the last pose settles */
export const WALK_FRACTION = 0.85;

// ---------------------------------------------------------------- schema

export type Hsl = { hue: number; sat: number; light: number };

/** The ground plan owns ALL spatial meaning. The agent picks slots in it. */
export type Plan =
  | { kind: "street"; northZ: number; southZ: number; pitch: number; x0: number }
  | { kind: "clearing"; radius: number; slots: number };

export interface SlotRef {
  row?: "north" | "south";
  slot: number;
}

/** Props come from the round-3 parts catalog (82 kinds). Kept under the old
 *  names so worlds and the checker read the same. */
/** a kit kind, a promoted part, or a part this world carries in `parts` */
export type PropKind = PropName;

export interface WaterPiece {
  w: number;
  d: number;
  at?: SlotRef;
  out?: number;
  along?: number;
  /** world x, z of the centre (instead of a slot) */
  pos?: [number, number];
  yaw?: number;
  /** surface height (m); default 0.06 so it wins over the ground */
  y?: number;
  /** current in m/s, world xz; crests drift with it. Default a slow +x */
  flow?: [number, number];
  /** crest density, 1 = the reference's */
  marks?: number;
}

export interface BuildingPiece {
  kind: "building";
  at: SlotRef;
  w: number;
  h: number;
  d: number;
  wall: Hsl & { clapboard?: boolean; painted?: Hsl & { wear: number } };
  roof: Hsl;
  falseFront?: number;
  windows?: number;
  lit?: number[];
  sign?: { text: string; bg: string; fg: string };
  seed: number;
  /** walls, roof, porch, awning, door, chimney, storeys... (partsSpec.ts) */
  style?: BuildingStyle;
}
export interface PlatformPiece { kind: "platform"; at: SlotRef; w: number; d: number; h: number; out: number; wood: Hsl }
export interface PathPiece { kind: "path"; width: number; hsl: Hsl }

export type Piece =
  | BuildingPiece
  | PlatformPiece
  | PathPiece
  | { kind: "poleRun"; at: SlotRef; count: number; spacing: number; height: number; out: number; axis: "x" | "z" }
  | {
      kind: "scatter";
      /** tree/rock/tuft, or ANY part kind (shrub, pineTree, deadTree, rockPile, reeds...) */
      what: "tree" | "rock" | "tuft" | PartKind;
      count: number;
      ring?: { r0: number; r1: number };
      band?: { x0: number; x1: number; z0: number; z1: number };
      scale: [number, number];
      seed: number;
      leaf?: Hsl;
    }
  /** one prop, placed in a slot like a mark is. `name` lets beats move, show, hide and act it
   *  (BeatSpec.props); `hidden` keeps it out of the world until a beat shows it. */
  | { kind: "prop"; what: PropKind; at: SlotRef; out: number; along?: number; turn?: number; name?: string; hidden?: boolean }
  /** set dressing around a mark: the agent says WHERE-ish, the kit packs it.
   *  "upstage" = behind the subject AS SEEN FROM `shot` — the only side that is
   *  reliably in a 9:16 frame, whose horizontal field of view is just ~27 deg. */
  | {
      kind: "cluster";
      near: string;
      side: "behind" | "left" | "right" | "around" | "upstage";
      shot?: string;
      r0: number;
      r1: number;
      count: number;
      what: PropKind[];
      seed: number;
    }
  | { kind: "fence"; at: SlotRef; out: number; along?: number; length: number; turn?: number };

export interface MarkSpec {
  name: string;
  at: SlotRef;
  out: number;
  along?: number;
}

export interface ShotSpec {
  name: string;
  subject: string;
  dist: number;
  height: number;
  swing: number;
  fov: number;
  aim: number;
  push?: number;
  rise?: number;
  /** FOREGROUND FRAMING: a prop placed just in front of the lens at one frame
   *  edge (side -1 = left, 1 = right), softened by the depth of field. The
   *  near-midground-far layering the reference shots all have. */
  fg?: { what: PropKind; side: -1 | 1; dist?: number; turn?: number };
  /** the camera travels with this NAMED prop: the shot is framed on its subject as usual at the beat's first
   *  frame, then camera and target move by the prop's displacement since then (a boat under way stays framed) */
  follow?: string;
  /** multiplier on the hold creep (the slow push every held shot has; default 1). A `follow` shot defaults to 0:
   *  it rides with its prop and keeps its framing, and `push` alone moves it. */
  creep?: number;
  /** DEPTH OF FIELD: blur-disc radius at infinity in px of a 1080x1920 frame (the skill's table: close-ups 12-14,
   *  medium shots 10-12, inserts 12-14, wides and aerials 0). Absent = from the focus distance. */
  dof?: number;
}

export interface WorldSpec {
  name: string;
  plan: Plan;
  ground: { tex: "dirt" | "cobbles" | "stone"; hsl: Hsl; seed: number };
  pieces: Piece[];
  marks: MarkSpec[];
  shots: ShotSpec[];
  backdrop?: { file: string; y: number; height: number; radius: number; repeat: number };
  fog: { near: number; far: number };
  tod: [number, number];
  /** per-world grade knobs (warmth, saturation, rim, sky hue) */
  look?: Look;
  /** parts this world brings along, written in the part grammar, by name.
   *  Props name them like kit kinds. Each one must pass the gate (gateCli.ts). */
  parts?: Record<string, PartSpec>;
  /** the people of this video, as data (kit/Figure.ts FigureSpec), by name. Beats name them in `cast[].who` beside
   *  the fixed "newsboy" and "operator". Each one must pass the gate like a part. */
  cast?: Record<string, FigureSpec>;
  /** rolling land beyond a flat playable zone (absent = a flat plane) */
  terrain?: TerrainSpec;
  /** WATER as kit surfaces (kit/Water.ts): flat sheets coloured by distance and by the light, with drifting crests.
   *  Placed at a slot like a prop (`at`, `out`, `along`) or at world coordinates (`pos`). Not solid, not walkable. */
  water?: WaterPiece[];
  /** ruts, puddles and worn patches — flat decals, so inside the flat zone only */
  detail?: GroundDetail;
  /** dust motes and fireflies (smoke comes from chimneys and fires automatically) */
  atmos?: Omit<AtmosphereOpts, "seed" | "smoke">;
}

export interface BeatSpec {
  start: number;
  end: number;
  shot: string;
  cut?: boolean;
  cast: {
    /** "operator", "newsboy", or a name from WorldSpec.cast */
    who: "operator" | "newsboy" | (string & {});
    mark: string;
    to?: string;
    action: "idle" | "walk" | "point" | "react";
    /** held through the beat, blended in over ~10 frames. Newsboy: wave cheer
     *  shout holdPaper shrug lookUp think. Operator: wave point armsCrossed
     *  handsOnHips talk. */
    gesture?: BoyGesture | OpGesture;
    /** -1 look left .. 1 look right */
    headTurn?: number;
    /** operator "point": degrees, 0 = screen right, 90 = up */
    pointAngle?: number;
    /** GESTURE CUES timed inside the beat, so a reaction lands on its word: at `frame` (absolute, inside the beat,
     *  taken from the timeline's word timings) the figure changes to `gesture` and/or turns the head, blended over
     *  ~10 frames and landing LEAD frames early like every gesture. Before the first cue the beat's own `gesture`
     *  holds; each cue holds until the next. In frame order. */
    cues?: { frame: number; gesture?: BoyGesture | OpGesture; headTurn?: number }[];
  }[];
  /** what named props do in this beat: move between places, appear, vanish, act. A prop keeps the state
   *  its last cue left it in (so a boat that sailed to the landing stays there). */
  props?: PropCue[];
  /** fog for this beat (metres), blended in over the beat's first `blend` frames (default 12; 0 = cut); absent =
   *  the world's fog. `color`: an on-screen hex (white-grey for a river fog, the sunset haze pink); absent = the
   *  sky's horizon (aerial perspective). The ink of fogged geometry fades toward the same colour. */
  fog?: { near: number; far: number; color?: string; blend?: number };
  /** TIME OF DAY for this beat, 0 day .. 0.5 golden hour .. 0.8 dusk .. 1 night, snapped at the beat's start
   *  (beats are cuts); absent = the world's clock `tod: [from, to]` over the video. A sunset video is "day" beats
   *  and "0.5" beats, not a clock that drifts through the grey in between. */
  tod?: number;
}

/** where a prop may be sent: a mark by name, or a slot like a piece */
export type Place = string | (SlotRef & { out: number; along?: number });

export interface PropCue {
  /** the prop piece's `name` */
  name: string;
  /** where it is when the beat starts (default: where its last cue left it, else its placed spot) */
  from?: Place;
  /** where it is when the beat ends; absent = stays at `from` */
  to?: Place;
  /** "linear" (a vehicle under way) or "inOut" (default: starts and stops gently) */
  ease?: "linear" | "inOut";
  /** false hides the prop for this beat (and after, until a cue shows it) */
  visible?: boolean;
  /** yaw in degrees relative to the place's facing (default: keep the piece's turn) */
  turn?: number;
  /** passed to a code part's animate() as `act` (see partSpecs/code/types.ts); e.g. { tap: 1 } or { busy: 1 } */
  act?: Record<string, number>;
}

// ------------------------------------------------------------ slot resolving

export interface Spot {
  pos: THREE.Vector3;
  face: THREE.Vector3;
  yaw: number;
}

export const resolveSlot = (plan: Plan, at: SlotRef): Spot => {
  if (plan.kind === "street") {
    const north = (at.row ?? "north") === "north";
    const face = new THREE.Vector3(0, 0, north ? 1 : -1);
    return {
      pos: new THREE.Vector3(plan.x0 + at.slot * plan.pitch, 0, north ? plan.northZ : plan.southZ),
      face,
      yaw: Math.atan2(face.x, face.z),
    };
  }
  const a = (at.slot / plan.slots) * Math.PI * 2;
  const pos = new THREE.Vector3(Math.cos(a) * plan.radius, 0, Math.sin(a) * plan.radius);
  const face = pos.clone().multiplyScalar(-1).normalize();
  return { pos, face, yaw: Math.atan2(face.x, face.z) };
};

const rightOf = (face: THREE.Vector3) => new THREE.Vector3(face.z, 0, -face.x);

export const offsetSpot = (plan: Plan, at: SlotRef, out: number, along = 0): Spot => {
  const s = resolveSlot(plan, at);
  const pos = s.pos.clone().addScaledVector(s.face, out).addScaledVector(rightOf(s.face), along);
  return { pos, face: s.face.clone(), yaw: s.yaw };
};

// -------------------------------------------------------------- placements

/** An oriented footprint box. Local x = the item's right, local z = its face. */
export interface Box {
  cx: number;
  cz: number;
  y0: number;
  w: number;
  h: number;
  d: number;
  yaw: number;
}

export const inBox = (b: Box, x: number, z: number, pad = 0) => {
  const dx = x - b.cx;
  const dz = z - b.cz;
  const c = Math.cos(b.yaw);
  const s = Math.sin(b.yaw);
  const lx = dx * c - dz * s;
  const lz = dx * s + dz * c;
  return Math.abs(lx) <= b.w / 2 + pad && Math.abs(lz) <= b.d / 2 + pad;
};

/** Sign board size and height, derived once and shared by builder and checker.
 *  The canvas widens with the text, and the board keeps the canvas's aspect so
 *  the texture is stretched exactly once across it. */
export const signDims = (b: BuildingPiece) => {
  const ch = 256;
  const cw = Math.max(768, Math.ceil((b.sign?.text.length ?? 0) * 84 + 140));
  const sw = Math.min(b.w * 0.85, (b.h * 0.22 * cw) / ch);
  const sh = (sw * ch) / cw;
  // above the windows (their trim tops out near 0.55h + 0.56), below the eave
  const cy = b.h * 0.86;
  return { cw, ch, sw, sh, cy };
};

export type Placed =
  | { kind: "building"; piece: BuildingPiece; pos: THREE.Vector3; yaw: number; boxes: Box[]; tag: string; sign?: THREE.Vector3[] }
  | { kind: "platform"; piece: PlatformPiece; pos: THREE.Vector3; yaw: number; boxes: Box[]; tag: string }
  | { kind: "pole"; pos: THREE.Vector3; yaw: number; height: number; run: number; boxes: Box[]; tag: string }
  | { kind: "tree"; pos: THREE.Vector3; scale: number; seed: number; leafHue: number; boxes: Box[]; tag: string }
  | { kind: "rock"; pos: THREE.Vector3; scale: number; seed: number; boxes: Box[]; tag: string }
  | { kind: "tuft"; pos: THREE.Vector3; scale: number; seed: number; boxes: Box[]; tag: string }
  | { kind: "prop"; what: PropKind; pos: THREE.Vector3; yaw: number; scale: number; seed: number; explicit: boolean; boxes: Box[]; tag: string; solid: boolean; walkable: boolean; name?: string; hidden?: boolean }
  | { kind: "fence"; pos: THREE.Vector3; yaw: number; length: number; boxes: Box[]; tag: string }
  | { kind: "path"; piece: PathPiece; boxes: Box[]; tag: string };

/** Things a character cannot stand inside, and a camera ray cannot pass. */
export const SOLID = new Set<Placed["kind"]>(["building", "pole", "tree", "rock", "prop", "fence"]);
/** Per item: a prop is solid only if the catalog says so and it is not a floor
 *  (rail track, pond and reeds are not solid; a dock is walked on). */
export const isSolid = (p: Placed) =>
  SOLID.has(p.kind) && !(p.kind === "prop" && (!p.solid || p.walkable));

export interface Layout {
  spec: WorldSpec;
  placed: Placed[];
  /** surface height under (x, z): a platform's top, else the ground */
  groundAt: (x: number, z: number) => number;
  markAt: (name: string) => THREE.Vector3;
  markFace: (name: string) => THREE.Vector3;
}

export const layout = (spec: WorldSpec): Layout => {
  const plan = spec.plan;
  const placed: Placed[] = [];
  const dimsOf = (what: PropKind) => partDims(what, spec.parts);
  const propBox = (what: PropKind, pos: THREE.Vector3, yaw: number, scale: number): Box => {
    const d = dimsOf(what);
    return { cx: pos.x, cz: pos.z, y0: pos.y, w: d.w * scale, h: d.h * scale, d: d.d * scale, yaw };
  };
  /** the catalog facts a placed prop carries, so the checker never looks them up */
  const facts = (what: PropKind) => {
    const i = partInfo(what, spec.parts);
    return { solid: i.solid, walkable: !!i.walkable };
  };
  const markSpots = new Map(spec.marks.map((m) => [m.name, offsetSpot(plan, m.at, m.out, m.along)]));
  const markList = [...markSpots.values()];

  /** extra floors a character can stand on: porches, docks, rail beds */
  const surfaces: Box[] = [];
  const buildingBoxes = () => placed.filter((p) => p.kind === "building").flatMap((p) => p.boxes);
  const platformBoxes = () => [
    ...placed.filter((p) => p.kind === "platform").flatMap((p) => p.boxes),
    ...surfaces,
    ...placed.filter((p) => p.kind === "prop" && p.walkable).flatMap((p) => p.boxes),
  ];
  const nearMark = (x: number, z: number, r: number) => markList.some((m) => Math.hypot(m.pos.x - x, m.pos.z - z) < r);
  const inAny = (bs: Box[], x: number, z: number, pad: number) => bs.some((b) => inBox(b, x, z, pad));
  /** a prop on a platform stands on its deck, not sunk into it */
  /** land height: 0 in the flat zone, rolling hills beyond it */
  const land = (x: number, z: number) => (spec.terrain ? terrainHeight(spec.terrain, x, z) : 0);
  const surface = (x: number, z: number) => {
    let y = land(x, z);
    for (const b of platformBoxes()) if (inBox(b, x, z)) y = Math.max(y, b.y0 + b.h);
    return y;
  };

  // 1. buildings and platforms — the fixed frame everything else avoids
  for (const p of spec.pieces) {
    if (p.kind === "building") {
      const s = resolveSlot(plan, p.at);
      const c = s.pos.clone().addScaledVector(s.face, -p.d / 2);
      const bin = { w: p.w, h: p.h, d: p.d, falseFront: p.falseFront, style: p.style, seed: p.seed, windows: p.windows, wall: p.wall };
      const top = buildingExtent(bin).top;
      const rs = resolveStyle(bin);
      if (rs.porch && rs.floor > 0.01) {
        const pc = s.pos.clone().addScaledVector(s.face, rs.porch.depth / 2);
        surfaces.push({ cx: pc.x, cz: pc.z, y0: 0, w: p.w, h: rs.floor, d: rs.porch.depth, yaw: s.yaw });
      }
      let sign: THREE.Vector3[] | undefined;
      if (p.sign) {
        const sd = signDims(p);
        const mid = s.pos.clone().addScaledVector(s.face, 0.13).setY(sd.cy);
        const r = rightOf(s.face);
        sign = [[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([a, b]) =>
          mid.clone().addScaledVector(r, (a * sd.sw) / 2).add(new THREE.Vector3(0, (b * sd.sh) / 2, 0)));
      }
      placed.push({
        kind: "building", piece: p, pos: s.pos, yaw: s.yaw, tag: `building@${p.at.row ?? ""}${p.at.slot}`,
        boxes: [{ cx: c.x, cz: c.z, y0: 0, w: p.w, h: top, d: p.d, yaw: s.yaw }], sign,
      });
    } else if (p.kind === "platform") {
      const s = offsetSpot(plan, p.at, p.out);
      placed.push({
        kind: "platform", piece: p, pos: s.pos, yaw: s.yaw, tag: `platform@${p.at.slot}`,
        boxes: [{ cx: s.pos.x, cz: s.pos.z, y0: 0, w: p.w, h: p.h, d: p.d, yaw: s.yaw }],
      });
    } else if (p.kind === "path") {
      const box: Box =
        plan.kind === "street"
          ? { cx: 0, cz: (plan.northZ + plan.southZ) / 2, y0: 0, w: 260, h: 0, d: p.width, yaw: 0 }
          : { cx: 0, cz: 0, y0: 0, w: p.width, h: 0, d: p.width, yaw: 0 };
      placed.push({ kind: "path", piece: p, boxes: [box], tag: "path" });
    }
  }

  // 2. explicit pieces the agent placed one by one
  let run = 0;
  for (const p of spec.pieces) {
    if (p.kind === "poleRun") {
      const s = offsetSpot(plan, p.at, p.out);
      for (let i = 0; i < p.count; i++) {
        const at = s.pos.clone();
        if (p.axis === "x") at.x += i * p.spacing;
        else at.z += i * p.spacing;
        placed.push({
          kind: "pole", pos: at, yaw: p.axis === "x" ? 0 : Math.PI / 2, height: p.height, run, tag: `pole${run}.${i}`,
          boxes: [{ cx: at.x, cz: at.z, y0: 0, w: 0.32, h: p.height, d: 0.32, yaw: 0 }],
        });
      }
      run++;
    } else if (p.kind === "prop") {
      const s = offsetSpot(plan, p.at, p.out, p.along);
      s.pos.y = surface(s.pos.x, s.pos.z);
      const yaw = s.yaw + ((p.turn ?? 0) * Math.PI) / 180;
      placed.push({
        kind: "prop", what: p.what, pos: s.pos, yaw, scale: 1, seed: 1, explicit: true, ...facts(p.what),
        tag: p.name ?? `${p.what}@${p.at.row ?? ""}${p.at.slot}`, boxes: [propBox(p.what, s.pos, yaw, 1)], name: p.name, hidden: p.hidden,
      });
    } else if (p.kind === "fence") {
      const s = offsetSpot(plan, p.at, p.out, p.along);
      const yaw = s.yaw + ((p.turn ?? 0) * Math.PI) / 180;
      const dir = new THREE.Vector3(Math.cos(yaw), 0, -Math.sin(yaw)); // local +x
      const c = s.pos.clone().addScaledVector(dir, p.length / 2);
      placed.push({
        kind: "fence", pos: s.pos, yaw, length: p.length, tag: `fence@${p.at.row ?? ""}${p.at.slot}`,
        boxes: [{ cx: c.x, cz: c.z, y0: 0, w: p.length, h: 1.1, d: 0.15, yaw }],
      });
    }
  }

  // 2b. foreground framing props: in front of the camera at the frame edge,
  // from the shot's own pose (same maths as poseForShot at t = 0)
  for (const sh of spec.shots) {
    if (!sh.fg) continue;
    const m = markSpots.get(sh.subject);
    if (!m) throw new Error(`shot ${sh.name}: unknown subject ${sh.subject}`);
    const dir = m.face.clone().applyAxisAngle(new THREE.Vector3(0, 1, 0), (sh.swing * Math.PI) / 180);
    const cam = m.pos.clone().addScaledVector(dir, sh.dist);
    const fwd = dir.clone().multiplyScalar(-1);
    const right = new THREE.Vector3(-fwd.z, 0, fwd.x);
    const d = sh.fg.dist ?? 2.4;
    // a 9:16 frame at these lenses is ~28 deg wide: half-width = 0.25 d, so
    // 0.23 d puts the prop's centre just inside the edge, half in frame
    const pos = cam.clone().addScaledVector(fwd, d).addScaledVector(right, sh.fg.side * d * 0.23);
    pos.y = surface(pos.x, pos.z);
    const yaw = Math.atan2(fwd.x, fwd.z) + ((sh.fg.turn ?? 0) * Math.PI) / 180;
    placed.push({
      kind: "prop", what: sh.fg.what, pos, yaw, scale: 1, seed: 3, explicit: false, ...facts(sh.fg.what),
      tag: `${sh.fg.what}#fg:${sh.name}`, boxes: [propBox(sh.fg.what, pos, yaw, 1)],
    });
  }

  // 3. fill — clusters and scatter are SUBORDINATE: an item that would land in
  // a building, on a mark, or on another prop is dropped here, deterministically.
  // The agent controls amount and region, never the individual position.
  const propsSoFar = () => placed.filter((p) => p.kind === "prop");
  for (const p of spec.pieces) {
    if (p.kind !== "cluster") continue;
    const m = markSpots.get(p.near);
    if (!m) throw new Error(`cluster: unknown mark ${p.near}`);
    const rng = makeRng(p.seed);
    const base = Math.atan2(m.face.x, m.face.z); // angle the mark faces
    // upstage: continue the camera's line of sight past the subject
    let upstage = 0;
    if (p.side === "upstage") {
      const sh = spec.shots.find((x) => x.name === p.shot);
      if (!sh) throw new Error(`cluster near ${p.near}: upstage needs a known shot, got ${p.shot}`);
      const sm = markSpots.get(sh.subject)!;
      const cdir = sm.face.clone().applyAxisAngle(new THREE.Vector3(0, 1, 0), (sh.swing * Math.PI) / 180);
      upstage = Math.atan2(-cdir.x, -cdir.z); // camera sits along +cdir, so its view runs along -cdir
    }
    const arc =
      p.side === "upstage" ? { mid: upstage, half: 0.42 }
      : p.side === "behind" ? { mid: base + Math.PI, half: 1.2 }
      : p.side === "left" ? { mid: base - Math.PI / 2, half: 0.9 }
      : p.side === "right" ? { mid: base + Math.PI / 2, half: 0.9 }
      : { mid: 0, half: Math.PI };
    let got = 0;
    for (let tries = 0; tries < p.count * 8 && got < p.count; tries++) {
      const a = arc.mid + range(rng, -arc.half, arc.half);
      const r = range(rng, p.r0, p.r1);
      const what = p.what[Math.floor(range(rng, 0, p.what.length)) % p.what.length];
      const yaw = range(rng, 0, Math.PI * 2);
      const scale = range(rng, 0.9, 1.12);
      const pos = new THREE.Vector3(m.pos.x + Math.sin(a) * r, 0, m.pos.z + Math.cos(a) * r);
      pos.y = surface(pos.x, pos.z);
      const size = Math.max(dimsOf(what).w, dimsOf(what).d) * scale;
      if (inAny(buildingBoxes(), pos.x, pos.z, size / 2 + 0.15)) continue;
      if (nearMark(pos.x, pos.z, 0.9 + size / 2)) continue;
      if (propsSoFar().some((q) => Math.hypot(q.pos.x - pos.x, q.pos.z - pos.z) < (size + Math.max(q.boxes[0].w, q.boxes[0].d)) * 0.5)) continue;
      placed.push({
        kind: "prop", what, pos, yaw, scale, seed: p.seed * 31 + tries, explicit: false, ...facts(what),
        tag: `${what}~${p.near}`, boxes: [propBox(what, pos, yaw, scale)],
      });
      got++;
    }
  }

  for (const p of spec.pieces) {
    if (p.kind !== "scatter") continue;
    const rng = makeRng(p.seed);
    for (let i = 0; i < p.count; i++) {
      let x: number, z: number;
      if (p.ring) {
        const a = range(rng, 0, Math.PI * 2);
        const r = range(rng, p.ring.r0, p.ring.r1);
        x = Math.cos(a) * r;
        z = Math.sin(a) * r;
      } else {
        const b = p.band!;
        x = range(rng, b.x0, b.x1);
        z = range(rng, b.z0, b.z1);
      }
      const sc = range(rng, p.scale[0], p.scale[1]);
      const pos = new THREE.Vector3(x, land(x, z), z);
      const seed = p.seed + i;
      if (p.what === "tree") {
        if (inAny(buildingBoxes(), x, z, 1.6 * sc) || nearMark(x, z, 1.8 * sc)) continue;
        placed.push({
          kind: "tree", pos, scale: sc, seed, leafHue: p.leaf?.hue ?? 120, tag: `tree${i}`,
          boxes: [
            { cx: x, cz: z, y0: pos.y, w: 0.4 * sc, h: 2.2 * sc, d: 0.4 * sc, yaw: 0 },
            { cx: x, cz: z, y0: pos.y + 2.0 * sc, w: 2.6 * sc, h: 2.4 * sc, d: 2.6 * sc, yaw: 0 },
          ],
        });
      } else if (p.what !== "rock" && p.what !== "tuft") {
        const what = p.what as PartKind;
        const yaw = range(rng, 0, Math.PI * 2);
        const dim = dimsOf(what);
        const size = Math.max(dim.w, dim.d) * sc;
        if (inAny(buildingBoxes(), x, z, size / 2 + 0.2) || nearMark(x, z, 1 + size / 2)) continue;
        placed.push({
          kind: "prop", what, pos, yaw, scale: sc, seed, explicit: false, tag: `${what}*${i}`, ...facts(what),
          boxes: [{ cx: x, cz: z, y0: pos.y, w: dim.w * sc, h: dim.h * sc, d: dim.d * sc, yaw }],
        });
      } else if (p.what === "rock") {
        if (inAny(buildingBoxes(), x, z, sc) || nearMark(x, z, 1 + sc)) continue;
        placed.push({ kind: "rock", pos, scale: sc, seed, tag: `rock${i}`, boxes: [{ cx: x, cz: z, y0: pos.y, w: 1.8 * sc, h: 1.4 * sc, d: 1.8 * sc, yaw: 0 }] });
      } else {
        if (inAny(buildingBoxes(), x, z, 0.2) || inAny(platformBoxes(), x, z, 0.2) || nearMark(x, z, 0.7)) continue;
        placed.push({ kind: "tuft", pos, scale: sc, seed, tag: `tuft${i}`, boxes: [] });
      }
    }
  }

  const groundAt = (x: number, z: number) => {
    let y = land(x, z);
    for (const b of platformBoxes()) if (inBox(b, x, z)) y = Math.max(y, b.y0 + b.h);
    return y;
  };
  const markAt = (name: string) => {
    const s = markSpots.get(name);
    if (!s) throw new Error(`unknown mark ${name}`);
    return new THREE.Vector3(s.pos.x, groundAt(s.pos.x, s.pos.z), s.pos.z);
  };
  const markFace = (name: string) => {
    const s = markSpots.get(name);
    if (!s) throw new Error(`unknown mark ${name}`);
    return s.face.clone();
  };
  return { spec, placed, groundAt, markAt, markFace };
};

// ------------------------------------------------------- derived camera poses

export const poseForShot = (L: Layout, shot: ShotSpec, t: number): Pose => {
  const m = L.markAt(shot.subject);
  const face = L.markFace(shot.subject);
  const dist = shot.dist - (shot.push ?? 0) * t;
  const height = shot.height + (shot.rise ?? 0) * t;
  const a = (shot.swing * Math.PI) / 180;
  const dir = face.applyAxisAngle(new THREE.Vector3(0, 1, 0), a);
  const pos = m.clone().addScaledVector(dir, dist);
  pos.y = m.y + height;
  return { pos: [pos.x, pos.y, pos.z], target: [m.x, m.y + shot.aim, m.z], fov: shot.fov, focus: dist };
};

export const buildBeats = (L: Layout, beats: BeatSpec[]): Beat[] =>
  beats.map((b) => {
    const shot = L.spec.shots.find((s) => s.name === b.shot);
    if (!shot) throw new Error(`beat at ${b.start}: unknown shot ${b.shot}`);
    return { start: b.start, end: b.end, from: poseForShot(L, shot, 0), to: poseForShot(L, shot, 1), cut: b.cut, creep: shot.creep ?? (shot.follow ? 0 : 1) };
  });

/** Where a cast member stands at frame f of a beat. Shared by renderer and checker. */
export const castPosition = (L: Layout, beat: BeatSpec, role: BeatSpec["cast"][number], f: number) => {
  const span = Math.max(1, beat.end - beat.start);
  const bt = Math.max(0, Math.min(1, (f - beat.start) / span));
  const from = L.markAt(role.mark);
  const to = role.to ? L.markAt(role.to) : from;
  const wt = role.action === "walk" ? Math.min(1, bt / WALK_FRACTION) : 0;
  const at = from.clone().lerp(to, wt);
  at.y = L.groundAt(at.x, at.z);
  const speed = role.action === "walk" ? (from.distanceTo(to) / (span * WALK_FRACTION)) * FPS : 0;
  return { at, wt, speed, walking: role.action === "walk" && wt < 1 };
};

export interface PropPose {
  pos: THREE.Vector3;
  yaw: number;
  visible: boolean;
  /** the act of the cue governing this frame (empty when none) */
  act: Record<string, number>;
  /** 0..1 through the governing beat (1 after it) */
  beatT: number;
  /** metres per second this frame, for the checker */
  speed: number;
}

/** a place as a world spot: a mark by name, or a slot with an offset */
export const placeSpot = (L: Layout, place: Place) => {
  if (typeof place === "string") return { pos: L.markAt(place), face: L.markFace(place) };
  const s = offsetSpot(L.spec.plan, { row: place.row, slot: place.slot }, place.out, place.along);
  return { pos: s.pos, face: s.face };
};

/** Where a NAMED prop is, whether it shows and what it does at frame f: its cues are applied in beat order, and
 *  the last cue that started governs. Shared by the renderer and the checker. Unnamed props never move. */
export const propPoseAt = (L: Layout, sheet: BeatSpec[], placed: Extract<Placed, { kind: "prop" }>, f: number): PropPose => {
  const base = { pos: placed.pos.clone(), yaw: placed.yaw, visible: !placed.hidden, act: {} as Record<string, number>, beatT: 1, speed: 0 };
  let cur = base;
  let last: { pos: THREE.Vector3; yaw: number; visible: boolean } = base;
  for (const beat of sheet) {
    if (beat.start > f) break;
    const cue = beat.props?.find((c) => c.name === placed.name);
    if (!cue) continue;
    const from = cue.from ? placeSpot(L, cue.from) : { pos: last.pos.clone(), face: null };
    const to = cue.to ? placeSpot(L, cue.to) : from;
    const span = Math.max(1, beat.end - beat.start);
    const bt = Math.max(0, Math.min(1, (f - beat.start) / span));
    const wt = cue.ease === "linear" ? bt : smooth(bt);
    const pos = from.pos.clone().lerp(to.pos, wt);
    pos.y = L.groundAt(pos.x, pos.z);
    // facing: the direction of travel when it moves, else the place's facing, else what it had
    let yaw = last.yaw;
    const d = to.pos.clone().sub(from.pos).setY(0);
    if (d.lengthSq() > 1e-4) yaw = Math.atan2(d.x, d.z);
    else if (to.face) yaw = Math.atan2(to.face.x, to.face.z);
    if (cue.turn !== undefined) yaw += (cue.turn * Math.PI) / 180;
    const visible = cue.visible ?? last.visible;
    const speed = cue.to && d.lengthSq() > 1e-4 ? (d.length() / span) * FPS : 0;
    cur = { pos, yaw, visible, act: cue.act ?? {}, beatT: bt, speed };
    last = { pos: to.pos.clone().setY(L.groundAt(to.pos.x, to.pos.z)), yaw, visible };
  }
  return cur;
};

/** how far the camera of a `follow` shot has to move at frame f: the followed prop's displacement since the beat
 *  began (zero for shots that follow nothing). Shared by the renderer and the checker. */
export const followShift = (L: Layout, sheet: BeatSpec[], beat: BeatSpec, f: number): THREE.Vector3 => {
  const shot = L.spec.shots.find((s) => s.name === beat.shot);
  if (!shot?.follow) return new THREE.Vector3();
  const prop = L.placed.find((p): p is Extract<Placed, { kind: "prop" }> => p.kind === "prop" && p.name === shot.follow);
  if (!prop) throw new Error(`shot "${shot.name}" follows "${shot.follow}", but no prop piece has that name`);
  const now = propPoseAt(L, sheet, prop, f).pos;
  const then = propPoseAt(L, sheet, prop, beat.start).pos;
  return now.sub(then).setY(0);
};

/** GESTURE AT FRAME f: the beat's own gesture and head turn until a cue's frame (`lead` frames early), then that
 *  cue's, with the one before it to blend from. `since` is the cue's frame, -Infinity before any cue. Shared by the
 *  renderer and the checker. */
export const gestureAt = (role: BeatSpec["cast"][number], f: number, lead: number) => {
  let gesture = role.gesture, from = role.gesture, headTurn = role.headTurn ?? 0, headFrom = headTurn, since = -Infinity;
  for (const c of role.cues ?? []) {
    if (c.frame - lead > f) break;
    from = gesture;
    headFrom = headTurn;
    if (c.gesture !== undefined) gesture = c.gesture;
    if (c.headTurn !== undefined) headTurn = c.headTurn;
    since = c.frame;
  }
  return { gesture, from, headTurn, headFrom, since };
};

/** standing height in metres of a cast member: the two fixed characters, or a grammar figure's */
export const FIXED_CAST_H: Record<string, number> = { operator: 1.72, newsboy: 1.26 };
export const castHeight = (spec: WorldSpec, who: string): number => {
  if (who in FIXED_CAST_H) return FIXED_CAST_H[who];
  const fig = spec.cast?.[who];
  if (!fig) throw new Error(`unknown cast member "${who}": not newsboy, not operator, and not in this world's cast`);
  return figureHeight(fig);
};
