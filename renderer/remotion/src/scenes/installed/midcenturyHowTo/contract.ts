/*
 * The Mid-century How-To data contract: the shape of `props.midcenturyHowTo`,
 * its limits, its catalogues (grounds, poses, faces, outfits, objects) and the
 * geometry the MCP server checks before render.
 *
 * Keep in sync: mcp/midcentury_howto.py holds the Python side of every
 * constant here, and the style pack's `extra` lists the catalogues for the
 * agent. Both are written from this file by character-tools/sync-contract.mjs
 * (never edit them by hand); mcp/tests/test_midcentury_howto.py fails when the
 * three disagree.
 */

export const W = 1080;
export const H = 1920;

export const LIMITS = {
  minSteps: 2,
  maxSteps: 6,
  maxShots: 30,
  maxEventsPerShot: 20,
  // Objects, labels and insets on stage at once in one shot; the presenter is not counted.
  maxElementsPerShot: 4,
  titleChars: 30,
  kickerChars: 22,
  headerChars: 18,
  tagChars: 26,
  labelChars: 22,
  insetChars: 10,
  maxStillSeconds: 3,
  minShotSeconds: 1.5,
  minStepSeconds: 3,
  minIntroSeconds: 1.5,
  minSummarySeconds: 2,
  // A label may not repeat this many narration words in a row: the captions carry the words.
  labelEchoWords: 4,
} as const;

export const TIMING = {
  // An object's entrance; its acts, presses, checks and insets may start only after it.
  objectIn: 8,
  // Two poses closer than this read as a twitch.
  minPoseGap: 8,
  // A pose blends into the next over this many frames (on twos).
  poseBlend: 4,
  // A press: the hand pulls back this many frames before the press frame, lands on it,
  // holds, then returns over `pressReturn`.
  pressLead: 6,
  pressHold: 12,
  pressReturn: 8,
  // A press needs this many frames before the next press of the same shot.
  minPressGap: 16,
  // An object's act plays for this long, then the object holds its last state.
  actFrames: 20,
  // Medallions, labels and insets pop over this many frames.
  pop: 8,
  // An event this close to its shot's end is cut before it is seen.
  endMargin: 6,
  // A step's header slides in for this long after the step's first frame.
  headerIn: 12,
} as const;

// Where things go, in frame pixels.
export const GEOMETRY = {
  safeLeft: 60,
  safeRight: 1020,
  // The stage of a step shot, under the step header and its tag.
  stageTop: 600,
  // The stage of an intro shot, under the big title.
  introStageTop: 860,
  floorY: 1385,
  // The presenter's feet stand at this x (left) or W minus it (right).
  presenterX: 205,
  // His body box: half its width and its height above the feet (arms excluded; they reach).
  presenterHalfWidth: 150,
  presenterHeight: 820,
  // The shoulder of the arm that reaches, relative to the feet (left-standing; mirrored on the right),
  // and the reach of that arm to the fingertip.
  shoulderDx: 52,
  shoulderDy: -588,
  armReach: 430,
  labelFontPx: 40,
  labelCharPx: 22,
  labelHeightPx: 64,
  insetRadius: 120,
  overlapTolerance: 6,
} as const;

export const GROUNDS = {
  mustard: "#E8B43A",
  blue: "#7F9CC0",
  olive: "#A7AE5B",
  rose: "#D9937E",
  sea: "#7DB8A8",
} as const;

export const EVENT_TYPES = ["pose", "object", "act", "press", "check", "cross", "inset", "label"] as const;
export const POSES = ["stand", "present", "point", "thumbsup", "wave", "think", "shrug", "hips"] as const;
// The poses the presenter may take on the summary card: none reaches across the step list.
export const SUMMARY_POSES = ["stand", "thumbsup", "wave", "hips"] as const;
// The poses whose hand aims at the object `at` names.
export const AIM_POSES = ["present", "point"] as const;
export const FACES = ["neutral", "smile", "grin", "worried", "surprised", "proud"] as const;
export const OUTFITS = ["coral", "teal", "mustard", "blue"] as const;
export const HAIRS = ["dark", "red", "blond", "grey"] as const;
export const SIDES = ["left", "right", "none"] as const;
export const ENTRANCES = ["pop", "drop", "slide", "rise"] as const;

