/**
 * Where everything sits on the board: region origins, the box each item's
 * content occupies inside its slot, the lines of text in it, and the path of
 * an arrow between two items. Pure functions of the data, computed once per
 * video.
 *
 * Keep in sync: mcp/whiteboard.py mirrors regionOrigin, placeItem, arrowEnds
 * and segmentHitsRect, because the validator refuses text that does not fit
 * and arrows that cross other items using these exact numbers.
 */
import { BOARD, LAYOUTS, LIMITS, SIZES, type PlacedItem, type Rect, type WBRegion, textWidth, wrapText } from "./contract";

export type Pt = [number, number];
export type TextLine = { text: string; x: number; y: number; size: number; width: number };
export type Placement = {
  /** The box the content occupies, in region coordinates. */
  bbox: Rect;
  lines: TextLine[];
  doodle?: { cx: number; cy: number; size: number };
};

/** Largest doodle edge, and the smallest a labelled doodle may shrink to. */
export const DOODLE_MAX = 420;
export const DOODLE_MIN = 120;
const DOODLE_LABEL_GAP = 28;

/** Top-left corner of region `i` on the board: two columns, snake order, so
 *  each move is one step right, left or down. */
export function regionOrigin(i: number): Pt {
  const row = Math.floor(i / 2);
  const col = row % 2 === 0 ? i % 2 : 1 - (i % 2);
  return [col * (BOARD.regionW + BOARD.gapX), row * (BOARD.regionH + BOARD.gapY)];
}

/** The centre of region `i`, where the camera rests on it. */
export function regionCenter(i: number): Pt {
  const [x, y] = regionOrigin(i);
  return [x + BOARD.regionW / 2, y + BOARD.regionH / 2];
}

const lh = (size: number) => size * SIZES.lineHeight;

function block(lines: string[], size: number, cx: number, top: number): TextLine[] {
  return lines.map((text, i) => {
    const width = textWidth(text, size);
    return { text, x: cx - width / 2, y: top + i * lh(size), size, width };
  });
}

function union(rects: Rect[]): Rect {
  const x0 = Math.min(...rects.map((r) => r[0]));
  const y0 = Math.min(...rects.map((r) => r[1]));
  const x1 = Math.max(...rects.map((r) => r[0] + r[2]));
  const y1 = Math.max(...rects.map((r) => r[1] + r[3]));
  return [x0, y0, x1 - x0, y1 - y0];
}

const lineRect = (l: TextLine): Rect => [l.x, l.y, l.width, lh(l.size)];

/** Lines a text item may use in a slot of height `h`. */
export function textLineCap(big: boolean, h: number): number {
  const size = big ? SIZES.big : SIZES.text;
  const fit = Math.floor((h - 2 * BOARD.pad) / lh(size));
  return Math.min(big ? 1 : LIMITS.textLines, fit);
}

/** Lay out one placed item in its slot. Content is centred in the slot. */
export function placeItem(it: PlacedItem, slot: Rect): Placement {
  const [sx, sy, sw, sh] = slot;
  const innerW = sw - 2 * BOARD.pad;
  const cx = sx + sw / 2;
  if (it.kind === "text" || it.kind === "formula") {
    const size = it.kind === "formula" ? SIZES.formula : it.big ? SIZES.big : SIZES.text;
    const raw = it.kind === "formula" ? [it.text.trim()] : wrapText(it.text, size, innerW);
    const top = sy + (sh - raw.length * lh(size)) / 2;
    const lines = block(raw, size, cx, top);
    return { bbox: union(lines.map(lineRect)), lines };
  }
  // A doodle, with an optional label.
  const inner = Math.min(innerW, sh - 2 * BOARD.pad);
  if (!it.label) {
    const size = Math.min(DOODLE_MAX, inner - 20);
    const cy = sy + sh / 2;
    return { bbox: [cx - size / 2, cy - size / 2, size, size], lines: [], doodle: { cx, cy, size } };
  }
  if (sw >= 1.8 * sh) {
    // Wide slot: doodle on the left, label beside it.
    const size = Math.min(DOODLE_MAX, sh - 2 * BOARD.pad - 20);
    const labelW = innerW - size - DOODLE_LABEL_GAP;
    const raw = wrapText(it.label, SIZES.label, labelW);
    const widest = Math.max(...raw.map((l) => textWidth(l, SIZES.label)));
    const groupW = size + DOODLE_LABEL_GAP + widest;
    const left = cx - groupW / 2;
    const cy = sy + sh / 2;
    const top = cy - (raw.length * lh(SIZES.label)) / 2;
    const lines = raw.map((text, i) => ({
      text,
      x: left + size + DOODLE_LABEL_GAP,
      y: top + i * lh(SIZES.label),
      size: SIZES.label,
      width: textWidth(text, SIZES.label),
    }));
    const doodle = { cx: left + size / 2, cy, size };
    return { bbox: union([[left, cy - size / 2, size, size], ...lines.map(lineRect)]), lines, doodle };
  }
  // Boxy slot: doodle on top, label below.
  const raw = wrapText(it.label, SIZES.label, innerW);
  const labelH = raw.length * lh(SIZES.label);
  const size = Math.min(DOODLE_MAX, innerW - 20, sh - 2 * BOARD.pad - labelH - 16);
  const groupH = size + 16 + labelH;
  const top = sy + (sh - groupH) / 2;
  const lines = block(raw, SIZES.label, cx, top + size + 16);
  const doodle = { cx, cy: top + size / 2, size };
  return { bbox: union([[cx - size / 2, top, size, size], ...lines.map(lineRect)]), lines, doodle };
}

