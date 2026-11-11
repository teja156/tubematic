/*
 * The Case File Story data contract: the shape of `props.caseFile`, its limits
 * and timings, and the geometry the MCP server checks before render.
 *
 * Keep in sync: mcp/case_file_story.py holds the Python side of every constant
 * here, and tubematic_core/style_packs/case_file_story.json lists the accents,
 * beat kinds, meter kinds and icons for the agent.
 * mcp/tests/test_case_file_story.py reads this file and fails when the three
 * disagree, and both sides run the shared cases in
 * mcp/tests/fixtures/case_file_story_contract.json.
 *
 * The frame has fixed zones, so nothing the agent places can land on another
 * zone: the meter row near the top (HUD), the picture or the card under it,
 * the captions at 72% (the shared Subtitles component), and the choice
 * buttons in the bottom fifth. A card's panel stops above the captions, which
 * then sit on the dark band under it.
 */

export const W = 1080;
export const H = 1920;

export const ACCENTS = { pink: "#E8327A", amber: "#F2A33A", teal: "#2FB5A6", red: "#E5484D" } as const;
export const ACCENT_NAMES = ["pink", "amber", "teal", "red"] as const;
export const BEAT_TYPES = ["shot", "count", "bars", "term", "choice"] as const;
export const METER_KINDS = ["money", "count", "percent"] as const;
export const ICONS = ["bill", "coin", "envelope", "person", "box", "card", "phone", "document", "key", "goldbar"] as const;

export type Accent = (typeof ACCENT_NAMES)[number];
export type MeterKind = (typeof METER_KINDS)[number];
export type Icon = (typeof ICONS)[number];

export const LIMITS = {
  // Generated stills per video, the lead sheet aside: each one is a paid image call.
  maxImages: 16,
  minMeters: 2,
  maxMeters: 3,
  maxBeats: 48,
  meterLabelChars: 12,
  // The largest number a meter or a card shows; drawn as "$999.9M", it still fits a meter cell.
  maxValue: 999999999,
  titleChars: 26,
  unitChars: 26,
  resultChars: 14,
  minBars: 2,
  maxBars: 6,
  barLabelChars: 6,
  thresholdLabelChars: 24,
  payoffChars: 30,
  termChars: 26,
  definitionChars: 110,
  stampChars: 16,
  citationChars: 34,
  optionChars: 10,
  minShotSeconds: 1,
  // The longest stretch, in seconds, with nothing new apart from the slow
  // push. The AI review is told the same number.
  maxStillSeconds: 4,
} as const;

export const TIMING = {
  // A beat start or a punch lands within this many frames of a word's start.
  snap: 2,
  // A card cross-fades in over this many frames; shots cut.
  cardFade: 4,
  // A meter's new value cross-dissolves over this many frames after the cut.
  hudDissolve: 2,
  // A punch this close to its shot's start or end reads as a glitch.
  punchMargin: 12,
  // Text needs this long on screen before its beat ends to be read.
  readFrames: 20,
  // Count card: the grid and the counter start, run and the result lands after.
  countStart: 10,
  countFrames: 36,
  resultDelay: 12,
  // Bars card: bars closer together than this blur into one; the payoff line follows the last.
  barStep: 8,
  payoffDelay: 11,
  // Term card: definition, then the stamp slams in, then the citation.
  definitionDelay: 20,
  stampDelay: 25,
  stampIn: 4,
  citationDelay: 10,
  // Choice: the first button, then the second.
  optionFirst: 8,
  optionStep: 20,
  // The large meter panel counts to its new value over this many frames.
  panelCount: 12,
} as const;

export const CAMERA = {
  // The slow push: scale gained per second, linear.
  push: 0.025,
  // A punch-in multiplies the scale by this, on one frame.
  punch: 1.5,
  // Where a shot is centred when it names no focus.
  focusU: 0.5,
  focusV: 0.45,
} as const;

