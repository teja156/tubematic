/*
 * UnderTheHood: the whole of an Under the Hood video, as one scene.
 *
 * A dark "how it really works" explainer. The middle of the frame is a
 * generated close-up photograph of the object (a plate), pushing in slowly
 * the whole time; on it, short capital labels are pinned to parts of the
 * photograph by leader lines, parts are boxed or bracketed, gold field arcs
 * bend from one part toward another, and a zoom-through rushes into a point
 * and cuts to a closer photograph. Below it a row of monospace counters
 * ticks, a footnote keeps the picture honest, and a cartoon presenter in the
 * bottom right swaps whole poses on the narrator's words. The captions are
 * the shared Subtitles layer in its "selection" look, near the top.
 *
 * The agent never writes this file's kind of code: it writes
 * `props.underTheHood` (plates and events timed to the narration), which the
 * MCP server validates against ./underTheHood/contract.ts before the video can
 * render. Every point on a photograph is [u, v] in the photograph's own
 * space and goes through the plate's camera (contract.ts projectAt, the same
 * mapping as ImageFX.project), so a label stays on its part through the push.
 *
 * Kept cheap on the CPU renderer (software GL): the presenter is a cached
 * bitmap (./underTheHood/sprite.tsx); no SVG filter, gradient, pattern or
 * stroke-dasharray (the glow under an arc is a wider translucent stroke, the
 * band's fade into the canvas is a stack of flat translucent strips, an
 * outline draws on by growing its path); every overlay layer is sized to the
 * plate band, never the whole frame; arcs stop breathing and sparks stop
 * flying TIMING.arcBend + TIMING.sparkFrames after they start.
 *
 * Measured in CPU-seconds per frame over the whole skill example (858 frames,
 * rendered from a prebuilt bundle with software GL, concurrency 2): 0.37
 * here, 0.23 for System Flow's example on the same day by the same method
 * (1.6x; Bean Explainer measured 1.65x by its own). With every event removed
 * the example costs 0.28: the slow push makes every frame a new photograph to
 * capture and encode, and the overlays add about 0.08. Drawing the photograph
 * with a CSS transform, a resized box or a viewBox-cropped SVG image all
 * measured the same; the SVG is used because it is the one that still draws
 * at a zoom-through's 4x (see Plate).
 */
import React, { useEffect, useState } from "react";
import { AbsoluteFill, cancelRender, continueRender, delayRender, interpolateColors, useCurrentFrame, useVideoConfig } from "remotion";
import {
  GEOMETRY, H, TIMING, W, chipBox, leaderStart, statText,
  type Tone, type UTHArcs, type UTHCallout, type UTHChart, type UTHCounters, type UTHEvent, type UTHOutline,
  type UTHPlate, type UTHStat, type UnderTheHoodData,
} from "./underTheHood/contract";
import { MONO, SANS, useUthFonts } from "./underTheHood/fonts";
import { PresenterSprite } from "./underTheHood/sprite";
import {
  blinkAt, camAt, clamp01, counterValue, easeOut, eventsUp, mouthAt, plateIndexAt, pointAt, poseAt,
  poseTrack, statValue, type Cam, type Word,
} from "./underTheHood/stage";

const BG = "#0E0F12";
const WHITE = "#F7F7F7";
const GREY = "#9B9CA1";
const DIM = "#6B6A6B";
const BLUE = "#3D6FBC";
const BLUE_HOT = "#518ED5";
const GOLD = "#D2AA4F";
const GOLD_HOT = "#F3CF80";
const GRID = "#17181D";
const TONE: Record<Tone, string> = { white: WHITE, blue: BLUE_HOT, gold: GOLD_HOT };

const G = GEOMETRY;
const BAND_H = G.plateBottom - G.plateTop;
const inOut = (t: number) => (t < 0.5 ? 4 * t ** 3 : 1 - (-2 * t + 2) ** 3 / 2);
const f1 = (n: number) => n.toFixed(1);

