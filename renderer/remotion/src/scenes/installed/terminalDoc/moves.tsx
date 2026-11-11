/*
 * The shipped Terminal Doc moves: one renderer per element type. Each draws
 * its element at a frame from the element's own event; nothing here keeps
 * state between frames.
 *
 * Render cost: no SVG filter, gradient or stroke-dasharray, no CSS transform
 * on a big layer, glow only as a text-shadow on the one glowing element.
 * Every move settles: after its frames it draws its final text as one Row,
 * and a held frame repaints nothing.
 */
import React from "react";
import { interpolateColors } from "remotion";
import { LIMITS, SIZES, SLOTS, TIMING, W, numberCells, wrapNote, type TDCustomMove } from "./contract";
import {
  CELL, Glyph, Row, caretOn, cellX, clamp01, ease, glowShadow, lerp, noiseGlyph, quad, scramble, seedOf, typed, tween,
  type MoveProps, type SkinTokens,
} from "./kit";
import { DEFAULT_TONE, elementFrames, finalText, glowOn, sizeOf, slotOf, type ElState, type GlowEvent } from "./stage";

export interface Cam {
  s: number;
  X: (x: number) => number;
  Y: (y: number) => number;
}

export const identityCam: Cam = { s: 1, X: (x) => x, Y: (y) => y };

/** The push-in: positions and sizes scale about the stage centre. */
export const camFor = (s: number): Cam =>
  s === 1 ? identityCam : { s, X: (x) => W / 2 + (x - W / 2) * s, Y: (y) => SLOTS.stage.y + (y - SLOTS.stage.y) * s };

export interface MoveContext {
  frame: number;
  skin: SkinTokens;
  glows: GlowEvent[];
  cam: Cam;
  custom: Record<string, TDCustomMove>;
  customDraw: Record<string, React.FC<MoveProps>>;
}

const toneOf = (el: ElState, skin: SkinTokens) => {
  const e = el.ev as { tone?: keyof SkinTokens["tones"] };
  return skin.tones[e.tone ?? DEFAULT_TONE[el.ev.type] ?? "white"];
};

/** The glow on an element: the colour and shadow its glowing part takes. */
function glowStyle(el: ElState, ctx: MoveContext, base: string) {
  const { k, ev } = glowOn(ctx.glows, el.id, ctx.frame);
  if (!ev || k <= 0) return null;
  const hex = ctx.skin.tones[ev.tone];
  return { color: interpolateColors(k, [0, 1], [base, hex]), shadow: glowShadow(hex, k), ev };
}

/** A settled single-line element: its text in one Row, with any glow. */
const SettledRow: React.FC<{ el: ElState; ctx: MoveContext; text: string; y: number; size: number; cells?: number; opacity: number; accent?: string }> = ({
  el, ctx, text, y, size, cells, opacity, accent,
}) => {
  const base = toneOf(el, ctx.skin);
  const g = glowStyle(el, ctx, base);
  let span: { from: number; to: number; color: string; shadow?: string } | undefined;
  let color = base;
  let shadow: string | undefined;
  if (g?.ev.span) span = { from: g.ev.span[0], to: g.ev.span[1], color: g.color, shadow: g.shadow };
  else if (g) {
    color = g.color;
    shadow = g.shadow;
  }
  if (!span && accent) {
    const i = text.indexOf(accent);
    if (i >= 0) span = { from: i, to: i + accent.length, color: ctx.skin.tones.red };
  }
  return <Row text={text} y={ctx.cam.Y(y)} size={size * ctx.cam.s} cx={ctx.cam.X(W / 2)} cells={cells} color={color} skin={ctx.skin} opacity={opacity} shadow={shadow} span={span} />;
};

// ── word ─────────────────────────────────────────────────────────────────────

