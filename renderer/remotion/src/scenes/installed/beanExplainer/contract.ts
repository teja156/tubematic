/*
 * The Bean Explainer data contract: the shape of `props.beanExplainer`, its
 * limits, its catalogues (poses, faces, marks, accessories, fields, props) and
 * the geometry the MCP server checks before render.
 *
 * Keep in sync: mcp/bean_explainer.py holds the Python side of every constant
 * here, and tubematic_core/style_packs/bean_explainer.json lists the
 * catalogues for the agent. mcp/tests/test_bean_explainer.py reads this file
 * and fails when the three disagree, and both sides run the shared cases in
 * mcp/tests/fixtures/bean_explainer_contract.json.
 */

export const W = 1080;
export const H = 1920;

export const LIMITS = {
  maxSections: 12,
  maxShots: 40,
  maxEventsPerShot: 24,
  // Props and labels on stage at once in one shot; the beans are not counted.
  maxElementsPerShot: 6,
  headerChars: 18,
  titleChars: 40,
  labelLineChars: 22,
  labelLines: 2,
  // The longest stretch, in seconds, with nothing new on screen. The look
  // lives on constant small changes; a held frame is its failure.
  maxStillSeconds: 3,
  minSectionSeconds: 2,
  minShotSeconds: 1.5,
  // A label may not repeat this many narration words in a row: the captions
  // carry the words, a label names a thing.
  labelEchoWords: 4,
} as const;

export const TIMING = {
  // A section change with `list` on plays the badge carousel for this long;
  // nothing in that shot may start before it ends.
  carousel: 30,
  // Two pose swaps of one bean closer than this read as a twitch.
  minPoseGap: 8,
  // A pose swap snaps over this many frames.
  poseSnap: 2,
  // A prop's entrance; its acts may start only after it.
  propIn: 10,
  // The red X and arrows draw on over this many frames.
  drawOn: 15,
  // Two impacts closer than this blur into one shake.
  minImpactGap: 15,
  // An event this close to its shot's end is cut before it is seen.
  endMargin: 6,
  // A prop's act plays for this long, then the prop holds its last state.
  actFrames: 60,
  // Pops and marks settle to exactly their rest after this many frames. A
  // spring that never quite arrives repaints its whole layer every frame,
  // which on the CPU renderer cost more than drawing the bean.
  settle: 30,
} as const;

// Where things go, in frame pixels. The stage is between the header and the
// floor line; the captions sit on the floor strip below it.
export const GEOMETRY = {
  safeLeft: 60,
  safeRight: 1020,
  stageTop: 460,
  floorY: 1300,
  // The bean's body box at scale 1: half its width and its height above the
  // feet (head, ears and hair; arms excluded, they may reach over a prop).
  beanHalfWidth: 150,
  beanHeight: 780,
  beanScale: 0.95,
  // Two beans on stage are drawn smaller so both fit with props.
  beanScaleTwo: 0.8,
  labelFontPx: 50,
  labelCharPx: 24,
  labelLinePx: 60,
  // Elements may touch; they may not overlap by more than this.
  overlapTolerance: 6,
} as const;

// Where a section's card sits on the carousel strip and in the corner.
export const BADGE = { x: 914, y: 300, r: 78 } as const;

export const EVENT_TYPES = ["pose", "prop", "act", "label", "mark", "impact", "strike", "arrow"] as const;
export const POSES = [
  "stand", "point", "present", "wave", "cheer", "shrug", "think", "facepalm", "hands-hips", "panic", "lean",
] as const;
export const FACES = ["neutral", "happy", "worried", "shocked", "squint", "smug", "sad", "angry"] as const;
export const LOOKS = ["front", "left", "right"] as const;
export const MARKS = ["sweat", "alarm", "question", "exclaim", "sparkle", "shock", "anger", "idea"] as const;
export const ACCESSORIES = ["none", "glasses", "cap", "tie", "headset", "hardhat", "beanie"] as const;
export const TINTS = ["cream", "peach", "grey", "mint", "lilac"] as const;
export const ENTRANCES = ["pop", "drop", "slide", "rise"] as const;
export const LABEL_TONES = ["ink", "red"] as const;
export const CAST_IDS = ["narrator", "other"] as const;

export const FIELDS = {
  yellow: "#F9D648",
  mint: "#A8E2C4",
  sky: "#9FD3F2",
  peach: "#FFC4A3",
  lilac: "#CDB8EE",
} as const;

export const SECTION_COLORS = {
  red: "#E2302B",
  blue: "#3B7DD8",
  green: "#2FA866",
  orange: "#F08A24",
  teal: "#1FA3A3",
  purple: "#8A5CD0",
} as const;