// ── the photograph ───────────────────────────────────────────────────────────
/**
 * Every photograph the video uses, loaded and decoded before the first frame.
 * A photograph that will not load fails the render, as a missing <Img> does:
 * a plate with no picture under its labels must never ship.
 */
function usePlateImages(srcs: string[]) {
  const key = srcs.join("|");
  const [handle] = useState(() => (srcs.length ? delayRender("UnderTheHood: loading the photographs") : null));
  useEffect(() => {
    if (handle === null) return;
    Promise.all(
      srcs.map((src) => {
        const img = new Image();
        img.src = src;
        return img.decode();
      }),
    )
      .then(() => continueRender(handle))
      .catch((err) => cancelRender(err));
    // the photographs are fixed for the whole render
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [handle, key]);
}

/**
 * The visible part of a plate's photograph, as an <image> in an SVG the size
 * of the band whose viewBox selects that part. Drawing the whole photograph
 * scaled up instead failed silently on the CPU renderer: past roughly 3000 px
 * a side (a zoom-through reaches 4x) the layer was dropped and the band went
 * empty. The viewBox keeps the drawn layer at the band's size at any zoom.
 */
const Plate: React.FC<{ plate: UTHPlate; cam: Cam }> = ({ plate, cam }) => {
  if (!plate.image) {
    // a plain dark panel (a chart plate), cross-fading over the plate before it
    return <div style={{ position: "absolute", inset: 0, background: BG, opacity: cam.opacity === 1 ? undefined : cam.opacity }} />;
  }
  return <PlatePhoto key={plate.image} src={plate.image} plate={plate} cam={cam} />;
};

/** The photograph itself; its first frame waits for this <image> element to load. */
const PlatePhoto: React.FC<{ src: string; plate: UTHPlate; cam: Cam }> = ({ src, plate, cam }) => {
  const [handle] = useState(() => delayRender(`UnderTheHood: drawing ${src}`));
  const [x0, y0] = pointAt(plate, cam, 0, 0);
  const [x1, y1] = pointAt(plate, cam, 1, 1);
  const iw = 1000, ih = 1000 * (plate.aspect ?? 1); // the photograph in its own units
  const vx = ((0 - x0) / (x1 - x0)) * iw, vy = ((G.plateTop - y0) / (y1 - y0)) * ih;
  const vw = (W / (x1 - x0)) * iw, vh = (BAND_H / (y1 - y0)) * ih;
  return (
    <svg width={W} height={BAND_H} viewBox={`${vx} ${vy} ${vw} ${vh}`} preserveAspectRatio="none"
      style={{ position: "absolute", left: 0, top: 0, opacity: cam.opacity === 1 ? undefined : cam.opacity }}>
      <image href={src} x={0} y={0} width={iw} height={ih} preserveAspectRatio="none"
        onLoad={() => continueRender(handle)}
        onError={() => cancelRender(new Error(`UnderTheHood: the photograph ${src} did not load`))} />
    </svg>
  );
};

/** The band's top and bottom edges fading into the canvas: flat strips, no gradient. */
const EdgeFade: React.FC = () => {
  const steps = 10, h = G.fadePx / steps;
  return (
    <svg width={W} height={BAND_H} style={{ position: "absolute", left: 0, top: 0 }}>
      {Array.from({ length: steps }, (_, i) => {
        const o = 1 - i / steps;
        return (
          <g key={i}>
            <rect x={0} y={i * h} width={W} height={h + 0.5} fill={BG} opacity={o} />
            <rect x={0} y={BAND_H - (i + 1) * h - 0.5} width={W} height={h + 0.5} fill={BG} opacity={o} />
          </g>
        );
      })}
    </svg>
  );
};

/** A faint square grid: the dark panel of a chart plate, and the bottom third. */
const Grid: React.FC<{ top: number; height: number }> = ({ top, height }) => {
  const step = 60;
  const lines: React.ReactNode[] = [];
  for (let x = 30; x < W; x += step) lines.push(<line key={`x${x}`} x1={x} x2={x} y1={0} y2={height} />);
  for (let y = 30; y < height; y += step) lines.push(<line key={`y${y}`} x1={0} x2={W} y1={y} y2={y} />);
  return (
    <svg width={W} height={height} style={{ position: "absolute", left: 0, top }}>
      <g stroke={GRID} strokeWidth={1.5}>{lines}</g>
    </svg>
  );
};

// ── overlays drawn in band coordinates (y measured from the band's top) ─────
const by = (y: number) => y - G.plateTop;

function partialPolyline(points: [number, number][], t: number): string {
  if (t >= 1) return points.map(([x, y]) => `${f1(x)},${f1(by(y))}`).join(" ");
  const segs: number[] = [];
  let total = 0;
  for (let i = 1; i < points.length; i++) {
    const d = Math.hypot(points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1]);
    segs.push(d);
    total += d;
  }
  let left = total * clamp01(t);
  const out: [number, number][] = [points[0]];
  for (let i = 1; i < points.length && left > 0; i++) {
    const d = segs[i - 1];
    const k = Math.min(1, left / (d || 1));
    out.push([points[i - 1][0] + (points[i][0] - points[i - 1][0]) * k, points[i - 1][1] + (points[i][1] - points[i - 1][1]) * k]);
    left -= d;
  }
  return out.map(([x, y]) => `${f1(x)},${f1(by(y))}`).join(" ");
}