/*
 * The object library. Each object is drawn once, by hand, in the style's
 * off-register cels (./objects/), centred on (0, 0). `w` and `h` are its box at
 * scale 1: every pixel the drawing can reach, act included. `text` is the most
 * characters its text slot takes (0 when it has none); a screen's text is up
 * to four lines split on "|", the first one its title. `acts` are its own
 * animations.
 */
export const OBJECTS = {
  // screens: text is "Title|row|row|row"
  phone: { w: 320, h: 560, text: 80, acts: ["row1", "row2", "row3", "done"] },
  laptop: { w: 540, h: 420, text: 70, acts: ["row1", "row2", "row3", "done"] },
  window: { w: 600, h: 440, text: 80, acts: ["row1", "row2", "row3", "done"] },
  // things you type into or scan
  qr: { w: 270, h: 270, text: 0, acts: ["scan", "done"] },
  keypad: { w: 380, h: 470, text: 8, acts: ["type", "done"] },
  password: { w: 560, h: 160, text: 18, acts: ["type", "done"] },
  toggle: { w: 280, h: 150, text: 0, acts: ["flip"] },
  button: { w: 360, h: 160, text: 14, acts: ["light"] },
  app: { w: 240, h: 270, text: 10, acts: ["bounce"] },
  // devices and security
  router: { w: 440, h: 290, text: 0, acts: ["blink"] },
  lock: { w: 230, h: 310, text: 0, acts: ["unlock"] },
  key: { w: 320, h: 170, text: 0, acts: ["turn"] },
  shield: { w: 250, h: 300, text: 0, acts: ["glow"] },
  usb: { w: 320, h: 150, text: 0, acts: ["plug"] },
  battery: { w: 320, h: 170, text: 0, acts: ["fill"] },
  // paper and mail
  envelope: { w: 360, h: 250, text: 20, acts: ["open"] },
  document: { w: 310, h: 390, text: 40, acts: ["stamp"] },
  checklist: { w: 360, h: 420, text: 72, acts: ["tick1", "tick2", "tick3", "tick4"] },
  card: { w: 390, h: 250, text: 16, acts: [] },
  sign: { w: 380, h: 270, text: 24, acts: ["wobble"] },
  calendar: { w: 300, h: 330, text: 6, acts: ["flip"] },
  // time, ideas and housekeeping
  clock: { w: 300, h: 300, text: 0, acts: ["spin"] },
  bulb: { w: 230, h: 330, text: 0, acts: ["light"] },
  gear: { w: 290, h: 290, text: 0, acts: ["turn"] },
  magnifier: { w: 300, h: 310, text: 0, acts: ["scan"] },
  bell: { w: 270, h: 290, text: 0, acts: ["ring"] },
  cloud: { w: 380, h: 250, text: 0, acts: ["upload"] },
  trash: { w: 250, h: 310, text: 0, acts: ["drop"] },
  table: { w: 480, h: 300, text: 0, acts: [] },
} as const;

export const OBJECT_SCALE = { min: 0.5, max: 1.5 } as const;

/*
 * An object the agent draws for one video, when the library has nothing for
 * the subject: a TSX file beside the video's other generated files
 * (generated/<video_id>/prop-<name>.tsx), modelled on a library object and
 * using the same helpers (./cel). `w` and `h` are its box at scale 1.
 */
export const CUSTOM = { maxProps: 8, minSide: 60, maxSide: 700, maxText: 80, maxActs: 4 } as const;

export type ObjectId = keyof typeof OBJECTS;
export type Ground = keyof typeof GROUNDS;
export type Pose = (typeof POSES)[number];
export type Face = (typeof FACES)[number];
export type Outfit = (typeof OUTFITS)[number];
export type Hair = (typeof HAIRS)[number];
export type Side = (typeof SIDES)[number];
export type Entrance = (typeof ENTRANCES)[number];

