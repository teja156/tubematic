/*
 * The Terminal Doc data contract: the shape of `props.terminalDoc`, its limits,
 * its timings and the geometry the MCP server checks before render.
 *
 * Keep in sync: mcp/terminal_doc.py holds the Python side of every constant
 * here, and tubematic_core/style_packs/terminal_doc.json lists the catalogues
 * for the agent. mcp/tests/test_terminal_doc.py reads this file and fails when
 * the three disagree, and both sides run the shared cases in
 * mcp/tests/fixtures/terminal_doc_contract.json.
 *
 * Every string on stage is drawn one glyph per cell, each cell CELL x its size
 * wide, whatever the font. That keeps the fit check exact (characters x cell),
 * lets letters leave their cells and arc somewhere else, and makes the two
 * skins' fonts interchangeable.
 */

export const W = 1080;
export const H = 1920;

/** A glyph cell is this fraction of the type size wide. */
export const CELL = 0.6;

export const GEOMETRY = {
  safeLeft: 60,
  safeRight: 1020,
} as const;

/** Type sizes, in frame pixels. */
export const SIZES = { s: 40, m: 64, l: 96, xl: 128 } as const;
export type Size = keyof typeof SIZES;

/**
 * Where things go: one element per slot at a time. The stage is three bands
 * (a, b, c); `stage` names all three at once (a grid, a wide custom move). The
 * context line holds one mono question or quoted line above the stage, the
 * note slot a bracket's quote and citation below it. The band under the note
 * belongs to the LOG captions and the bottom of the frame stays empty.
 */
export const SLOTS = {
  context: { y: 384, top: 230, bottom: 538, sizes: ["s", "m"] },
  a: { y: 640, top: 538, bottom: 742, sizes: ["s", "m", "l", "xl"] },
  b: { y: 845, top: 742, bottom: 947, sizes: ["s", "m", "l", "xl"] },
  c: { y: 1050, top: 947, bottom: 1152, sizes: ["s", "m", "l", "xl"] },
  note: { y: 1248, top: 1152, bottom: 1344, sizes: ["s"] },
  stage: { y: 845, top: 538, bottom: 1152, sizes: ["s", "m"] },
} as const;
export type SlotName = keyof typeof SLOTS;
export const STAGE_BANDS = ["a", "b", "c"] as const;

export const TONES = ["white", "grey", "dim", "red", "blue"] as const;
export type Tone = (typeof TONES)[number];
export const GLOW_TONES = ["red", "blue"] as const;
export const REVEALS = ["scramble", "type", "cut"] as const;
export const SKINS = ["house", "crt"] as const;
export type Skin = (typeof SKINS)[number];
export const CUTS = ["hard", "collapse"] as const;

export const MOVES = [
  "word", "rearrange", "encode", "number", "wall", "grid", "stream", "bracket", "glow", "type", "push", "clear", "custom",
] as const;
export type MoveType = (typeof MOVES)[number];

export const LIMITS = {
  maxBeats: 40,
  maxEventsPerBeat: 24,
  // Elements on screen at once in one beat, the context line and the note
  // included. The look is a mostly empty frame; a full one is its failure.
  maxOnStage: 4,
  maxStillSeconds: 3,
  minBeatSeconds: 2,
  // Stage text may not repeat this many narration words in a row: the
  // captions carry the sentence, the stage shows the thing it is about.
  echoWords: 4,
  noteChars: 36,
  noteLines: 2,
  labelChars: 16,
  // An encode box's label and sub-label sit right of the box.
  boxLabelChars: 12,
  maxGuesses: 40,
  minGridRows: 1,
  maxGridRows: 8,
  maxOutputLines: 3,
  minStreamFrames: 30,
  maxStreamFrames: 150,
  minPushFrames: 45,
  maxPushFrames: 450,
  minPushScale: 1.02,
  maxPushScale: 1.15,
  maxCite: 99,
} as const;

export const TIMING = {
  // A word scrambles in over this many frames; a typed one at typeRate
  // characters per frame.
  reveal: 9,
  typeRate: 1.6,
  // One letter's flight in a rearrange or an encode, and the stagger between
  // letters: the slow ease-in-out arc of the house look.
  arc: 16,
  stagger: 3,
  // An encode: letters scramble inside the box this long, then fly out.
  encodeHold: 5,
  encodeOut: 15,
  // A number: noise for lockStart frames, then one digit locks every lockStep
  // frames, right to left.
  lockStart: 6,
  lockStep: 1.4,
  // A grid builds one row every rowStep frames.
  rowStep: 4,
  bracketDraw: 14,
  glowIn: 10,
  outputStagger: 2,
  clearOut: 8,
  collapse: 8,
  // An event must finish this long before its beat ends, or it is cut before
  // anyone can read it.
  readMargin: 15,
  // A cut lands on a word: within this many frames of one.
  snap: 2,
} as const;

