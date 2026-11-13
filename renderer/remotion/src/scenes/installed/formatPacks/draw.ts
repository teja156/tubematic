/*
 * Format Packs' looks and small drawing helpers: the two palettes, the easing
 * curves, and the hand-drawn ring and underline paths. A mark draws on by
 * growing a clip over its one short path (never a stroke dash array, which is
 * slow in software GL), and nothing here uses filters, blurs or shadows.
 */

export const PALETTES = {
  dark: {
    canvas: "#121417",
    title: "#F4F1E8",
    muted: "#8B9098",
    frame: "#2A2E35",
    screen: "#0B0C0E",
    header: "#15171B",
    hair: "#24272C",
    incoming: "#2A2D33",
    incomingText: "#ECEDEF",
    outgoing: "#0A84FF",
    outgoingText: "#FFFFFF",
    avatar: "#3A3E46",
    avatarInk: "#8B9098",
    input: "#16181C",
    accent: "#FF3B30",
    card: "#F4F1E8",
    cardInk: "#121417",
    cardLead: "#C8231B",
    lemon: "#F2CF1D",
    highlight: "#FFE14A",
    amber: "#F0A020",
    optionBg: "#1D2025",
    optionBorder: "#33373F",
    optionText: "#F4F1E8",
    board: "#1B1D21",
    boardInk: "#F4F1E8",
  },
  light: {
    canvas: "#F4F1E8",
    title: "#121417",
    muted: "#6B6F76",
    frame: "#26292E",
    screen: "#ECE9E0",
    header: "#F7F5EF",
    hair: "#D6D2C6",
    incoming: "#FFFFFF",
    incomingText: "#1D1F22",
    outgoing: "#0A6CDB",
    outgoingText: "#FFFFFF",
    avatar: "#D3CFC4",
    avatarInk: "#7A7E85",
    input: "#FFFFFF",
    accent: "#E0261B",
    card: "#FFFFFF",
    cardInk: "#121417",
    cardLead: "#C8231B",
    lemon: "#F2CF1D",
    highlight: "#FFE14A",
    amber: "#F0A020",
    optionBg: "#FFFFFF",
    optionBorder: "#D6D2C6",
    optionText: "#121417",
    board: "#1B1D21",
    boardInk: "#F4F1E8",
  },
} as const;
export type Palette = keyof typeof PALETTES;
export type Look = (typeof PALETTES)[Palette];

export const clamp01 = (v: number) => Math.max(0, Math.min(1, v));
export const easeOut = (t: number) => 1 - Math.pow(1 - clamp01(t), 3);
/** cubic-bezier(0.16, 1, 0.3, 1), the row entrance, by a few Newton steps. */
export function expoOut(t: number): number {
  const x = clamp01(t);
  const bez = (p1: number, p2: number, s: number) => 3 * p1 * s * (1 - s) ** 2 + 3 * p2 * s * s * (1 - s) + s ** 3;
  let s = x;
  for (let i = 0; i < 6; i++) {
    const fx = bez(0.16, 0.3, s) - x;
    const d = 3 * 0.16 * (1 - s) ** 2 + 6 * (0.3 - 0.16) * s * (1 - s) + 3 * (1 - 0.3) * s * s;
    if (Math.abs(d) < 1e-6) break;
    s = clamp01(s - fx / d);
  }
  return bez(1, 1, s);
}
/** A small overshoot for pops (about 6%). */
export const backOut = (t: number) => {
  const x = clamp01(t) - 1;
  return 1 + 2.2 * x * x * x + 1.2 * x * x;
};

/**
 * How far an arrival at `at` has come by `frame`, 0 to 1 over `dur` frames.
 * Anything that arrives at the insert's first frame is already there: the
 * insert slides in showing its picture.
 */
export function arrival(frame: number, at: number, dur: number, origin: number): number {
  if (at <= origin) return 1;
  return clamp01((frame - at) / dur);
}

/** A loose hand-drawn ellipse in a w x h box, starting top-left and running
 *  a little past where it began. */
export function ringPath(w: number, h: number): string {
  const cx = w / 2;
  const cy = h / 2;
  const rx = w / 2 - 4;
  const ry = h / 2 - 4;
  const pts: string[] = [];
  const turns = 1.08;
  for (let i = 0; i <= 48; i++) {
    const a = Math.PI * 1.15 + (i / 48) * Math.PI * 2 * turns;
    const wob = 1 + 0.035 * Math.sin(i * 0.9);
    pts.push(`${(cx + Math.cos(a) * rx * wob).toFixed(1)} ${(cy + Math.sin(a) * ry * wob).toFixed(1)}`);
  }
  return `M${pts.join(" L")}`;
}

/** A slightly wavy underline across a w-wide box. */
export function underlinePath(w: number): string {
  const n = Math.max(2, Math.round(w / 40));
  let d = "M2 6";
  for (let i = 1; i <= n; i++) {
    const x = (i / n) * (w - 4) + 2;
    d += ` Q${(x - w / (2 * n)).toFixed(1)} ${i % 2 ? 2 : 10} ${x.toFixed(1)} 6`;
  }
  return d;
}