const Outline: React.FC<{ e: UTHOutline; plate: UTHPlate; cam: Cam; frame: number }> = ({ e, plate, cam, frame }) => {
  const [u0, v0, u1, v1] = e.region;
  const [x0, y0] = pointAt(plate, cam, u0, v0);
  const [x1, y1] = pointAt(plate, cam, u1, v1);
  const t = clamp01((frame - e.frame) / TIMING.drawOn);
  const color = TONE[e.tone ?? "blue"];
  if ((e.shape ?? "box") === "bracket") {
    const leg = Math.min(x1 - x0, y1 - y0) * 0.22 * easeOut(t);
    const corners: [number, number, number, number][] = [[x0, y0, 1, 1], [x1, y0, -1, 1], [x1, y1, -1, -1], [x0, y1, 1, -1]];
    return (
      <g>
        {corners.map(([x, y, sx, sy], i) => (
          <polyline key={i} points={`${f1(x + sx * leg)},${f1(by(y))} ${f1(x)},${f1(by(y))} ${f1(x)},${f1(by(y + sy * leg))}`}
            fill="none" stroke={color} strokeWidth={5} strokeLinecap="round" strokeLinejoin="round" />
        ))}
      </g>
    );
  }
  const pts: [number, number][] = [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]];
  return (
    <g>
      {t >= 1 && <rect x={x0} y={by(y0)} width={x1 - x0} height={y1 - y0} fill={color} opacity={0.1} />}
      <polyline points={partialPolyline(pts, t)} fill="none" stroke={color} strokeWidth={3.5} strokeLinejoin="round" strokeLinecap="round" />
    </g>
  );
};

// deterministic spark directions, so every render draws the same frames
const SPARKS = Array.from({ length: 10 }, (_, i) => ({ a: (i * 2.399963) % (Math.PI * 2), ph: (i * 0.618034) % 1, sp: 0.045 + (i % 4) * 0.012 }));