const WordView: React.FC<{ el: ElState; ctx: MoveContext; opacity: number }> = ({ el, ctx, opacity }) => {
  const e = el.ev as Extract<ElState["ev"], { type: "word" }>;
  const size = SIZES[sizeOf(e)];
  const y = SLOTS[e.slot].y;
  const t = ctx.frame - e.at;
  const reveal = e.reveal ?? "scramble";
  if (reveal === "cut" || (reveal === "scramble" && t >= TIMING.reveal)) {
    return <SettledRow el={el} ctx={ctx} text={e.text} y={y} size={size} opacity={opacity} accent={e.accent} />;
  }
  if (reveal === "scramble") {
    return <Row text={scramble(e.text, t, TIMING.reveal, seedOf(e.id))} cells={e.text.length} y={ctx.cam.Y(y)} size={size * ctx.cam.s} cx={ctx.cam.X(W / 2)} color={toneOf(el, ctx.skin)} skin={ctx.skin} opacity={opacity} />;
  }
  const shown = typed(e.text, t, TIMING.typeRate);
  const done = shown.length >= e.text.length;
  if (done && !caretOn(ctx.frame)) return <SettledRow el={el} ctx={ctx} text={e.text} y={y} size={size} opacity={opacity} accent={e.accent} />;
  const caretUntil = e.at + Math.ceil(e.text.length / TIMING.typeRate) + 20;
  return (
    <>
      <SettledRow el={el} ctx={ctx} text={shown} cells={e.text.length} y={y} size={size} opacity={opacity} accent={done ? e.accent : undefined} />
      {ctx.frame < caretUntil && (!done || caretOn(ctx.frame)) && (
        <Caret x={ctx.cam.X(cellX(Math.min(shown.length, e.text.length - 1), e.text.length, size) + (done ? size * CELL : 0))} y={ctx.cam.Y(y)} size={size * ctx.cam.s} color={toneOf(el, ctx.skin)} />
      )}
    </>
  );
};

const Caret: React.FC<{ x: number; y: number; size: number; color: string }> = ({ x, y, size, color }) => (
  <div style={{ position: "absolute", left: x - size * CELL * 0.31, top: y - size * 0.42, width: size * CELL * 0.62, height: size * 0.84, background: color, opacity: 0.8 }} />
);

// ── rearrange ────────────────────────────────────────────────────────────────

/** Which source letter flies to each target letter: same character, nearest
 *  cell first; -1 where the target letter comes out of noise. */
export function letterMap(from: string, to: string): number[] {
  const used = new Set<number>();
  return Array.from(to).map((ch, j) => {
    if (ch === " ") return -1;
    let best = -1, bestD = Infinity;
    for (let i = 0; i < from.length; i++) {
      if (used.has(i) || from[i] !== ch) continue;
      const d = Math.abs(i / Math.max(1, from.length) - j / Math.max(1, to.length));
      if (d < bestD) {
        best = i;
        bestD = d;
      }
    }
    if (best >= 0) used.add(best);
    return best;
  });
}

