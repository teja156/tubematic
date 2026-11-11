/*
 * The Terminal Doc kit: the helpers every move is built from, the shipped ones
 * and the ones an agent writes for one video. A custom move imports only this
 * file, ./contract, react and remotion (mcp/terminal_doc.py checks it).
 *
 * Everything here is a pure function of its arguments: no clock, no
 * Math.random. Noise comes from `hash`, seeded by the caller, so every render
 * of a video draws the same frames.
 */
import React from "react";
import { Easing } from "remotion";
import { CELL, H, SIZES, W, type Size, type Skin, type Tone } from "./contract";

export { CELL, H, SIZES, W };

// ── skins ────────────────────────────────────────────────────────────────────

export interface SkinTokens {
  name: Skin;
  canvas: string;
  /** The font every stage glyph is drawn in, and the size it is drawn at
   *  relative to its cell size (VT323 is a narrow face, so it is drawn larger
   *  to fill the same cell). */
  font: string;
  fontScale: number;
  weight: number;
  tones: Record<Tone, string>;
  /** The colour a glyph of noise is drawn in. */
  noise: string;
  /** Hairlines: brackets, box corners, rules. */
  line: string;
  /** A soft bloom on every glyph (the phosphor), or "" for none. */
  bloom: string;
}

export const MONO = "'IBM Plex Mono', 'JetBrains Mono', Menlo, Consolas, monospace";
export const PIXEL = "VT323, 'IBM Plex Mono', monospace";

export const SKIN_TOKENS: Record<Skin, SkinTokens> = {
  house: {
    name: "house",
    canvas: "#0c0c0c",
    font: MONO,
    fontScale: 1,
    weight: 700,
    tones: { white: "#f1f1f1", grey: "#8c8c8c", dim: "#555555", red: "#ff2a2a", blue: "#3a8cff" },
    noise: "#6a6a6a",
    line: "#9a9a9a",
    bloom: "",
  },
  crt: {
    name: "crt",
    canvas: "#090604",
    font: PIXEL,
    fontScale: 1.36,
    weight: 400,
    tones: { white: "#ffb000", grey: "#b07a10", dim: "#6a4a10", red: "#ff5a2a", blue: "#ffe7a8" },
    noise: "#7a5410",
    line: "#b07a10",
    bloom: "0 0 6px rgba(255,176,0,0.45)",
  },
};

export const skinTokens = (skin: Skin | undefined): SkinTokens => SKIN_TOKENS[skin === "crt" ? "crt" : "house"];

// ── numbers and easing ───────────────────────────────────────────────────────

export const clamp01 = (v: number) => (v < 0 ? 0 : v > 1 ? 1 : v);
export const lerp = (a: number, b: number, p: number) => a + (b - a) * p;
/** A quadratic Bezier at p: a start, a control point and an end. */
export const quad = (p: number, a: number, c: number, b: number) => (1 - p) * (1 - p) * a + 2 * (1 - p) * p * c + p * p * b;

export const ease = {
  out: Easing.bezier(0.16, 1, 0.3, 1),
  in: Easing.bezier(0.32, 0, 0.67, 0),
  /** The slow ease-in-out every letter flight uses. */
  arc: Easing.bezier(0.65, 0, 0.35, 1),
  land: Easing.bezier(0.3, 0, 0.2, 1),
};

/** 0..1 between frames `from` and `to`, clamped, eased. */
export const tween = (frame: number, from: number, to: number, fn: (t: number) => number = ease.out) =>
  to <= from ? (frame >= to ? 1 : 0) : fn(clamp01((frame - from) / (to - from)));

/** A deterministic number in [0, 1) from up to three integers. */
export const hash = (a: number, b = 0, c = 0): number => {
  let h = (Math.imul(a | 0, 374761393) ^ Math.imul(b | 0, 668265263) ^ Math.imul(c | 0, 1274126177)) >>> 0;
  h = Math.imul(h ^ (h >>> 15), 2246822519) >>> 0;
  h = Math.imul(h ^ (h >>> 13), 3266489917) >>> 0;
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
};

/** A seed from a string (an element id), so two elements never share noise. */
export const seedOf = (s: string): number => {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return h >>> 0;
};

export const NOISE = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789#%&*+=<>/?$@";

/** One glyph of noise that changes every `every` frames. */
export const noiseGlyph = (seed: number, frame: number, every = 2): string =>
  NOISE[Math.floor(hash(seed, Math.floor(frame / every), 7) * NOISE.length)];

/**
 * A scramble reveal at a local frame t: characters appear left to right, show
 * noise, then lock left to right within `frames`. Spaces stay spaces.
 */