/*
 * The prop library. Each prop is drawn once, by hand, in the bean's line and
 * palette (./props/), and a person approved it on the prop sheet. `w` and `h`
 * are its box at scale 1, in frame pixels: every pixel the drawing can reach,
 * outline and drawn act included, measured with BeanPropSheet's measure mode
 * (a box smaller than the drawing lets the validator pass a real overlap).
 * Re-measure after changing a drawing. `text` is the most characters its one
 * text slot takes (0 when it has none); `acts` are its own animations.
 */
export const PROPS = {
  // text-carrying
  phone: { w: 260, h: 440, text: 40, acts: ["buzz"] },
  browser: { w: 640, h: 150, text: 26, acts: ["flash"] },
  laptop: { w: 460, h: 340, text: 30, acts: ["flash"] },
  sign: { w: 400, h: 350, text: 24, acts: ["wobble"] },
  document: { w: 330, h: 410, text: 20, acts: ["stamp"] },
  note: { w: 300, h: 310, text: 30, acts: [] },
  speech: { w: 460, h: 270, text: 40, acts: [] },
  thought: { w: 450, h: 300, text: 40, acts: [] },
  pricetag: { w: 340, h: 210, text: 10, acts: ["swing"] },
  calendar: { w: 320, h: 340, text: 6, acts: ["flip"] },
  envelope: { w: 360, h: 260, text: 20, acts: ["shake"] },
  // money
  coins: { w: 280, h: 250, text: 0, acts: ["shake"] },
  banknote: { w: 400, h: 210, text: 6, acts: ["swing"] },
  wallet: { w: 340, h: 270, text: 0, acts: ["shake"] },
  piggybank: { w: 390, h: 310, text: 0, acts: ["shake"] },
  creditcard: { w: 400, h: 260, text: 16, acts: ["swing"] },
  chartup: { w: 400, h: 340, text: 16, acts: ["grow"] },
  chartdown: { w: 400, h: 340, text: 16, acts: ["grow"] },
  // health and the body
  brain: { w: 400, h: 330, text: 0, acts: ["spark"] },
  heart: { w: 300, h: 260, text: 0, acts: ["beat"] },
  stomach: { w: 260, h: 340, text: 0, acts: ["shake"] },
  pill: { w: 270, h: 180, text: 0, acts: ["spin"] },
  coffee: { w: 310, h: 390, text: 0, acts: ["steam"] },
  water: { w: 210, h: 340, text: 0, acts: ["fill"] },
  bed: { w: 500, h: 370, text: 0, acts: ["zzz"] },
  dumbbell: { w: 410, h: 150, text: 0, acts: ["shake"] },
  apple: { w: 260, h: 250, text: 0, acts: ["spin"] },
  // tech
  lock: { w: 260, h: 430, text: 0, acts: ["unlock"] },
  key: { w: 330, h: 220, text: 0, acts: ["spin"] },
  server: { w: 320, h: 400, text: 0, acts: ["flash"] },
  wifi: { w: 350, h: 260, text: 0, acts: ["pulse"] },
  bug: { w: 290, h: 300, text: 0, acts: ["wobble"] },
  shield: { w: 280, h: 340, text: 0, acts: ["flash"] },
  cursor: { w: 270, h: 350, text: 0, acts: ["click"] },
  // time and feeling
  clock: { w: 360, h: 340, text: 0, acts: ["ring"] },
  hourglass: { w: 240, h: 360, text: 0, acts: ["spin"] },
  gears: { w: 360, h: 280, text: 0, acts: ["turn"] },
  bulb: { w: 340, h: 390, text: 0, acts: ["light"] },
  cloud: { w: 410, h: 330, text: 0, acts: ["rain"] },
  trophy: { w: 360, h: 370, text: 0, acts: ["spark"] },
  bomb: { w: 330, h: 340, text: 0, acts: ["shake"] },
  magnifier: { w: 260, h: 350, text: 0, acts: ["wobble"] },
} as const;

export const PROP_SCALE = { min: 0.5, max: 1.4 } as const;

/*
 * A prop the agent draws for one video, when the library has nothing for the
 * subject: a TSX file it writes beside the video's other generated files
 * (generated/<video_id>/prop-<name>.tsx), modelled on a library prop and
 * using the same helpers (./props/common). `w` and `h` are its box at scale 1,
 * which the agent declares and the preview outlines; `text` and `acts` say
 * what the drawing does with a text slot and an act, as in PROPS.
 */
