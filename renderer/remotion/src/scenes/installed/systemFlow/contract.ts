/*
 * The System Flow data contract: the shape of `props.systemFlow`, its limits,
 * and the two rules the MCP server must compute the same way before render
 * (label wrapping and row assignment).
 *
 * Keep in sync: mcp/system_flow.py holds the Python side of every constant and
 * rule here. mcp/tests/test_system_flow.py reads LIMITS and TIMING from this
 * file, and both sides run the shared cases in
 * mcp/tests/fixtures/system_flow_contract.json.
 */

export const LIMITS = {
  maxBoards: 12,
  maxNodesPerBoard: 9,
  maxPerRow: 3,
  // Three rows, not four: at the full-board pull-back a fourth row shrinks
  // the labels below 40 px on screen.
  maxRows: 3,
  labelLineChars: 14,
  labelLines: 2,
  chipChars: 24,
  headlineChars: 40,
  pillChars: 24,
  // The longest stretch, in seconds, with nothing new on screen.
  maxStillSeconds: 3.5,
} as const;

export const TIMING = {
  nodeIn: 16,
  edgeDraw: 15,
  packetTravel: 20,
  chipHold: 75,
  boardFade: 6,
  cameraMove: 30,
  // The camera starts moving this many frames before the event, so it has
  // made room by the time a new node lands (a later start let a node appear
  // outside the diagram band, over the captions).
  cameraLead: 26,
  // An edge may start drawing this many frames after its source enters.
  edgeAfterSource: 8,
  // The target must have entered by this many frames after its edge starts.
  targetWithin: 30,
  // A node's label types on this many frames after the node event, then one
  // character every labelTypeFrames frames (about 15 a second).
  labelTypeDelay: 6,
  labelTypeFrames: 2,
} as const;

export const TONES = ["structure", "relation", "ok", "fault"] as const;
export type Tone = (typeof TONES)[number];

export const EVENT_TYPES = ["node", "edge", "packet", "focus", "chip", "fault"] as const;

export type SFNode = { id: string; label: string; icon: string };
export type SFEdge = { from: string; to: string };
export type SFEvent =
  | { type: "node"; node: string; at: number }
  | { type: "edge"; edge: string; at: number }
  | { type: "packet"; edge: string; at: number; reverse?: boolean; tone?: Tone }
  | { type: "focus"; node: string; at: number }
  | { type: "chip"; edge: string; at: number; text: string; tone?: Tone }
  | { type: "fault"; node: string; at: number };

export type SFBoard = {
  startFrame: number;
  headline: string;
  pill?: string;
  nodes: SFNode[];
  edges: SFEdge[];
  events: SFEvent[];
};

export type SystemFlowData = { boards: SFBoard[] };

/** An edge's id in events: "from>to". */
export const edgeId = (e: SFEdge) => `${e.from}>${e.to}`;

/**
 * A node label in at most LIMITS.labelLines lines of LIMITS.labelLineChars:
 * greedy by words. A single word longer than a line stays whole on its own
 * line; the validator refuses it rather than this splitting it.
 */
export function wrapLabel(label: string): string[] {
  const words = label.trim().split(/\s+/).filter(Boolean);
  const lines: string[] = [];
  for (const w of words) {
    const last = lines[lines.length - 1];
    if (last !== undefined && last.length + 1 + w.length <= LIMITS.labelLineChars) {
      lines[lines.length - 1] = `${last} ${w}`;
    } else {
      lines.push(w);
    }
  }
  return lines;
}

/**
 * Each node's row: 0 for a node no edge points to, otherwise one below the
 * lowest row among the nodes that point to it (the longest path from a
 * source). The layout pins dagre to these rows through each edge's minlen, so
 * the validator's count of nodes per row is the count the frame shows.
 * Assumes an acyclic graph; the validator refuses a cycle first.
 */
export function computeRows(nodes: { id: string }[], edges: SFEdge[]): Record<string, number> {
  const rows: Record<string, number> = {};
  const preds: Record<string, string[]> = {};
  for (const n of nodes) preds[n.id] = [];
  for (const e of edges) preds[e.to]?.push(e.from);
  const visit = (id: string, depth: number): number => {
    if (rows[id] !== undefined) return rows[id];
    if (depth > nodes.length) return 0; // a cycle; never reached on validated data
    const ps = preds[id] ?? [];
    const r = ps.length === 0 ? 0 : Math.max(...ps.map((p) => visit(p, depth + 1))) + 1;
    rows[id] = r;
    return r;
  };
  for (const n of nodes) visit(n.id, 0);
  return rows;
}
