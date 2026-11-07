// PROBE 2 — terrain as data. PURE: no DOM, no three.js, no textures, so it can
// be unit-checked headless and called from layout code to seat props.
//
// The playable area is EXACTLY flat (y = 0, not "nearly"): every placement,
// walk and decal in the kit assumes it. Outside it the land rises over `edge`
// metres with a C1 ramp (zero slope where it meets the flat, so no crease for
// the ink pass to catch), into rolling hills whose height grows with distance,
// so the far land climbs toward the painted backdrop instead of meeting it at a
// ruler-straight line.

export interface TerrainSpec {
  seed: number;
  flat: { kind: "circle"; x: number; z: number; r: number } | { kind: "rect"; x0: number; x1: number; z0: number; z1: number };
  /** falloff width in metres: flat -> full hill height */
  edge: number;
  /** typical hill height, metres */
  amp: number;
  /** hill wavelength, metres */
  scale: number;
}

/** Integer hash -> [0, 1). Pure, stable across runs and tabs. */
const hash2 = (ix: number, iz: number, seed: number) => {
  let h = Math.imul(ix | 0, 0x27d4eb2d) ^ Math.imul(iz | 0, 0x165667b1) ^ Math.imul(seed | 0, 0x9e3779b1);
  h = Math.imul(h ^ (h >>> 15), 0x85ebca6b);
  h = Math.imul(h ^ (h >>> 13), 0xc2b2ae35);
  h ^= h >>> 16;
  return (h >>> 0) / 4294967296;
};

/** quintic fade: C2, so the hills have no slope seams at lattice lines */
const fade = (t: number) => t * t * t * (t * (t * 6 - 15) + 10);

/** 2D value noise in [0, 1] */
const vnoise = (x: number, z: number, seed: number) => {
  const ix = Math.floor(x);
  const iz = Math.floor(z);
  const fx = fade(x - ix);
  const fz = fade(z - iz);
  const a = hash2(ix, iz, seed);
  const b = hash2(ix + 1, iz, seed);
  const c = hash2(ix, iz + 1, seed);
  const d = hash2(ix + 1, iz + 1, seed);
  return a + (b - a) * fx + (c - a) * fz + (a - b - c + d) * fx * fz;
};

/** Distance outside the flat zone (0 inside). C1 everywhere outside. */
export const flatDistance = (t: TerrainSpec, x: number, z: number) => {
  const f = t.flat;
  if (f.kind === "circle") return Math.max(0, Math.hypot(x - f.x, z - f.z) - f.r);
  const dx = Math.max(f.x0 - x, 0, x - f.x1);
  const dz = Math.max(f.z0 - z, 0, z - f.z1);
  return Math.hypot(dx, dz);
};

const smooth01 = (s: number) => {
  const x = Math.min(1, Math.max(0, s));
  return x * x * (3 - 2 * x);
};

/** Distance over which the hills keep growing taller toward the horizon. */
const GROW_RANGE = 200;

/**
 * Ground height at (x, z). Deterministic in (spec, x, z). Exactly 0 inside the
 * flat zone; C1-smooth across its boundary (the ramp has zero slope at d = 0).
 */
export const terrainHeight = (t: TerrainSpec, x: number, z: number): number => {
  const d = flatDistance(t, x, z);
  if (d <= 0) return 0;
  const w = smooth01(d / Math.max(1e-6, t.edge));
  const s = Math.max(1e-6, t.scale);
  // two gentle octaves, no high-frequency bumps: rolling, never lumpy
  const n = 0.68 * vnoise(x / s, z / s, t.seed) + 0.32 * vnoise((x / s) * 2.13 + 17.3, (z / s) * 2.13 - 9.1, t.seed + 1);
  // hills grow toward the distance, so the far land climbs to the backdrop
  const grow = 1 + 1.6 * smooth01(d / GROW_RANGE);
  return w * t.amp * (0.3 + 1.4 * n) * grow;
};