const RearrangeView: React.FC<{ el: ElState; ctx: MoveContext; opacity: number }> = ({ el, ctx, opacity }) => {
  const e = el.ev as Extract<ElState["ev"], { type: "rearrange" }>;
  const t = ctx.frame - e.at;
  const dur = elementFrames(el, ctx.custom);
  const slot = slotOf(el);
  const size1 = SIZES[sizeOf(e)];
  const y1 = SLOTS[slot].y;
  if (t >= dur || !el.from) return <SettledRow el={el} ctx={ctx} text={e.text} y={y1} size={size1} opacity={opacity} />;
  const src = finalText(el.from.ev);
  const size0 = SIZES[sizeOf(el.from.ev)];
  const y0 = SLOTS[slotOf(el.from)].y;
  const map = letterMap(src, e.text);
  const usedSrc = new Set(map.filter((i) => i >= 0));
  const color = toneOf(el, ctx.skin);
  const { cam, skin } = ctx;
  const out: React.ReactNode[] = [];
  let order = 0;
  map.forEach((i, j) => {
    if (e.text[j] === " ") return;
    const s = order++ * TIMING.stagger;
    const p = ease.arc(clamp01((t - s) / TIMING.arc));
    const x1 = cellX(j, e.text.length, size1);
    if (i >= 0) {
      const x0 = cellX(i, src.length, size0);
      const lift = Math.min(y0, y1) - 0.9 * Math.max(size0, size1);
      out.push(<Glyph key={`m${j}`} x={cam.X(quad(p, x0, (x0 + x1) / 2, x1))} y={cam.Y(quad(p, y0, lift, y1))} size={lerp(size0, size1, p) * cam.s} ch={e.text[j]} color={color} skin={skin} opacity={opacity} />);
    } else if (t >= s) {
      out.push(<Glyph key={`n${j}`} x={cam.X(x1)} y={cam.Y(y1)} size={size1 * cam.s} ch={p < 0.6 ? noiseGlyph(seedOf(e.id) + j, t, 1) : e.text[j]} color={p < 0.6 ? skin.noise : color} skin={skin} opacity={opacity * clamp01(p * 3)} />);
    }
  });
  Array.from(src).forEach((ch, i) => {
    if (ch === " " || usedSrc.has(i)) return;
    const p = clamp01(t / TIMING.arc);
    out.push(<Glyph key={`o${i}`} x={cam.X(cellX(i, src.length, size0))} y={cam.Y(y0 + 30 * p)} size={size0 * cam.s} ch={ch} color={skin.tones.dim} skin={skin} opacity={opacity * (1 - p)} />);
  });
  return <>{out}</>;
};

// ── encode ───────────────────────────────────────────────────────────────────

const BOX = { w: 230, h: 150, corner: 40 };

const EncodeView: React.FC<{ el: ElState; ctx: MoveContext; opacity: number }> = ({ el, ctx, opacity }) => {
  const e = el.ev as Extract<ElState["ev"], { type: "encode" }>;
  const t = ctx.frame - e.at;
  const dur = elementFrames(el, ctx.custom);
  const size1 = SIZES[sizeOf(e)];
  const y1 = SLOTS[e.slot].y;
  const { cam, skin } = ctx;
  const boxY = SLOTS.b.y;
  const boxOp = opacity * (t < dur ? tween(t, 0, 8) : 1 - clamp01((t - dur) / 8));
  const nodes: React.ReactNode[] = [];
  if (boxOp > 0) nodes.push(<EncodeBox key="box" ctx={ctx} y={boxY} label={e.label} sub={e.sub} t={t} opacity={boxOp} lit={t < dur - TIMING.encodeOut * 0.4} />);
  if (t >= dur || !el.from) {
    nodes.push(<SettledRow key="out" el={el} ctx={ctx} text={e.text} y={y1} size={size1} opacity={opacity} />);
    return <>{nodes}</>;
  }
  const src = finalText(el.from.ev);
  const size0 = SIZES[sizeOf(el.from.ev)];
  const y0 = SLOTS[slotOf(el.from)].y;
  const inner = Math.min(46, size0, size1);
  const srcIdx = Array.from(src).map((c, i) => (c === " " ? -1 : i)).filter((i) => i >= 0);
  const holdEnd = TIMING.stagger * (srcIdx.length - 1) + TIMING.arc + TIMING.encodeHold;
  const color = toneOf(el, ctx.skin);
  srcIdx.forEach((i, n) => {
    const s = n * TIMING.stagger;
    if (t >= holdEnd) return;
    const x0 = cellX(i, src.length, size0);
    const side = n % 2 ? 1 : -1;
    if (t < s + TIMING.arc) {
      const p = ease.arc(clamp01((t - s) / TIMING.arc));
      const xm = W / 2 + side * 10;
      nodes.push(<Glyph key={`i${i}`} x={cam.X(quad(p, x0, (x0 + xm) / 2, xm))} y={cam.Y(quad(p, y0, Math.min(y0, boxY) - 120, boxY))} size={lerp(size0, inner, p) * cam.s} ch={p < 0.5 ? src[i] : noiseGlyph(seedOf(e.id) + i, t, 1)} color={color} skin={skin} opacity={opacity} />);
    } else {
      nodes.push(<Glyph key={`i${i}`} x={cam.X(W / 2 + side * (10 + 5 * Math.sin(t * 1.7 + i)))} y={cam.Y(boxY + side * 7)} size={inner * cam.s} ch={noiseGlyph(seedOf(e.id) + i * 3, t, 1)} color={skin.tones.blue} skin={skin} opacity={opacity} />);
    }
  });
  const outIdx = Array.from(e.text).map((c, j) => (c === " " ? -1 : j)).filter((j) => j >= 0);
  outIdx.forEach((j, k) => {
    const s = holdEnd + (k / Math.max(1, outIdx.length)) * TIMING.encodeOut * 0.4;
    if (t < s) return;
    const p = ease.land(clamp01((t - s) / (TIMING.encodeOut * 0.6)));
    const x1 = cellX(j, e.text.length, size1);
    nodes.push(<Glyph key={`o${j}`} x={cam.X(quad(p, W / 2, x1, x1))} y={cam.Y(quad(p, boxY, (boxY + y1) / 2, y1))} size={lerp(inner, size1, p) * cam.s} ch={p < 0.62 ? noiseGlyph(seedOf(e.id) + 50 + j, t, 2) : e.text[j]} color={color} skin={skin} opacity={opacity} />);
  });
  return <>{nodes}</>;
};

