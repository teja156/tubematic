/*
 * The Under the Hood data contract: the shape of `props.underTheHood`, its
 * limits and timings, and the geometry the MCP server checks before render.
 *
 * Keep in sync: mcp/under_the_hood.py holds the Python side of every constant
 * here, and tubematic_core/style_packs/under_the_hood.json lists the poses,
 * event kinds and tones for the agent. mcp/tests/test_under_the_hood.py reads
 * this file and fails when the three disagree, and both sides run the shared
 * cases in mcp/tests/fixtures/under_the_hood_contract.json.
 *
 * The frame has fixed zones, so nothing the agent places can land on another
 * zone: captions near the top (the shared Subtitles component, at 19%), the
 * plate band in the middle (the photograph and everything pinned to it), and
 * the bottom third (the counter row and the footnote on the left, the
 * presenter on the right).
 */

export const W = 1080;
export const H = 1920;

export const LIMITS = {
  // Generated photographs per video: each one is a paid image call.
  maxImages: 12,
  maxPlates: 30,
  maxEventsPerPlate: 16,
  // Callouts, outlines, arc fans, a stat and a chart on one plate at once.
  maxElementsPerPlate: 6,
  calloutChars: 18,
  statLabelChars: 22,
  chipChars: 10,
  affixChars: 3,
  chartLabelChars: 24,
  footnoteChars: 32,
  maxCounters: 4,
  maxCounterValue: 99999,
  // Stats and charts show numbers up to this size; larger needs other units.
  maxAbsValue: 9999999,
  minChartPoints: 2,
  maxChartPoints: 24,
  minArcs: 3,
  maxArcs: 9,
  minPlateSeconds: 1.5,
  // The longest stretch, in seconds, with nothing new apart from the slow
  // push. The look lives on constant small changes; the AI review is told the
  // same number.
  maxStillSeconds: 3,
} as const;

export const TIMING = {
  // A plate that cuts in cross-fades over this many frames.
  fade: 3,
  // A zoom-through: the outgoing plate rushes 1x to 4x into a point over the
  // last `zoomOut` frames, and the new plate settles from 1.25x over `zoomIn`.
  zoomOut: 6,
  zoomIn: 8,
  // A plate start or a pose lands within this many frames of a word's start.
  snap: 2,
  // Two pose swaps closer than this read as a twitch.
  minPoseGap: 8,
  // An event this close to its plate's end is cut before it is seen.
  endMargin: 6,
  // Text needs this long on screen before its plate ends to be read.
  readFrames: 20,
  // A chip pops in over chipIn frames, its leader draws over leaderIn.
  chipIn: 4,
  leaderIn: 7,
  // Outlines and brackets draw on over this many frames.
  drawOn: 8,
  // Arcs bend toward their target over arcBend frames; sparks fly for sparkFrames, then stop.
  arcBend: 20,
  sparkFrames: 45,
  // Counters change value every tickStep frames and settle after tickFrames.
  tickStep: 4,
  tickFrames: 16,
  // A stat counts up over statCount frames.
  statCount: 24,
  // A chart draws for its `duration`, between these bounds.
  chartMin: 30,
  chartMax: 150,
} as const;