const Arcs: React.FC<{ e: UTHArcs; plate: UTHPlate; cam: Cam; frame: number }> = ({ e, plate, cam, frame }) => {
  const F = pointAt(plate, cam, e.from[0], e.from[1]);
  const T = pointAt(plate, cam, e.to[0], e.to[1]);
  const n = e.count ?? 7;
  const dx = T[0] - F[0], dy = T[1] - F[1];
  const d = Math.hypot(dx, dy) || 1;
  const nx = -dy / d, ny = dx / d; // a perpendicular to spread the fan
  const age = frame - e.frame;
  const live = age < TIMING.arcBend + TIMING.sparkFrames; // after this the arcs hold still
  const paths: { d: string; b: number }[] = [];
  for (let j = 0; j < n; j++) {
    const off = j - (n - 1) / 2;
    const b = inOut(clamp01((age - j * 1.5) / TIMING.arcBend));
    const breathe = live ? Math.sin(frame * 0.12 + j) * 5 * (1 - clamp01((age - TIMING.arcBend) / TIMING.sparkFrames)) : 0;
    const A: [number, number] = [F[0] + nx * off * 16, F[1] + ny * off * 16];
    // at rest each arc leaves the source and curls back beside it; bent, it reaches the target
    const B0: [number, number] = [F[0] + nx * off * 34 + dx * 0.08, F[1] + ny * off * 34 + dy * 0.08];
    const B1: [number, number] = [T[0] + nx * off * 14, T[1] + ny * off * 14];
    const lift = 60 + Math.abs(off) * 26 + breathe;
    const C0: [number, number] = [A[0] + dx * 0.04 + nx * off * 10, A[1] - lift];
    const C1: [number, number] = [(F[0] + T[0]) / 2 + nx * off * 62, (F[1] + T[1]) / 2 + ny * off * 62 - lift * 0.6];
    const L = (p: [number, number], q: [number, number]) => [p[0] + (q[0] - p[0]) * b, p[1] + (q[1] - p[1]) * b];
    const B = L(B0, B1), C = L(C0, C1);
    paths.push({ d: `M ${f1(A[0])} ${f1(by(A[1]))} Q ${f1(C[0])} ${f1(by(C[1]))} ${f1(B[0])} ${f1(by(B[1]))}`, b });
  }
  const bAll = inOut(clamp01((age - 6) / TIMING.arcBend));
  return (
    <g>
      {paths.map((p, i) => <path key={`g${i}`} d={p.d} fill="none" stroke={GOLD_HOT} strokeOpacity={0.1 + 0.22 * p.b} strokeWidth={10} strokeLinecap="round" />)}
      {paths.map((p, i) => (
        <path key={`c${i}`} d={p.d} fill="none" stroke={interpolateColors(p.b, [0, 1], [GOLD, GOLD_HOT])}
          strokeOpacity={0.55 + 0.4 * p.b} strokeWidth={2.4 + 1.2 * p.b} strokeLinecap="round" />
      ))}
      {live && bAll > 0.4 && SPARKS.map((s, i) => {
        const t = (age * s.sp + s.ph) % 1;
        const r = 8 + t * 46;
        return <circle key={i} cx={T[0] + Math.cos(s.a) * r} cy={by(T[1] + Math.sin(s.a) * r * 0.7)} r={2.6 * (1 - t) + 0.6} fill={GOLD_HOT} opacity={(1 - t) * bAll} />;
      })}
      {bAll > 0 && <circle cx={T[0]} cy={by(T[1])} r={7 + 5 * bAll} fill={GOLD_HOT} opacity={0.9 * bAll} />}
    </g>
  );
};

const Leader: React.FC<{ e: UTHCallout; plate: UTHPlate; cam: Cam; frame: number }> = ({ e, plate, cam, frame }) => {
  const box = chipBox(e.text, e.chip);
  const target = pointAt(plate, cam, e.at[0], e.at[1]);
  const a = leaderStart(box, target);
  const k = easeOut((frame - e.frame - 2) / TIMING.leaderIn);
  if (k <= 0) return null;
  const color = TONE[e.tone ?? "white"];
  const x = a[0] + (target[0] - a[0]) * k, y = a[1] + (target[1] - a[1]) * k;
  return (
    <g>
      <line x1={a[0]} y1={by(a[1])} x2={x} y2={by(y)} stroke={color} strokeWidth={2.5} opacity={0.9} />
      {k >= 1 && <circle cx={target[0]} cy={by(target[1])} r={7} fill={color} stroke={BG} strokeWidth={2} />}
    </g>
  );
};

