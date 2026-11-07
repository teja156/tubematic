// Part grammar — the PURE half (TMDEV-181). A part is plain JSON data: a list of
// primitives plus a few attach points and flags. partCompile.ts builds the
// meshes from it; deriveDims/deriveInfo build its QA footprint from the SAME
// placement walk, so the box the layout and checker use cannot disagree with
// what is drawn. No DOM here: the headless checker imports this through
// partsSpec.ts. (three's math classes are pure and already used by qa.ts.)
//
// Conventions are the parts pool's: the part stands on y = 0 at the origin,
// faces +z, local +x to its right. Lengths in metres, angles in degrees.
import * as THREE from "three";
import type { PartMaterials } from "./parts";

export type V3 = [number, number, number];

/** a single material from makePartMaterials() (type-only import: erased in Node) */
export type KitMat = { [K in keyof PartMaterials]: PartMaterials[K] extends THREE.Material ? K : never }[keyof PartMaterials];

/** A kit material, a list of them (one per geometry group: a closed cylinder's
 *  side, top, bottom), or a flat colour. `glow` makes it a lamp surface the
 *  scene drives at night (emissive rgb * peak); a glowing surface casts no shadow. */
export type MatRef = KitMat | KitMat[] | { hsl: V3; glow?: { rgb: V3; peak: number } };

/** canvas drawings a card can name (cardDraw.ts) */
export type CardDraw = "figure" | "plate";

interface Base {
  /** where the primitive sits in its parent's frame (default origin) */
  at?: V3;
  /** degrees, XYZ order like THREE.Euler */
  rot?: V3;
  mat?: MatRef;
  /** a decal: no ink outline and no cast shadow */
  noInk?: boolean;
  /** n copies; copy k is moved by k*step and turned by k*turn (degrees) about the parent origin */
  repeat?: { n: number; step?: V3; turn?: V3 };
  /** seeded +- spread per copy, drawn from the part seed in walk order.
   *  `rot` jitter is meant as a spin about the primitive's own axis: the footprint ignores it */
  jitter?: { at?: V3; rot?: V3 };
  /** texture coordinate scale */
  uv?: [number, number];
}

export type Prim =
  /** centred box, texture tiled per metre */
  | (Base & { kind: "box"; size: V3 })
  /** upright cylinder centred on `at`; `r` is the bottom radius, rTop 0 makes a cone */
  | (Base & { kind: "cylinder"; r: number; rTop?: number; h: number; seg?: number; open?: boolean })
  /** a cylinder from `from` (radius r) to `to` (radius rTop ?? r) */
  | (Base & { kind: "rod"; from: V3; to: V3; r: number; rTop?: number; seg?: number })
  /** sphere, or ellipsoid when r is per-axis radii */
  | (Base & { kind: "sphere"; r: number | V3; seg?: [number, number] })
  /** ring in the xy plane (axle along z) */
  | (Base & { kind: "torus"; r: number; tube: number; seg?: [number, number] })
  /** profile [radius, y][] spun about y; stands on `at` */
  | (Base & { kind: "lathe"; points: [number, number][]; seg?: number })
  /** outline [x, y][] in the xy plane: flat, or extruded `depth` along z (centred) */
  | (Base & { kind: "shape"; points: [number, number][]; depth?: number })
  /** flat rectangle in the xy plane facing +z, centred */
  | (Base & { kind: "plane"; size: [number, number] })
  /** canvas-drawn flat panel facing +z that STANDS on `at` (bottom centre).
   *  `heights` lets the seed pick its height (width keeps the size's aspect);
   *  `text` lets it pick the drawing's text; `thick` is the depth the flat
   *  figure stands for, used only by the footprint. */
  | (Base & { kind: "card"; draw: CardDraw; size: [number, number]; heights?: number[]; text?: string[]; thick?: number })
  /** a sub-assembly placed (and repeated) as one */
  | (Base & { kind: "group"; items: Prim[] });

export type Leaf = Exclude<Prim, { kind: "group" }>;

