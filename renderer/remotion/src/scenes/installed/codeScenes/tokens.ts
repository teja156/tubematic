/*
 * Syntax colouring for Code Scenes: Shiki's synchronous core with its
 * JavaScript regex engine, so tokenising runs inside a frame's render with
 * nothing async and no WASM. Only the languages in contract.ts LANGS are
 * loaded (each grammar is bundled).
 *
 * Shiki merges neighbouring characters of one colour into one token ("(row)").
 * The morph needs finer pieces, so each Shiki token is split again into words,
 * numbers, single punctuation marks and whitespace, each keeping its colour.
 */
import { createHighlighterCoreSync, type HighlighterCore, type ThemeRegistrationAny } from "shiki/core";
import { createJavaScriptRegexEngine } from "shiki/engine/javascript";
import c from "@shikijs/langs/c";
import css from "@shikijs/langs/css";
import go from "@shikijs/langs/go";
import html from "@shikijs/langs/html";
import java from "@shikijs/langs/java";
import javascript from "@shikijs/langs/javascript";
import json from "@shikijs/langs/json";
import python from "@shikijs/langs/python";
import rust from "@shikijs/langs/rust";
import sql from "@shikijs/langs/sql";
import typescript from "@shikijs/langs/typescript";
import yaml from "@shikijs/langs/yaml";
import githubLight from "@shikijs/themes/github-light";
import type { Lang } from "./contract";

/** The two looks: the house dark card, and a light card for a light video. */
export const PALETTES = {
  dark: {
    canvas: "#131512",
    card: "#262034",
    chrome: "#1D1829",
    pane: "#1B1725",
    text: "#ECE7F5",
    muted: "#8E87A0",
    lineNo: "#5E5870",
    focusBar: "rgba(255,255,255,0.07)",
    focusEdge: "#6DAED8",
    accent: "#F15471",
    error: "#D02037",
    errorText: "#FF8597",
    calloutBg: "rgba(208,32,55,0.16)",
    track: "#2E2A38",
    fill: "#ECE7F5",
    dots: ["#E0605A", "#D9A23E", "#4FAE5D"],
    shadow: "0 18px 50px rgba(0,0,0,0.45)",
  },
  light: {
    canvas: "#F8FAFC",
    card: "#FFFFFF",
    chrome: "#F1F3F6",
    pane: "#F6F8FA",
    text: "#24292E",
    muted: "#6A737D",
    lineNo: "#A0A8B2",
    focusBar: "rgba(3,102,214,0.08)",
    focusEdge: "#0366D6",
    accent: "#D73A49",
    error: "#CB2431",
    errorText: "#B31D28",
    calloutBg: "rgba(203,36,49,0.08)",
    track: "#DDE2E8",
    fill: "#24292E",
    dots: ["#E0605A", "#D9A23E", "#4FAE5D"],
    shadow: "0 14px 40px rgba(20,30,50,0.14)",
  },
} as const;
export type Palette = keyof typeof PALETTES;

const HOUSE_DARK: ThemeRegistrationAny = {
  name: "tubematic-code-dark",
  type: "dark",
  fg: PALETTES.dark.text,
  bg: PALETTES.dark.card,
  tokenColors: [
    { settings: { foreground: PALETTES.dark.text } },
    { scope: ["comment", "punctuation.definition.comment"], settings: { foreground: "#6E6884" } },
    { scope: ["keyword", "storage", "storage.type", "keyword.operator.new", "keyword.control", "variable.language"],
      settings: { foreground: "#F15471" } },
    { scope: ["string", "string.quoted", "string.template", "markup.inline.raw"], settings: { foreground: "#E5C07B" } },
    { scope: ["constant.numeric", "constant.language", "constant.character", "support.constant"],
      settings: { foreground: "#C7A3F5" } },
    { scope: ["entity.name.function", "support.function", "meta.function-call", "entity.name.tag"],
      settings: { foreground: "#6DAED8" } },
    { scope: ["entity.name.type", "entity.name.class", "support.type", "support.class", "entity.other.attribute-name"],
      settings: { foreground: "#7FD1B9" } },
    { scope: ["keyword.operator", "punctuation"], settings: { foreground: "#9A93AB" } },
    { scope: ["constant.character.format.placeholder", "punctuation.definition.template-expression", "meta.fstring"],
      settings: { foreground: "#F15471" } },
  ],
};

let highlighter: HighlighterCore | null = null;
function shiki(): HighlighterCore {
  if (!highlighter) {
    highlighter = createHighlighterCoreSync({
      themes: [HOUSE_DARK, githubLight],
      langs: [c, css, go, html, java, javascript, json, python, rust, sql, typescript, yaml],
      engine: createJavaScriptRegexEngine(),
    });
  }
  return highlighter;
}

/** One piece of code on the card: its text, colour and grid position. */
export type Piece = { text: string; color: string; row: number; col: number };

const SPLIT = /\s+|[A-Za-z_$][\w$]*|\d[\w.]*|[^\sA-Za-z_$\d]/g;

/** Every visible piece of `code`, in reading order (whitespace dropped, its
 *  width kept in the columns). */
export function tokenize(code: string, lang: Lang, palette: Palette): Piece[] {
  const theme = palette === "light" ? githubLight.name! : HOUSE_DARK.name!;
  let lines: { content: string; color?: string }[][];
  try {
    lines = shiki().codeToTokensBase(code, { lang, theme });
  } catch {
    // An unexpected grammar failure shows plain text rather than no code.
    lines = code.split("\n").map((l) => [{ content: l }]);
  }
  const fallback = PALETTES[palette].text;
  const out: Piece[] = [];
  lines.forEach((line, row) => {
    let col = 0;
    for (const tok of line) {
      for (const m of tok.content.matchAll(SPLIT)) {
        const text = m[0];
        if (!/^\s+$/.test(text)) out.push({ text, color: tok.color ?? fallback, row, col });
        col += text.length;
      }
    }
  });
  return out;
}
