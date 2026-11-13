/*
 * The Night Signal data contract: the shape of `props.nightSignal`, its limits
 * and timings, and the geometry the MCP server checks before render.
 *
 * Keep in sync: mcp/night_signal.py holds the Python side of every constant
 * here, and tubematic_core/style_packs/night_signal.json lists the catalogues
 * for the agent. Both are written from this file by
 * renderer/remotion/nightsignal-tools/sync-contract.mjs, with the shared cases
 * in mcp/tests/fixtures/night_signal_contract.json; the tests on both sides
 * fail until it has run.
 *
 * The frame has fixed zones, so nothing the agent writes can land on another
 * zone: the case-file row near the top (the HUD), the picture band under it,
 * where every scene is drawn, and the captions at 70% (the shared Subtitles
 * layer). Positions inside the band come from named slots, never coordinates.
 */
import { ANIMALS, OBJECTS, POSES } from "./parts";

export const W = 1080;
export const H = 1920;

export const SCENE_KINDS = ["tableau", "camera", "phone", "rule", "case", "steps"] as const;
export const SETTINGS = ["night", "street", "room", "plain"] as const;
export const SLOTS = ["left", "midleft", "center", "midright", "right"] as const;
export const SCREENS = ["message", "link", "qr", "call", "alert"] as const;
export const MARKS = ["check", "cross"] as const;
export const CUTS = ["glitch", "hard"] as const;
export const BUBBLES = ["thought", "speech"] as const;
export const SHAPES = ["circle", "rect", "line", "poly"] as const;
export const TONES = ["ink", "grey", "dim", "core", "red", "hole"] as const;

export type SceneKind = (typeof SCENE_KINDS)[number];
export type Setting = (typeof SETTINGS)[number];
export type Slot = (typeof SLOTS)[number];
export type Screen = (typeof SCREENS)[number];
export type Tone = (typeof TONES)[number];

/** The people, animals and objects a scene may show, by name. */
export const PEOPLE = Object.keys(POSES).map((p) => (p === "stand" ? "person" : `person_${p}`));
export const ANIMAL_NAMES = Object.keys(ANIMALS);
export const OBJECT_NAMES = Object.keys(OBJECTS);

export const LIMITS = {
  minScenes: 3,
  maxScenes: 14,
  maxItems: 4,
  maxCustomParts: 6,
  maxShapes: 40,
  // Custom part coordinates: a box this wide and tall, ground at y = 0, x centred.
  partBox: 400,
  fileTitleChars: 16,
  cameraLabelChars: 22,
  buttonChars: 6,
  phoneTitleChars: 12,
  phoneLines: 3,
  phoneLineChars: 16,
  ruleLines: 2,
  ruleLineChars: 12,
  caseLabelChars: 10,
  caseNameChars: 12,
  minBars: 2,
  maxBars: 4,
  stampChars: 10,
  stepsTitleChars: 20,
  minSteps: 2,
  maxSteps: 4,
  stepChars: 24,
  minSceneSeconds: 1.5,
  // The longest stretch, in seconds, in which nothing new happens apart from
  // the running loops and the slow push. The AI review is told the same number.
  maxStillSeconds: 5,
} as const;

export const TIMING = {
  // A scene start or an event lands within this many frames of a word's start.
  snap: 2,
  // A glitch tear runs from tearBefore frames before a scene's start to tearAfter after it.
  tearBefore: 2,
  tearAfter: 1,
  // An item that enters pops in with an overshoot over this many frames.
  pop: 10,
  // A small step to another slot takes this many frames.
  step: 18,
  // A connector draws on over this many frames; a bubble pops over `pop`.
  connector: 15,
  // The threat turns red over this many frames.
  redden: 6,
  // The rule card: the underline, then the ring draws, then the slash.
  underline: 10,
  ringStart: 4,
  ringFrames: 12,
  slashDelay: 16,
  slashFrames: 6,
  // A mark (check or cross) and a stamp land over this many frames.
  mark: 8,
  // A step line of the steps card slides in over this many frames.
  stepIn: 8,
  // Text needs this long on screen before its scene ends to be read.
  readFrames: 20,
} as const;

export const CAMERA = {
  // The slow push over a scene: the band's scale at its end.
  push: 1.05,
} as const;

export const GEOMETRY = {
  // The picture band, in frame pixels.
  bandTop: 360,
  bandHeight: 780,
  // The ground line inside the band, and the x of each slot.
  ground: 640,
  slotX: { left: 220, midleft: 390, center: 540, midright: 690, right: 860 } as Record<Slot, number>,
  // A camera panel draws its items at this scale on its own floor.
  cameraScale: 0.62,
  cameraGround: 470,
  // The HUD row.
  hudTop: 204,
  safeLeft: 66,
  safeRight: 1014,
  // Card text: the widest a line may be drawn, and the advance of one capital in ems a fit assumes.
  lineWidth: 900,
  capCharWidth: 0.72,
} as const;