export interface PartSpec {
  name: string;
  blurb: string;
  prims: Prim[];
  smoke?: { at: V3; kind: "chimney" | "fire" | "stack" }[];
  /** PointLight the scene drives up at night (colour as hsl, default warm white) */
  lamp?: { at: V3; colour?: V3 }[];
  /** blocks walking and camera rays (default true) */
  solid?: boolean;
  /** a character may stand on it */
  walkable?: boolean;
  lightAtNight?: boolean;
}

// ------------------------------------------------------------------ walk

const DEG = Math.PI / 180;
const euler = (r: V3 | undefined) => new THREE.Euler((r?.[0] ?? 0) * DEG, (r?.[1] ?? 0) * DEG, (r?.[2] ?? 0) * DEG);

/** the seeded pick for a card's heights/text and the jitter stream (same seeding as makePart) */
export const pickBySeed = <X>(seed: number, list: X[]) => list[Math.abs(seed) % list.length];

export interface Placed {
  prim: Leaf;
  /** primitive frame -> part frame */
  m: THREE.Matrix4;
}

/** Every leaf primitive with its placement, in spec order. `rnd` draws the
 *  jitter (uniform 0..1); without it jitter sits at its centre. */
export const walk = (prims: Prim[], rnd?: () => number, parent = new THREE.Matrix4(), out: Placed[] = []): Placed[] => {
  for (const p of prims) {
    const n = p.repeat?.n ?? 1;
    for (let k = 0; k < n; k++) {
      const step = p.repeat?.step ?? [0, 0, 0];
      const turn = p.repeat?.turn ?? [0, 0, 0];
      const copy = new THREE.Matrix4()
        .makeTranslation(step[0] * k, step[1] * k, step[2] * k)
        .multiply(new THREE.Matrix4().makeRotationFromEuler(euler([turn[0] * k, turn[1] * k, turn[2] * k])));
      const at = [...(p.at ?? [0, 0, 0])] as V3;
      const rot = [...(p.rot ?? [0, 0, 0])] as V3;
      if (p.jitter && rnd) {
        for (const [dst, j] of [[at, p.jitter.at], [rot, p.jitter.rot]] as const) {
          if (j) for (let i = 0; i < 3; i++) if (j[i]) dst[i] += (rnd() * 2 - 1) * j[i];
        }
      }
      const local = new THREE.Matrix4().compose(new THREE.Vector3(...at), new THREE.Quaternion().setFromEuler(euler(rot)), new THREE.Vector3(1, 1, 1));
      const m = parent.clone().multiply(copy).multiply(local);
      if (p.kind === "group") walk(p.items, rnd, m, out);
      else out.push({ prim: p, m });
    }
  }
  return out;
};

// ------------------------------------------------------------------ bounds

/** grow `b` by a disc of radius r centred at c with unit normal n (exact) */
const disc = (b: THREE.Box3, c: THREE.Vector3, n: THREE.Vector3, r: number) => {
  const e = new THREE.Vector3(r * Math.sqrt(Math.max(0, 1 - n.x * n.x)), r * Math.sqrt(Math.max(0, 1 - n.y * n.y)), r * Math.sqrt(Math.max(0, 1 - n.z * n.z)));
  b.expandByPoint(c.clone().sub(e)).expandByPoint(c.clone().add(e));
};
/** grow `b` by a local box's eight corners under m */
const corners = (b: THREE.Box3, m: THREE.Matrix4, lo: V3, hi: V3) => {
  for (let i = 0; i < 8; i++) {
    b.expandByPoint(new THREE.Vector3(i & 1 ? hi[0] : lo[0], i & 2 ? hi[1] : lo[1], i & 4 ? hi[2] : lo[2]).applyMatrix4(m));
  }
};

/** the height a card is drawn at for this seed, and its width */
export const cardSize = (c: Extract<Leaf, { kind: "card" }>, seed: number) => {
  const h = c.heights ? pickBySeed(seed, c.heights) : c.size[1];
  return { w: (c.size[0] * h) / c.size[1], h };
};