export const scramble = (text: string, t: number, frames: number, seed: number): string => {
  if (t < 0) return "";
  let s = "";
  for (let i = 0; i < text.length; i++) {
    if (t < i * 0.35) break;
    const lock = frames * 0.45 + (i / Math.max(1, text.length)) * frames * 0.55;
    s += text[i] === " " || t >= lock ? text[i] : noiseGlyph(seed * 97 + i, t, 1);
  }
  return s;
};

/** The typed prefix of a text at a local frame t, `rate` characters a frame. */
export const typed = (text: string, t: number, rate: number) => text.slice(0, Math.max(0, Math.floor(t * rate)));

/** The caret blinks on half a second, off half a second. */
export const caretOn = (frame: number) => Math.floor(frame / 15) % 2 === 0;

const rgba = (hex: string, a: number) => {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
};

/** The glow on the one emphasised element: two soft text-shadow layers. */
export const glowShadow = (hex: string, k = 1): string =>
  k <= 0.01 ? "none" : `0 0 ${8 * k}px ${rgba(hex, Math.min(1, 0.85 * k))}, 0 0 ${24 * k}px ${rgba(hex, Math.min(1, 0.45 * k))}`;

// ── glyphs ───────────────────────────────────────────────────────────────────

export const cellOf = (size: Size | number) => (typeof size === "number" ? size : SIZES[size]) * CELL;

/** The x of cell i's centre in a centred row of n cells at a size. */
export const cellX = (i: number, n: number, size: Size | number) => W / 2 + (i - (n - 1) / 2) * cellOf(size);

export interface GlyphProps {
  x: number;
  y: number;
  size: number;
  ch: string;
  color: string;
  skin: SkinTokens;
  opacity?: number;
  shadow?: string;
}

/** One glyph centred on (x, y), in its cell. */
export const Glyph: React.FC<GlyphProps> = ({ x, y, size, ch, color, skin, opacity = 1, shadow }) => {
  if (!ch || ch === " " || opacity <= 0.001) return null;
  const fs = size * skin.fontScale;
  return (
    <div
      style={{
        position: "absolute",
        left: x - size * CELL * 0.5,
        top: y - fs * 0.6,
        width: size * CELL,
        height: fs * 1.2,
        fontFamily: skin.font,
        fontSize: fs,
        lineHeight: `${fs * 1.2}px`,
        fontWeight: skin.weight,
        textAlign: "center",
        color,
        opacity,
        textShadow: shadow && shadow !== "none" ? shadow : skin.bloom || undefined,
        whiteSpace: "pre",
      }}
    >
      {ch}
    </div>
  );
};

export interface RowProps {
  text: string;
  y: number;
  size: number;
  color: string;
  skin: SkinTokens;
  opacity?: number;
  shadow?: string;
  /** Characters [from, to) drawn in another colour and shadow. */
  span?: { from: number; to: number; color: string; shadow?: string };
  /** The cells the row is laid out for; defaults to the text's length, so a
   *  row being typed keeps its final position. */
  cells?: number;
  /** Horizontal centre; defaults to the frame's. */
  cx?: number;
}

/**
 * A row of glyphs centred on y, one cell per character. One element with
 * fixed-width spans, cheaper than a div per glyph when nothing moves.
 */
export const Row: React.FC<RowProps> = ({ text, y, size, color, skin, opacity = 1, shadow, span, cells, cx = W / 2 }) => {
  if (!text || opacity <= 0.001) return null;
  const n = cells ?? text.length;
  const cw = size * CELL;
  const fs = size * skin.fontScale;
  return (
    <div
      style={{
        position: "absolute",
        left: cx - (n * cw) / 2,
        top: y - fs * 0.6,
        height: fs * 1.2,
        fontFamily: skin.font,
        fontSize: fs,
        lineHeight: `${fs * 1.2}px`,
        fontWeight: skin.weight,
        color,
        opacity,
        whiteSpace: "pre",
        textShadow: shadow && shadow !== "none" ? shadow : skin.bloom || undefined,
      }}
    >
      {Array.from(text).map((ch, i) => {
        const inSpan = span && i >= span.from && i < span.to;
        return (
          <span
            key={i}
            style={{
              display: "inline-block",
              width: cw,
              textAlign: "center",
              ...(inSpan ? { color: span.color, textShadow: span.shadow && span.shadow !== "none" ? span.shadow : undefined } : {}),
            }}
          >
            {ch}
          </span>
        );
      })}
    </div>
  );
};

/** What a custom move is given. It draws inside `box` and never reads the
 *  frame itself: `t` is its own frame, from 0 at its event to `frames`. */
export interface MoveProps {
  t: number;
  frames: number;
  text: string;
  box: { x: number; y: number; w: number; h: number };
  skin: SkinTokens;
  /** A seed for `hash` and `noiseGlyph`, fixed for this element. */
  seed: number;
}
