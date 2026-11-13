/*
 * The Archive and Engraving data contract: the shape of `props.archive`, its
 * limits and timings, and the page geometry the MCP server checks before
 * render.
 *
 * Keep in sync: mcp/archive_engraving.py holds the Python side of every
 * constant here, and tubematic_core/style_packs/archive_engraving.json lists
 * the card kinds, events and emblems for the agent.
 * mcp/tests/test_archive_engraving.py reads this file and fails when they
 * disagree, and both sides run the shared cases in
 * mcp/tests/fixtures/archive_engraving_contract.json.
 *
 * The page has fixed zones, so nothing the agent writes can land on another
 * zone: the running header at the top, the dated serif title, one museum
 * card in the plate band, the captions under it (the shared Subtitles
 * component, "fill" look on a "chip"), and an optional timeline ruler at the
 * bottom. The agent never writes a coordinate on the page: a point it gives
 * ([u, v]) is a fraction of a still, and the renderer places the rest.
 *
 * People are name cards with an engraved roundel (an emblem or initials):
 * there is no field for a face or a picture of a person. A plate or chart
 * card always carries the footnote "Illustration" and a document card
 * "Recreation"; neither has a field that turns it off.
 */

export const W = 1080;
export const H = 1920;

export const COLORS = {
  parchment: "#EAE2D5",
  edge: "#BAAF9B",
  card: "#F1E8D2",
  ink: "#181411",
  inkSoft: "#5A5148",
  rule: "#8C8172",
  red: "#A83A3A",
} as const;

export const CARD_KINDS = ["plate", "chart", "person", "people", "document"] as const;
export type CardKind = (typeof CARD_KINDS)[number];
export const EVENTS = ["strike", "stamp", "magnify", "route", "timeline", "underline"] as const;
export type EventKind = (typeof EVENTS)[number];
export const EMBLEMS = ["laurel", "quill", "gear", "compass", "scroll", "book", "anchor", "telescope", "scales", "lamp"] as const;
export type Emblem = (typeof EMBLEMS)[number];

// The renderer draws these under every card of the kind; there is no field to change or hide them.
export const FOOTNOTES = { plate: "Illustration", chart: "Illustration", document: "Recreation" } as const;

// The fixed zones, in frame pixels.
export const ZONES = {
  headerY: 244,          // the running header's rule (under the watermark's corner)
  titleLeft: 64,
  titleWidth: 952,
  dateTop: 280,
  titleTop: 336,
  withTop: 590,          // the italic line a strike raises under the title
  bandBottom: 690,       // the title band ends here
  cardLeft: 90,
  cardRight: 990,
  cardTop: 700,
  cardBottom: 1268,
  // the picture window on a plate or a chart card
  winLeft: 120,
  winTop: 726,
  winW: 840,
  winH: 430,
  rulerY: 1640,
  rulerLeft: 110,
  rulerRight: 970,
  stampX: 800,
  stampY: 1110,
} as const;

// The title's font sizes, largest first: the largest that fits two lines wins.
export const TITLE_SIZES = [104, 92, 80, 70] as const;
// A title character's width as a share of its font size: a generous estimate
// for Cormorant Upright, so a line laid out here never runs off the page.
export const TITLE_CHAR_W = 0.5;

export const LIMITS = {
  maxBeats: 32,
  minBeatSeconds: 1.5,
  // A people card is empty until its first person arrives; this soon after the beat starts, at most.
  firstPersonSeconds: 1.5,
  headerChars: 34,
  titleChars: 48,
  dateChars: 24,
  withChars: 28,
  nameChars: 28,
  noteChars: 40,
  datesChars: 20,
  roleChars: 32,
  lineChars: 40,
  stampChars: 14,
  minLines: 1,
  maxLines: 6,
  minPeople: 2,
  maxPeople: 4,
  minRoute: 2,
  maxRoute: 8,
  maxInitials: 3,
  // generated stills per video, each a paid image call
  maxImages: 10,
  minYear: 0,
  maxYear: 2100,
  maxRulerTicks: 8,
  // The longest stretch, in seconds, with nothing new on the page (a beat, an
  // event, a person or a line arriving); the slow push does not count. The AI
  // review is told the same number.
  maxStillSeconds: 3.5,
} as const;

export const TIMING = {
  // A beat start or an event lands within this many frames of a word's start.
  snap: 2,
  // An event this close to its beat's end is never read.
  readFrames: 8,
  enter: 10,
  dateType: 12,
  strike: 15,
  withRise: 12,
  underline: 12,
  stamp: 6,
  kick: 4,
  magnify: 14,
  route: 20,
  timeline: 20,
  rulerFade: 10,
  person: 10,
  connector: 12,
  // characters written per frame on a document line
  typeRate: 2,
  handRate: 1.5,
  // a plate's slow push over the whole beat
  push: 0.06,
  magnifyZoom: 2.5,
} as const;

export type UV = [number, number];

export interface Person {
  name: string;
  dates: string;
  role: string;
  emblem?: Emblem;
  initials?: string;
  at?: number;            // in a `people` card: the frame this person arrives, on a word
}

export interface PlateCard { kind: "plate"; image: string; focus?: UV; name: string; note?: string }
export interface ChartCard { kind: "chart"; image: string; focus?: UV; name: string; note?: string; route: UV[] }
export interface PersonCard extends Person { kind: "person" }
export interface PeopleCard { kind: "people"; people: Person[] }
export interface DocLine { text: string; at: number }
export interface DocumentCard { kind: "document"; lines: DocLine[]; hand?: boolean }
export type Card = PlateCard | ChartCard | PersonCard | PeopleCard | DocumentCard;

export interface ArchiveEvent {
  at: number;
  do: EventKind;
  word?: string;          // strike, underline: a word of the title
  with?: string;          // strike: the italic words that rise under the title
  text?: string;          // stamp
  point?: UV;             // magnify
  from?: number;          // timeline
  to?: number;            // timeline
}

export interface Beat {
  start: number;
  title: { text: string; red: string };
  date?: string;
  card: Card;
  events?: ArchiveEvent[];
}

export interface ArchiveData {
  header: string;
  beats: Beat[];
}