// Where things go, in frame pixels.
export const GEOMETRY = {
  // The plate band: the photograph is drawn in it and everything pinned to
  // the photograph must stay in it.
  plateTop: 460,
  plateBottom: 1350,
  plateCx: 540,
  plateCy: 905,
  // The photograph's width at zoom 1; its height follows its aspect.
  plateWidth: 1080,
  // The band's top and bottom edges fade into the canvas over this many pixels.
  fadePx: 90,
  safeLeft: 60,
  safeRight: 1020,
  // A callout chip: capital letters on a dark rounded box.
  chipFontPx: 36,
  chipCharPx: 27,
  chipPadPx: 22,
  chipHeight: 60,
  // A leader shorter than this reads as a chip sitting on its point.
  minLeaderPx: 40,
  // The stat block, right-aligned; its top is one of two slots.
  statRight: 1010,
  statUpperTop: 500,
  statLowerTop: 1050,
  // Sizes measured from the bundled fonts: a numeral is up to 106 px a
  // character (125 for %), a capital in the label about 26 on average.
  statHeight: 300,
  statFontPx: 170,
  statCharPx: 110,
  statLabelCharPx: 28,
  // The chart's box on a plate with no photograph.
  chartLeft: 90,
  chartRight: 990,
  chartTop: 700,
  chartBottom: 1250,
  // The value above the chart is drawn at 150 px, where a digit is up to 93 px wide.
  chartCharPx: 96,
  // The counter row and the footnote, bottom left.
  counterLeft: 70,
  counterTop: 1400,
  counterWidth: 520,
  // JetBrains Mono at 64 px is 38.4 px a digit; each column keeps a little room.
  counterCharPx: 39,
  counterPadPx: 8,
  footnoteTop: 1560,
  // The presenter, bottom right, cut off by the frame's bottom edge.
  presenterLeft: 610,
  presenterTop: 1380,
  presenterWidth: 440,
  presenterHeight: 620,
  // A point pinned to the photograph must sit this far inside the band.
  // Half the band's faded edge: a point nearer the band's top or bottom sits in the dark.
  anchorMargin: 45,
  // A pinned point within this much of a chip or the stat is hidden by it.
  pointClearPx: 10,
  overlapTolerance: 4,
} as const;

// The camera's slow push and its zoom limits.
export const CAMERA = { push: 0.01, minZoom: 1, maxZoom: 3, through: 4, enterFrom: 1.25 } as const;

export const EVENT_TYPES = ["callout", "outline", "arcs", "counters", "stat", "chart", "footnote", "pose"] as const;
export const POSES = ["idle", "point", "present", "think", "surprise", "hands_on_head", "thumbs", "shrug", "explain"] as const;
export const TONES = ["white", "blue", "gold"] as const;
export const SHAPES = ["box", "bracket"] as const;
export const ENTRANCES = ["cut", "zoom"] as const;
export const STAT_SLOTS = ["upper", "lower"] as const;

export type UV = [number, number];
export type Pose = (typeof POSES)[number];
export type Tone = (typeof TONES)[number];

export interface UTHEventBase { frame: number }
export interface UTHCallout extends UTHEventBase { type: "callout"; text: string; at: UV; chip: UV; tone?: Tone }
export interface UTHOutline extends UTHEventBase { type: "outline"; region: [number, number, number, number]; tone?: Tone; shape?: (typeof SHAPES)[number] }
export interface UTHArcs extends UTHEventBase { type: "arcs"; from: UV; to: UV; count?: number }
export interface UTHCounters extends UTHEventBase { type: "counters"; values: { from: number; to: number }[] }
export interface UTHStat extends UTHEventBase {
  type: "stat"; value: number; from?: number; decimals?: number; prefix?: string; suffix?: string;
  label: string; chip?: string; place?: (typeof STAT_SLOTS)[number];
}
export interface UTHChart extends UTHEventBase {
  type: "chart"; points: number[]; label: string; duration?: number; decimals?: number;
  prefix?: string; suffix?: string; chip?: string;
}
export interface UTHFootnote extends UTHEventBase { type: "footnote"; text: string }
export interface UTHPose extends UTHEventBase { type: "pose"; pose: Pose }
export type UTHEvent = UTHCallout | UTHOutline | UTHArcs | UTHCounters | UTHStat | UTHChart | UTHFootnote | UTHPose;

export interface UTHPlate {
  start: number;
  /** The public_path generate_image returned; absent for a plain dark panel (a chart). */
  image?: string;
  /** Height over width of the photograph; write_scene_config fills it in from the file. */
  aspect?: number;
  /** The point of the photograph at the band's centre, [u, v] from 0 to 1. */
  focus?: UV;
  zoom?: number;
  enter?: (typeof ENTRANCES)[number];
  /** With enter "zoom": the point of the previous plate's photograph the camera rushes into. */
  through?: UV;
  events: UTHEvent[];
}

export interface UnderTheHoodData { plates: UTHPlate[] }

export type Box = [number, number, number, number];