const EncodeBox: React.FC<{ ctx: MoveContext; y: number; label: string; sub?: string; t: number; opacity: number; lit: boolean }> = ({ ctx, y, label, sub, t, opacity, lit }) => {
  const { cam, skin } = ctx;
  const w = BOX.w * cam.s, h = BOX.h * cam.s, L = BOX.corner * cam.s;
  const cx = cam.X(W / 2), cy = cam.Y(y);
  const x0 = cx - w / 2, x1 = cx + w / 2, y0 = cy - h / 2, y2 = cy + h / 2;
  const d = `M ${x0} ${y0 + L} V ${y0} H ${x0 + L} M ${x1 - L} ${y0} H ${x1} V ${y0 + L} M ${x1} ${y2 - L} V ${y2} H ${x1 - L} M ${x0 + L} ${y2} H ${x0} V ${y2 - L}`;
  const lx = x1 + 30 * cam.s;
  const ls = SIZES.s * cam.s;
  return (
    <>
      <svg width={W} height={1920} style={{ position: "absolute", left: 0, top: 0, opacity }}>
        <path d={d} fill="none" stroke={lit ? skin.tones.white : skin.line} strokeWidth={3} />
      </svg>
      <div style={{ position: "absolute", left: lx, top: cy - ls * 1.25, opacity, fontFamily: skin.font, fontWeight: skin.weight, whiteSpace: "pre" }}>
        <div style={{ fontSize: ls * 1.1 * skin.fontScale, lineHeight: `${ls * 1.3}px`, color: skin.tones.white, textShadow: skin.bloom || undefined }}>{scramble(label, t, TIMING.reveal, 3)}</div>
        {sub ? <div style={{ fontSize: ls * skin.fontScale, lineHeight: `${ls * 1.2}px`, color: skin.tones.grey, fontWeight: 400 }}>{scramble(sub, t - 4, TIMING.reveal, 4)}</div> : null}
      </div>
    </>
  );
};

// ── number ───────────────────────────────────────────────────────────────────

const groupLike = (template: string, n: number) => {
  const digits = String(Math.floor(n));
  if (!template.includes(",")) return digits;
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
};