/** World-space (part-frame) bounds of one placed primitive, over every seed. */
export const leafBounds = ({ prim: p, m }: Placed, b = new THREE.Box3()) => {
  const at = (v: V3) => new THREE.Vector3(...v).applyMatrix4(m);
  const axis = (v: V3) => new THREE.Vector3(...v).transformDirection(m);
  switch (p.kind) {
    case "box":
      corners(b, m, [-p.size[0] / 2, -p.size[1] / 2, -p.size[2] / 2], [p.size[0] / 2, p.size[1] / 2, p.size[2] / 2]);
      break;
    case "cylinder": {
      const n = axis([0, 1, 0]);
      disc(b, at([0, -p.h / 2, 0]), n, p.r);
      disc(b, at([0, p.h / 2, 0]), n, p.rTop ?? p.r);
      break;
    }
    case "rod": {
      const a = at(p.from);
      const c = at(p.to);
      const n = c.clone().sub(a).normalize();
      disc(b, a, n, p.r);
      disc(b, c, n, p.rTop ?? p.r);
      break;
    }
    case "sphere": {
      const r = typeof p.r === "number" ? [p.r, p.r, p.r] : p.r;
      corners(b, m, [-r[0], -r[1], -r[2]], r as V3);
      break;
    }
    case "torus": {
      const R = p.r + p.tube;
      corners(b, m, [-R, -R, -p.tube], [R, R, p.tube]);
      break;
    }
    case "lathe": {
      const R = Math.max(...p.points.map(([r]) => r));
      const ys = p.points.map(([, y]) => y);
      corners(b, m, [-R, Math.min(...ys), -R], [R, Math.max(...ys), R]);
      break;
    }
    case "shape": {
      const xs = p.points.map(([x]) => x);
      const ys = p.points.map(([, y]) => y);
      const z = (p.depth ?? 0) / 2;
      corners(b, m, [Math.min(...xs), Math.min(...ys), -z], [Math.max(...xs), Math.max(...ys), z]);
      break;
    }
    case "plane":
      corners(b, m, [-p.size[0] / 2, -p.size[1] / 2, 0], [p.size[0] / 2, p.size[1] / 2, 0]);
      break;
    case "card": {
      const h = Math.max(...(p.heights ?? [p.size[1]]));
      const w = (p.size[0] * h) / p.size[1];
      const t = (p.thick ?? 0) / 2;
      corners(b, m, [-w / 2, 0, -t], [w / 2, h, t]);
      break;
    }
  }
  const j = p.jitter?.at;
  if (j) b.expandByVector(new THREE.Vector3(Math.abs(j[0]), Math.abs(j[1]), Math.abs(j[2])));
  return b;
};

/** Part-frame bounds of everything the spec draws. */
export const specBounds = (spec: PartSpec) => {
  const b = new THREE.Box3();
  for (const pl of walk(spec.prims)) b.union(leafBounds(pl));
  return b;
};

const up = (v: number) => Math.ceil(v * 100 - 1e-6) / 100;

/** The footprint box the layout and checker use (PART_DIMS): centred on the
 *  origin in x and z, from the ground up, rounded up to the centimetre. */
export const deriveDims = (spec: PartSpec) => {
  const b = specBounds(spec);
  return {
    w: up(2 * Math.max(-b.min.x, b.max.x)),
    h: up(b.max.y),
    d: up(2 * Math.max(-b.min.z, b.max.z)),
  };
};

/** The catalog facts (PART_INFO): flags as given, smoke from the attach points. */
export const deriveInfo = (spec: PartSpec) => ({
  solid: spec.solid ?? true,
  walkable: !!spec.walkable,
  lightAtNight: !!spec.lightAtNight,
  smoke: !!spec.smoke?.length,
  blurb: spec.blurb,
});

// ------------------------------------------------------------ validation
// For parts an AGENT writes (WorldSpec.parts): the cheap deterministic half of
// the gate. Everything here is a fact about the spec, never taste; taste is the
// vision judge's job (gate/gateCli.ts). Kit parts are not validated: they were
// looked at in the gallery.

/** every kit material a spec may name. Checked against makePartMaterials() at
 *  compile time both ways (see the two assertions under it). */
