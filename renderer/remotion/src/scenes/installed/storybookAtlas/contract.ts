/*
 * The Storybook Atlas contract: what `props.storybookAtlas` may hold, its limits
 * and its timings. The MCP validator (mcp/storybook_atlas.py) checks a config
 * against the same values before the video can render. The prop catalogue
 * (each prop's box, place, states, acts and portal) is written beside each
 * drawing in ./props/; the style pack's `extra.props` is a copy the validator
 * reads, and a test holds the two equal.
 */
import { PROPS as LIBRARY } from "./props";
import { BACKDROPS, type Backdrop } from "./backdrops";
import { BUILDS, COLORS, FACES, GARMENTS, HAIRS, HAIR_COLORS, HATS, PERSON_POSES, SKINS, type Person, type PersonPose } from "./figure";
import { GUIDE_POSES, type GuideCoat, type GuidePose } from "./guide";
import { COAT_COLORS } from "./palette";
import type { Act, Place } from "./props/types";

export { BACKDROPS, BUILDS, COLORS, FACES, GARMENTS, GUIDE_POSES, HAIRS, HAIR_COLORS, HATS, PERSON_POSES, SKINS };
export const COATS = Object.keys(COAT_COLORS) as GuideCoat[];

export const W = 1080;
export const H = 1920;

/** A library prop's catalogue entry. */
export type PropSpec = { box: [number, number]; place: Place; states: number; acts: Act[]; portal?: [number, number] };
export const PROPS: Record<string, PropSpec> = Object.fromEntries(
  Object.entries(LIBRARY).map(([id, e]) => [id, { box: e.box, place: e.place, states: e.states, acts: e.acts, ...(e.portal ? { portal: e.portal } : {}) }]),
);

export const LIMITS = {
  chapters: [3, 5],
  /** A chapter lasts at least this long (seconds). */
  chapterMinSeconds: 8,
  cast: 4,
  /** People on stage at once. */
  onStage: 2,
  /** Props on stage at once in a chapter. */
  propsOnStage: 6,
  title: 18, // characters per line, 2 lines
  titleLines: 2,
  byline: 28,
  name: 24,
  tag: 24,
  /** Constellation: words per set, characters per word. */
  words: 2,
  wordChars: 10,
  gaugeLabel: 24,
  /** The longest stretch with nothing new on stage (seconds). */
  quietSeconds: 4,
  /** A plate (constellation, gauge, morph) lasts this long (seconds). */
  plateSeconds: [2.5, 8],
  propScale: [0.6, 1.4],
} as const;

/** Frame timings. */
export const TIMING = {
  /** How close to a word's first frame an event or chapter must start. */
  onWord: 2,
  /** Walking speed (px per frame) and the frames each walk drawing is held. */
  walkSpeed: 9,
  walkHold: 2,
  /** A prop's entrance, an act's length, a state switch's cross-fade. */
  propIn: 10,
  act: 48,
  cycleHold: 4,
  switchFade: 4,
  /** A tag's fade-in. */
  tagIn: 6,
  /** A plate opening and closing (brass shutters parting from a centre seam). */
  plateOpen: 10,
  /** Chapter transitions. */
  pushFrames: 14,
  pushScale: 4,
  whiteHold: 2,
  dissolve: 5,
  wipeFrames: 14,
  /** An event in the last frames of a chapter could not be seen before the transition. */
  endMargin: 20,
} as const;

/** The stage: where things may stand or hang. */
export const STAGE = {
  left: 60,
  right: 1020,
  top: 430, // below the plaque band
  floor: 1344,
  /** Wall props hang with their base between these heights. */
  wallBase: [620, 1240],
  /** Where the guide stands when a chapter opens, if it does not move first. */
  guideHome: 210,
  /** Plates fill this box over the stage. */
  plate: { x: 90, y: 450, w: 900, h: 860 },
} as const;

export const PROP_ENTRANCES = ["pop", "drop", "slide", "rise", "fade"] as const;
export const FACINGS = ["left", "right"] as const;
export const ENTERS = ["push", "wipe"] as const;
/** Characters the constellation lettering can draw. */
export const GLYPHS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" as const;

export type Facing = (typeof FACINGS)[number];
export type PropEntrance = (typeof PROP_ENTRANCES)[number];

export type CastMember = Person & { id: string; name: string };

export type SAEvent =
  | { type: "guide"; at: number; x?: number; pose?: GuidePose; facing?: Facing }
  | { type: "person"; at: number; who: string; x?: number; pose?: PersonPose; facing?: Facing; exit?: boolean }
  | { type: "prop"; at: number; id: string; prop: string; x: number; y?: number; scale?: number; enter?: PropEntrance }
  | { type: "act"; at: number; id: string; act: Act }
  | { type: "tag"; at: number; on: string; text: string }
  | { type: "constellation"; at: number; until: number; words: string[]; then?: string[]; thenAt?: number }
  | { type: "gauge"; at: number; until: number; label: string; from: number; to: number; max: number; danger?: number }
  | { type: "morph"; at: number; until: number; prop?: string; word?: string };

export type Chapter = {
  start: number;
  title: string;
  byline: string;
  backdrop: Backdrop;
  enter?: (typeof ENTERS)[number];
  events: SAEvent[];
};

export type CustomProp = PropSpec & { id: string; src: string };

export type StorybookAtlasData = {
  guide: { coat: GuideCoat };
  cast: CastMember[];
  chapters: Chapter[];
  customProps?: CustomProp[];
};

export const PLATE_EVENTS = ["constellation", "gauge", "morph"] as const;
export type PlateEvent = Extract<SAEvent, { type: (typeof PLATE_EVENTS)[number] }>;

/** Split a title into lines of at most LIMITS.title characters, at spaces. */
export function wrapTitle(title: string): string[] {
  const out: string[] = [];
  let line = "";
  for (const word of title.trim().split(/\s+/)) {
    const next = line ? `${line} ${word}` : word;
    if (next.length > LIMITS.title && line) {
      out.push(line);
      line = word;
    } else {
      line = next;
    }
  }
  if (line) out.push(line);
  return out;
}