const NumberView: React.FC<{ el: ElState; ctx: MoveContext; opacity: number }> = ({ el, ctx, opacity }) => {
  const e = el.ev as Extract<ElState["ev"], { type: "number" }>;
  const t = ctx.frame - e.at;
  const size = SIZES[sizeOf(e)];
  const y = SLOTS[e.slot].y;
  const { cam, skin } = ctx;
  const color = toneOf(el, skin);
  const dur = elementFrames(el, ctx.custom);
  const caret = e.value.indexOf("^");
  if (e.count) {
    const target = Number(e.value.replace(/,/g, ""));
    const q = t >= dur ? 1 : ease.arc(clamp01(t / e.count));
    const s = groupLike(e.value, target * q).padStart(e.value.length, " ");
    if (t >= dur) return <SettledRow el={el} ctx={ctx} text={e.value} y={y} size={size} opacity={opacity} />;
    return <Row text={s} y={cam.Y(y)} size={size * cam.s} cx={cam.X(W / 2)} color={color} skin={skin} opacity={opacity} />;
  }
  if (t >= dur + 10 && caret < 0) return <SettledRow el={el} ctx={ctx} text={e.value} y={y} size={size} opacity={opacity} />;
  // Glyph by glyph: noise first, then each locks right to left with a flash.
  const cells = numberCells(e.value);
  const g = glowStyle(el, ctx, color);
  const chars = Array.from(e.value);
  const lockable = chars.map((c, i) => (c === " " || c === "^" ? -1 : i)).filter((i) => i >= 0);
  let xCell = 0;
  const nodes: React.ReactNode[] = [];
  chars.forEach((ch, i) => {
    if (ch === "^") return;
    const sup = caret >= 0 && i > caret;
    const sz = sup ? size / 2 : size;
    const cx = W / 2 - (cells * size * CELL) / 2 + xCell + (sz * CELL) / 2;
    xCell += sz * CELL;
    if (ch === " ") return;
    const rank = lockable.length - 1 - lockable.indexOf(i);
    const lock = TIMING.lockStart + rank * TIMING.lockStep;
    const appear = clamp01((t - i * 0.4) / 3);
    const locked = t >= lock;
    const flash = clamp01(1 - (t - lock) / 10);
    // A glow with a span lights only its characters, as the settled row does.
    const lit = g && (!g.ev.span || (i >= g.ev.span[0] && i < g.ev.span[1]));
    const c = locked ? (lit ? g.color : interpolateColors(flash, [0, 1], [color, skin.tones.white])) : skin.noise;
    nodes.push(
      <Glyph key={i} x={cam.X(cx)} y={cam.Y(sup ? y - size * 0.36 : y)} size={sz * cam.s} ch={locked ? ch : noiseGlyph(seedOf(e.id) + i, t, 2)} color={c} skin={skin} opacity={opacity * appear} shadow={locked && lit ? g.shadow : undefined} />,
    );
  });
  return <>{nodes}</>;
};

// ── grid ─────────────────────────────────────────────────────────────────────

export const gridLayout = (rows: number, size: number) => {
  const lh = size * 1.3;
  const top = SLOTS.stage.y - (rows * lh) / 2 + lh / 2;
  return { lh, top };
};

const GridView: React.FC<{ el: ElState; ctx: MoveContext; opacity: number }> = ({ el, ctx, opacity }) => {
  const e = el.ev as Extract<ElState["ev"], { type: "grid" }>;
  const t = ctx.frame - e.at;
  const size = SIZES[sizeOf(e)];
  const { lh, top } = gridLayout(e.rows.length, size);
  const base = toneOf(el, ctx.skin);
  const g = glowStyle(el, ctx, base);
  return (
    <>
      {e.rows.map((row, r) => {
        const rt = t - r * TIMING.rowStep;
        if (rt < 0) return null;
        const lit = g && (g.ev.row === undefined || g.ev.row === r);
        const text = rt >= TIMING.reveal ? row : scramble(row, rt, TIMING.reveal, seedOf(e.id) + r);
        const span = lit && g.ev.span ? { from: g.ev.span[0], to: g.ev.span[1], color: g.color, shadow: g.shadow } : undefined;
        return (
          <Row key={r} text={text} cells={row.length} y={ctx.cam.Y(top + r * lh)} size={size * ctx.cam.s} cx={ctx.cam.X(W / 2)}
            color={lit && !span ? g.color : base} shadow={lit && !span ? g.shadow : undefined} span={span} skin={ctx.skin} opacity={opacity} />
        );
      })}
    </>
  );
};

