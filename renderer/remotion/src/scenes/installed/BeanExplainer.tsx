/*
 * BeanExplainer: the whole of a Bean Explainer video, as one scene.
 *
 * A big-headed bean with a thick ink outline reacts on a flat colour field,
 * pose by pose on the narrator's words, while a section header, a badge,
 * props and short handwritten labels build up; with `list` on, a badge
 * carousel runs between sections. The agent never writes this file's kind of
 * code: it writes `props.beanExplainer` (sections, shots and events timed to
 * the narration, props chosen from a fixed library), which the MCP server
 * validates against ./beanExplainer/contract.ts before the video can render.
 *
 * Kept cheap on the CPU renderer (software GL), measured in CPU-seconds per
 * frame over the whole example video: 0.28 here, 0.17 for System Flow's
 * example, 0.10 for an empty frame with the same captions. What got it there:
 * - The bean is a cached bitmap (./beanExplainer/sprite.tsx). Drawn as live
 *   SVG it alone cost about 0.3 per frame; as a sprite, 0.07.
 * - Everything settles: springs end at exactly 1, marks stop pulsing after a
 *   second, a prop's act plays for TIMING.actFrames and then holds.
 * - TMDEV-196's rules: no SVG filters (shadows are flat translucent shapes),
 *   no gradients or patterns (the field is one flat colour), no
 *   stroke-dasharray (the X, the arrows and the header underline draw on by
 *   growing their path), the impact kick an SVG transform attribute.
 * Text that the audit must measure (header, title, labels) is HTML.
 *
 * Fonts are bundled in public/fonts and loaded before the first frame, so a
 * renderer with no internet access renders the same picture. Instrument Sans
 * is loaded here for the captions, which the pack points at it.
 */