export const KIT_MATS = [
  "crate", "lightWood", "midWood", "darkWood", "tieWood", "greyWood", "greyWoodV", "freshWood", "barrel", "barrelDS",
  "redPaint", "redPaintV", "creamPaint", "greenPaint", "bluePaint", "bark", "barkGrey", "rings", "ringsFresh",
  "iron", "steel", "tinSheet", "rust", "brass", "burlap", "canvas", "mailCanvas", "straw", "strawEnd", "twine", "rope",
  "leather", "leatherLight", "blanket", "flag", "flagCanton", "shirt", "denim", "stone", "stoneDark", "stoneRough",
  "rockMat", "hill", "gravel", "sandstone", "coal", "ore", "soil", "mud", "water", "waterTop", "river", "leaf", "leafDark",
  "leafDry", "reed", "cattail", "cactus", "cactusH", "lily", "birch", "clock", "arrow", "arrowDark", "dark", "darkHole",
  "personRef", "engineBlack", "engineRed", "coachPaint", "coachRoof",
] as const satisfies readonly KitMat[];
// a kit material missing from the list is a compile error here
const _everyKitMat: Exclude<KitMat, (typeof KIT_MATS)[number]> extends never ? true : never = true;
void _everyKitMat;

export const PRIM_KINDS = ["box", "cylinder", "rod", "sphere", "torus", "lathe", "shape", "plane", "card", "group"] as const;
export const CARD_DRAWS: readonly CardDraw[] = ["figure", "plate"];

/** what an agent-made part may be: a name the kit does not use, a sane number
 *  of primitives, nothing bigger than a house, nothing thinner than a nail,
 *  known materials, and nothing floating. */
export const PART_LIMITS = {
  name: /^[a-z][A-Za-z0-9]{1,31}$/,
  blurbChars: 200,
  leaves: 160,
  depth: 4,
  repeat: 48,
  /** metres */
  maxH: 14,
  maxWD: 18,
  minSize: 0.01,
  maxTris: 40000,
  /** two primitives closer than this touch */
  touch: 0.03,
} as const;

const finite = (...xs: unknown[]) => xs.every((x) => typeof x === "number" && Number.isFinite(x));
const v3 = (x: unknown): x is V3 => Array.isArray(x) && x.length === 3 && finite(...x);
const v2 = (x: unknown): x is [number, number] => Array.isArray(x) && x.length === 2 && finite(...x);
const pts = (x: unknown, min: number) => Array.isArray(x) && x.length >= min && x.every((p) => v2(p));

const tris = (p: Leaf): number => {
  switch (p.kind) {
    case "box": return 12;
    case "cylinder": return (p.seg ?? 10) * 4;
    case "rod": return (p.seg ?? 10) * 4;
    case "sphere": return (p.seg?.[0] ?? 12) * (p.seg?.[1] ?? 8) * 2;
    case "torus": return (p.seg?.[0] ?? 6) * (p.seg?.[1] ?? 24) * 2;
    case "lathe": return (p.points.length - 1) * (p.seg ?? 16) * 2;
    case "shape": return p.points.length * (p.depth ? 4 : 1);
    case "plane": case "card": return 2;
  }
};

const matOk = (m: MatRef | undefined, where: string, out: string[]) => {
  if (m === undefined) return;
  const one = (k: unknown) => (KIT_MATS as readonly string[]).includes(k as string);
  if (typeof m === "string") {
    if (!one(m)) out.push(`${where}: unknown material "${m}" (kit materials: ${KIT_MATS.join(", ")})`);
  } else if (Array.isArray(m)) {
    for (const k of m) if (!one(k)) out.push(`${where}: unknown material "${k}"`);
  } else if (typeof m === "object" && m && v3((m as { hsl?: unknown }).hsl)) {
    const [h, s, l] = (m as { hsl: V3 }).hsl;
    if (h < 0 || h > 360 || s < 0 || s > 1 || l < 0 || l > 1) out.push(`${where}: hsl must be [0-360, 0-1, 0-1]`);
    const g = (m as { glow?: { rgb?: unknown; peak?: unknown } }).glow;
    if (g && !(v3(g.rgb) && finite(g.peak))) out.push(`${where}: glow needs rgb [r,g,b] and a numeric peak`);
  } else out.push(`${where}: mat must be a kit material name, a list of them, or {hsl: [h,s,l]}`);
};