const Chip: React.FC<{ e: UTHCallout; frame: number }> = ({ e, frame }) => {
  const box = chipBox(e.text, e.chip);
  const o = easeOut((frame - e.frame) / TIMING.chipIn);
  const color = TONE[e.tone ?? "white"];
  return (
    <div style={{
      position: "absolute", left: box[0], top: box[1] - G.plateTop, width: box[2] - box[0], height: box[3] - box[1],
      borderRadius: 10, background: "rgba(14,15,18,0.88)", border: `2px solid ${e.tone && e.tone !== "white" ? color : "#3A3C43"}`,
      display: "flex", alignItems: "center", justifyContent: "center", fontFamily: SANS, fontWeight: 700,
      fontSize: G.chipFontPx, letterSpacing: 2, color, textTransform: "uppercase", whiteSpace: "nowrap",
      opacity: o >= 1 ? undefined : o, transform: o >= 1 ? undefined : `translateY(${(1 - o) * 10}px)`,
    }}>
      {e.text}
    </div>
  );
};

const Stat: React.FC<{ e: UTHStat; frame: number }> = ({ e, frame }) => {
  const t = frame - e.frame;
  const o = easeOut(t / TIMING.chipIn);
  const v = statValue(e.from ?? 0, e.value, t);
  const top = (e.place === "upper" ? G.statUpperTop : G.statLowerTop) - G.plateTop;
  const chipIn = easeOut((t - TIMING.statCount) / TIMING.chipIn);
  return (
    <div style={{ position: "absolute", right: W - G.statRight, top, textAlign: "right", opacity: o >= 1 ? undefined : o }}>
      <div style={{ fontFamily: SANS, fontWeight: 700, fontSize: G.statFontPx, lineHeight: 1, color: WHITE, letterSpacing: -4 }}>
        {statText(v, e.decimals ?? 0, e.prefix ?? "", e.suffix ?? "")}
      </div>
      <div style={{ fontFamily: SANS, fontWeight: 700, fontSize: 36, letterSpacing: 3, color: "#D8D8DA", textTransform: "uppercase", marginTop: 6, whiteSpace: "nowrap" }}>
        {e.label}
      </div>
      {e.chip && chipIn > 0 && (
        <div style={{ display: "inline-block", marginTop: 12, padding: "6px 18px", border: `2px solid ${BLUE_HOT}`, borderRadius: 8, fontFamily: MONO, fontWeight: 700, fontSize: 34, color: WHITE, opacity: chipIn >= 1 ? undefined : chipIn }}>
          {e.chip}
        </div>
      )}
    </div>
  );
};

/** A chart's points in frame pixels across the chart box. */
function chartPoints(points: number[]): [number, number][] {
  const lo = Math.min(...points), hi = Math.max(...points);
  const pad = (hi - lo || 1) * 0.1;
  return points.map((v, i) => [
    G.chartLeft + ((G.chartRight - G.chartLeft) * i) / Math.max(1, points.length - 1),
    G.chartBottom - ((v - lo + pad) / (hi - lo + 2 * pad)) * (G.chartBottom - G.chartTop),
  ]);
}

const ChartLine: React.FC<{ e: UTHChart; frame: number }> = ({ e, frame }) => {
  const pts = chartPoints(e.points);
  const t = clamp01((frame - e.frame) / (e.duration ?? 88));
  const drawn = partialPolyline(pts, easeOut(t)).split(" ");
  const head = drawn[drawn.length - 1].split(",").map(Number);
  return (
    <g>
      <line x1={G.chartLeft} x2={G.chartRight} y1={by(G.chartBottom)} y2={by(G.chartBottom)} stroke="#3A3C43" strokeWidth={2} />
      <polyline points={drawn.join(" ")} fill="none" stroke={BLUE_HOT} strokeWidth={4} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={head[0]} cy={head[1]} r={9} fill={WHITE} />
    </g>
  );
};