/** A text's length in characters (code points), as the validator counts it; JS .length counts UTF-16 units. */
export const chars = (text: string): number => Array.from(text).length;

/** The camera scale of a plate `t` frames after it starts, before any transition. */
export function plateScale(plate: UTHPlate, t: number, fps: number): number {
  return (plate.zoom ?? 1) * (1 + (CAMERA.push * Math.max(0, t)) / fps);
}

/** Where the photograph's point [u, v] is in the frame at camera scale `s`. */
export function projectAt(plate: UTHPlate, s: number, u: number, v: number): [number, number] {
  const [fu, fv] = plate.focus ?? [0.5, 0.5];
  const a = plate.aspect ?? 1;
  return [GEOMETRY.plateCx + (u - fu) * GEOMETRY.plateWidth * s, GEOMETRY.plateCy + (v - fv) * GEOMETRY.plateWidth * a * s];
}

/** The photograph's box in the frame at camera scale `s`. */
export function imageBox(plate: UTHPlate, s: number): Box {
  const [x0, y0] = projectAt(plate, s, 0, 0);
  const [x1, y1] = projectAt(plate, s, 1, 1);
  return [x0, y0, x1, y1];
}

/** A callout chip's box, centred on its chip point (frame fractions). */
export function chipBox(text: string, chip: UV): Box {
  const w = chars(text) * GEOMETRY.chipCharPx + 2 * GEOMETRY.chipPadPx;
  const cx = chip[0] * W, cy = chip[1] * H;
  return [cx - w / 2, cy - GEOMETRY.chipHeight / 2, cx + w / 2, cy + GEOMETRY.chipHeight / 2];
}

/** The text a stat shows when it has counted to `value`. */
export function statText(value: number, decimals = 0, prefix = "", suffix = ""): string {
  return `${prefix}${value.toFixed(decimals)}${suffix}`;
}

/** A stat block's box: the numeral (at its wider end of the count) and its label, right-aligned. */
export function statBox(e: Pick<UTHStat, "value" | "from" | "decimals" | "prefix" | "suffix" | "label" | "place">): Box {
  const numeral = Math.max(
    ...[e.from ?? 0, e.value].map((v) => chars(statText(v, e.decimals ?? 0, e.prefix ?? "", e.suffix ?? ""))),
  ) * GEOMETRY.statCharPx;
  const label = chars(e.label) * GEOMETRY.statLabelCharPx;
  const w = Math.max(numeral, label);
  const top = e.place === "upper" ? GEOMETRY.statUpperTop : GEOMETRY.statLowerTop;
  return [GEOMETRY.statRight - w, top, GEOMETRY.statRight, top + GEOMETRY.statHeight];
}

/** The widest the value above a chart gets, over its points. */
export function chartTextWidth(e: Pick<UTHChart, "points" | "decimals" | "prefix" | "suffix">): number {
  return Math.max(...e.points.map((v) => chars(statText(v, e.decimals ?? 0, e.prefix ?? "", e.suffix ?? "")))) * GEOMETRY.chartCharPx;
}

/** Whether a counter row's widest value fits its column. */
export function counterFits(values: { from: number; to: number }[]): boolean {
  const digits = Math.max(...values.map((v) => Math.max(String(v.from).length, String(v.to).length, 2)));
  return digits * GEOMETRY.counterCharPx + GEOMETRY.counterPadPx <= GEOMETRY.counterWidth / values.length;
}

/** The point on a chip's edge where its leader starts: the middle of the side facing the target. */
export function leaderStart(box: Box, target: [number, number]): [number, number] {
  const cx = (box[0] + box[2]) / 2, cy = (box[1] + box[3]) / 2;
  if (target[0] < box[0]) return [box[0], cy];
  if (target[0] > box[2]) return [box[2], cy];
  return [cx, target[1] < cy ? box[1] : box[3]];
}

export function overlaps(a: Box, b: Box): boolean {
  const t = GEOMETRY.overlapTolerance;
  return a[0] < b[2] - t && b[0] < a[2] - t && a[1] < b[3] - t && b[1] < a[3] - t;
}