// ── stream ───────────────────────────────────────────────────────────────────

const StreamView: React.FC<{ el: ElState; ctx: MoveContext; opacity: number }> = ({ el, ctx, opacity }) => {
  const e = el.ev as Extract<ElState["ev"], { type: "stream" }>;
  const t = ctx.frame - e.at;
  const size = SIZES[sizeOf(e)];
  const y = SLOTS[e.slot].y;
  const { cam, skin } = ctx;
  if (t >= e.frames) {
    const lockedEl = { ...el, ev: { ...e, tone: (e as { tone?: string }).tone ?? "red" } } as ElState;
    return <SettledRow el={lockedEl} ctx={ctx} text={e.target} y={y} size={size} opacity={opacity} />;
  }
  const list = [...e.guesses, e.target];
  const s = (list.length - 1) * ease.out(clamp01(t / e.frames));
  const rows: React.ReactNode[] = [];
  for (let k = Math.max(0, Math.floor(s) - 1); k <= Math.min(list.length - 1, Math.floor(s) + 2); k++) {
    const d = k - s;
    const op = d < 0 ? clamp01(1 + d / 0.6) : d < 1 ? lerp(1, 0.4, d) : lerp(0.4, 0.12, d - 1);
    const yy = y + d * size * 0.95;
    if (Math.abs(yy - y) > (SLOTS[e.slot].bottom - SLOTS[e.slot].top) / 2) continue;
    const cur = Math.abs(d) < 0.5;
    rows.push(<Row key={k} text={list[k]} y={cam.Y(yy)} size={size * cam.s} cx={cam.X(W / 2)} color={cur ? skin.tones.white : skin.tones.grey} skin={skin} opacity={opacity * op} />);
  }
  return <>{rows}</>;
};

// ── type ─────────────────────────────────────────────────────────────────────

/** A typed block's width in pixels: the command (prompt included) at its size, the output at size s. */
export const typeWidthPx = (cmdCells: number, size: number, outs: string[]) =>
  Math.max(cmdCells * size * CELL, ...outs.map((o) => o.length * SIZES.s * CELL));

export const typeLayout = (size: number, outputs: number, slotY: number) => {
  const outLh = SIZES.s * 1.2;
  const h = size * 1.2 + outputs * outLh;
  const cmdY = slotY - h / 2 + (size * 1.2) / 2;
  return { cmdY, outY: (k: number) => cmdY + (size * 1.2) / 2 + outLh * (k + 0.5) };
};

const TypeView: React.FC<{ el: ElState; ctx: MoveContext; opacity: number }> = ({ el, ctx, opacity }) => {
  const e = el.ev as Extract<ElState["ev"], { type: "type" }>;
  const t = ctx.frame - e.at;
  const size = SIZES[sizeOf(e)];
  const outs = e.output ?? [];
  const { cmdY, outY } = typeLayout(size, outs.length, SLOTS[e.slot].y);
  const { cam, skin } = ctx;
  const line = `$ ${e.text}`;
  const shown = `$ ${typed(e.text, t, TIMING.typeRate)}`;
  const done = shown.length >= line.length;
  const typedEnd = Math.ceil(e.text.length / TIMING.typeRate);
  // The block is centred by its widest line in pixels: the command is drawn at
  // its own size, the output at size s.
  const left = W / 2 - typeWidthPx(line.length, size, outs) / 2;
  const cmdCx = left + (line.length * size * CELL) / 2;
  const nodes: React.ReactNode[] = [];
  nodes.push(<Row key="cmd" text={done ? line : shown} cells={line.length} y={cam.Y(cmdY)} size={size * cam.s} cx={cam.X(cmdCx)} color={toneOf(el, skin)} skin={skin} opacity={opacity} span={{ from: 0, to: 1, color: skin.tones.dim }} />);
  const caretShown = !done || (t < typedEnd + 30 && caretOn(ctx.frame));
  if (caretShown && !outs.length) {
    const cx = cmdCx - (line.length * size * CELL) / 2 + (shown.length + 0.5) * size * CELL;
    nodes.push(<Caret key="caret" x={cam.X(cx)} y={cam.Y(cmdY)} size={size * cam.s} color={toneOf(el, skin)} />);
  }
  outs.forEach((o, k) => {
    const ot = t - typedEnd - k * TIMING.outputStagger;
    if (ot < 0) return;
    const oCx = left + (o.length * SIZES.s * CELL) / 2;
    nodes.push(<Row key={`o${k}`} text={ot >= TIMING.reveal ? o : scramble(o, ot, TIMING.reveal, seedOf(e.id) + k)} cells={o.length} y={cam.Y(outY(k))} size={SIZES.s * cam.s} cx={cam.X(oCx)} color={skin.tones.grey} skin={skin} opacity={opacity} />);
  });
  return <>{nodes}</>;
};