const ChartText: React.FC<{ e: UTHChart; frame: number }> = ({ e, frame }) => {
  const t = clamp01((frame - e.frame) / (e.duration ?? 88));
  const k = easeOut(t) * (e.points.length - 1);
  const i = Math.min(e.points.length - 2, Math.floor(k));
  const v = e.points.length > 1 ? e.points[i] + (e.points[i + 1] - e.points[i]) * (k - i) : e.points[0];
  const typed = e.label.slice(0, Math.max(0, frame - e.frame));
  const chipIn = easeOut((frame - e.frame - (e.duration ?? 88)) / TIMING.chipIn);
  return (
    <>
      <div style={{ position: "absolute", right: W - G.chartRight, top: G.chartTop - 250 - G.plateTop, textAlign: "right" }}>
        <div style={{ fontFamily: SANS, fontWeight: 700, fontSize: 150, lineHeight: 1, color: WHITE, letterSpacing: -4 }}>
          {statText(v, e.decimals ?? 0, e.prefix ?? "", e.suffix ?? "")}
        </div>
        {e.chip && chipIn > 0 && (
          <div style={{ display: "inline-block", marginTop: 10, padding: "6px 18px", background: BLUE, borderRadius: 8, fontFamily: MONO, fontWeight: 700, fontSize: 34, color: WHITE, opacity: chipIn >= 1 ? undefined : chipIn }}>
            {e.chip}
          </div>
        )}
      </div>
      <div style={{ position: "absolute", left: G.chartLeft, top: G.chartBottom + 18 - G.plateTop, fontFamily: MONO, fontWeight: 500, fontSize: 28, color: GREY, whiteSpace: "nowrap" }}>
        {typed}
      </div>
    </>
  );
};

// ── the bottom third ─────────────────────────────────────────────────────────
const Counters: React.FC<{ e: UTHCounters; frame: number }> = ({ e, frame }) => {
  const t = frame - e.frame;
  const n = e.values.length;
  const cw = G.counterWidth / n;
    const settledAll = t >= TIMING.tickFrames;
  const changedIdx = e.values.map((v, i) => (v.from !== v.to ? i : -1)).filter((i) => i >= 0);
  return (
    <div style={{ position: "absolute", left: G.counterLeft, top: G.counterTop, width: G.counterWidth, height: 110 }}>
      {e.values.map((v, i) => {
        const val = counterValue(v.from, v.to, t);
        const changed = v.from !== v.to && t >= TIMING.tickStep;
        const enter = easeOut((t + 1 - i * 2) / TIMING.chipIn);
        return (
          <div key={i} style={{
            position: "absolute", left: i * cw, width: cw, textAlign: "center", fontFamily: MONO, fontSize: 64,
            fontWeight: changed ? 700 : 500, color: changed ? WHITE : GREY, opacity: enter >= 1 ? undefined : enter,
          }}>
            {String(val).padStart(2, "0")}
          </div>
        );
      })}
      {settledAll && changedIdx.length > 0 && (
        <svg width={G.counterWidth} height={30} style={{ position: "absolute", left: 0, top: 82 }}>
          <polyline
            points={`${changedIdx[0] * cw + 12},4 ${changedIdx[0] * cw + 12},16 ${(changedIdx[changedIdx.length - 1] + 1) * cw - 12},16 ${(changedIdx[changedIdx.length - 1] + 1) * cw - 12},4`}
            fill="none" stroke={WHITE} strokeOpacity={0.7} strokeWidth={2.5} />
        </svg>
      )}
    </div>
  );
};

