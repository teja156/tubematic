/*
 * FlatVectorScience: the whole of a Flat Vector Science video, as one scene.
 *
 * Flat, outline-free glowing subjects drift on a dark abyss, a night sky or
 * the inside of a body, named by pills whose words light as they are spoken.
 * Shots show scale: one subject with a measuring rule, a ladder of ever larger
 * things (each new one growing in from beyond the frame while the last
 * shrinks to a mark), a power-of-ten zoom with a scale bar, a descent through
 * the ocean with a depth counter and a gauge, a process in stages. Something
 * always drifts. One red accent per shot. Captions are the shared Subtitles
 * layer, small and shadowed at 78%.
 *
 * The agent never writes this file's kind of code: it writes
 * `props.flatVector` (shots timed to the narration, props from the library or
 * drawn for the video as static SVG), which the MCP server validates against
 * ./flatVector/contract.ts before the video can render.
 *
 * Kept cheap on the CPU renderer (software GL): the world is one Canvas 2D
 * layer; every prop is a bitmap drawn once (./flatVector/sprites.ts) and only
 * moved; backdrops, specks and halos are canvases drawn once; text is DOM over
 * the canvas, with no filters and no stroke-dasharray.
 */
import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { AbsoluteFill, cancelRender, continueRender, delayRender, interpolateColors, useCurrentFrame, useVideoConfig } from "remotion";
import {
  BACKDROPS, GEOMETRY, H, TIMING, W, grouped, pillWidth, propScale, type CustomProp, type DescentShot, type FlatVectorData,
  type LadderShot, type Pill, type Shot, type StagesShot, type SubjectShot, type ZoomShot,
} from "./flatVector/contract";
import { COLORS, boxOf, drawShot, makeBackdrop, makeDescent, makeSpeck, type Assets } from "./flatVector/draw";
import { useFlatVectorFonts, LABEL, ROUND } from "./flatVector/fonts";
import { PROPS } from "./flatVector/props";
import { halo, rasterise } from "./flatVector/sprites";
import {
  counterValue, depthAt, drift, easeInOut, easeOut, itemScale, pictureAts, ramp, shotAts, shotEnd, shotIndexAt, stepAt, transitionAt,
} from "./flatVector/stage";

const G = GEOMETRY;
const T = TIMING;