// ── bracket ──────────────────────────────────────────────────────────────────

/** The horizontal extent and bottom edge of an element, for its bracket. */
export function extentOf(el: ElState): { x0: number; x1: number; bottom: number } {
  const e = el.ev;
  const size = SIZES[sizeOf(e)];
  if (e.type === "grid") {
    const { lh, top } = gridLayout(e.rows.length, size);
    const n = Math.max(...e.rows.map((r) => r.length));
    return { x0: W / 2 - (n * size * CELL) / 2, x1: W / 2 + (n * size * CELL) / 2, bottom: top + (e.rows.length - 1) * lh + size * 0.62 };
  }
  if (e.type === "type") {
    const outs = e.output ?? [];
    const { cmdY, outY } = typeLayout(size, outs.length, SLOTS[e.slot].y);
    const width = typeWidthPx(e.text.length + 2, size, outs);
    return { x0: W / 2 - width / 2, x1: W / 2 + width / 2, bottom: outs.length ? outY(outs.length - 1) + SIZES.s * 0.62 : cmdY + size * 0.62 };
  }
  const cells = e.type === "number" ? numberCells(e.value) : finalText(e).length;
  const y = SLOTS[slotOf(el)].y;
  return { x0: W / 2 - (cells * size * CELL) / 2, x1: W / 2 + (cells * size * CELL) / 2, bottom: y + size * 0.62 };
}

// The gap keeps the label almost clear of the font box of the string above
// (ascent plus descent, about 0.64 of its size below the centre line), not only
// of its ink: the text audit measures font boxes and reports a label inside one
// as an overlap. Wider pushes a large string's label into the next band.
export const BRACKET = { gap: 22, label: 32, tick: 16, pad: 12 } as const;