export const CUSTOM = { maxProps: 8, minSide: 60, maxSide: 700, maxText: 40, maxActs: 4 } as const;

export type PropId = keyof typeof PROPS;
export type Pose = (typeof POSES)[number];
export type Face = (typeof FACES)[number];
export type Look = (typeof LOOKS)[number];
export type MarkType = (typeof MARKS)[number];
export type Accessory = (typeof ACCESSORIES)[number];
export type Tint = (typeof TINTS)[number];
export type Entrance = (typeof ENTRANCES)[number];
export type CastId = (typeof CAST_IDS)[number];
export type FieldId = keyof typeof FIELDS;
export type SectionColor = keyof typeof SECTION_COLORS;

export type BECast = { id: CastId; accessory?: Accessory; tint?: Tint };
export type BESection = { start: number; header: string; color: SectionColor; badge: string };
export type BEEvent =
  | { type: "pose"; frame: number; who: CastId; pose: Pose; face: Face; look?: Look; x?: number; at?: string }
  | { type: "prop"; frame: number; id?: string; prop: string; x: number; y: number; scale?: number; enter?: Entrance; text?: string }
  | { type: "act"; frame: number; target: string; act: string }
  | { type: "label"; frame: number; text: string; x: number; y: number; tone?: (typeof LABEL_TONES)[number] }
  | { type: "mark"; frame: number; who: CastId; mark: MarkType }
  | { type: "impact"; frame: number; strength?: 1 | 2 | 3 }
  | { type: "strike"; frame: number; target: string }
  | { type: "arrow"; frame: number; from: string; to: string };
export type BEShot = { start: number; events: BEEvent[] };
export type BECustomProp = { id: string; src: string; w: number; h: number; text?: number; acts?: string[] };
export type BeanExplainerData = {
  customProps?: BECustomProp[];
  field?: FieldId;
  title?: string;
  list?: boolean;
  cast: BECast[];
  sections: BESection[];
  shots: BEShot[];
};

/** Greedy word wrap at LIMITS.labelLineChars; same rule as mcp/bean_explainer.py. */
export function wrapLabel(text: string): string[] {
  const lines: string[] = [];
  for (const word of text.split(/\s+/).filter(Boolean)) {
    const last = lines[lines.length - 1];
    if (last !== undefined && last.length + 1 + word.length <= LIMITS.labelLineChars) lines[lines.length - 1] = `${last} ${word}`;
    else lines.push(word);
  }
  return lines;
}

/** An element's id on stage: a prop's own id, or its prop name. */
export const propInstanceId = (e: { id?: string; prop: string }) => e.id ?? e.prop;

/** The bean's scale in a shot: smaller when both beans are on stage. */
export const beanScale = (beansOnStage: number) => (beansOnStage > 1 ? GEOMETRY.beanScaleTwo : GEOMETRY.beanScale);

/** A prop's box at scale 1: the library's, or the size a custom prop declares. */
export function propSize(prop: string, custom: BECustomProp[] = []): { w: number; h: number } {
  if (prop in PROPS) return PROPS[prop as PropId];
  const c = custom.find((q) => q.id === prop);
  return c ? { w: c.w, h: c.h } : { w: 0, h: 0 };
}

/** [left, top, right, bottom] of a prop placed at (x, y) as fractions of the frame. */
export function propBox(prop: string, x: number, y: number, scale = 1, custom: BECustomProp[] = []): [number, number, number, number] {
  const p = propSize(prop, custom);
  const cx = x * W, cy = y * H, hw = (p.w * scale) / 2, hh = (p.h * scale) / 2;
  return [cx - hw, cy - hh, cx + hw, cy + hh];
}

/** [left, top, right, bottom] of a label centred at (x, y). */
export function labelBox(text: string, x: number, y: number): [number, number, number, number] {
  const lines = wrapLabel(text);
  const width = Math.max(...lines.map((l) => l.length), 1) * GEOMETRY.labelCharPx;
  const height = lines.length * GEOMETRY.labelLinePx;
  const cx = x * W, cy = y * H;
  return [cx - width / 2, cy - height / 2, cx + width / 2, cy + height / 2];
}

/** [left, top, right, bottom] of a bean's body standing at x (fraction) on the floor. */
export function beanBox(x: number, scale: number): [number, number, number, number] {
  const cx = x * W;
  return [cx - GEOMETRY.beanHalfWidth * scale, GEOMETRY.floorY - GEOMETRY.beanHeight * scale, cx + GEOMETRY.beanHalfWidth * scale, GEOMETRY.floorY];
}
