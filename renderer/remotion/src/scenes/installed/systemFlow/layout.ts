/*
 * Board layout: dagre places each board's nodes top to bottom, once per board,
 * in world units. Rows are fixed by computeRows (the rule the validator counts
 * with) through each edge's minlen: when every edge's minlen equals the row
 * difference that rule wants, every edge is tight at exactly those rows, which
 * is the least total edge length dagre's ranker looks for, so it lands on them.
 * That needs a connected board, which the validator requires.
 */
import dagre from "@dagrejs/dagre";
import { computeRows, edgeId, wrapLabel, type SFBoard } from "./contract";

// World geometry. A node "slot" is its box plus the label under it; dagre lays
// out slots, so a label always has its own space and edges leave below it.
// Sized so a full board (3 rows of 3) still shows labels at about 40 px on
// screen when the camera pulls back to it: a slot is as tall as its label needs.
export const BOX_W = 200;
export const BOX_H = 130;
export const LABEL_PX = 58;
export const LABEL_LINE = 1.12;
export const LABEL_GAP = 14;
export const SLOT_W = 400; // a 14-character Barlow label at 58 px is about 375
export const slotHeight = (lines: number) => BOX_H + LABEL_GAP + Math.max(1, lines) * LABEL_PX * LABEL_LINE;
const NODESEP = 40;
const RANKSEP = 140;
const EDGE_GAP = 14;
// Spacing of the dots that draw a connector.
export const DOT_STEP = 15;

export type Pt = { x: number; y: number };
export type LaidNode = { id: string; x: number; y: number; slotH: number; boxTop: number; boxBottom: number; lines: string[] };
export type LaidEdge = { id: string; from: string; to: string; points: Pt[]; length: number; dots: Pt[] };
export type Box = { x0: number; y0: number; x1: number; y1: number };
export type BoardLayout = { nodes: Record<string, LaidNode>; edges: Record<string, LaidEdge>; bounds: Box };

export function polylineLength(points: Pt[]): number {
  let len = 0;
  for (let i = 1; i < points.length; i++) len += Math.hypot(points[i].x - points[i - 1].x, points[i].y - points[i - 1].y);
  return len;
}

/** The point at `t` (0..1) of the way along a polyline, and the direction there. */
export function pointAlong(points: Pt[], t: number): { p: Pt; angle: number } {
  const total = polylineLength(points);
  let want = Math.max(0, Math.min(1, t)) * total;
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1];
    const b = points[i];
    const seg = Math.hypot(b.x - a.x, b.y - a.y);
    if (want <= seg || i === points.length - 1) {
      const k = seg === 0 ? 0 : Math.min(1, want / seg);
      return { p: { x: a.x + (b.x - a.x) * k, y: a.y + (b.y - a.y) * k }, angle: Math.atan2(b.y - a.y, b.x - a.x) };
    }
    want -= seg;
  }
  return { p: points[0], angle: Math.PI / 2 };
}

export function layoutBoard(board: SFBoard): BoardLayout {
  const rows = computeRows(board.nodes, board.edges);
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: "TB", nodesep: NODESEP, ranksep: RANKSEP, edgesep: 30 });
  g.setDefaultEdgeLabel(() => ({}));
  for (const n of board.nodes) g.setNode(n.id, { width: SLOT_W, height: slotHeight(wrapLabel(n.label).length) });
  for (const e of board.edges) {
    g.setEdge(e.from, e.to, { minlen: Math.max(1, (rows[e.to] ?? 1) - (rows[e.from] ?? 0)) });
  }
  // Within a row, nodes sit left to right in the order the board lists them,
  // so the author decides which side "the attacker" is on, not the heuristic.
  const constraints: { left: string; right: string }[] = [];
  const lastInRow: Record<number, string> = {};
  for (const n of board.nodes) {
    const r = rows[n.id] ?? 0;
    if (lastInRow[r] !== undefined) constraints.push({ left: lastInRow[r], right: n.id });
    lastInRow[r] = n.id;
  }
  dagre.layout(g, { constraints });

  const nodes: Record<string, LaidNode> = {};
  for (const n of board.nodes) {
    const d = g.node(n.id) as { x: number; y: number };
    const lines = wrapLabel(n.label);
    const slotH = slotHeight(lines.length);
    const top = d.y - slotH / 2;
    nodes[n.id] = { id: n.id, x: d.x, y: d.y, slotH, boxTop: top, boxBottom: top + BOX_H, lines };
  }
  const edges: Record<string, LaidEdge> = {};
  for (const e of board.edges) {
    const raw = ((g.edge(e.from, e.to) as { points?: Pt[] }).points ?? []).map((p) => ({ x: p.x, y: p.y }));
    const src = nodes[e.from];
    const dst = nodes[e.to];
    // dagre ends edges on the slot's outline, which is wider than the box; an
    // edge must leave below the source's label and arrive at the target's box.
    const start = { x: src.x, y: src.y + src.slotH / 2 + EDGE_GAP };
    const end = { x: dst.x, y: dst.boxTop - EDGE_GAP };
    const points = [start, ...raw.slice(1, -1), end];
    const length = polylineLength(points);
    const count = Math.max(2, Math.round(length / DOT_STEP));
    const dots = Array.from({ length: count + 1 }, (_, k) => pointAlong(points, k / count).p);
    edges[edgeId(e)] = { id: edgeId(e), from: e.from, to: e.to, points, length, dots };
  }
  const label = g.graph() as { width?: number; height?: number };
  return { nodes, edges, bounds: { x0: 0, y0: 0, x1: label.width ?? SLOT_W, y1: label.height ?? slotHeight(1) } };
}

/** A node's slot as a box in world units. */
export function slotBox(n: LaidNode): Box {
  return { x0: n.x - SLOT_W / 2, y0: n.y - n.slotH / 2, x1: n.x + SLOT_W / 2, y1: n.y + n.slotH / 2 };
}
