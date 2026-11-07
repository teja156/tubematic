// Seeded PRNG (mulberry32). Every random choice in the kit goes through this so a
// frame renders identically in any tab, in any order.
export type Rng = () => number;

export const makeRng = (seed: number): Rng => {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
};

export const range = (rng: Rng, lo: number, hi: number) => lo + (hi - lo) * rng();

// Stateless hash in [0,1) for per-frame jitter (spark i at frame f, etc.).
export const hash = (...n: number[]) => {
  let h = 2166136261;
  for (const v of n) {
    h ^= Math.floor(v * 1000) | 0;
    h = Math.imul(h, 16777619);
  }
  return makeRng(h)();
};

export const clamp01 = (x: number) => Math.min(1, Math.max(0, x));
export const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
export const smooth = (t: number) => {
  const x = clamp01(t);
  return x * x * (3 - 2 * x);
};
// Map frame f from [a,b] to 0..1, smoothstepped.
export const ramp = (f: number, a: number, b: number) => smooth((f - a) / (b - a));