/** Why an item does not fit its slot, or "" when it does. */
export function fitProblem(it: PlacedItem, slot: Rect): string {
  const [, , sw, sh] = slot;
  const innerW = sw - 2 * BOARD.pad;
  const p = placeItem(it, slot);
  const tooWide = p.lines.find((l) => l.width > innerW + 0.5);
  if (it.kind === "formula") {
    return tooWide ? "is too long for one line in this slot" : "";
  }
  if (it.kind === "text") {
    const cap = textLineCap(!!it.big, sh);
    if (tooWide) return `has a word too long for this slot ("${tooWide.text}")`;
    if (p.lines.length > cap) return `needs ${p.lines.length} lines; this slot holds ${cap}`;
    return "";
  }
  if (!it.label) return "";
  if (p.lines.length > LIMITS.labelLines) return `label needs ${p.lines.length} lines; at most ${LIMITS.labelLines}`;
  if (tooWide || p.lines.some((l) => l.x + l.width > slot[0] + sw - BOARD.pad + 0.5)) return "label is too long for this slot";
  if ((p.doodle?.size ?? 0) < DOODLE_MIN) return "label leaves the doodle too small; shorten it or use a bigger slot";
  return "";
}

const grow = (r: Rect, d: number): Rect => [r[0] - d, r[1] - d, r[2] + 2 * d, r[3] + 2 * d];
const center = (r: Rect): Pt => [r[0] + r[2] / 2, r[1] + r[3] / 2];

/** Liang-Barsky: the parameters [t0, t1] of segment p->q inside rect r, or null. */
function clipT(p: Pt, q: Pt, r: Rect): [number, number] | null {
  const dx = q[0] - p[0];
  const dy = q[1] - p[1];
  let t0 = 0;
  let t1 = 1;
  const edges: [number, number][] = [
    [-dx, p[0] - r[0]],
    [dx, r[0] + r[2] - p[0]],
    [-dy, p[1] - r[1]],
    [dy, r[1] + r[3] - p[1]],
  ];
  for (const [pp, qq] of edges) {
    if (pp === 0) {
      if (qq < 0) return null;
    } else {
      const t = qq / pp;
      if (pp < 0) t0 = Math.max(t0, t);
      else t1 = Math.min(t1, t);
    }
  }
  return t0 <= t1 ? [t0, t1] : null;
}

/** Whether segment p->q passes through rect r. */
export function segmentHitsRect(p: Pt, q: Pt, r: Rect): boolean {
  return clipT(p, q, r) !== null;
}

export const ARROW_CLEAR = 18;

/** Where an arrow from box a to box b starts and ends: on the line between
 *  their centres, just outside each box. */
export function arrowEnds(a: Rect, b: Rect): [Pt, Pt] {
  const ca = center(a);
  const cb = center(b);
  const ta = clipT(ca, cb, grow(a, ARROW_CLEAR));
  const tb = clipT(ca, cb, grow(b, ARROW_CLEAR));
  const s = ta ? ta[1] : 0;
  const e = tb ? tb[0] : 1;
  const at = (t: number): Pt => [ca[0] + (cb[0] - ca[0]) * t, ca[1] + (cb[1] - ca[1]) * t];
  return [at(s), at(e)];
}

/** The placement of every placed item of a region, by id, in region coordinates. */
export function placeRegion(region: WBRegion): Map<string, Placement> {
  const slots = LAYOUTS[region.layout];
  const out = new Map<string, Placement>();
  for (const it of region.items) {
    if ((it.kind === "text" || it.kind === "formula" || it.kind === "doodle") && slots[it.slot]) {
      out.set(it.id, placeItem(it, slots[it.slot]));
    }
  }
  return out;
}
