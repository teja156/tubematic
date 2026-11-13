/*
 * The Code Scenes data contract: the shape of `props.codeScenes`, its limits,
 * its timings and the geometry the MCP server checks before render.
 *
 * Code Scenes is an insert style only: a code card whose tokens morph from one
 * version of the code to the next while unchanged tokens stay put, a highlight
 * on the lines the narration is about, an error squiggle with a ruled callout,
 * and a small pane with what the code prints.
 *
 * Keep in sync: mcp/code_scenes.py holds the Python side of every constant
 * here. Both sides run the shared cases in
 * mcp/tests/fixtures/code_scenes_contract.json, which also pins the constants.
 *
 * The code font is monospace, so every fit check is characters x the font's
 * advance (0.6 of its size): the validator never needs the tokeniser.
 */

export const W = 1080;
export const H = 1920;

/** A monospace glyph advance, as a fraction of the font size. */
export const ADVANCE = 0.6;

/** The languages the tokeniser carries; a step's `lang` is one of these. */
export const LANGS = [
  "python", "javascript", "typescript", "sql", "c", "java", "go", "rust", "json", "yaml", "html", "css",
] as const;
export type Lang = (typeof LANGS)[number];

export const LIMITS = {
  maxSteps: 4,
  maxLines: 14,
  maxCols: 40,
  tagChars: 24,
  fileChars: 24,
  labelChars: 24,
  errorChars: 48,
  outputLines: 3,
  outputChars: 40,
  outputLabelChars: 12,
  // Characters a typed first step may hold: typing is for a line or two.
  typeChars: 120,
  // Frames between two steps, and from the last step to the insert's end.
  minStepGap: 45,
  endHold: 30,
  maxStillSeconds: 3,
} as const;

export const TIMING = {
  morph: 15,
  focus: 8,
  callout: 10,
  squiggle: 10,
  outputStagger: 3,
  outputIn: 8,
  typePerChar: 1,
} as const;

/**
 * The layout, in frame pixels, before the insert moves clear of the captions.
 * The pack's insert.block is [BAND.top, BAND.bottom].
 */
export const BAND = { top: 200, bottom: 1340 } as const;
export const LAYOUT = {
  headerY: 200,
  headerH: 56,
  progressY: 268,
  cardX: 50,
  cardW: 980,
  cardY: 290,
  titleH: 60,
  codePad: 18,
  // The code area's height budget: the card, the callout and the output pane
  // must end by BAND.bottom whatever the code holds.
  codeBudget: 650,
  calloutH: 80,
  // The one-line error callout shrinks to fit its box, down to this size
  // (mcp/code_scenes.py CALLOUT_MIN_FONT refuses a message wider than that).
  calloutMinFont: 22,
  textWidth: 768,
  paneGap: 16,
  paneHeadH: 48,
  paneLineH: 44,
  panePad: 24,
  maxFont: 40,
  lineHeight: 1.4,
} as const;

/** The code's font size: as large as fits the longest line and the line
 *  count, never above maxFont. With the limits above it is at least 32. */
export function fontSizeFor(lines: number, cols: number): number {
  const byCols = cols > 0 ? LAYOUT.textWidth / (ADVANCE * cols) : LAYOUT.maxFont;
  const byRows = lines > 0 ? LAYOUT.codeBudget / (LAYOUT.lineHeight * lines) : LAYOUT.maxFont;
  return Math.floor(Math.min(LAYOUT.maxFont, byCols, byRows));
}

export function lineHeightFor(fontSize: number): number {
  return Math.round(fontSize * LAYOUT.lineHeight);
}

/** The lines of a code string, as the card shows them. */
export function codeLines(code: string): string[] {
  const lines = code.replace(/\r\n?/g, "\n").split("\n");
  while (lines.length > 1 && lines[lines.length - 1] === "") lines.pop();
  return lines;
}

/** Frames a typed first step takes to type out. */
export function typeFrames(code: string): number {
  return Math.ceil(code.replace(/\n/g, "").length * TIMING.typePerChar);
}

export type CodeError = { line: number; match: string; text: string };
export type CodeOutput = { lines: string[]; label?: string };

export type CodeStep = {
  /** Frame the step starts on, on the video's clock. */
  at: number;
  /** The code from this step on; left out, the code stays as it was. */
  code?: string;
  label?: string;
  /** 1-based lines the narration is about; the rest dim. */
  focus?: number[];
  error?: CodeError;
  /** What the code on screen prints; cleared when the code changes. */
  output?: CodeOutput;
  /** Step 1 only: type the code in instead of showing it at once. */
  reveal?: "type";
};

export type CodeScenesData = {
  lang: Lang;
  file?: string;
  tag?: string;
  steps: CodeStep[];
};

/** The code each step shows: its own, or the last one before it. */
export function codeAt(data: CodeScenesData, index: number): string {
  for (let i = index; i >= 0; i--) {
    const c = data.steps[i]?.code;
    if (typeof c === "string") return c;
  }
  return "";
}

/** The output pane a step shows: its own output, or the one from an earlier
 *  step while the code has not changed since. Output belongs to the code on
 *  screen, so a code change clears it. */
export function outputAt(data: CodeScenesData, index: number): { output: CodeOutput; from: number } | null {
  for (let i = index; i >= 0; i--) {
    const s = data.steps[i];
    if (!s) break;
    if (s.output) return { output: s.output, from: i };
    if (typeof s.code === "string") return null;
  }
  return null;
}

/** The font size that fits every version of the code in the insert, so the
 *  card keeps one size from step to step. */
export function insertFontSize(data: CodeScenesData): number {
  let lines = 1;
  let cols = 1;
  data.steps.forEach((_, i) => {
    const ls = codeLines(codeAt(data, i));
    lines = Math.max(lines, ls.length);
    cols = Math.max(cols, ...ls.map((l) => l.length));
  });
  return fontSizeFor(lines, cols);
}
