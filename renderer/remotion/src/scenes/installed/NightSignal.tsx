/*
 * NightSignal: the whole of a Night Signal video, as one scene.
 *
 * A warning story or a list of rules, told with glowing warm-white
 * pictograms on a near-black field: a figure at a door, a phone lighting up,
 * a stranger in red (the one red thing, the threat), a doorbell camera, a
 * RULE card with a prohibition ring, a case card, a navy card of steps. A
 * case-file row near the top (FILE number, progress squares, a running
 * timecode) and a light CRT finish frame it; scenes change through short
 * glitch tears. The captions are the shared Subtitles layer in spaced capitals.
 *
 * The agent never writes this file's kind of code: it writes
 * `props.nightSignal` (scenes timed to the narration, from a library of
 * pictograms plus its own parts made of the same shapes), which the MCP server
 * validates against ./nightSignal/contract.ts before the video can render.
 *
 * Kept cheap on the CPU renderer (software GL): the picture band is one
 * Canvas 2D layer redrawn per frame; its glow is one blurred copy at a quarter
 * of the size added on top, never an SVG filter; the threat's faceless head is
 * a soft gradient disc, never a canvas blur; the glitch tear is canvas slices
 * of the two scenes; the scanlines, vignette and one static grain tile are
 * drawn once and placed inside the band; dotted lines are dots, never
 * stroke-dasharray.
 */
import React, { useLayoutEffect, useMemo, useRef, useState } from "react";
import { AbsoluteFill, continueRender, delayRender, useCurrentFrame, useVideoConfig } from "remotion";
import { GEOMETRY, H, W, timecode, type NightSignalData } from "./nightSignal/contract";
import { BH, BW, COLORS, FONT, drawScene, rng } from "./nightSignal/draw";
import { useNightSignalFonts } from "./nightSignal/fonts";
import { pushAt, sceneEnd, sceneIndexAt, squaresAt, tearAt } from "./nightSignal/stage";

const G = GEOMETRY;
const SMALL = 4;

function makeCanvas(w: number, h: number): HTMLCanvasElement {
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  return c;
}

/** Scene `i` drawn on `target` (cleared first) as it looks at `frame`. */
function paintScene(target: HTMLCanvasElement, data: NightSignalData, i: number, frame: number, fps: number, total: number) {
  const ctx = target.getContext("2d")!;
  ctx.clearRect(0, 0, BW, BH);
  const scene = data.scenes[i];
  drawScene(ctx, data, scene, i, frame, fps, pushAt(scene.start, sceneEnd(data, i, total), frame));
}

/** A silhouette of `src` in one colour, for a tear's colour fringes. */
function tint(target: HTMLCanvasElement, src: HTMLCanvasElement, color: string) {
  const ctx = target.getContext("2d")!;
  ctx.globalCompositeOperation = "source-over";
  ctx.clearRect(0, 0, BW, BH);
  ctx.drawImage(src, 0, 0);
  ctx.globalCompositeOperation = "source-in";
  ctx.fillStyle = color;
  ctx.fillRect(0, 0, BW, BH);
  ctx.globalCompositeOperation = "source-over";
}

interface Buffers {
  a: HTMLCanvasElement;
  b: HTMLCanvasElement;
  ta: HTMLCanvasElement;
  tb: HTMLCanvasElement;
  small: HTMLCanvasElement;
  finish: HTMLCanvasElement;
  grain: HTMLCanvasElement[];
  hum: HTMLCanvasElement;
}

