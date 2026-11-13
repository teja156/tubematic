/*
 * PaperDiorama: the whole of a Paper Diorama video, as one scene.
 *
 * A playful explainer told in paper rooms. Each set is a room from the
 * papercut-explainer kit (MIT) with a taped banner naming the beat; props of
 * cut paper pop, slide or drop into named slots on the stage, the house clay
 * critter reacts, and stamps, red rings, label pills and paper routes land on
 * the stressed words. The captions are the shared Subtitles layer in its
 * "tags" look: one torn coral tag per word.
 *
 * The agent never writes this file's kind of code: it writes
 * `props.paperDiorama` (sets, items and events timed to the narration, and
 * any props of its own as paper pieces), which the MCP server validates
 * against ./paperDiorama/contract.ts before the video can render.
 *
 * Kept cheap on the CPU renderer (software GL): a room is one JPEG drawn once
 * onto a canvas; every prop and every critter pose is painted ONCE onto a
 * canvas (paint.ts) and copied onto a canvas of its own that only moves; no
 * <img>, SVG filter, blend mode, gradient or stroke-dasharray; the stage is
 * transformed only on the frames a snap zoom is running, and there is no slow
 * camera push (it made every prop redraw on every frame).
 *
 * Measured in CPU-seconds per frame over the whole skill example (956 frames,
 * rendered from a prebuilt bundle with software GL, concurrency 2): 0.44 here,
 * 0.23 for System Flow's example on the same day by the same method (1.9x).
 * The detailed paper rooms are most of it, and the torn-tag captions about 0.1.
 */
import React, { useEffect, useState } from "react";
import { AbsoluteFill, cancelRender, continueRender, delayRender, staticFile, useCurrentFrame } from "remotion";
import {
  COLORS, H, SCALES, TIMING, W, ZONES,
  type Expression, type Item, type PaperDioramaData, type PaperSet, type PropDef,
} from "./paperDiorama/contract";
import { PAD, color, hashSeed, paintProp } from "./paperDiorama/paint";
import { CRITTER_H, CRITTER_W, blinking, bob, critterDef } from "./paperDiorama/critter";
import {
  critterPose, drawProgress, itemPose, popScale, ringPoints, scaled, setIndexAt, slotBox, stageScale,
  tearReveal, zoomOrigin,
} from "./paperDiorama/stage";
import { loadFonts, type FontFile } from "./paper/fonts";
import LIBRARY from "./paperDiorama/props.json";

const PROPS = LIBRARY as unknown as Record<string, PropDef>;

export const PAPER_FONTS: FontFile[] = [
  ["Archivo Black", "fonts/archivo-black-latin-400-normal.woff2", "400"],
  ["Inter", "fonts/inter-latin-800-normal.woff2", "800"],
  ["JetBrains Mono", "fonts/jetbrains-mono-latin-700-normal.woff2", "700"],
  ["Fraunces", "fonts/fraunces-latin-900-normal.woff2", "900"],
];

export interface PaperDioramaProps {
  paperDiorama: PaperDioramaData;
}

export const propDef = (data: PaperDioramaData, name: string): PropDef | undefined =>
  data.customProps?.[name] ?? PROPS[name];

const critterKey = (expr: string) => `critter:${expr}`;

/** Every bitmap the video shows, painted once before the first frame. Kept as
 *  canvases: an <img> (or Remotion's <Img>) of the same picture costs the
 *  software-GL renderer far more per frame than a canvas copied once (measured:
 *  a still room as an <Img> took twice the CPU of the same room on a canvas). */
