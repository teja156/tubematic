/*
 * The two full-frame layers: the ciphertext wall and the CRT glass. Both are
 * canvases drawn as rarely as possible, because full-frame work is what this
 * style's cost is made of.
 *
 * Measured on the CPU renderer (software GL), on the research sample: a wall
 * of DOM text rows under a CSS mask gradient, with two full-frame radial
 * gradients for a halo and a vignette, cost about 1.6 CPU-seconds per frame,
 * six times everything else in the frame together. Here the wall's fade and
 * halo are baked into each glyph's alpha, the glyphs are drawn on a canvas
 * only when the flicker tick changes, and the level changes by the canvas's
 * opacity. The CRT scanlines and vignette are drawn once.
 */
import React, { useLayoutEffect, useRef } from "react";
import { H, W } from "./contract";
import { hash, type SkinTokens } from "./kit";

const COLS = 58, ADV = 18, FONT = 30, ROWH = 38, LEFT = 18;
const SET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
const ROWS = Math.ceil(H / ROWH);
/** The flicker: every TICK frames about FLICKER of the glyphs change. */
const TICK = 6, FLICKER = 0.02;
/** The wall's alpha at level 2 (bright); level 1 is LEVEL1 of it. */
export const WALL_ALPHA = 0.26;
export const LEVEL1 = 0.42;
/** Where the wall fades out above the captions, and the clear ellipse round the stage. */
const FADE_FROM = 1180, FADE_TO = 1330, HALO = { cx: W / 2, cy: 845, rx: 520, ry: 420, keep: 0.3 };

const glyphAlpha = (x: number, y: number) => {
  const fade = y < FADE_FROM ? 1 : y > FADE_TO ? 0.1 : 1 - 0.9 * ((y - FADE_FROM) / (FADE_TO - FADE_FROM));
  const d = ((x - HALO.cx) / HALO.rx) ** 2 + ((y - HALO.cy) / HALO.ry) ** 2;
  const halo = d >= 1 ? 1 : HALO.keep + (1 - HALO.keep) * d;
  return fade * halo;
};

const cellChar = (r: number, c: number, tick: number) => {
  const base = SET[Math.floor(hash(r, c, 4242) * SET.length)];
  return hash(r, c, tick + 99) < FLICKER ? SET[Math.floor(hash(r, c, tick + 999) * SET.length)] : base;
};

export const Wall: React.FC<{ frame: number; opacity: number; skin: SkinTokens; ready: boolean }> = ({ frame, opacity, skin, ready }) => {
  const ref = useRef<HTMLCanvasElement>(null);
  const drawn = useRef<string>("");
  const tick = Math.floor(frame / TICK);
  useLayoutEffect(() => {
    const cv = ref.current;
    const key = `${tick}:${skin.name}`;
    if (!cv || !ready || drawn.current === key) return;
    const ctx = cv.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, W, H);
    ctx.font = `400 ${FONT * skin.fontScale}px ${skin.font}`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    const n = parseInt(skin.tones.grey.slice(1), 16);
    const rgb = `${(n >> 16) & 255},${(n >> 8) & 255},${n & 255}`;
    for (let r = 0; r < ROWS; r++) {
      const y = r * ROWH + ROWH / 2;
      for (let c = 0; c < COLS; c++) {
        const x = LEFT + c * ADV + ADV / 2;
        const a = WALL_ALPHA * glyphAlpha(x, y);
        if (a < 0.006) continue;
        ctx.fillStyle = `rgba(${rgb},${a.toFixed(3)})`;
        ctx.fillText(cellChar(r, c, tick), x, y);
      }
    }
    drawn.current = key;
  }, [tick, skin, ready]);
  // Hidden, never unmounted: a remounted canvas would be blank until the next tick.
  return <canvas ref={ref} width={W} height={H} style={{ position: "absolute", left: 0, top: 0, opacity, display: opacity <= 0.001 ? "none" : undefined }} />;
};

/** The CRT glass: scanlines every 5 px and a vignette, drawn once. */
export const CrtGlass: React.FC = () => {
  const ref = useRef<HTMLCanvasElement>(null);
  useLayoutEffect(() => {
    const ctx = ref.current?.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = "rgba(0,0,0,0.28)";
    for (let y = 0; y < H; y += 5) ctx.fillRect(0, y + 3, W, 2);
    const g = ctx.createRadialGradient(W / 2, H * 0.45, H * 0.3, W / 2, H * 0.45, H * 0.72);
    g.addColorStop(0, "rgba(0,0,0,0)");
    g.addColorStop(1, "rgba(0,0,0,0.6)");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, W, H);
  }, []);
  return <canvas ref={ref} width={W} height={H} style={{ position: "absolute", left: 0, top: 0 }} />;
};