export const GEOMETRY = {
  safeLeft: 60,
  safeRight: 1020,
  hudTop: 232,
  hudHeight: 106,
  hudGap: 11,
  hudRadius: 15,
  // A card's panel ends here; the band under it holds the captions.
  cardBottom: 1240,
  // The bars chart area inside a card.
  chartLeft: 130,
  chartRight: 950,
  chartTop: 520,
  chartBottom: 1010,
  barGap: 26,
  // The count grid.
  gridCols: 8,
  gridRows: 5,
  gridLeft: 150,
  gridTop: 470,
  gridCell: 98,
  // The widest a term may be drawn, and the size it starts from.
  termWidth: 920,
  termSize: 112,
  // The width a one-line card text may take, and the advance of one character
  // in ems that a fit assumes: capitals of the bundled sans average 0.7.
  lineWidth: 960,
  capCharWidth: 0.75,
  // The choice buttons.
  optionTop: 1500,
  optionHeight: 150,
  optionGap: 30,
} as const;

export interface Meter {
  id: string;
  label: string;
  kind: MeterKind;
  /** The value shown from the first frame. A whole number, 0 or more. */
  value: number;
}

export interface Shot {
  type: "shot";
  start: number;
  image: string;
  /** Where the push-in is centred, [u, v] in the still (0..1 from its top left). */
  focus?: [number, number];
  /** A hard cut to a tighter crop of the same still, on a word. */
  punch?: { frame: number; at: [number, number] };
  /** Meter values that change on this cut, by meter id. */
  set?: Record<string, number>;
  /** false hides the meter row for this shot (a close-up). */
  hud?: boolean;
  /** A meter id: its large panel is shown over this shot, counting to the value `set` gives it. */
  panel?: string;
}

export interface CountCard {
  type: "count";
  start: number;
  title: string;
  /** The conversion that makes the number physical ("1 bill is 1 gram"). */
  unit?: string;
  icon: Icon;
  /** What the counter climbs to. */
  to: number;
  kind: MeterKind;
  /** What it comes to ("100 kg"). */
  result: string;
  /** The frame the result lands on; absent, TIMING.resultDelay after the count ends. */
  resultFrame?: number;
}

export interface BarsCard {
  type: "bars";
  start: number;
  title: string;
  kind: MeterKind;
  threshold: { value: number; label: string };
  /** Each bar appears whole on its frame, a word of the narration. */
  bars: { label: string; value: number; frame: number }[];
  payoff: string;
  /** The frame the payoff line appears on; absent, TIMING.payoffDelay after the last bar. */
  payoffFrame?: number;
}

export interface TermCard {
  type: "term";
  start: number;
  term: string;
  definition: string;
  stamp: string;
  citation?: string;
  /** The frame the definition appears on; absent, TIMING.definitionDelay after the card starts. */
  definitionFrame?: number;
  /** The frame the stamp lands on; absent, TIMING.stampDelay after the definition. */
  stampFrame?: number;
}

export interface Choice {
  type: "choice";
  start: number;
  image: string;
  focus?: [number, number];
  /** The two options, in the order they are spoken. The second is the accent button. */
  options: [string, string];
  /** The frame each button appears on; absent, TIMING.optionFirst after the start and TIMING.optionStep apart. */
  optionFrames?: [number, number];
}

export type Beat = Shot | CountCard | BarsCard | TermCard | Choice;

export interface CaseFileData {
  accent: Accent;
  hud: Meter[];
  beats: Beat[];
}

// ── numbers ─────────────────────────────────────────────────────────────────
function grouped(n: number): string {
  const s = String(Math.floor(n));
  let out = "";
  for (let i = 0; i < s.length; i++) {
    if (i > 0 && (s.length - i) % 3 === 0) out += ",";
    out += s[i];
  }
  return out;
}

/**
 * A meter or card number as it is drawn. Whole-number arithmetic only, so the
 * Python copy cannot round differently: a million or more is shown in
 * millions with one decimal, cut (never rounded up).
 */
export function formatValue(kind: MeterKind, value: number): string {
  const v = Math.max(0, Math.floor(value));
  if (kind === "percent") return `${v}%`;
  let text: string;
  if (v >= 1000000) {
    const tenths = Math.floor(v / 100000);
    const whole = Math.floor(tenths / 10);
    const frac = tenths % 10;
    text = frac === 0 ? `${whole}M` : `${whole}.${frac}M`;
  } else {
    text = grouped(v);
  }
  return kind === "money" ? `$${text}` : text;
}

