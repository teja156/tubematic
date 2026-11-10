/**
 * Doodles: drawings the marker can make, written as data.
 *
 * A doodle is a list of strokes in a 100 x 100 box, y pointing down, drawn in
 * the order listed, the way a person would draw it (outline first, then
 * details). A stroke is a list of segments joined into one continuous line,
 * and a segment is one primitive (line, poly, curve, arc, circle, ellipse,
 * rect, star, gear). The renderer scales a doodle to its slot and adds a seeded
 * hand wobble.
 *
 * The shipped library is doodles.json, hand-built once. A video may also
 * define its own doodles in the same format (`props.whiteboard.doodles`) for an
 * object the library lacks; the agent previews them with the preview_doodles
 * tool before it writes them, because no automatic check can tell whether a
 * drawing reads as what it is meant to be.
 *
 * Keep in sync: mcp/whiteboard.py's expand_doodle mirrors expandDoodle step for
 * step (the validator checks the expanded points against the box), and the
 * shared cases in mcp/tests/fixtures/whiteboard_contract.json pin the two. The
 * library's names are the pack's extra.doodles, and
 * agent_files/skills/tubematic-whiteboard/reference/doodles.json is a copy of
 * doodles.json that the agent reads; tests pin all three.
 */
import LIBRARY from "./doodles.json";

export type P = [number, number];
export type Segment =
  | { line: P[] }
  | { poly: P[] }
  | { curve: [P, P, P] }
  | { arc: number[] }
  | { circle: number[] }
  | { ellipse: number[] }
  | { rect: number[] }
  | { star: number[] }
  | { gear: number[] };
export type DoodleDef = Segment[][];

const rad = (d: number) => (d * Math.PI) / 180;

/** Ellipse arc, angles in degrees (0 = right, 90 = down). */
function arc(cx: number, cy: number, rx: number, ry: number, a0: number, a1: number): P[] {
  const n = Math.max(6, Math.ceil(Math.abs(a1 - a0) / 8));
  const out: P[] = [];
  for (let i = 0; i <= n; i++) {
    const a = rad(a0 + ((a1 - a0) * i) / n);
    out.push([cx + Math.cos(a) * rx, cy + Math.sin(a) * ry]);
  }
  return out;
}

/** A closed ellipse from angle `from`, rotated by `rot` degrees about its centre. */
function ellipse(cx: number, cy: number, rx: number, ry: number, rot = 0, from = -100): P[] {
  if (!rot) return arc(cx, cy, rx, ry, from, from + 365);
  const c = Math.cos(rad(rot));
  const s = Math.sin(rad(rot));
  return arc(0, 0, rx, ry, from, from + 365).map(([x, y]) => [cx + x * c - y * s, cy + x * s + y * c] as P);
}

/** A rectangle from its top-left corner, closing with a small overlap; rounded when r > 0. */
function rect(x: number, y: number, w: number, h: number, r = 0): P[] {
  if (!r) return [[x, y], [x + w, y], [x + w, y + h], [x, y + h], [x, y - 1]];
  return [
    ...arc(x + r, y + r, r, r, 180, 270),
    ...arc(x + w - r, y + r, r, r, 270, 360),
    ...arc(x + w - r, y + h - r, r, r, 0, 90),
    ...arc(x + r, y + h - r, r, r, 90, 180),
    [x, y + r * 0.5],
  ];
}

function curve(a: P, c: P, b: P, n = 12): P[] {
  const out: P[] = [];
  for (let i = 0; i <= n; i++) {
    const t = i / n;
    const u = 1 - t;
    out.push([u * u * a[0] + 2 * u * t * c[0] + t * t * b[0], u * u * a[1] + 2 * u * t * c[1] + t * t * b[1]]);
  }
  return out;
}

/** Points alternating between the outer and inner radius, starting at the top. */
function star(cx: number, cy: number, r0: number, r1: number, n: number): P[] {
  const out: P[] = [];
  for (let i = 0; i <= n * 2; i++) {
    const a = rad(-90 + (i * 180) / n);
    const r = i % 2 === 0 ? r1 : r0;
    out.push([cx + Math.cos(a) * r, cy + Math.sin(a) * r]);
  }
  return out;
}

function gear(cx: number, cy: number, r0: number, r1: number, n: number): P[] {
  const out: P[] = [];
  const step = 360 / n;
  for (let i = 0; i <= n; i++) {
    const a = -90 + i * step;
    for (const [da, r] of [[-step * 0.32, r0], [-step * 0.2, r1], [step * 0.2, r1], [step * 0.32, r0]] as [number, number][]) {
      out.push([cx + Math.cos(rad(a + da)) * r, cy + Math.sin(rad(a + da)) * r]);
    }
  }
  return out;
}

/** The points of one segment. Validated data only: mcp/whiteboard.py refuses
 *  an unknown primitive or a wrong number of values before anything renders. */
export function expandSegment(seg: Segment): P[] {
  if ("line" in seg) return seg.line.map(([x, y]) => [x, y] as P);
  if ("poly" in seg) return [...seg.poly.map(([x, y]) => [x, y] as P), [seg.poly[0][0], seg.poly[0][1]]];
  if ("curve" in seg) return curve(seg.curve[0], seg.curve[1], seg.curve[2]);
  if ("arc" in seg) {
    const [cx, cy, rx, ry, a0, a1] = seg.arc;
    return arc(cx, cy, rx, ry, a0, a1);
  }
  if ("circle" in seg) {
    const [cx, cy, r, from = -100] = seg.circle;
    return arc(cx, cy, r, r, from, from + 365);
  }
  if ("ellipse" in seg) {
    const [cx, cy, rx, ry, rot = 0, from = -100] = seg.ellipse;
    return ellipse(cx, cy, rx, ry, rot, from);
  }
  if ("rect" in seg) {
    const [x, y, w, h, r = 0] = seg.rect;
    return rect(x, y, w, h, r);
  }
  if ("star" in seg) {
    const [cx, cy, r0, r1, n] = seg.star;
    return star(cx, cy, r0, r1, n);
  }
  const [cx, cy, r0, r1, n] = seg.gear;
  return gear(cx, cy, r0, r1, n);
}

/** Every stroke of a doodle as one polyline. */
export function expandDoodle(def: DoodleDef): P[][] {
  return def.map((stroke) => stroke.flatMap(expandSegment));
}

export const LIBRARY_DEFS = LIBRARY as unknown as Record<string, DoodleDef>;
export const DOODLES: Record<string, P[][]> = Object.fromEntries(
  Object.entries(LIBRARY_DEFS).map(([name, def]) => [name, expandDoodle(def)]),
);
export const DOODLE_NAMES = Object.keys(DOODLES).sort();
