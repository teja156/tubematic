/*
 * The token morph: from one version of the code to the next, pieces present in
 * both keep their identity and glide from their old grid place to their new
 * one, removed pieces fade where they were, and new pieces fade in where they
 * land. Unchanged code that does not move holds perfectly still.
 *
 * Pieces are matched by a longest common subsequence over their text, in
 * reading order. Pure and frame-derived: the same frame always draws the same
 * picture.
 */
import type { Piece } from "./tokens";

export type Pair = { from: Piece | null; to: Piece | null };

/** Pairs every piece of `a` and `b`: matched pieces share a pair, a removed
 *  piece has no `to`, an added piece has no `from`. In reading order of `b`
 *  with removed pieces next to where they stood. */
export function matchPieces(a: Piece[], b: Piece[]): Pair[] {
  const n = a.length;
  const m = b.length;
  // dp[i][j]: the longest common run of a[i..] and b[j..].
  const dp: Uint16Array[] = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] = a[i].text === b[j].text ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const pairs: Pair[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (a[i].text === b[j].text && dp[i][j] === dp[i + 1][j + 1] + 1) {
      pairs.push({ from: a[i++], to: b[j++] });
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      pairs.push({ from: a[i++], to: null });
    } else {
      pairs.push({ from: null, to: b[j++] });
    }
  }
  while (i < n) pairs.push({ from: a[i++], to: null });
  while (j < m) pairs.push({ from: null, to: b[j++] });
  return pairs;
}

export type Drawn = { key: string; text: string; color: string; row: number; col: number; opacity: number };

const easeInOutCubic = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
const clamp01 = (v: number) => Math.max(0, Math.min(1, v));

/** The pieces to draw `t` of the way (0 to 1) through a morph. Rows and
 *  columns are fractional while a piece travels. */
export function morphAt(pairs: Pair[], t: number): Drawn[] {
  const k = easeInOutCubic(clamp01(t));
  return pairs.map((p, idx) => {
    if (p.from && p.to) {
      return {
        key: `m${idx}`,
        text: p.to.text,
        color: k < 0.5 ? p.from.color : p.to.color,
        row: p.from.row + (p.to.row - p.from.row) * k,
        col: p.from.col + (p.to.col - p.from.col) * k,
        opacity: 1,
      };
    }
    if (p.from) {
      return { key: `r${idx}`, text: p.from.text, color: p.from.color, row: p.from.row, col: p.from.col,
        opacity: 1 - clamp01(k / 0.6) };
    }
    const to = p.to!;
    return { key: `a${idx}`, text: to.text, color: to.color, row: to.row, col: to.col,
      opacity: clamp01((k - 0.4) / 0.6) };
  });
}

/** The pieces of one version, at rest. */
export function still(pieces: Piece[]): Drawn[] {
  return pieces.map((p, idx) => ({ key: `s${idx}`, ...p, opacity: 1 }));
}