// ── the meter row ───────────────────────────────────────────────────────────
/** The [left, width] of each of `n` equal meter cells across the safe width. */
export function hudCells(n: number): [number, number][] {
  const G = GEOMETRY;
  const width = (G.safeRight - G.safeLeft - G.hudGap * (n - 1)) / n;
  return Array.from({ length: n }, (_, i) => [G.safeLeft + i * (width + G.hudGap), width]);
}

// ── the camera on a still ───────────────────────────────────────────────────
/**
 * The scale of a shot `t` frames after it starts: the slow push, times the
 * punch once its frame has passed (`punchAfter` is frames from the shot's
 * start to the punch, or null).
 */
export function shotScale(t: number, fps: number, punchAfter: number | null): number {
  const push = 1 + (CAMERA.push * Math.max(0, t)) / fps;
  return punchAfter !== null && t >= punchAfter ? push * CAMERA.punch : push;
}

/**
 * The part of the frame-sized still that is on screen at `scale` about
 * [u, v]: [x, y, width, height] in frame pixels, kept inside the still so no
 * edge ever shows. The still is drawn to cover the frame, so u and v are
 * fractions of the frame here.
 */
export function shotView(scale: number, u: number, v: number): [number, number, number, number] {
  const s = Math.max(1, scale);
  const vw = W / s, vh = H / s;
  const x = Math.min(W - vw, Math.max(0, u * W - vw / 2));
  const y = Math.min(H - vh, Math.max(0, v * H - vh / 2));
  return [x, y, vw, vh];
}

// ── cards ───────────────────────────────────────────────────────────────────
/** The font size, at most `size`, at which one line of `text` fits `width` pixels. */
export function fitFontSize(text: string, size: number, width: number): number {
  const n = Math.max(1, text.length);
  return Math.min(size, Math.floor(width / (n * GEOMETRY.capCharWidth)));
}

/** The font size a term is drawn at so it fits the card's width. */
export function termFontSize(term: string): number {
  return fitFontSize(term, GEOMETRY.termSize, GEOMETRY.termWidth);
}

/**
 * The bars of a bars card as [x, y, width, height] in frame pixels, with the
 * y of the threshold line last. The scale tops out 15% above the larger of
 * the threshold and the tallest bar.
 */
export function barLayout(values: number[], threshold: number): { bars: [number, number, number, number][]; lineY: number } {
  const G = GEOMETRY;
  const top = Math.max(threshold, ...values, 1) * 1.15;
  const span = G.chartBottom - G.chartTop;
  const n = values.length;
  const width = (G.chartRight - G.chartLeft - G.barGap * (n - 1)) / n;
  const bars = values.map((v, i): [number, number, number, number] => {
    const h = (Math.max(0, v) / top) * span;
    return [G.chartLeft + i * (width + G.barGap), G.chartBottom - h, width, h];
  });
  return { bars, lineY: G.chartBottom - (threshold / top) * span };
}

/**
 * The frames at which a beat's parts appear, in order, starting with the beat
 * itself. A shot: its cut and its punch. A count card: its start, the end of
 * the climb, the result. A bars card: its start, each bar, the payoff line.
 * A term card: its start, the definition, the stamp, the citation. The
 * choice: its start and each button. Parts the agent did not time fall on
 * the TIMING defaults.
 */
export function partFrames(beat: Beat): number[] {
  const T = TIMING;
  switch (beat.type) {
    case "shot":
      return beat.punch ? [beat.start, beat.punch.frame] : [beat.start];
    case "count": {
      const counted = beat.start + T.countStart + T.countFrames;
      return [beat.start, counted, beat.resultFrame ?? counted + T.resultDelay];
    }
    case "bars": {
      const bars = beat.bars.map((b) => b.frame);
      return [beat.start, ...bars, beat.payoffFrame ?? bars[bars.length - 1] + T.payoffDelay];
    }
    case "term": {
      const definition = beat.definitionFrame ?? beat.start + T.definitionDelay;
      const stamp = beat.stampFrame ?? definition + T.stampDelay;
      return beat.citation ? [beat.start, definition, stamp, stamp + T.stampIn + T.citationDelay] : [beat.start, definition, stamp];
    }
    case "choice": {
      const [a, b] = beat.optionFrames ?? [beat.start + T.optionFirst, beat.start + T.optionFirst + T.optionStep];
      return [beat.start, a, b];
    }
  }
}