/** A move the agent writes for one video (generated/<video_id>/move-<name>.tsx). */
export const CUSTOM = { maxMoves: 6, minFrames: 15, maxFrames: 240, maxText: 40 } as const;

// ── the data ──────────────────────────────────────────────────────────────────

export type TDEvent =
  | { type: "word"; at: number; id: string; slot: SlotName; text: string; size?: Size; tone?: Tone; reveal?: (typeof REVEALS)[number]; accent?: string }
  | { type: "rearrange"; at: number; id: string; from: string; text: string; slot?: SlotName; size?: Size; tone?: Tone }
  | { type: "encode"; at: number; id: string; from: string; text: string; slot: SlotName; label: string; sub?: string; size?: Size; tone?: Tone }
  | { type: "number"; at: number; id: string; slot: SlotName; value: string; size?: Size; tone?: Tone; count?: number }
  | { type: "wall"; at: number; level: 0 | 1 | 2 }
  | { type: "grid"; at: number; id: string; rows: string[]; size?: Size; tone?: Tone }
  | { type: "stream"; at: number; id: string; slot: SlotName; guesses: string[]; target: string; frames: number; size?: Size }
  | { type: "bracket"; at: number; target: string; label: string; tone?: Tone; note?: string; cite?: number }
  | { type: "glow"; at: number; target: string; tone: (typeof GLOW_TONES)[number]; row?: number; span?: [number, number] }
  | { type: "type"; at: number; id: string; slot: SlotName; text: string; output?: string[]; size?: Size }
  | { type: "push"; at: number; frames: number; scale: number }
  | { type: "clear"; at: number; targets: string[] }
  | { type: "custom"; at: number; id: string; move: string; slot: SlotName; text?: string };

export interface TDBeat {
  start: number;
  cut?: (typeof CUTS)[number];
  events: TDEvent[];
}

export interface TDCustomMove {
  id: string;
  /** "<video_id>/move-<name>", the file written with write_scene_file. */
  src: string;
  frames: number;
  /** The longest text the move is given, 0 for none. */
  text: number;
}

export interface TerminalDocData {
  skin: Skin;
  beats: TDBeat[];
  customMoves?: TDCustomMove[];
}

// ── shared rules (mirrored in mcp/terminal_doc.py) ────────────────────────────

/** Characters that fit across the safe width at a size. */
export function maxChars(size: Size): number {
  return Math.floor((GEOMETRY.safeRight - GEOMETRY.safeLeft) / (SIZES[size] * CELL));
}

/** The cells a number takes: digits after "^" are an exponent at half size. */
export function numberCells(value: string): number {
  const i = value.indexOf("^");
  return i < 0 ? value.length : i + (value.length - i - 1) / 2;
}

/** Greedy word wrap of a note at LIMITS.noteChars; same rule as the Python side. */
export function wrapNote(text: string): string[] {
  const lines: string[] = [];
  for (const word of text.split(/\s+/).filter(Boolean)) {
    if (lines.length && lines[lines.length - 1].length + 1 + word.length <= LIMITS.noteChars) {
      lines[lines.length - 1] += ` ${word}`;
    } else {
      lines.push(word);
    }
  }
  return lines;
}

/** How long a move takes to play out, in frames; 0 for a held setting. */
export function moveFrames(e: TDEvent, custom: Record<string, TDCustomMove> = {}, fromText = ""): number {
  switch (e.type) {
    case "word":
      return e.reveal === "cut" ? 1 : e.reveal === "type" ? Math.ceil(e.text.length / TIMING.typeRate) : TIMING.reveal;
    case "rearrange": {
      const n = Math.max(fromText.replace(/ /g, "").length, e.text.replace(/ /g, "").length, 1);
      return TIMING.arc + TIMING.stagger * (n - 1);
    }
    case "encode": {
      const n = Math.max(fromText.replace(/ /g, "").length, 1);
      return TIMING.stagger * (n - 1) + TIMING.arc + TIMING.encodeHold + TIMING.encodeOut;
    }
    case "number":
      return e.count ? e.count : Math.ceil(TIMING.lockStart + TIMING.lockStep * (e.value.replace(/[^0-9A-Za-z]/g, "").length - 1)) + 1;
    case "grid":
      return TIMING.rowStep * (e.rows.length - 1) + TIMING.reveal;
    case "stream":
      return e.frames;
    case "bracket":
      return TIMING.bracketDraw + TIMING.reveal;
    case "glow":
      return TIMING.glowIn;
    case "type":
      return Math.ceil(e.text.length / TIMING.typeRate) + TIMING.outputStagger * (e.output?.length ?? 0) + TIMING.reveal;
    case "push":
      return e.frames;
    case "clear":
      return TIMING.clearOut;
    case "custom":
      return custom[e.move]?.frames ?? 0;
    case "wall":
      return TIMING.reveal;
  }
}