function paintBand(out: CanvasRenderingContext2D, buf: Buffers, data: NightSignalData, frame: number, fps: number, total: number) {
  out.globalCompositeOperation = "source-over";
  out.globalAlpha = 1;
  out.fillStyle = COLORS.bg;
  out.fillRect(0, 0, BW, BH);
  if (!data.scenes.length) return;
  const tear = tearAt(data, frame);
  if (!tear) {
    // straight onto the band: no copy through a buffer
    const i = sceneIndexAt(data, frame);
    const scene = data.scenes[i];
    drawScene(out, data, scene, i, frame, fps, pushAt(scene.start, sceneEnd(data, i, total), frame));
  } else {
    // Both scenes at once, in torn horizontal slices with colour fringes, seeded by the frame.
    paintScene(buf.a, data, tear.into - 1, frame, fps, total);
    paintScene(buf.b, data, tear.into, frame, fps, total);
    tint(buf.ta, buf.a, "#ff2846");
    tint(buf.tb, buf.b, "#3cdcff");
    const r = rng(frame * 7919 + 17);
    let y = 0;
    while (y < BH) {
      const h = 18 + r() * 96;
      const big = r() < 0.35;
      const dx = (r() - 0.5) * (big ? 180 : 40);
      const next = r() < tear.progress;
      const ch = 4 + r() * 9;
      const src = next ? buf.b : buf.a;
      out.globalCompositeOperation = "source-over";
      out.globalAlpha = 1;
      out.drawImage(src, 0, y, BW, h, dx, y, BW, h);
      out.globalCompositeOperation = "lighter";
      out.globalAlpha = 0.45;
      out.drawImage(next ? buf.tb : buf.ta, 0, y, BW, h, dx - ch, y, BW, h);
      out.drawImage(next ? buf.ta : buf.tb, 0, y, BW, h, dx + ch, y, BW, h);
      y += h;
    }
    out.globalCompositeOperation = "source-over";
    out.globalAlpha = 1;
    // tear streaks
    const rs = rng(frame * 31 + 5);
    for (let i = 0; i < 12; i++) {
      out.fillStyle = [COLORS.core, "#ff5a6a", "#6af0ff", COLORS.grey][Math.floor(rs() * 4)];
      out.globalAlpha = 0.35 + rs() * 0.5;
      out.fillRect(rs() * 700, rs() * BH, 120 + rs() * 600, 2 + rs() * 5);
    }
    out.globalAlpha = 1;
  }
  // The glow: the scene at a quarter of the size, blurred, added back on top.
  const sctx = buf.small.getContext("2d")!;
  sctx.clearRect(0, 0, buf.small.width, buf.small.height);
  sctx.filter = "blur(3px)";
  sctx.drawImage(out.canvas, 0, 0, buf.small.width, buf.small.height);
  sctx.filter = "none";
  // take the field's own colour out, so only what is drawn glows and the black stays black
  sctx.globalCompositeOperation = "difference";
  sctx.fillStyle = COLORS.bg;
  sctx.fillRect(0, 0, buf.small.width, buf.small.height);
  sctx.globalCompositeOperation = "source-over";
  out.globalCompositeOperation = "lighter";
  out.globalAlpha = 0.42;
  out.drawImage(buf.small, 0, 0, BW, BH);
  // The CRT finish, inside the band (the field around it is black, where a
  // finish shows nothing): a light hum band rolling down, then one overlay
  // holding the scanlines, the vignette and a static grain, drawn once and
  // only placed here. As separate full-frame layers they cost more than the
  // rest of the frame, and grain that changes every frame made the encoded
  // video ten times larger.
  out.globalAlpha = 1;
  out.drawImage(buf.hum, 0, ((frame * 4) % (BH + 600)) - 300);
  out.globalCompositeOperation = "source-over";
  out.drawImage(buf.finish, 0, 0);
}

/** The CRT finish over the band, drawn once: scanlines every 6 px and a vignette. */
function paintFinish(c: HTMLCanvasElement) {
  const ctx = c.getContext("2d")!;
  ctx.fillStyle = "rgba(0,0,0,0.17)";
  for (let y = 0; y < BH; y += 6) ctx.fillRect(0, y, BW, 2);
  const g = ctx.createRadialGradient(BW / 2, BH * 0.45, BH * 0.35, BW / 2, BH * 0.45, BH * 0.85);
  g.addColorStop(0, "rgba(0,0,0,0)");
  g.addColorStop(1, "rgba(0,0,0,0.45)");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, BW, BH);
}

/** One grain tile, drawn once: faint white specks. */
function paintGrain(c: HTMLCanvasElement, seed: number) {
  const ctx = c.getContext("2d")!;
  const img = ctx.createImageData(c.width, c.height);
  const r = rng(seed);
  for (let i = 0; i < img.data.length; i += 4) {
    const v = r();
    img.data[i] = img.data[i + 1] = img.data[i + 2] = 255;
    img.data[i + 3] = v > 0.55 ? Math.floor((v - 0.55) * 50) : 0;
  }
  ctx.putImageData(img, 0, 0);
}

function paintHum(c: HTMLCanvasElement) {
  const ctx = c.getContext("2d")!;
  const g = ctx.createLinearGradient(0, 0, 0, c.height);
  g.addColorStop(0, "rgba(251,252,240,0)");
  g.addColorStop(0.5, "rgba(251,252,240,0.035)");
  g.addColorStop(1, "rgba(251,252,240,0)");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, c.width, c.height);
}

// One grain tile that never changes, baked into the finish.
const GRAIN_TILES = 1;