import React, { useEffect, useState } from "react";
import { HAND, ROUND, useBeanFonts } from "./beanExplainer/fonts";
import { AbsoluteFill, cancelRender, continueRender, delayRender, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { BeanMarks, INK, LINE, RED, blendedPose, headPlace, squashAt, toBody, type BeanProps, type V } from "./beanExplainer/bean";
import { BeanSprite } from "./beanExplainer/sprite";
import {
  FIELDS, GEOMETRY, H, LIMITS, SECTION_COLORS, TIMING, W, wrapLabel,
  type BeanExplainerData, type BECustomProp, type BESection,
} from "./beanExplainer/contract";
import { WHOLE_PROP_ACTS, wholePropMotion } from "./beanExplainer/props";
import { LIBRARY_KIT, makeKit, type Drawing, type PropKit } from "./beanExplainer/kit";
import { BADGE_SLOT, STRIP, anchorOf, clamp01, ease, kickAt, sectionContentStart, settled, stageAt, type PropState, type StageState } from "./beanExplainer/stage";

const FLOOR = "#E8E8E8";
const FLOOR_LOW = "#DEDEDE";
const HEADER_CX = 445; // centred left of the badge
const HEADER_W = 740;

// ── a prop on stage ───────────────────────────────────────────────────────────
export const PropView: React.FC<{ p: PropState; frame: number; fps: number; kit: PropKit }> = ({ p, frame, fps, kit }) => {
  const Draw = kit.draw(p.prop);
  const box = kit.size(p.prop);
  if (!Draw) return null;
  const t = frame - p.since;
  let dx = 0, dy = 0, s = 1, op = 1;
  if (p.enter === "drop") {
    const k = clamp01(t / TIMING.propIn);
    dy = -1400 * (1 - k * k);
    const after = t - TIMING.propIn;
    if (after >= 0 && after < 7) s = 1 - 0.14 * Math.exp(-after / 1.8);
  } else if (p.enter === "slide") {
    const k = ease.out(clamp01(t / TIMING.propIn));
    dx = (p.x < W / 2 ? -1 : 1) * (W / 2 + box.w) * (1 - k);
  } else if (p.enter === "rise") {
    const k = ease.out(clamp01(t / TIMING.propIn));
    dy = 160 * (1 - k);
    op = k;
  } else {
    s = t < 0 ? 0 : settled(spring({ frame: t, fps, config: { stiffness: 160, damping: 14, mass: 0.6 } }), t);
  }
  // An act plays for TIMING.actFrames, then the prop holds; a prop with no
  // act is drawn at a fixed frame, so its idle details hold still too.
  const actT = p.actAt >= 0 ? Math.min(frame - p.actAt, TIMING.actFrames) : -1;
  const drawFrame = p.actAt >= 0 ? Math.min(frame, p.actAt + TIMING.actFrames) : p.since;
  const whole = (WHOLE_PROP_ACTS as readonly string[]).includes(p.act);
  const [mx, my, mr, ms, pivot] = whole ? wholePropMotion(p.act, actT, box.h) : [0, 0, 0, 1, 0];
  const scale = p.scale * s * ms;
  if (scale <= 0.001 || op <= 0) return null;
  return (
    <g opacity={op} transform={`translate(${p.x + dx + mx} ${p.y + dy + my}) scale(${scale}) rotate(${mr} 0 ${pivot})`}>
      <Draw frame={drawFrame} actT={whole ? -1 : actT} text={p.text} round={ROUND} hand={HAND} />
    </g>
  );
};

/** A path drawn on from its start: the first `t` (0..1) of a quadratic curve, as polyline points. */
function partialQuad(a: V, c: V, b: V, t: number, steps = 16): string {
  const pts: string[] = [];
  const n = Math.max(1, Math.round(steps * t));
  for (let i = 0; i <= n; i++) {
    const u = (t * i) / n;
    const x = (1 - u) ** 2 * a[0] + 2 * (1 - u) * u * c[0] + u * u * b[0];
    const y = (1 - u) ** 2 * a[1] + 2 * (1 - u) * u * c[1] + u * u * b[1];
    pts.push(`${x.toFixed(1)},${y.toFixed(1)}`);
  }
  return pts.join(" ");
}

const Strike: React.FC<{ state: StageState; target: string; since: number; frame: number; kit: PropKit }> = ({ state, target, since, frame, kit }) => {
  const p = state.props.find((q) => q.key === target);
  if (!p) return null;
  const box = kit.size(p.prop);
  const hw = (box.w * p.scale) / 2 * 0.8, hh = (box.h * p.scale) / 2 * 0.8;
  const t = clamp01((frame - since) / TIMING.drawOn);
  const a = clamp01(t * 2), b = clamp01(t * 2 - 1);
  const line = (x0: number, y0: number, x1: number, y1: number, k: number) =>
    k <= 0 ? null : (
      <g>
        <path d={`M ${x0},${y0} L ${x0 + (x1 - x0) * k},${y0 + (y1 - y0) * k}`} stroke={INK} strokeWidth={46} strokeLinecap="round" />
        <path d={`M ${x0},${y0} L ${x0 + (x1 - x0) * k},${y0 + (y1 - y0) * k}`} stroke={RED} strokeWidth={30} strokeLinecap="round" />
      </g>
    );
  return (
    <g transform={`translate(${p.x} ${p.y})`}>
      {line(-hw, -hh, hw, hh, a)}
      {line(hw, -hh, -hw, hh, b)}
    </g>
  );
};

const Arrow: React.FC<{ state: StageState; from: string; to: string; since: number; frame: number }> = ({ state, from, to, since, frame }) => {
  const a0 = anchorOf(state, from), b0 = anchorOf(state, to);
  if (!a0 || !b0) return null;
  const d = Math.hypot(b0[0] - a0[0], b0[1] - a0[1]) || 1;
  const ux = (b0[0] - a0[0]) / d, uy = (b0[1] - a0[1]) / d;
  const inset = Math.min(110, d * 0.28);
  const a: V = [a0[0] + ux * inset, a0[1] + uy * inset];
  const b: V = [b0[0] - ux * inset, b0[1] - uy * inset];
  const c: V = [(a[0] + b[0]) / 2 + uy * d * 0.18, (a[1] + b[1]) / 2 - Math.abs(ux) * d * 0.18];
  const t = clamp01((frame - since) / TIMING.drawOn);
  if (t <= 0) return null;
  const pts = partialQuad(a, c, b, t);
  const tipT = t;
  const tx = 2 * (1 - tipT) * (c[0] - a[0]) + 2 * tipT * (b[0] - c[0]);
  const ty = 2 * (1 - tipT) * (c[1] - a[1]) + 2 * tipT * (b[1] - c[1]);
  const ang = (Math.atan2(ty, tx) * 180) / Math.PI;
  const last = pts.split(" ").pop()!.split(",").map(Number);
  return (
    <g>
      <polyline points={pts} fill="none" stroke={INK} strokeWidth={26} strokeLinecap="round" strokeLinejoin="round" />
      <polyline points={pts} fill="none" stroke={RED} strokeWidth={12} strokeLinecap="round" strokeLinejoin="round" />
      {t >= 1 && (
        <g transform={`translate(${last[0]} ${last[1]}) rotate(${ang})`}>
          <path d="M 6,0 L -30,-24 L -30,24 Z" fill={RED} stroke={INK} strokeWidth={6} strokeLinejoin="round" />
        </g>
      )}
    </g>
  );
};

// ── header, badge and carousel ────────────────────────────────────────────────
export const Badge: React.FC<{ x: number; y: number; r: number; section: BESection; frame: number; kit: PropKit }> = ({ x, y, r, section, frame, kit }) => {
  const Draw = kit.draw(section.badge);
  const box = kit.size(section.badge);
  if (!Draw) return null;
  const k = (r * 1.25) / Math.max(box.w, box.h);
  return (
    <g transform={`translate(${x} ${y})`}>
      <circle cx={0} cy={r * 0.07} r={r} fill={INK} opacity={0.18} />
      <circle cx={0} cy={0} r={r} fill={SECTION_COLORS[section.color]} stroke={INK} strokeWidth={Math.max(4, (LINE * r) / 80)} />
      <g transform={`scale(${k})`}>
        <Draw frame={frame} actT={-1} text="" round={ROUND} hand={HAND} />
      </g>
    </g>
  );
};

const headerPx = (text: string) => Math.min(108, HEADER_W / (Math.max(text.length, 1) * 0.66));

const Header: React.FC<{ section: BESection; frame: number; at: number }> = ({ section, frame, at }) => {
  const k = frame - at;
  if (k < 0) return null;
  const px = headerPx(section.header);
  const pulse = k < 10 ? 0.06 * Math.exp(-k / 2.5) * Math.cos(k * 0.9) : 0;
  const enter = ease.outBack(clamp01(k / 6));
  const textW = Math.min(HEADER_W, section.header.length * px * 0.66);
  const draw = clamp01((k - 2) / 12);
  const base = 372;
  return (
    <>
      {draw > 0 && (
        // sized to the underline, not the frame: a full-frame layer costs a full-frame repaint
        <svg width={HEADER_W + 40} height={60} viewBox={`${HEADER_CX - HEADER_W / 2 - 20} ${base} ${HEADER_W + 40} 60`}
          style={{ position: "absolute", left: HEADER_CX - HEADER_W / 2 - 20, top: base }}>
          <polyline
            points={partialQuad([HEADER_CX - textW / 2, base + 34], [HEADER_CX, base + 22], [HEADER_CX + textW / 2, base + 26], draw)}
            fill="none" stroke={SECTION_COLORS[section.color]} strokeWidth={18} strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )}
      <div
        style={{
          position: "absolute", left: HEADER_CX - HEADER_W / 2, width: HEADER_W, top: base - px, height: px * 1.1,
          textAlign: "center", fontFamily: ROUND, fontWeight: 700, fontSize: px, lineHeight: 1.1, color: INK, letterSpacing: 2,
          whiteSpace: "nowrap", transform: k < 10 ? `scale(${(1 + pulse) * enter}, ${(1 - pulse) * enter})` : undefined,
        }}
      >
        {section.header}
      </div>
    </>
  );
};

const Carousel: React.FC<{ data: BeanExplainerData; c: NonNullable<StageState["carousel"]>; frame: number; fps: number; kit: PropKit }> = ({ data, c, frame, fps, kit }) => {
  const slide = spring({ frame: Math.max(0, c.t - 6), fps, config: { stiffness: 120, damping: 15, mass: 1 } });
  const pos = c.from + (c.to - c.from) * slide;
  const fade = clamp01(c.t / 4) * clamp01((TIMING.carousel - c.t) / 4);
  return (
    <g opacity={fade}>
      {data.sections.map((s, i) => {
        const x = W / 2 + STRIP.gap * (i - pos);
        if (x < -STRIP.big * 2 || x > W + STRIP.big * 2) return null;
        const dist = Math.min(1, Math.abs(x - W / 2) / STRIP.gap);
        const r = STRIP.big * (1 - 0.4 * dist);
        return (
          <g key={i}>
            <Badge x={x} y={STRIP.y} r={r} section={s} frame={frame} kit={kit} />
            {/* Only the name at the centre is read: long names on neighbouring
                badges ran into it, so they fade as they leave the centre, and the
                centre name is sized to fit the frame. */}
            {dist < 0.55 && (
              <text x={x} y={STRIP.y + r + 80} textAnchor="middle" fontSize={Math.min(58, 940 / (Math.max(s.header.length, 1) * 0.74))}
                fontWeight={700} fill={INK} opacity={1 - dist / 0.55} letterSpacing={1} style={{ fontFamily: ROUND }}>{s.header}</text>
            )}
          </g>
        );
      })}
    </g>
  );
};

// ── the video's own props ────────────────────────────────────────────────────
/**
 * The props the agent drew for this video, imported from generated/ and held
 * until they load: the frame waits, and a prop that will not load fails the
 * render (a frame without a prop the narration names would ship silently).
 */
function useCustomProps(list: BECustomProp[]): PropKit | null {
  const [drawings, setDrawings] = useState<Record<string, Drawing> | null>(list.length ? null : {});
  const [handle] = useState(() => (list.length ? delayRender("BeanExplainer: loading the video's own props") : null));
  useEffect(() => {
    if (handle === null) return;
    Promise.all(
      list.map((c) => import(`../generated/${c.src}.tsx`).then((m: { default: Drawing }) => [c.id, m.default] as const)),
    )
      .then((pairs) => {
        setDrawings(Object.fromEntries(pairs));
        continueRender(handle);
      })
      .catch((err) => cancelRender(err));
    // The props are static for the whole render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [handle]);
  return drawings === null ? null : list.length ? makeKit(list, drawings) : LIBRARY_KIT;
}

// ── the scene ─────────────────────────────────────────────────────────────────
export default function BeanExplainer({ beanExplainer, durationInFrames }: { beanExplainer?: BeanExplainerData; durationInFrames: number }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  useBeanFonts("BeanExplainer");
  const data = beanExplainer ?? { cast: [], sections: [], shots: [] };
  const loaded = useCustomProps(data.customProps ?? []);
  const kit = loaded ?? LIBRARY_KIT;
  const field = FIELDS[data.field ?? "yellow"] ?? FIELDS.yellow;
  const state = stageAt(data, durationInFrames, frame);
  const section = state && state.section >= 0 ? data.sections[state.section] : null;
  const contentAt = state && state.section >= 0 ? sectionContentStart(data, state.section) : 0;
  const cam = state ? kickAt(state.impacts, frame, fps) : { x: 0, y: 0, z: 0 };
  const camT = cam.x || cam.y || cam.z ? `translate(${cam.x} ${cam.y}) translate(540 1100) scale(${1 + cam.z}) translate(-540 -1100)` : undefined;
  const showStage = state && !state.carousel;
  const beanProps: { props: BeanProps; squash: [number, number] }[] = showStage
    ? state.beans.map((b) => {
        const aim = b.aimAt ? anchorOf(state, b.aimAt) : null;
        const props: BeanProps = {
          frame, fps, x: b.x, y: GEOMETRY.floorY + b.hopY, scale: b.scale,
          pose: b.pose, prevPose: b.prevPose, poseT: b.poseT, face: b.face, look: b.look, swapFrame: b.swapFrame,
          aim: aim ? toBody(b.x, GEOMETRY.floorY, b.scale, aim) : undefined,
          marks: b.marks, enter: b.enter, accessory: b.cast.accessory ?? "none", tint: b.cast.tint ?? "cream",
          seed: b.seed, font: ROUND, uid: `bean-${b.id}`, poseAt: b.poseAt,
        };
        return { props, squash: squashAt(frame, b.swapFrame) };
      })
    : [];

  return (
    <AbsoluteFill style={{ background: field, width: W, height: H, overflow: "hidden" }}>
      <svg width={W} height={H} style={{ position: "absolute", left: 0, top: 0 }}>
        <rect x={0} y={GEOMETRY.floorY} width={W} height={H - GEOMETRY.floorY} fill={FLOOR} />
        <rect x={0} y={GEOMETRY.floorY + 90} width={W} height={H - GEOMETRY.floorY} fill={FLOOR_LOW} />
        <line x1={0} x2={W} y1={GEOMETRY.floorY} y2={GEOMETRY.floorY} stroke={INK} strokeWidth={LINE} />
        {section && !state?.carousel && frame >= contentAt && <Badge x={BADGE_SLOT.x} y={BADGE_SLOT.y} r={BADGE_SLOT.r} section={section} frame={frame} kit={kit} />}
        {state?.carousel && <Carousel data={data} c={state.carousel} frame={frame} fps={fps} kit={kit} />}
        {showStage && (
          <g transform={camT}>
            {state.props.map((p) => <PropView key={p.key} p={p} frame={frame} fps={fps} kit={kit} />)}
          </g>
        )}
      </svg>
      {showStage && (
        <AbsoluteFill style={camT ? { transform: `translate(${cam.x}px, ${cam.y}px) scale(${1 + cam.z})`, transformOrigin: "540px 1100px" } : undefined}>
          {beanProps.map(({ props, squash }) => <BeanSprite key={props.uid} p={props} squash={squash} />)}
        </AbsoluteFill>
      )}
      {showStage && (
        <svg width={W} height={H} style={{ position: "absolute", left: 0, top: 0 }}>
          <g transform={camT}>
            {beanProps.map(({ props, squash }) => {
              const head = headPlace(blendedPose(props));
              const k = props.scale * props.enter;
              const hx = props.x + head.at[0] * k * squash[0], hy = props.y + head.at[1] * k * squash[1];
              return (
                <g key={props.uid} transform={`translate(${hx} ${hy}) rotate(${head.rot}) scale(${k})`}>
                  <BeanMarks marks={props.marks} frame={frame} fps={fps} font={ROUND} />
                </g>
              );
            })}
            {state.strikes.map((s, i) => <Strike key={i} state={state} target={s.target} since={s.since} frame={frame} kit={kit} />)}
            {state.arrows.map((a, i) => <Arrow key={i} state={state} from={a.from} to={a.to} since={a.since} frame={frame} />)}
          </g>
        </svg>
      )}
      {data.title && (
        <div style={{ position: "absolute", left: HEADER_CX - HEADER_W / 2, width: HEADER_W, top: 196, textAlign: "center", fontFamily: HAND, fontSize: 46, lineHeight: 1.2, color: INK, opacity: 0.8, whiteSpace: "nowrap" }}>
          {data.title.slice(0, LIMITS.titleChars)}
        </div>
      )}
      {section && !state?.carousel && <Header section={section} frame={frame} at={contentAt} />}
      {showStage && (
        <AbsoluteFill style={camT ? { transform: `translate(${cam.x}px, ${cam.y}px) scale(${1 + cam.z})`, transformOrigin: "540px 1100px" } : undefined}>
          {state.labels.map((l) => {
            const k = frame - l.since;
            const s = settled(spring({ frame: Math.max(0, k), fps, config: { stiffness: 260, damping: 15, mass: 0.6 } }), k);
            const lines = wrapLabel(l.text);
            return (
              <div
                key={l.key}
                style={{
                  position: "absolute", left: l.x - 400, width: 800, top: l.y - (lines.length * GEOMETRY.labelLinePx) / 2,
                  textAlign: "center", fontFamily: HAND, fontSize: GEOMETRY.labelFontPx, lineHeight: `${GEOMETRY.labelLinePx}px`,
                  color: l.red ? RED : INK, opacity: s >= 1 ? undefined : Math.min(1, s * 1.5),
                  transform: s >= 1 ? "rotate(-3deg)" : `scale(${0.7 + 0.3 * s}) rotate(-3deg)`,
                }}
              >
                {lines.map((ln, i) => <div key={i}>{ln}</div>)}
              </div>
            );
          })}
        </AbsoluteFill>
      )}
    </AbsoluteFill>
  );
}
