/*
 * The Editorial Collage data contract: the shape of `props.collage`, its
 * limits and timings, and the desk geometry the MCP server checks before
 * render.
 *
 * Keep in sync: mcp/editorial_collage.py holds the Python side of every
 * constant here, and tubematic_core/style_packs/editorial_collage.json lists
 * the headline kinds, hero kinds and events for the agent.
 * mcp/tests/test_editorial_collage.py reads this file and fails when they
 * disagree, and both sides run the shared cases in
 * mcp/tests/fixtures/editorial_collage_contract.json.
 *
 * The video is a paper desk larger than the frame. The code lays the stations
 * out on it in a zig-zag (left column, right column, a little lower each
 * time) and one camera glides from station to station; the agent never writes
 * a coordinate. While the camera rests on a station, the station has fixed
 * zones in frame pixels: its headline at the top, its hero in the middle, the
 * captions (the shared Subtitles component, "highlight" look) under it.
 *
 * A real person is never pictured: no field takes a face. A print always
 * carries the small note "Illustration" and a recreation index card the note
 * "Recreation"; neither has a field that turns it off.
 */

export const W = 1080;
export const H = 1920;

export const COLORS = {
  desk: "#E4DCCF",
  deskFibre: "#A3967C",
  paper: "#E0DCDA",
  newsprint: "#E9E1D0",
  clipping: "#CFB195",
  card: "#F0EBE0",
  rule: "#93A9C2",
  edge: "#F5F2EA",
  ink: "#171716",
  inkSoft: "#4A4743",
  red: "#B65255",
  redDark: "#93403C",
  highlight: "#DACF08",
} as const;

export const HEADLINE_KINDS = ["clipping", "label", "black"] as const;
export type HeadlineKind = (typeof HEADLINE_KINDS)[number];
export const HERO_KINDS = ["print", "sticker", "index", "figure", "stack"] as const;
export type HeroKind = (typeof HERO_KINDS)[number];
export const EVENTS = ["circle", "underline", "highlight", "stamp", "arrow", "strike"] as const;
export type EventKind = (typeof EVENTS)[number];
export const ARROW_SIDES = ["left", "right"] as const;

// The renderer draws these; there is no field to change or hide them.
export const NOTES = { print: "Illustration", recreation: "Recreation" } as const;

// A station's zones in frame pixels while the camera rests on it.
export const ZONES = {
  headTop: 236,
  headBottom: 600,
  heroTop: 640,
  heroBottom: 1280,
  left: 100,
  right: 980,
  heroCenterY: 960,
} as const;

// The zig-zag: station i rests at desk point (i odd ? dx : 0, i * dy).
export const DESK = {
  dx: 620,
  dy: 1140,
  // the desk's fibre texture repeats every `tile` pixels
  tile: 1024,
} as const;

// Headline layout per kind: the font sizes tried largest first, a character's
// width as a share of its size (a generous estimate, so a line laid out here
// never runs off its paper), the text width, the line height, the paper's
// padding, the most lines and the zone height the text may take.
// `blackFull` is a black card with no hero under it: it takes both zones.
export const HEADLINE = {
  clipping: { sizes: [96, 84, 72, 62], charW: 0.56, width: 780, line: 1.04, pad: 34, maxLines: 3, zone: 364 },
  label: { sizes: [72, 62, 52, 44], charW: 0.66, width: 800, line: 1.1, pad: 22, maxLines: 2, zone: 364 },
  black: { sizes: [96, 84, 72, 62], charW: 0.56, width: 760, line: 1.04, pad: 40, maxLines: 3, zone: 364 },
  blackFull: { sizes: [128, 112, 96, 84, 72], charW: 0.56, width: 760, line: 1.04, pad: 70, maxLines: 6, zone: 1044 },
} as const;
export type HeadlineLayoutKind = keyof typeof HEADLINE;
// The kicker line above a headline takes this much of its zone.
export const KICKER_H = 64;

export const LIMITS = {
  maxStations: 20,
  minStationSeconds: 1.5,
  headlineChars: 60,
  kickerChars: 28,
  captionChars: 40,
  labelChars: 24,
  lineChars: 34,
  minLines: 1,
  maxLines: 4,
  prefixChars: 3,
  suffixChars: 10,
  figureLabelChars: 24,
  maxFigure: 999999999,
  figureDecimals: 2,
  minStack: 2,
  maxStack: 3,
  stackCaptionChars: 24,
  stampChars: 12,
  // generated stills per video, each a paid image call
  maxImages: 10,
  // The longest stretch, in seconds, with nothing new on the desk (a station,
  // an event, a typed line or a count starting); the sticker's sway does not
  // count. The AI review is told the same number.
  maxStillSeconds: 3.5,
} as const;

export const TIMING = {
  // A station start or an event lands within this many frames of a word's start.
  snap: 2,
  // An event this close to its station's end is never read.
  readFrames: 8,
  // the camera's glide from one station to the next, from the station's start
  glide: 36,
  // pieces move on twelve steps a second: positions update every `step` frames
  step: 2.5,
  headLand: 8,
  heroDelay: 4,
  heroLand: 10,
  labelDelay: 10,
  labelLand: 8,
  stackStagger: 4,
  circle: 30,
  underline: 15,
  highlight: 10,
  strike: 10,
  stamp: 6,
  kick: 4,
  arrow: 8,
  count: 30,
  // characters typed a second on an index card, on twos
  typeRate: 13,
  // a sticker's idle sway, degrees either way, and its period in frames
  sway: 1.5,
  swayPeriod: 72,
  // a print's tilt, degrees either way, from a seed
  tilt: 4,
} as const;

export interface Headline {
  text: string;
  kind: HeadlineKind;
  kicker?: string;
}

export interface StackItem { image: string; caption?: string }
export interface IndexLine { text: string; at: number }

export interface PrintHero { kind: "print"; image: string; caption?: string }
export interface StickerHero { kind: "sticker"; image: string; label?: string }
export interface IndexHero { kind: "index"; lines: IndexLine[]; recreation?: boolean }
export interface FigureHero { kind: "figure"; value: number; prefix?: string; suffix?: string; label: string; countAt: number }
export interface StackHero { kind: "stack"; items: StackItem[] }
export type Hero = PrintHero | StickerHero | IndexHero | FigureHero | StackHero;

export interface CollageEvent {
  at: number;
  do: EventKind;
  word?: string;          // underline, highlight, strike: a word of the headline
  text?: string;          // stamp
  from?: "left" | "right"; // arrow
}

export interface Station {
  start: number;
  headline?: Headline;
  hero?: Hero;
  events?: CollageEvent[];
}

export interface CollageData {
  stations: Station[];
}