/** One drawn shape of a custom part, in the part's own box (x from -200 to 200, y from -400 to 0). */
export type Shape =
  | { shape: "circle"; cx: number; cy: number; r: number; tone: Tone }
  | { shape: "rect"; x: number; y: number; w: number; h: number; r?: number; tone: Tone }
  | { shape: "line"; points: [number, number][]; width: number; tone: Tone }
  | { shape: "poly"; points: [number, number][]; tone: Tone };

export interface CustomPart {
  id: string;
  shapes: Shape[];
}

export interface Item {
  /** A person pose, an animal, an object or a custom part's id. */
  what: string;
  slot: Slot;
  /** The frame it pops in on; absent, it is there when the scene starts. */
  at?: number;
  /** The one red thing in the scene. */
  threat?: boolean;
  /** The frame the threat turns red on; absent, it is red from its first frame. */
  redAt?: number;
  face?: "left" | "right";
  /** A small step to another slot on a word. */
  to?: { slot: Slot; at: number };
}

export interface Connector {
  from: Slot;
  to: Slot;
  at: number;
}

export interface Bubble {
  over: Slot;
  icon: string;
  kind?: "thought" | "speech";
  at: number;
}

interface SceneBase {
  start: number;
  /** How the scene arrives: a glitch tear (the default) or a hard cut. */
  cut?: "glitch" | "hard";
}

export interface Tableau extends SceneBase {
  kind: "tableau";
  setting: Setting;
  items: Item[];
  connector?: Connector;
  bubble?: Bubble;
}

export interface CameraPanel extends SceneBase {
  kind: "camera";
  label: string;
  items: Item[];
  connector?: Connector;
  button?: { text: string; crossAt?: number };
}

export interface PhoneScreen extends SceneBase {
  kind: "phone";
  screen: Screen;
  title: string;
  lines: string[];
  mark?: { kind: "check" | "cross"; at: number };
}

export interface RuleCard extends SceneBase {
  kind: "rule";
  number: number;
  lines: string[];
  icon: string;
  slashAt?: number;
}

export interface CaseCard extends SceneBase {
  kind: "case";
  label: string;
  name: string;
  icon: string;
  bars: number;
  stamp?: { text: string; at: number };
}

export interface StepsCard extends SceneBase {
  kind: "steps";
  title: string;
  steps: { text: string; at: number }[];
}

export type Scene = Tableau | CameraPanel | PhoneScreen | RuleCard | CaseCard | StepsCard;

export interface NightSignalData {
  file: { number: number; title: string };
  /** The clock the HUD's timecode starts from, "HH:MM". */
  clock?: string;
  scenes: Scene[];
  customParts?: CustomPart[];
}

// ── helpers both sides share ───────────────────────────────────────────────
/** The font size, at most `size`, at which one line of `text` fits `width` pixels. */
export function fitFontSize(text: string, size: number, width: number = GEOMETRY.lineWidth): number {
  const n = Math.max(1, text.length);
  return Math.min(size, Math.floor(width / (n * GEOMETRY.capCharWidth)));
}

/**
 * The frames at which something new happens in a scene, in order, starting
 * with the scene itself: items popping in, steps, red, connectors, bubbles,
 * marks, the rule's slash, the stamp, each step line.
 */
export function eventFrames(scene: Scene): number[] {
  const T = TIMING;
  const out = [scene.start];
  const items = scene.kind === "tableau" || scene.kind === "camera" ? scene.items : [];
  for (const it of items) {
    if (it.at !== undefined) out.push(it.at);
    if (it.to) out.push(it.to.at);
    if (it.redAt !== undefined) out.push(it.redAt);
  }
  if (scene.kind === "tableau" || scene.kind === "camera") {
    if (scene.connector) out.push(scene.connector.at);
  }
  if (scene.kind === "tableau" && scene.bubble) out.push(scene.bubble.at);
  if (scene.kind === "camera" && scene.button?.crossAt !== undefined) out.push(scene.button.crossAt);
  if (scene.kind === "phone" && scene.mark) out.push(scene.mark.at);
  if (scene.kind === "rule") out.push(scene.slashAt ?? scene.start + T.slashDelay);
  if (scene.kind === "case" && scene.stamp) out.push(scene.stamp.at);
  if (scene.kind === "steps") for (const s of scene.steps) out.push(s.at);
  return [...new Set(out)].sort((a, b) => a - b);
}

/** The HUD's timecode at a frame: the clock plus the video's own time, "HH:MM:SS:FF". */
export function timecode(clock: string | undefined, frame: number, fps: number): string {
  const m = /^(\d\d):(\d\d)$/.exec(clock ?? "") ?? ["", "03", "12"];
  const start = (Number(m[1]) * 60 + Number(m[2])) * 60;
  const secs = start + Math.floor(frame / fps);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(Math.floor(secs / 3600) % 24)}:${pad(Math.floor(secs / 60) % 60)}:${pad(secs % 60)}:${pad(frame % fps)}`;
}