function makeBuffers(): Buffers {
  const grain = Array.from({ length: GRAIN_TILES }, (_, i) => {
    const c = makeCanvas(BW / 4, BH / 4);
    paintGrain(c, 97 + i * 13);
    return c;
  });
  const finish = makeCanvas(BW, BH);
  const fctx = finish.getContext("2d")!;
  fctx.drawImage(grain[0], 0, 0, BW, BH);
  // the grain fades out at the band's top and bottom, so the band has no edge against the field
  const fadeMask = fctx.createLinearGradient(0, 0, 0, BH);
  fadeMask.addColorStop(0, "rgba(0,0,0,0)");
  fadeMask.addColorStop(0.12, "rgba(0,0,0,1)");
  fadeMask.addColorStop(0.88, "rgba(0,0,0,1)");
  fadeMask.addColorStop(1, "rgba(0,0,0,0)");
  fctx.globalCompositeOperation = "destination-in";
  fctx.fillStyle = fadeMask;
  fctx.fillRect(0, 0, BW, BH);
  fctx.globalCompositeOperation = "source-over";
  paintFinish(finish);
  const hum = makeCanvas(BW, 300);
  paintHum(hum);
  return {
    a: makeCanvas(BW, BH), b: makeCanvas(BW, BH), ta: makeCanvas(BW, BH), tb: makeCanvas(BW, BH),
    small: makeCanvas(BW / SMALL, BH / SMALL), finish, grain, hum,
  };
}

const Hud: React.FC<{ data: NightSignalData; frame: number; fps: number; glitch: boolean }> = ({ data, frame, fps, glitch }) => {
  const { count, current } = squaresAt(data, frame);
  const rgb = glitch ? "-5px 0 0 rgba(255,40,70,.75), 5px 0 0 rgba(60,220,255,.75)" : undefined;
  const common: React.CSSProperties = {
    position: "absolute", top: G.hudTop, fontFamily: FONT, fontWeight: 600, fontSize: 40, color: COLORS.grey,
    letterSpacing: "0.18em", lineHeight: "48px", textShadow: rgb, whiteSpace: "nowrap",
  };
  const squares = Math.min(count, 14);
  const size = squares > 9 ? 20 : 28;
  return (
    <>
      <div style={{ ...common, left: G.safeLeft }}>FILE {String(data.file?.number ?? 1).padStart(3, "0")}</div>
      <div style={{ ...common, top: G.hudTop + 54, left: G.safeLeft, opacity: 0.6, letterSpacing: "0.14em" }}>
        /// {(data.file?.title ?? "").toUpperCase()}
      </div>
      <div style={{ position: "absolute", top: G.hudTop + 9, left: 412, display: "flex", gap: squares > 9 ? 7 : 10 }}>
        {Array.from({ length: squares }, (_, i) => {
          const done = i < current;
          const now = i === current;
          const blink = now ? 0.45 + 0.55 * (Math.floor(frame / 8) % 2) : 1;
          return (
            <div
              key={i}
              style={{
                width: size, height: size, borderRadius: 4, boxSizing: "border-box",
                border: `3px solid ${done || now ? COLORS.ink : "#3d4046"}`,
                background: done ? COLORS.ink : now ? `rgba(233,232,208,${(0.55 * blink).toFixed(2)})` : "transparent",
              }}
            />
          );
        })}
      </div>
      <div style={{ ...common, right: W - G.safeRight, letterSpacing: "0.08em", fontVariantNumeric: "tabular-nums" }}>
        {timecode(data.clock, frame, fps)}
      </div>
    </>
  );
};

export interface NightSignalProps {
  nightSignal: NightSignalData;
}

export default function NightSignal({ nightSignal }: NightSignalProps) {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const ready = useNightSignalFonts("NightSignal");
  const data: NightSignalData = nightSignal ?? { file: { number: 1, title: "" }, scenes: [] };
  // The first frame is captured only after the band has been drawn with the bundled face.
  const [firstDraw] = useState(() => delayRender("NightSignal: first drawing"));
  const drawn = useRef(false);

  const band = useRef<HTMLCanvasElement>(null);
  const buf = useMemo<Buffers>(makeBuffers, []);

  useLayoutEffect(() => {
    const ctx = band.current?.getContext("2d", { alpha: false });
    if (!ctx) return;
    paintBand(ctx, buf, data, frame, fps, durationInFrames);
    if (ready && !drawn.current) {
      drawn.current = true;
      continueRender(firstDraw);
    }
  });

  const glitch = tearAt(data, frame) !== null;
  return (
    <AbsoluteFill style={{ background: COLORS.bg, width: W, height: H, overflow: "hidden" }}>
      <canvas ref={band} width={BW} height={BH} style={{ position: "absolute", left: 0, top: G.bandTop }} />
      <Hud data={data} frame={frame} fps={fps} glitch={glitch} />
    </AbsoluteFill>
  );
}