function useSprites(data: PaperDioramaData): Map<string, HTMLCanvasElement> | null {
  const [sprites, setSprites] = useState<Map<string, HTMLCanvasElement> | null>(null);
  const [handle] = useState(() => delayRender("PaperDiorama: painting the paper props"));
  useEffect(() => {
    const names = new Set<string>();
    const exprs = new Set<string>(["idle", "blink"]);
    for (const s of data.sets) {
      for (const it of s.items ?? []) names.add(it.prop);
      if (s.critter?.expr) exprs.add(s.critter.expr);
      for (const e of s.events ?? []) {
        if (e.do === "swap" && e.prop) names.add(e.prop);
        if (e.do === "expr" && e.value) exprs.add(e.value);
      }
    }
    loadFonts(PAPER_FONTS)
      .catch((err) => console.error("PaperDiorama: font load failed", err))
      .then(() => {
        const out = new Map<string, HTMLCanvasElement>();
        for (const n of names) {
          const def = propDef(data, n);
          if (def) out.set(n, paintProp(def, hashSeed(n)));
        }
        const body = data.critter?.color ?? "hero";
        const acc = data.critter?.acc ?? "none";
        for (const ex of exprs) {
          out.set(critterKey(ex), paintProp(critterDef(body, acc, ex as Expression | "blink"), 4242, 5));
        }
        setSprites(out);
        continueRender(handle);
      });
  }, [data, handle]);
  return sprites;
}

// ── the banner ───────────────────────────────────────────────────────────────
export function bannerFontSize(text: string): number {
  return Math.max(34, Math.min(62, Math.floor(ZONES.bannerMaxWidth / Math.max(1, text.length * 0.74))));
}

const TapeBanner: React.FC<{ text: string; frame: number }> = ({ text, frame }) => {
  const size = bannerFontSize(text);
  // the paper boils on twos: the strip shifts a pixel, never the type inside it
  const step = Math.floor(frame / 2);
  const jx = ((step * 37) % 3) - 1, jy = ((step * 53) % 3) - 1;
  return (
    <div style={{
      position: "absolute", left: "50%", top: (ZONES.bannerTop + ZONES.bannerBottom) / 2 + jy,
      transform: `translate(calc(-50% + ${jx}px), -50%) rotate(-1deg)`, maxWidth: ZONES.bannerMaxWidth + 60,
      background: COLORS.paper, padding: `${size * 0.32}px ${size * 0.62}px`,
      boxShadow: "2px 5px 0 rgba(0,0,0,0.22)", whiteSpace: "nowrap",
      fontFamily: "'Archivo Black', 'Arial Black', Impact, sans-serif", fontSize: size, lineHeight: 1.05,
      color: COLORS.ink, letterSpacing: "0.01em", textTransform: "uppercase",
    }}>
      {[-1, 1].map((side) => (
        <span key={side} style={{
          position: "absolute", top: -size * 0.28, [side < 0 ? "left" : "right"]: -size * 0.45,
          width: size * 1.5, height: size * 0.62, background: COLORS.tape, opacity: 0.9,
          transform: `rotate(${side * -14}deg)`,
        } as React.CSSProperties} />
      ))}
      {text}
    </div>
  );
};

// ── a set ────────────────────────────────────────────────────────────────────
/** A painted bitmap copied once onto a canvas of its own, then only moved. */
const Bitmap: React.FC<{ src: HTMLCanvasElement; style: React.CSSProperties }> = ({ src, style }) => {
  const ref = React.useRef<HTMLCanvasElement>(null);
  React.useLayoutEffect(() => {
    const g = ref.current?.getContext("2d");
    if (g) {
      g.clearRect(0, 0, src.width, src.height);
      g.drawImage(src, 0, 0);
    }
  }, [src]);
  return <canvas ref={ref} width={src.width} height={src.height} style={style} />;
};

const Sprite: React.FC<{ src?: HTMLCanvasElement; w: number; h: number; x: number; bottom: number; scale: number; dy?: number; flip?: boolean }> = ({
  src, w, h, x, bottom, scale, dy = 0, flip,
}) => {
  if (!src || scale <= 0) return null;
  const left = x - w / 2 - PAD, top = bottom - h - PAD + dy;
  const tf = [scale !== 1 ? `scale(${scale.toFixed(4)})` : "", flip ? "scaleX(-1)" : ""].filter(Boolean).join(" ");
  return (
    <Bitmap src={src} style={{
      position: "absolute", left, top, width: w + 2 * PAD, height: h + 2 * PAD,
      transform: tf || undefined, transformOrigin: `50% ${((h + PAD) / (h + 2 * PAD)) * 100}%`,
    }} />
  );
};