// ── the scene ─────────────────────────────────────────────────────────────────
export default function UnderTheHood({ underTheHood, words = [] }: { underTheHood?: UnderTheHoodData; durationInFrames?: number; words?: Word[] }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  useUthFonts("UnderTheHood");
  const data: UnderTheHoodData = underTheHood && underTheHood.plates?.length ? underTheHood : { plates: [{ start: 0, events: [] }] };
  usePlateImages([...new Set(data.plates.map((p) => p.image).filter((v): v is string => !!v))]);
  const i = plateIndexAt(data, frame);
  const plate = data.plates[i];
  const cam = camAt(data, i, frame, fps);
  const under = cam.opacity < 1 && i > 0 && plate.enter !== "zoom" ? i - 1 : -1;
  const camUnder = under >= 0 ? camAt(data, under, frame, fps) : null;
  const up = eventsUp(plate, frame);
  // a zoom-through rushes the camera into the next photograph: what is pinned
  // to this one leaves with it over the zoom's first frames
  const nextPlate = data.plates[i + 1];
  const zoomFrom = nextPlate && nextPlate.enter === "zoom" ? nextPlate.start - TIMING.zoomOut : Infinity;
  const pinnedOpacity = frame < zoomFrom ? 1 : clamp01(1 - (frame - zoomFrom + 1) / 3);
  const of = <T extends UTHEvent["type"]>(t: T) => up.filter((e): e is Extract<UTHEvent, { type: T }> => e.type === t);
  // the counter row and footnote hold until the next plate replaces them
  const counters = of("counters").pop();
  const footnote = of("footnote").pop();
  const chart = of("chart").pop();
  const stat = of("stat").pop();
  const track = poseTrack(data);
  const { pose, dissolveFrom } = poseAt(track, frame);
  const mouth = mouthAt(words, frame);
  const blink = blinkAt(frame);

  return (
    <AbsoluteFill style={{ background: BG, width: W, height: H, overflow: "hidden" }}>
      <Grid top={G.plateBottom} height={H - G.plateBottom} />
      <div style={{ position: "absolute", left: 0, top: G.plateTop, width: W, height: BAND_H, overflow: "hidden" }}>
        {camUnder && <Plate plate={data.plates[under]} cam={{ ...camUnder, opacity: 1 }} />}
        <Plate plate={plate} cam={cam} />
        {!plate.image && <Grid top={0} height={BAND_H} />}
        <EdgeFade />
        <div style={{ position: "absolute", inset: 0, opacity: pinnedOpacity === 1 ? undefined : pinnedOpacity }}>
        <svg width={W} height={BAND_H} style={{ position: "absolute", left: 0, top: 0 }}>
          {of("outline").map((e, k) => <Outline key={`o${k}`} e={e} plate={plate} cam={cam} frame={frame} />)}
          {of("arcs").map((e, k) => <Arcs key={`a${k}`} e={e} plate={plate} cam={cam} frame={frame} />)}
          {of("callout").map((e, k) => <Leader key={`l${k}`} e={e} plate={plate} cam={cam} frame={frame} />)}
          {chart && <ChartLine e={chart} frame={frame} />}
        </svg>
        {of("callout").map((e, k) => <Chip key={`c${k}`} e={e} frame={frame} />)}
        {stat && <Stat e={stat} frame={frame} />}
        {chart && <ChartText e={chart} frame={frame} />}
        </div>
      </div>
      {counters && <Counters e={counters} frame={frame} />}
      {footnote && (
        <div style={{ position: "absolute", left: G.counterLeft, top: G.footnoteTop, width: G.presenterLeft - G.counterLeft - 20, fontFamily: SANS, fontWeight: 400, fontSize: 28, color: DIM, whiteSpace: "nowrap" }}>
          {footnote.text}
        </div>
      )}
      {dissolveFrom && <PresenterSprite pose={dissolveFrom} mouth={mouth} blink={blink} left={G.presenterLeft} top={G.presenterTop} opacity={0.5} />}
      <PresenterSprite pose={pose} mouth={mouth} blink={blink} left={G.presenterLeft} top={G.presenterTop} opacity={dissolveFrom ? 0.5 : 1} />
    </AbsoluteFill>
  );
}
