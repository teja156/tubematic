/*
 * The Storybook Reveal data contract: the shape of `props.reveal`, its limits
 * and timings, and the page geometry the MCP server checks before render.
 *
 * Keep in sync: mcp/storybook_reveal.py holds the Python side of every
 * constant here, and tubematic_core/style_packs/storybook_reveal.json lists
 * the turns and the treatment for the agent.
 * mcp/tests/test_storybook_reveal.py reads this file and fails when they
 * disagree, and both sides run the shared cases in
 * mcp/tests/fixtures/storybook_reveal_contract.json.
 *
 * The page has fixed zones, so nothing the agent writes can land on another
 * zone: the hand-lettered title near the top, one rounded panel holding the
 * page's square picture (contain-fitted, never cropped), the captions under it (the
 * shared Subtitles component, "fill" look with no plate) and the page number.
 * The agent never writes a coordinate on the page: `focus` is a point of the
 * still the slow push keeps in place.
 *
 * Every page shows one generated still twice: its pencil plate (the
 * treat_image "pencil" copy, which lines up with the still pixel for pixel)
 * wipes in first, then the colour still floods over it.
 */

export const W = 1080;
export const H = 1920;

export const COLORS = {
  page: "#F4F5EE",
  warm: "#E9DDC3",
  ink: "#38382F",
  olive: "#A09969",
  brown: "#7D6247",
  flapEdge: "#BFB197",
  shade: "#3B2E20",
} as const;

export const TURNS = ["cut", "curl"] as const;
export type Turn = (typeof TURNS)[number];

// The fixed zones, in frame pixels.
export const ZONES = {
  titleTop: 230,
  titleBottom: 390,
  titleWidth: 880,
  swashY: 362,          // the pencil swash under the title
  panelLeft: 90,
  panelTop: 410,
  panelWidth: 900,
  panelHeight: 870,
  panelRadius: 44,
  feather: 44,          // how far a picture's edges fade into the panel
  captionTop: 1300,
  captionBottom: 1500,
  pageNoY: 1640,
} as const;

// The title is one line of hand-lettered capitals: the largest size up to the
// first that fits ZONES.titleWidth at TITLE_CHAR_W of its size per character,
// never under the second.
export const TITLE_SIZES = [92, 56] as const;
// A Patrick Hand capital with the title's letter spacing is about this share of its size wide (generous).
export const TITLE_CHAR_W = 0.6;

export const LIMITS = {
  maxPages: 24,
  // different stills (pages may show one again), each a paid image call
  maxImages: 12,
  titleChars: 24,
  titleWords: 3,
  minPageSeconds: 2.5,
  maxCurls: 2,
  // The longest stretch, in seconds, with nothing new on a page (a page, the
  // pencil wipe, the colour flood); the slow push does not count. The AI
  // review is told the same number.
  maxHoldSeconds: 6,
} as const;

export const TIMING = {
  // A page start, a pencil wipe or a colour flood lands within this many frames of a word's start.
  // The colour follows the pencil within a second, so a page's whole reveal takes at most about 1.6 s.
  snap: 2,
  title: 10,
  // the pencil wipe starts at least this many frames after its page (except a first page drawn at frame 0)
  pencilAfter: 6,
  pencil: 12,
  // the colour starts flooding at least TIMING.pencil and at most this many frames after the pencil starts
  colourWithin: 30,
  colour: 18,
  // the colour has finished flooding at least this many frames before its page ends
  read: 8,
  curl: 14,
  // the slow push from 1 to 1 + push, from the colour landing to the page's end
  push: 0.06,
} as const;

export type UV = [number, number];

export interface Page {
  start: number;
  title: string;
  image: string;        // /public/<video_id>/images/<name>.png
  pencil: string;       // /public/<video_id>/images/treated/<name>.pencil.png
  focus?: UV;
  pencilAt: number;
  colourAt: number;
  turn?: Turn;
}

export interface RevealData {
  pages: Page[];
}
