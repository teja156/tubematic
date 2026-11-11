/*
 * Constellation lettering: each character is a few polylines on a 4 x 6 grid
 * (x right, y down), angular like a star map. A star sits on every vertex and
 * gold strokes draw between them. contract.ts's GLYPHS lists what exists here.
 */
export type Glyph = [number, number][][];

const O: Glyph = [[[1, 0], [3, 0], [4, 1.5], [4, 4.5], [3, 6], [1, 6], [0, 4.5], [0, 1.5], [1, 0]]];
const P: Glyph = [[[0, 6], [0, 0], [3, 0], [4, 1], [4, 2.5], [3, 3.5], [0, 3.5]]];

export const GLYPH_SET: Record<string, Glyph> = {
  A: [[[0, 6], [2, 0], [4, 6]], [[1, 3.5], [3, 3.5]]],
  B: [[[0, 6], [0, 0], [3, 0], [4, 1], [3, 3], [0, 3]], [[3, 3], [4, 4.5], [3, 6], [0, 6]]],
  C: [[[4, 1], [3, 0], [1, 0], [0, 1.5], [0, 4.5], [1, 6], [3, 6], [4, 5]]],
  D: [[[0, 0], [0, 6], [2.5, 6], [4, 4.5], [4, 1.5], [2.5, 0], [0, 0]]],
  E: [[[4, 0], [0, 0], [0, 6], [4, 6]], [[0, 3], [3, 3]]],
  F: [[[4, 0], [0, 0], [0, 6]], [[0, 3], [3, 3]]],
  G: [[[4, 1], [3, 0], [1, 0], [0, 1.5], [0, 4.5], [1, 6], [3, 6], [4, 5], [4, 3.5], [2, 3.5]]],
  H: [[[0, 0], [0, 6]], [[4, 0], [4, 6]], [[0, 3], [4, 3]]],
  I: [[[1, 0], [3, 0]], [[2, 0], [2, 6]], [[1, 6], [3, 6]]],
  J: [[[1, 0], [4, 0], [4, 5], [3, 6], [1, 6], [0, 5]]],
  K: [[[0, 0], [0, 6]], [[4, 0], [0, 3.5]], [[1.2, 2.8], [4, 6]]],
  L: [[[0, 0], [0, 6], [4, 6]]],
  M: [[[0, 6], [0, 0], [2, 3], [4, 0], [4, 6]]],
  N: [[[0, 6], [0, 0], [4, 6], [4, 0]]],
  O,
  P,
  Q: [...O, [[2.6, 4.6], [4, 6]]],
  R: [...P, [[2, 3.5], [4, 6]]],
  S: [[[4, 1], [3, 0], [1, 0], [0, 1], [0, 2.2], [4, 3.8], [4, 5], [3, 6], [1, 6], [0, 5]]],
  T: [[[0, 0], [4, 0]], [[2, 0], [2, 6]]],
  U: [[[0, 0], [0, 4.8], [1, 6], [3, 6], [4, 4.8], [4, 0]]],
  V: [[[0, 0], [2, 6], [4, 0]]],
  W: [[[0, 0], [1, 6], [2, 2.5], [3, 6], [4, 0]]],
  X: [[[0, 0], [4, 6]], [[4, 0], [0, 6]]],
  Y: [[[0, 0], [2, 3]], [[4, 0], [2, 3], [2, 6]]],
  Z: [[[0, 0], [4, 0], [0, 6], [4, 6]]],
  "0": [...O, [[0.6, 5], [3.4, 1]]],
  "1": [[[1, 1], [2, 0], [2, 6]], [[1, 6], [3, 6]]],
  "2": [[[0, 1], [1, 0], [3, 0], [4, 1], [4, 2.5], [0, 6], [4, 6]]],
  "3": [[[0, 0.8], [1, 0], [3, 0], [4, 1], [4, 2], [3, 3], [1.5, 3]], [[3, 3], [4, 4], [4, 5], [3, 6], [1, 6], [0, 5.2]]],
  "4": [[[3, 6], [3, 0], [0, 4], [4, 4]]],
  "5": [[[4, 0], [0.5, 0], [0, 3], [3, 2.8], [4, 4], [4, 5], [3, 6], [1, 6], [0, 5.2]]],
  "6": [[[3.5, 0], [1, 1], [0, 3.5], [0, 5], [1, 6], [3, 6], [4, 5], [4, 4], [3, 3], [1, 3], [0, 3.8]]],
  "7": [[[0, 0], [4, 0], [1.5, 6]]],
  "8": [[[1, 3], [0, 2], [0, 1], [1, 0], [3, 0], [4, 1], [4, 2], [3, 3], [1, 3], [0, 4], [0, 5], [1, 6], [3, 6], [4, 5], [4, 4], [3, 3]]],
  "9": [[[0.5, 6], [3, 5], [4, 2.5], [4, 1], [3, 0], [1, 0], [0, 1], [0, 2], [1, 3], [3, 3], [4, 2.2]]],
};

/** Grid units a glyph takes, and the gap after it. */
export const GLYPH_W = 4;
export const GLYPH_GAP = 1.6;

export type Segment = [[number, number], [number, number]];
export type Lettering = { stars: [number, number][]; segments: Segment[][] /* per word */ };

/**
 * Lays out up to two words, one per line, centred on (cx, cy), fitted into
 * `width` px: every vertex becomes a star (shared vertices once) and every
 * polyline a run of segments, grouped per word in drawing order.
 */
export function letter(words: string[], cx: number, cy: number, width: number): Lettering {
  const longest = Math.max(...words.map((w) => w.length), 1);
  const unit = Math.min(22, width / (longest * (GLYPH_W + GLYPH_GAP) - GLYPH_GAP));
  const lineH = 6 * unit;
  const gapH = 2.6 * unit;
  const totalH = words.length * lineH + (words.length - 1) * gapH;
  const stars: [number, number][] = [];
  const seen = new Set<string>();
  const segments: Segment[][] = [];
  words.forEach((word, li) => {
    const chars = [...word.toUpperCase()];
    const ww = (chars.length * (GLYPH_W + GLYPH_GAP) - GLYPH_GAP) * unit;
    const x0 = cx - ww / 2;
    const y0 = cy - totalH / 2 + li * (lineH + gapH);
    const segs: Segment[] = [];
    chars.forEach((ch, ci) => {
      for (const line of GLYPH_SET[ch] ?? []) {
        const pts = line.map(([gx, gy]) => [x0 + (ci * (GLYPH_W + GLYPH_GAP) + gx) * unit, y0 + gy * unit] as [number, number]);
        for (const p of pts) {
          const k = `${Math.round(p[0])},${Math.round(p[1])}`;
          if (!seen.has(k)) {
            seen.add(k);
            stars.push(p);
          }
        }
        for (let i = 1; i < pts.length; i++) segs.push([pts[i - 1], pts[i]]);
      }
    });
    segments.push(segs);
  });
  return { stars, segments };
}