const BracketView: React.FC<{ el: ElState; ctx: MoveContext; opacity: number }> = ({ el, ctx, opacity }) => {
  const b = el.bracket;
  if (!b) return null;
  const t = ctx.frame - b.at;
  if (t < 0) return null;
  const { cam, skin } = ctx;
  const ex = extentOf(el);
  const labelW = b.label.length * BRACKET.label * CELL;
  let x0 = ex.x0 - BRACKET.pad, x1 = ex.x1 + BRACKET.pad;
  if (x1 - x0 < labelW + 120) {
    x0 = W / 2 - labelW / 2 - 60;
    x1 = W / 2 + labelW / 2 + 60;
  }
  const y = ex.bottom + BRACKET.gap;
  const gl = W / 2 - labelW / 2 - 14, gr = W / 2 + labelW / 2 + 14;
  const p = tween(t, 0, TIMING.bracketDraw * 0.8);
  const tick = tween(t, TIMING.bracketDraw * 0.5, TIMING.bracketDraw);
  const tone = skin.tones[b.tone ?? "red"];
  const X = cam.X, Y = cam.Y;
  // The citation wraps with its note, as the validator wraps it. The note is
  // an annotation under the stage and does not move with a push.
  const cite = b.cite ? `[${b.cite}]` : "";
  const lines = b.note ? wrapNote(cite ? `${b.note} ${cite}` : b.note) : [];
  const noteT = t - TIMING.bracketDraw;
  return (
    <>
      <svg width={W} height={1920} style={{ position: "absolute", left: 0, top: 0, opacity }}>
        <line x1={X(gl)} y1={Y(y)} x2={X(lerp(gl, x0, p))} y2={Y(y)} stroke={tone} strokeWidth={2} />
        <line x1={X(gr)} y1={Y(y)} x2={X(lerp(gr, x1, p))} y2={Y(y)} stroke={tone} strokeWidth={2} />
        {tick > 0 && <line x1={X(x0)} y1={Y(y)} x2={X(x0)} y2={Y(y - BRACKET.tick * tick)} stroke={tone} strokeWidth={2} />}
        {tick > 0 && <line x1={X(x1)} y1={Y(y)} x2={X(x1)} y2={Y(y - BRACKET.tick * tick)} stroke={tone} strokeWidth={2} />}
      </svg>
      <Row text={scramble(b.label, t - 2, TIMING.reveal, seedOf(b.label))} cells={b.label.length} y={Y(y)} size={BRACKET.label * cam.s} cx={X(W / 2)} color={tone} skin={skin} opacity={opacity} />
      {lines.map((text, k) => {
        const last = k === lines.length - 1;
        const ny = SLOTS.note.y + (k - (lines.length - 1) / 2) * SIZES.s * 1.2;
        const shown = noteT < 0 ? "" : typed(text, noteT, TIMING.typeRate * 2);
        const citeFrom = last && cite && text.endsWith(cite) ? text.length - cite.length : text.length;
        return <Row key={k} text={shown} cells={text.length} y={ny} size={SIZES.s} cx={W / 2} color={skin.tones.grey} skin={skin} opacity={opacity} span={{ from: citeFrom, to: text.length, color: skin.tones.dim }} />;
      })}
    </>
  );
};

// ── custom ───────────────────────────────────────────────────────────────────

const CustomView: React.FC<{ el: ElState; ctx: MoveContext; opacity: number }> = ({ el, ctx, opacity }) => {
  const e = el.ev as Extract<ElState["ev"], { type: "custom" }>;
  const Draw = ctx.customDraw[e.move];
  const spec = ctx.custom[e.move];
  if (!Draw || !spec) return null;
  const band = SLOTS[e.slot];
  const t = Math.min(ctx.frame - e.at, spec.frames);
  return (
    <div style={{ position: "absolute", inset: 0, opacity }}>
      <Draw t={t} frames={spec.frames} text={e.text ?? ""} box={{ x: GEOMETRY_LEFT, y: band.top, w: GEOMETRY_W, h: band.bottom - band.top }} skin={ctx.skin} seed={seedOf(e.id)} />
    </div>
  );
};
const GEOMETRY_LEFT = 60;
const GEOMETRY_W = 960;

// ── one element ──────────────────────────────────────────────────────────────

const VIEWS: Record<string, React.FC<{ el: ElState; ctx: MoveContext; opacity: number }>> = {
  word: WordView, rearrange: RearrangeView, encode: EncodeView, number: NumberView, grid: GridView,
  stream: StreamView, type: TypeView, custom: CustomView,
};

export const ElementView: React.FC<{ el: ElState; ctx: MoveContext }> = ({ el, ctx }) => {
  const View = VIEWS[el.ev.type];
  if (!View) return null;
  const opacity = Number.isFinite(el.outAt) ? 1 - clamp01((ctx.frame - el.outAt) / TIMING.clearOut) : 1;
  if (opacity <= 0) return null;
  return (
    <>
      <View el={el} ctx={ctx} opacity={opacity} />
      <BracketView el={el} ctx={ctx} opacity={opacity} />
    </>
  );
};

export { LIMITS };
