/*
 * The Format Packs data contract: the shape of `props.formatPacks`, its limits,
 * its timings and the geometry the MCP server checks before render.
 *
 * Format Packs is an insert style only: one phone-native format per insert, a
 * chat thread, a short numbered list, a quiz board or a news strap, all text
 * and data. Every message thread and every headline without a source is made
 * up, so the component draws an EXAMPLE tag on it that the data cannot remove,
 * and nothing in it imitates a real app: no notch or status bar, no app or
 * brand names, no verified ticks, phone numbers only from the ranges set aside
 * for fiction.
 *
 * Keep in sync: mcp/format_packs.py holds the Python side of every constant
 * here. Both sides run the shared cases in
 * mcp/tests/fixtures/format_packs_contract.json, which also pins the constants.
 *
 * Text is laid out by the browser (CSS wraps it); the validator only needs to
 * know that it fits, so it counts lines with `wrapLines`, which estimates each
 * text's width in its box (../fitText.ts) on the wide side of the real font.
 */
import { wrapCount } from "../fitText";

export const W = 1080;
export const H = 1920;

export const FORMATS = ["chat", "list", "quiz", "strap"] as const;
export type Format = (typeof FORMATS)[number];

export const LIMITS = {
  minMessages: 2,
  maxMessages: 5,
  messageChars: 90,
  contactChars: 24,
  titleChars: 40,
  titleLines: 2,
  maxMarks: 3,
  markLabelChars: 16,
  // A marked run is drawn on one line, so it never runs longer than a line.
  markChars: 22,
  minItems: 2,
  maxItems: 4,
  leadChars: 24,
  itemChars: 64,
  itemLines: 2,
  questionChars: 80,
  questionLines: 3,
  minOptions: 2,
  maxOptions: 4,
  optionChars: 30,
  kickerChars: 20,
  headlineChars: 70,
  headlineLines: 3,
  dateChars: 24,
  sourceChars: 40,
  flapChars: 10,
  flapLabelChars: 20,
  maxStrapMarks: 2,
  // Frames between two arrivals (bubbles, rows, options), from a message's
  // arrival to a mark on it, and from the last change to the insert's end.
  minGap: 18,
  markLead: 8,
  endHold: 30,
  maxStillSeconds: 3,
} as const;

export const TIMING = {
  bubbleIn: 7,
  dots: 14,
  rowIn: 14,
  optionIn: 10,
  lock: 10,
  mark: 14,
  headlineIn: 12,
  flip: 8,
  flipPerTile: 3,
} as const;

/** Characters per line the validator assumes for each kind of text. */
/** Each wrapped text's font size, box width and whether it is in capitals, as
 *  the components draw it. */
export const WRAP = {
  bubble: [44, 580, false],
  title: [56, 796, true],
  item: [36, 686, false],
  question: [52, 768, false],
  headline: [60, 756, false],
} as const;
export type WrapKind = keyof typeof WRAP;

/** One-line texts that shrink to fit their box: smallest size, box width,
 *  letter spacing, capitals. */
export const ONE_LINE = {
  chatTitle: [36, 620, 1, true],
  option: [30, 680, 0, false],
} as const;

/** The layout, in frame pixels, before the insert moves clear of the captions.
 *  The pack's insert.block is [BAND.top, BAND.bottom]. */
export const BAND = { top: 200, bottom: 1330 } as const;
export const LAYOUT = {
  left: 120,
  right: 960,
  titleY: 200,
  titleLine: 64,
  // The phone: a plain rounded slab, no notch and no status bar.
  phoneTop: 290,
  phoneBottom: 1330,
  headerH: 118,
  threadTop: 440,
  threadBudget: 760,
  bubbleLine: 54,
  bubblePadY: 22,
  bubbleGap: 22,
  bubbleMaxW: 640,
  // The list: rows of paper cards under a title.
  listBudget: 1100,
  itemLine: 46,
  rowBase: 104,
  rowGap: 20,
} as const;

/** How many lines `text` takes in the box of a WRAP kind (mcp/format_packs.py wrap_lines). */
export function wrapLines(text: string, kind: WrapKind): number {
  const [size, box, upper] = WRAP[kind];
  return wrapCount(upper ? text.toUpperCase() : text, size, box);
}

export function bubbleHeight(text: string): number {
  return wrapLines(text, "bubble") * LAYOUT.bubbleLine + 2 * LAYOUT.bubblePadY;
}

/** The thread's height with every message on screen. */
export function threadHeight(texts: string[]): number {
  return texts.reduce((h, t) => h + bubbleHeight(t), 0) + Math.max(0, texts.length - 1) * LAYOUT.bubbleGap;
}

/** The list's height: its title and every row. */
export function listHeight(title: string, items: { lead: string; text: string }[]): number {
  const t = (title ? wrapLines(title, "title") : 0) * LAYOUT.titleLine + 40;
  return t + items.reduce((h, it) => h + LAYOUT.rowBase + wrapLines(it.text, "item") * LAYOUT.itemLine, 0)
    + Math.max(0, items.length - 1) * LAYOUT.rowGap;
}

/** Characters that read as a verified mark or a tick; never drawn. */
export const TICKS = ["✓", "✔", "☑", "✅", "\u{1F5F8}", "☑️", "✔️"] as const;

/** Messaging and social apps, never named in a header (whole words; "X" only
 *  in capitals). */
export const APPS = [
  "WhatsApp", "iMessage", "Messenger", "Instagram", "TikTok", "X", "Twitter", "Facebook", "Telegram", "Signal",
  "Snapchat",
] as const;

/** A phone number from the ranges set aside for fiction: the UK's 07700 900000
 *  to 900999 and North America's 555-0100 to 555-0199. */
export function isFictionNumber(raw: string): boolean {
  const n = raw.replace(/[\s().\-/\u2010-\u2015]/g, "");
  return /^(?:\+44|0044|0)7700900\d{3}$/.test(n) || /^(?:\+?1)?(?:\d{3})?55501\d{2}$/.test(n);
}

export type ChatMessage = { at: number; from: "them" | "me"; text: string };
export type ChatMark = { at: number; message: number; match: string; kind: "underline" | "ring"; label?: string };
export type ChatData = {
  format: "chat";
  title?: string;
  contact: { name: string; number?: string };
  messages: ChatMessage[];
  marks?: ChatMark[];
};
export type ListData = { format: "list"; title: string; items: { at: number; lead: string; text: string }[] };
export type QuizData = {
  format: "quiz";
  question: string;
  options: { at: number; text: string }[];
  answer: number;
  lockAt: number;
};
export type StrapData = {
  format: "strap";
  kicker: string;
  headline: string;
  date: string;
  source?: string;
  marks?: { at: number; match: string }[];
  flap?: { label: string; from: string; to: string; at: number };
};
export type FormatPacksData = ChatData | ListData | QuizData | StrapData;

/** Every frame something new happens in a format, in order: the moments the
 *  stillness rule and the text audit count. */
export function changeFrames(data: FormatPacksData, start: number): number[] {
  const at: number[] = [start];
  if (data.format === "chat") {
    data.messages.forEach((m) => at.push(m.at));
    (data.marks ?? []).forEach((m) => at.push(m.at));
  } else if (data.format === "list") {
    data.items.forEach((it) => at.push(it.at));
  } else if (data.format === "quiz") {
    data.options.forEach((o) => at.push(o.at));
    at.push(data.lockAt);
  } else {
    (data.marks ?? []).forEach((m) => at.push(m.at));
    if (data.flap) at.push(data.flap.at);
  }
  return [...new Set(at.filter((f) => Number.isFinite(f)))].sort((a, b) => a - b);
}