export type MCStep = { start: number; header: string; tag?: string; ground: Ground };
export type MCEvent =
  | { type: "pose"; frame: number; pose: Pose; face: Face; at?: string }
  | { type: "object"; frame: number; id?: string; object: string; x: number; y: number; scale?: number; text?: string; enter?: Entrance }
  | { type: "act"; frame: number; target: string; act: string }
  | { type: "press"; frame: number; target: string }
  | { type: "check"; frame: number; target: string }
  | { type: "cross"; frame: number; target: string }
  | { type: "inset"; frame: number; target: string; text: string; x: number; y: number }
  | { type: "label"; frame: number; text: string; x: number; y: number };
export type MCShot = { start: number; presenter?: Side; events: MCEvent[] };
export type MCCustomProp = { id: string; src: string; w: number; h: number; text?: number; acts?: string[] };
export type MidcenturyData = {
  title: string;
  kicker?: string;
  presenter?: { outfit?: Outfit; hair?: Hair };
  customProps?: MCCustomProp[];
  steps: MCStep[];
  // The frame the summary card starts: every step's medallion and header, to the end.
  summary?: number;
  shots: MCShot[];
};

/** An element's id on stage: an object's own id, or its object name. */
export const objectInstanceId = (e: { id?: string; object: string }) => e.id ?? e.object;

/** An object's box at scale 1: the library's, or the size a custom prop declares. */
export function objectSize(object: string, custom: readonly MCCustomProp[] = []): { w: number; h: number } {
  if (object in OBJECTS) return OBJECTS[object as ObjectId];
  const c = custom.find((q) => q.id === object);
  return c ? { w: c.w, h: c.h } : { w: 0, h: 0 };
}

/** [left, top, right, bottom] of an object placed at (x, y) as fractions of the frame. */
export function objectBox(object: string, x: number, y: number, scale = 1, custom: readonly MCCustomProp[] = []): [number, number, number, number] {
  const p = objectSize(object, custom);
  const cx = x * W, cy = y * H, hw = (p.w * scale) / 2, hh = (p.h * scale) / 2;
  return [cx - hw, cy - hh, cx + hw, cy + hh];
}

/** [left, top, right, bottom] of a label chip centred at (x, y): the text, the star and the padding. */
export function labelBox(text: string, x: number, y: number): [number, number, number, number] {
  const width = Math.max(text.length, 1) * GEOMETRY.labelCharPx + 90;
  const cx = x * W, cy = y * H;
  return [cx - width / 2, cy - GEOMETRY.labelHeightPx / 2, cx + width / 2, cy + GEOMETRY.labelHeightPx / 2];
}

/** [left, top, right, bottom] of an inset circle centred at (x, y). */
export function insetBox(x: number, y: number): [number, number, number, number] {
  const r = GEOMETRY.insetRadius, cx = x * W, cy = y * H;
  return [cx - r, cy - r, cx + r, cy + r];
}

/** The x of the presenter's feet on a side. */
export const presenterFeetX = (side: Side) => (side === "right" ? W - GEOMETRY.presenterX : GEOMETRY.presenterX);

/** [left, top, right, bottom] of the presenter's body standing on a side. */
export function presenterBox(side: Side): [number, number, number, number] {
  const cx = presenterFeetX(side);
  return [cx - GEOMETRY.presenterHalfWidth, GEOMETRY.floorY - GEOMETRY.presenterHeight, cx + GEOMETRY.presenterHalfWidth, GEOMETRY.floorY];
}

/** The reaching shoulder of the presenter on a side, in frame pixels. */
export function shoulderAt(side: Side): [number, number] {
  const dx = side === "right" ? -GEOMETRY.shoulderDx : GEOMETRY.shoulderDx;
  return [presenterFeetX(side) + dx, GEOMETRY.floorY + GEOMETRY.shoulderDy];
}

/** Whether the presenter's own arm reaches a point; a press out of reach comes from the frame's edge. */
export function inReach(side: Side, px: number, py: number): boolean {
  if (side === "none") return false;
  const [sx, sy] = shoulderAt(side);
  return Math.hypot(px - sx, py - sy) <= GEOMETRY.armReach;
}

/** A screen object's text as its title and rows. */
export function screenLines(text: string): string[] {
  return text.split("|").map((s) => s.trim()).filter(Boolean).slice(0, 4);
}