/** The room, a JPEG drawn once onto a canvas (see useSprites for why not an <Img>). */
const Room: React.FC<{ room: string }> = ({ room }) => {
  const ref = React.useRef<HTMLCanvasElement>(null);
  const [handle] = useState(() => delayRender(`PaperDiorama: loading the room ${room}`));
  useEffect(() => {
    const im = new Image();
    im.onload = () => {
      ref.current?.getContext("2d")?.drawImage(im, 0, 0, W, H);
      continueRender(handle);
    };
    // A room that will not load fails the render, as a missing <Img> does.
    im.onerror = () => cancelRender(new Error(`PaperDiorama: the room ${room} did not load`));
    im.src = staticFile(`paperDiorama/rooms/${room}.jpg`);
  }, [room, handle]);
  return <canvas ref={ref} width={W} height={H} style={{ position: "absolute", left: 0, top: 0, width: W, height: H }} />;
};

const Stamp: React.FC<{ text: string; x: number; y: number; age: number; tint: string }> = ({ text, x, y, age, tint }) => (
  <div style={{
    position: "absolute", left: x, top: y, transform: `translate(-50%, -50%) rotate(-12deg) scale(${(age < TIMING.stamp ? 1.5 - 0.5 * (age / TIMING.stamp) : 1).toFixed(3)})`,
    border: `6px solid ${tint}`, borderRadius: 10, padding: 4, opacity: 0.94,
  }}>
    <div style={{
      border: `3px solid ${tint}`, borderRadius: 6, padding: "6px 22px", color: tint, whiteSpace: "nowrap",
      fontFamily: "'Archivo Black', 'Arial Black', Impact, sans-serif", fontSize: 60, lineHeight: 1, letterSpacing: "0.03em",
    }}>{text}</div>
  </div>
);

const Label: React.FC<{ text: string; x: number; y: number; age: number }> = ({ text, x, y, age }) => (
  <div style={{
    position: "absolute", left: x, top: y, transform: `translate(-50%, -100%) scale(${popScale(age, TIMING.label).toFixed(3)})`,
    background: COLORS.ink, color: COLORS.paper, whiteSpace: "nowrap", borderRadius: 9, padding: "7px 18px 9px",
    fontFamily: "Inter, 'Helvetica Neue', Arial, sans-serif", fontWeight: 800, fontSize: 34, letterSpacing: "0.02em",
    boxShadow: "1px 3px 5px rgba(0,0,0,0.35)",
  }}>{text}</div>
);