/** shape errors of one primitive (and, for a group, its items) */
const primErrors = (p: Prim, where: string, depth: number, out: string[]) => {
  const L = PART_LIMITS;
  if (!p || typeof p !== "object" || !(PRIM_KINDS as readonly string[]).includes((p as { kind?: string }).kind as string)) {
    out.push(`${where}: kind must be one of ${PRIM_KINDS.join(", ")}`);
    return;
  }
  if (p.at !== undefined && !v3(p.at)) out.push(`${where}: at must be [x,y,z]`);
  if (p.rot !== undefined && !v3(p.rot)) out.push(`${where}: rot must be [x,y,z] degrees`);
  if (p.repeat !== undefined) {
    if (!finite(p.repeat.n) || p.repeat.n < 1 || p.repeat.n > L.repeat) out.push(`${where}: repeat.n must be 1..${L.repeat}`);
    if (p.repeat.step !== undefined && !v3(p.repeat.step)) out.push(`${where}: repeat.step must be [x,y,z]`);
    if (p.repeat.turn !== undefined && !v3(p.repeat.turn)) out.push(`${where}: repeat.turn must be [x,y,z] degrees`);
  }
  matOk(p.mat, where, out);
  const size = (...xs: number[]) => {
    if (!finite(...xs)) out.push(`${where}: sizes must be numbers`);
    else if (Math.min(...xs) < L.minSize) out.push(`${where}: a size under ${L.minSize} m (hairline)`);
    else if (Math.max(...xs) > L.maxWD) out.push(`${where}: a size over ${L.maxWD} m`);
  };
  switch (p.kind) {
    case "box": if (v3(p.size)) size(...p.size); else out.push(`${where}: box needs size [w,h,d]`); break;
    case "cylinder": size(p.r, p.h); if (p.rTop !== undefined && (!finite(p.rTop) || p.rTop < 0)) out.push(`${where}: rTop must be >= 0`); break;
    case "rod": if (v3(p.from) && v3(p.to)) size(p.r, Math.hypot(p.to[0] - p.from[0], p.to[1] - p.from[1], p.to[2] - p.from[2])); else out.push(`${where}: rod needs from and to`); break;
    case "sphere": if (typeof p.r === "number") size(p.r); else if (v3(p.r)) size(...p.r); else out.push(`${where}: sphere r must be a number or [x,y,z]`); break;
    case "torus": size(p.r, p.tube); break;
    case "lathe": if (pts(p.points, 2)) size(Math.max(...p.points.map(([r]) => r)), Math.max(...p.points.map(([, y]) => y)) - Math.min(...p.points.map(([, y]) => y))); else out.push(`${where}: lathe needs >= 2 [radius, y] points`); break;
    case "shape": if (pts(p.points, 3)) size(...(p.depth !== undefined ? [p.depth] : [1])); else out.push(`${where}: shape needs >= 3 [x, y] points`); break;
    case "plane": if (v2(p.size)) size(...p.size); else out.push(`${where}: plane needs size [w,h]`); break;
    case "card":
      if (!CARD_DRAWS.includes(p.draw)) out.push(`${where}: card draw must be one of ${CARD_DRAWS.join(", ")}`);
      if (v2(p.size)) size(...p.size); else out.push(`${where}: card needs size [w,h]`);
      break;
    case "group":
      if (depth >= L.depth) out.push(`${where}: groups nest deeper than ${L.depth}`);
      else if (!Array.isArray(p.items) || !p.items.length) out.push(`${where}: group needs items`);
      else p.items.forEach((q, i) => primErrors(q, `${where}.items[${i}]`, depth + 1, out));
      break;
  }
};