/** Every prop the video uses, its own drawings imported, all rasterised before the first frame. */
function useAssets(data: FlatVectorData): Assets | null {
  const [assets, setAssets] = useState<Assets | null>(null);
  const [handle] = useState(() => delayRender("FlatVectorScience: drawing the props"));
  useEffect(() => {
    const used = new Set<string>();
    for (const s of data.shots) {
      if (s.kind === "subject") s.items.forEach((i) => used.add(i.what));
      if (s.kind === "ladder") s.rungs.forEach((r) => used.add(r.what));
      if (s.kind === "zoom") s.levels.forEach((l) => used.add(l.what));
      if (s.kind === "descent") s.layers.forEach((l) => l.what && used.add(l.what));
      if (s.kind === "stages") s.steps.forEach((st) => used.add(st.what));
    }
    const custom = data.customProps ?? [];
    const load = async () => {
      const drawings: Record<string, React.ReactNode> = {};
      await Promise.all(
        custom.filter((c: CustomProp) => used.has(c.id)).map((c) =>
          import(`./../generated/${c.src}.tsx`).then((m: { default: React.FC }) => {
            drawings[c.id] = React.createElement(m.default);
          }),
        ),
      );
      const sprites: Assets["sprites"] = {};
      const lights = new Set<string>();
      for (const what of used) {
        const lib = PROPS[what];
        const node = lib ? lib.draw() : drawings[what];
        if (!node) continue;
        const box = boxOf(what, data);
        // drawn at the largest size it is ever shown: size l, with room for a pop or a zoom
        const scale = Math.min(2, (propScale(box, "l") * 1.25));
        sprites[what] = await rasterise(node, box[0], box[1], scale);
        const light = lib ? lib.light : custom.find((c) => c.id === what)?.light;
        if (light) lights.add(light);
      }
      const halos: Assets["halos"] = {};
      for (const l of lights) halos[l] = halo(l);
      const backdrops: Assets["backdrops"] = {};
      for (const b of BACKDROPS) if (data.shots.some((s) => s.backdrop === b)) backdrops[b] = makeBackdrop(b);
      setAssets({ sprites, halos, backdrops, descent: makeDescent(), speck: makeSpeck(false), blur: makeSpeck(true) });
    };
    load()
      .then(() => continueRender(handle))
      .catch((err) => cancelRender(err));
    // The props are static for the whole render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [handle]);
  return assets;
}

/** Paints the frame: the shot, or both shots of a transition. */
function paint(ctx: CanvasRenderingContext2D, scratch: HTMLCanvasElement, a: Assets, data: FlatVectorData, frame: number) {
  ctx.globalAlpha = 1;
  ctx.globalCompositeOperation = "source-over";
  const tr = transitionAt(data, frame);
  const cur = shotIndexAt(data, frame);
  if (!tr) {
    drawShot(ctx, a, data, data.shots[cur], frame);
    return;
  }
  const prev = data.shots[tr.into - 1];
  const next = data.shots[tr.into];
  if (tr.kind === "flash") {
    drawShot(ctx, a, data, next, frame);
    ctx.fillStyle = "#ffffff";
    ctx.globalAlpha = 1 - tr.progress;
    ctx.fillRect(0, 0, W, H);
    ctx.globalAlpha = 1;
    return;
  }
  if (tr.kind === "push") {
    // push through the old shot: it scales up from the centre and fades into the new one
    const sctx = scratch.getContext("2d")!;
    drawShot(sctx, a, data, prev, frame);
    drawShot(ctx, a, data, next, frame);
    const k = 1 + 2.5 * easeInOut(tr.progress);
    ctx.globalAlpha = 1 - easeInOut(tr.progress);
    ctx.drawImage(scratch, W / 2 - (W * k) / 2, H * 0.48 - (H * k) / 2, W * k, H * k);
    ctx.globalAlpha = 1;
    return;
  }
  // lens: the new shot opens inside a growing circle with a cyan ring
  drawShot(ctx, a, data, prev, frame);
  const r = 40 + 1180 * easeInOut(tr.progress);
  const [cx, cy] = G.slot.center;
  ctx.save();
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.clip();
  drawShot(ctx, a, data, next, frame);
  ctx.restore();
  ctx.strokeStyle = "#7DD3DC";
  ctx.lineWidth = 8;
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.stroke();
}

// ── text over the world ─────────────────────────────────────────────────────
const Pills: React.FC<{ shot: SubjectShot; frame: number }> = ({ shot, frame }) => {
  const list = shot.pills ?? [];
  return (
    <>
      {list.map((p: Pill, i) => {
        const item = shot.items.find((it) => it.slot === p.on);
        const at = p.parts[0].at;
        if (!item || frame < at) return null;
        const [ax0, ay0] = G.slot[p.on];
        const d = drift(frame, shot.items.indexOf(item) + 1);
        const ax = ax0 + d.dx, ay = ay0 + d.dy;
        const grow = easeOut(ramp(frame, at + 3, T.pillGrow));
        const reveal = easeOut(ramp(frame, at + 7, T.pillReveal));
        const pop = 0.88 + 0.12 * easeOut(ramp(frame, at + 3, 8));
        const line = easeOut(ramp(frame, at, 9));
        const width = Math.min(G.pillMaxWidth, pillWidth(p.parts));
        // the pill sits above its item (below it when the item is high), clamped inside the safe width
        const above = ay0 > 760;
        const y = above ? ay0 - 330 : ay0 + 300;
        const x = Math.max(G.safeLeft, Math.min(G.safeRight - width, ax - 60));
        const ex = x + 36, ey = above ? y + 38 : y - 38;
        return (
          <React.Fragment key={i}>
            <svg width={W} height={H} style={{ position: "absolute", left: 0, top: 0 }}>
              <line x1={ax} y1={ay} x2={ax + (ex - ax) * line} y2={ay + (ey - ay) * line} stroke={COLORS.white} strokeOpacity={0.75} strokeWidth={3} />
              <circle cx={ax} cy={ay} r={9 * line} fill={COLORS.white} />
            </svg>
            <div style={{ position: "absolute", left: x, top: y - G.pillHeight / 2, transform: `scale(${pop.toFixed(3)})`, transformOrigin: "24px 50%" }}>
              <div style={{
                display: "flex", alignItems: "center", gap: 18, whiteSpace: "nowrap", height: G.pillHeight, padding: "0 30px",
                borderRadius: G.pillHeight / 2, background: "rgba(4,16,20,0.82)",
                clipPath: `inset(0 calc((100% - ${G.pillHeight}px) * ${(1 - grow).toFixed(3)}) 0 0 round ${G.pillHeight / 2}px)`,
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 18, clipPath: `inset(0 ${((1 - reveal) * 100).toFixed(1)}% 0 0)` }}>
                  {p.parts.map((part, k) => {
                    const lit = ramp(frame, part.at, T.light);
                    const color = interpolateColors(lit, [0, 1], [COLORS.unlit, part.red ? COLORS.red : COLORS.white]);
                    return (
                      <React.Fragment key={k}>
                        {k > 0 ? <div style={{ width: 9, height: 9, borderRadius: 5, background: COLORS.gold, opacity: 0.85 }} /> : null}
                        <span style={{ fontFamily: LABEL, fontWeight: 800, fontSize: G.pillText, letterSpacing: "0.06em", color }}>{part.text}</span>
                      </React.Fragment>
                    );
                  })}
                </div>
              </div>
            </div>
          </React.Fragment>
        );
      })}
    </>
  );
};

const DIGIT_H = 132;
/** A rolling odometer: each digit flicks over in the last quarter of its step. */
const Odometer: React.FC<{ value: number; unit: string; red: number }> = ({ value, unit, red }) => {
  const v = Math.max(0, value);
  const n = Math.max(1, Math.floor(v).toString().length);
  const cols: React.ReactNode[] = [];
  for (let k = n - 1; k >= 0; k--) {
    const p = Math.pow(10, k);
    const digit = Math.floor(v / p) % 10;
    const rest = v % p;
    const raw = k === 0 ? v % 1 : Math.min(1, Math.max(0, rest - (p - 1)));
    const frac = easeInOut(Math.min(1, Math.max(0, (raw - 0.75) / 0.25)));
    cols.push(
      <div key={`d${k}`} style={{ width: 0.6 * DIGIT_H, height: DIGIT_H, overflow: "hidden", position: "relative" }}>
        <div style={{ position: "absolute", left: 0, top: -(digit + frac) * DIGIT_H }}>
          {[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 0].map((dg, i) => (
            <div key={i} style={{ height: DIGIT_H, lineHeight: `${DIGIT_H}px`, textAlign: "center", width: 0.6 * DIGIT_H }}>{dg}</div>
          ))}
        </div>
      </div>,
    );
    if (k % 3 === 0 && k > 0) cols.push(<div key={`c${k}`} style={{ width: 0.24 * DIGIT_H, height: DIGIT_H, lineHeight: `${DIGIT_H}px` }}>,</div>);
  }
  return (
    <div style={{ display: "flex", alignItems: "flex-end", fontFamily: ROUND, fontWeight: 600, fontSize: 120, color: interpolateColors(red, [0, 1], [COLORS.white, COLORS.red]) }}>
      {cols}
      <div style={{ fontSize: 64, lineHeight: `${DIGIT_H}px`, marginLeft: 14, height: DIGIT_H, opacity: 0.9 }}>{unit}</div>
    </div>
  );
};

const Readout: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div style={{ position: "absolute", left: G.safeLeft, top: G.readoutTop }}>
    <div style={{ fontFamily: LABEL, fontWeight: 800, fontSize: 40, letterSpacing: "0.08em", color: COLORS.white, opacity: 0.8 }}>{label}</div>
    {children}
  </div>
);

/** The value pill of a ladder rung, a zoom level or a stage: centred under the readout row. */
const Title: React.FC<{ text: string; value?: string; red?: boolean; k: number; low?: boolean }> = ({ text, value, red, k, low }) => (
  <div style={{ position: "absolute", left: 0, right: 0, top: low ? G.readoutTop + 220 : G.readoutTop + 40, display: "flex", justifyContent: "center", opacity: k }}>
    <div style={{ display: "flex", gap: 18, alignItems: "center", height: G.pillHeight, padding: "0 30px", borderRadius: G.pillHeight / 2, background: "rgba(4,16,20,0.82)", whiteSpace: "nowrap" }}>
      <span style={{ fontFamily: LABEL, fontWeight: 800, fontSize: G.pillText, letterSpacing: "0.06em", color: COLORS.white }}>{text}</span>
      {value ? <div style={{ width: 9, height: 9, borderRadius: 5, background: COLORS.gold }} /> : null}
      {value ? <span style={{ fontFamily: LABEL, fontWeight: 800, fontSize: G.pillText, letterSpacing: "0.06em", color: red ? COLORS.red : COLORS.white }}>{value}</span> : null}
    </div>
  </div>
);

const Overlay: React.FC<{ data: FlatVectorData; frame: number; total: number }> = ({ data, frame, total }) => {
  const i = shotIndexAt(data, frame);
  const shot: Shot = data.shots[i];
  if (!shot) return null;
  const out: React.ReactNode[] = [];
  // the counter keeps the last shot's value as its start, so a value rolls on across a cut
  if (shot.counter) {
    const prevCounter = [...data.shots.slice(0, i)].reverse().find((s) => s.counter)?.counter;
    const v = counterValue(shot.counter, frame, prevCounter ? prevCounter.value : 0);
    const red = shot.counter.red ? ramp(frame, shot.counter.at + T.roll, 6) : 0;
    out.push(<Readout key="c" label={shot.counter.label.toUpperCase()}><Odometer value={v} unit={shot.counter.unit} red={red} /></Readout>);
  }
  if (shot.kind === "subject") {
    out.push(<Pills key="p" shot={shot} frame={frame} />);
    if (shot.rule) {
      const item = shot.items.find((it) => it.slot === shot.rule!.beside);
      if (item && frame >= shot.rule.at) {
        const box = boxOf(item.what, data);
        const s = propScale(box, item.size) * itemScale(item, frame);
        const hgt = box[1] * s;
        const [cx, cy] = G.slot[item.slot];
        const x = Math.min(G.safeRight - 40, cx + (box[0] * s) / 2 + 40);
        const k = easeOut(ramp(frame, shot.rule.at, 12));
        out.push(
          <React.Fragment key="r">
            <svg width={W} height={H} style={{ position: "absolute", left: 0, top: 0 }}>
              <rect x={x} y={cy - (hgt * k) / 2} width={6} height={hgt * k} fill={COLORS.white} opacity={0.85} />
              <rect x={x - 14} y={cy - (hgt * k) / 2} width={34} height={6} fill={COLORS.white} opacity={0.85} />
              <rect x={x - 14} y={cy + (hgt * k) / 2 - 6} width={34} height={6} fill={COLORS.white} opacity={0.85} />
            </svg>
            <div style={{ position: "absolute", left: Math.min(x + 28, G.safeRight - 220), top: cy - 24, fontFamily: LABEL, fontWeight: 800, fontSize: 40, letterSpacing: "0.06em", color: COLORS.white, opacity: k, whiteSpace: "nowrap" }}>
              {shot.rule.label.toUpperCase()}
            </div>
          </React.Fragment>,
        );
      }
    }
  } else if (shot.kind === "ladder" || shot.kind === "zoom" || shot.kind === "stages") {
    // titles light on their own words; the zoom's scale bar follows the picture, there from the shot's start
    const { index, progress } = stepAt(shot.kind === "zoom" ? pictureAts(shot) : shotAts(shot), frame);
    if (index >= 0) {
      const k = Math.min(1, progress * 2);
      if (shot.kind === "ladder") {
        const r = (shot as LadderShot).rungs[index];
        out.push(<Title key="t" text={r.label.toUpperCase()} value={r.value.toUpperCase()} red={r.red} k={k} />);
      } else if (shot.kind === "stages") {
        const st = (shot as StagesShot).steps[index];
        out.push(<Title key="t" text={`${index + 1}`} value={st.label.toUpperCase()} red={st.red} k={k} />);
      } else {
        // the scale bar: it shrinks as the camera pulls back, then snaps to full width as its label jumps
        const lv = (shot as ZoomShot).levels[index];
        const bar = 360 * (progress < 0.85 ? 1 - 0.9 * (progress / 0.85) : 1);
        out.push(
          <div key="z" style={{ position: "absolute", left: (W - 360) / 2, top: G.stripY, width: 360 }}>
            <div style={{ height: 8, width: bar, background: lv.red ? COLORS.red : COLORS.white, borderRadius: 4, opacity: 0.9 }} />
            <div style={{ fontFamily: LABEL, fontWeight: 800, fontSize: 40, letterSpacing: "0.06em", color: lv.red ? COLORS.red : COLORS.white, marginTop: 10 }}>
              {(progress < 0.85 && index > 0 ? (shot as ZoomShot).levels[index - 1].label : lv.label).toUpperCase()}
            </div>
          </div>,
        );
      }
    }
  } else if (shot.kind === "descent") {
    const ds = shot as DescentShot;
    const depth = depthAt(ds, frame);
    const max = ds.layers[ds.layers.length - 1].value;
    const { index } = stepAt(shotAts(ds), frame);
    const top = 470, bot = 1240;
    const gy = (m: number) => top + (m / Math.max(1, max)) * (bot - top);
    const lastRed = ds.layers[ds.layers.length - 1].red && index === ds.layers.length - 1;
    out.push(
      <Readout key="d" label={ds.label.toUpperCase()}><Odometer value={depth} unit={ds.unit} red={lastRed ? ramp(frame, ds.layers[index].at + T.rung, 6) : 0} /></Readout>,
      <svg key="g" width={W} height={H} style={{ position: "absolute", left: 0, top: 0 }}>
        <rect x={80} y={top - 8} width={16} height={bot - top + 16} rx={8} fill={COLORS.white} opacity={0.14} />
        <rect x={80} y={top - 8} width={16} height={gy(depth) - top + 8} rx={8} fill={COLORS.white} opacity={0.7} />
        {ds.layers.map((l, k) => <circle key={k} cx={88} cy={gy(l.value)} r={depth >= l.value - 0.5 ? 11 : 7} fill={depth >= l.value - 0.5 ? (l.red ? COLORS.red : COLORS.gold) : COLORS.white} opacity={depth >= l.value - 0.5 ? 1 : 0.4} />)}
      </svg>,
    );
    if (index >= 0) {
      const l = ds.layers[index];
      out.push(<Title key="t" low text={l.name.toUpperCase()} value={`${grouped(l.value)} ${ds.unit}`.toUpperCase()} red={l.red} k={Math.min(1, ramp(frame, l.at, 8))} />);
    }
  }
  void total;
  return <>{out}</>;
};

export interface FlatVectorScienceProps {
  flatVector: FlatVectorData;
}

export default function FlatVectorScience({ flatVector }: FlatVectorScienceProps) {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  useFlatVectorFonts("FlatVectorScience");
  const data: FlatVectorData = flatVector ?? { shots: [] };
  const assets = useAssets(data);
  const canvas = useRef<HTMLCanvasElement>(null);
  const scratch = useMemo(() => {
    const c = document.createElement("canvas");
    c.width = W;
    c.height = H;
    return c;
  }, []);
  useLayoutEffect(() => {
    const ctx = canvas.current?.getContext("2d", { alpha: false });
    if (ctx && assets && data.shots.length) paint(ctx, scratch, assets, data, frame);
  });
  void shotEnd;
  return (
    <AbsoluteFill style={{ background: "#030c0f", width: W, height: H, overflow: "hidden" }}>
      <canvas ref={canvas} width={W} height={H} style={{ position: "absolute", left: 0, top: 0 }} />
      {assets ? <Overlay data={data} frame={frame} total={durationInFrames} /> : null}
    </AbsoluteFill>
  );
}