const SetLayer: React.FC<{
  data: PaperDioramaData; set: PaperSet; frame: number; start: number; sprites: Map<string, HTMLCanvasElement>;
}> = ({ data, set, frame, start, sprites }) => {
  const size = (it: Item): [number, number] => {
    const def = propDef(data, it.prop);
    return def ? scaled(def, it.scale) : [0, 0];
  };
  const box = (id: string): [number, number, number, number] | null => {
    const it = (set.items ?? []).find((i) => i.id === id);
    if (!it) return null;
    const pose = itemPose(set, it, frame);
    const def = propDef(data, pose.prop);
    if (!def) return null;
    const [w, h] = scaled(def, it.scale);
    return [pose.x - w / 2, pose.bottom - h, pose.x + w / 2, pose.bottom];
  };
  const scale = stageScale(set, frame);
  const [ox, oy] = scale !== 1 ? zoomOrigin(set, frame, size) : [540, 960];
  const cr = critterPose(set, frame, start);
  const crExpr = cr.expr === "idle" && blinking(frame) ? "blink" : cr.expr;
  const events = (set.events ?? []).filter((e) => e.at <= frame);
  return (
    <AbsoluteFill style={{ overflow: "hidden" }}>
      <AbsoluteFill style={scale !== 1 ? { transform: `scale(${scale.toFixed(4)})`, transformOrigin: `${ox}px ${oy}px` } : undefined}>
        <Room room={set.room} />
        {events.filter((e) => e.do === "route").map((e, i) => {
          const a = e.from ? box(e.from) : null, b = e.target ? box(e.target) : null;
          if (!a || !b) return null;
          const p = drawProgress(e, frame);
          const ax = (a[0] + a[2]) / 2, ay = a[3] - 18, bx = (b[0] + b[2]) / 2, by = b[3] - 18;
          const n = Math.max(1, Math.round((Math.hypot(bx - ax, by - ay) / 30) * p));
          return (
            <svg key={`r${i}`} width={W} height={H} style={{ position: "absolute", left: 0, top: 0 }}>
              {Array.from({ length: n }, (_, k) => {
                const t = k / Math.max(1, Math.round(Math.hypot(bx - ax, by - ay) / 30));
                const x = ax + (bx - ax) * t, y = ay + (by - ay) * t - Math.sin(t * Math.PI) * 60;
                return <rect key={k} x={x - 9} y={y - 4} width={18} height={8} rx={3} fill={color(e.color ?? "tape")} />;
              })}
            </svg>
          );
        })}
        {(set.items ?? []).map((it) => {
          const pose = itemPose(set, it, frame);
          if (!pose.visible) return null;
          const def = propDef(data, pose.prop);
          if (!def) return null;
          const s = SCALES[it.scale ?? "m"];
          return (
            <React.Fragment key={it.id}>
              <Sprite src={sprites.get(pose.prop)} w={def.w * s} h={def.h * s} x={pose.x} bottom={pose.bottom} scale={pose.scale} dy={pose.dy} />
              {pose.label && <Label text={pose.label} x={pose.x} y={pose.bottom - def.h * s - 14 + pose.dy} age={pose.labelAge} />}
            </React.Fragment>
          );
        })}
        {cr.visible && (
          <Sprite src={sprites.get(critterKey(crExpr)) ?? sprites.get(critterKey("idle"))} w={CRITTER_W} h={CRITTER_H}
            x={cr.x} bottom={cr.bottom} scale={1} dy={cr.dy + bob(frame - start)} flip={cr.face === -1} />
        )}
        {events.filter((e) => e.do === "ring").map((e, i) => {
          const b = e.target ? box(e.target) : null;
          if (!b) return null;
          const pts = ringPoints(b, drawProgress(e, frame), i + 1);
          return (
            <svg key={`g${i}`} width={W} height={H} style={{ position: "absolute", left: 0, top: 0 }}>
              <polyline points={pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ")} fill="none"
                stroke={color(e.color ?? "nogo")} strokeWidth={8} strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          );
        })}
        {events.filter((e) => e.do === "stamp").map((e, i) => {
          const tgt = e.target ? box(e.target) : null;
          const x = tgt ? (tgt[0] + tgt[2]) / 2 : 540;
          const y = tgt ? (tgt[1] + tgt[3]) / 2 : slotBox(set, "c", e.level ?? "shelf", 0, 0)[3] - 80;
          return <Stamp key={`s${i}`} text={e.text ?? ""} x={x} y={y} age={frame - e.at} tint={color(e.color ?? "nogo")} />;
        })}
      </AbsoluteFill>
      <TapeBanner text={set.banner} frame={frame} />
    </AbsoluteFill>
  );
};

export default function PaperDiorama({ paperDiorama }: PaperDioramaProps) {
  const frame = useCurrentFrame();
  const data = paperDiorama;
  const sprites = useSprites(data);
  const i = setIndexAt(data.sets, frame);
  const set = data.sets[i];
  const start = set?.start ?? 0;
  const tearing = set?.cut === "tear" && i > 0 && frame - start < TIMING.tear;
  if (!set || !sprites) return <AbsoluteFill style={{ background: COLORS.cream }} />;
  const current = <SetLayer data={data} set={set} frame={frame} start={start} sprites={sprites} />;
  if (!tearing) return current;
  const prev = data.sets[i - 1];
  const reveal = tearReveal(frame, start);
  // the new set is uncovered from the bottom up along a torn edge
  const edgeY = H * (1 - reveal);
  const teeth = Array.from({ length: 19 }, (_, k) => `${(k / 18) * 100}% ${(edgeY + ((k * 41) % 7) * 6 - 18).toFixed(1)}px`);
  return (
    <AbsoluteFill>
      <SetLayer data={data} set={prev} frame={frame} start={prev.start} sprites={sprites} />
      <AbsoluteFill style={{ clipPath: `polygon(${teeth.join(", ")}, 100% 100%, 0% 100%)` }}>{current}</AbsoluteFill>
    </AbsoluteFill>
  );
}