/** Every reason a spec cannot be used, in plain words the author can act on.
 *  Empty means it may go to the visual gate. `reserved` is every name already
 *  taken (the kit's kinds and the promoted parts). */
export const validatePartSpec = (spec: unknown, reserved: readonly string[] = []): string[] => {
  const out: string[] = [];
  const L = PART_LIMITS;
  if (!spec || typeof spec !== "object") return ["part must be an object"];
  const s = spec as Partial<PartSpec>;
  if (typeof s.name !== "string" || !L.name.test(s.name)) out.push(`name must match ${L.name} (lowerCamelCase, 2-32 chars)`);
  else if (reserved.includes(s.name)) out.push(`name "${s.name}" is already a kit part: use it, or pick another name`);
  if (typeof s.blurb !== "string" || !s.blurb.trim()) out.push("blurb must say what the part is");
  else if (s.blurb.length > L.blurbChars) out.push(`blurb is over ${L.blurbChars} characters`);
  if (!Array.isArray(s.prims) || !s.prims.length) out.push("prims must be a non-empty list");
  else s.prims.forEach((p, i) => primErrors(p, `prims[${i}]`, 0, out));
  for (const k of ["solid", "walkable", "lightAtNight"] as const) {
    if (s[k] !== undefined && typeof s[k] !== "boolean") out.push(`${k} must be true or false`);
  }
  if (s.smoke !== undefined && !(Array.isArray(s.smoke) && s.smoke.every((x) => v3(x?.at) && ["chimney", "fire", "stack"].includes(x?.kind as string)))) {
    out.push("smoke must be a list of {at: [x,y,z], kind: chimney|fire|stack}");
  }
  if (s.lamp !== undefined && !(Array.isArray(s.lamp) && s.lamp.every((x) => v3(x?.at) && (x.colour === undefined || v3(x.colour))))) {
    out.push("lamp must be a list of {at: [x,y,z], colour?: [h,s,l]}");
  }
  if (out.length) return out;

  // geometry facts, now that the shape is sound
  const full = s as PartSpec;
  const leaves = walk(full.prims);
  if (leaves.length > L.leaves) out.push(`${leaves.length} primitives after repeats (limit ${L.leaves})`);
  const t = leaves.reduce((n, pl) => n + tris(pl.prim), 0);
  if (t > L.maxTris) out.push(`about ${t} triangles (limit ${L.maxTris})`);
  const dims = deriveDims(full);
  if (dims.h > L.maxH) out.push(`${dims.h} m tall (limit ${L.maxH})`);
  if (dims.w > L.maxWD || dims.d > L.maxWD) out.push(`${dims.w} x ${dims.d} m footprint (limit ${L.maxWD})`);
  const b = specBounds(full);
  if (b.min.y < -0.1) out.push(`reaches ${(-b.min.y).toFixed(2)} m below the ground`);

  // floating: every primitive must be connected, through touching primitives,
  // to one that stands on the ground
  const boxes = leaves.map((pl) => leafBounds(pl).expandByScalar(L.touch));
  const parent = boxes.map((_, i) => i);
  const find = (i: number): number => (parent[i] === i ? i : (parent[i] = find(parent[i])));
  for (let i = 0; i < boxes.length; i++) {
    for (let j = i + 1; j < boxes.length; j++) if (boxes[i].intersectsBox(boxes[j])) parent[find(i)] = find(j);
  }
  const grounded = new Set<number>();
  boxes.forEach((bx, i) => { if (bx.min.y <= L.touch) grounded.add(find(i)); });
  const floating = leaves.map((pl, i) => ({ pl, i })).filter(({ i }) => !grounded.has(find(i)));
  for (const { pl, i } of floating.slice(0, 6)) {
    const c = boxes[i].getCenter(new THREE.Vector3());
    out.push(`primitive ${i} (${pl.prim.kind} at ${c.x.toFixed(2)}, ${c.y.toFixed(2)}, ${c.z.toFixed(2)}) floats: it touches neither the ground nor anything that does`);
  }
  if (floating.length > 6) out.push(`...and ${floating.length - 6} more floating primitives`);
  return out;
};
