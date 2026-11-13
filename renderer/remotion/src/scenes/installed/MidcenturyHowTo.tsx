/*
 * MidcenturyHowTo: the whole of a Mid-century How-To video, as one scene.
 *
 * A 1950s classroom-film cartoon on warm paper: one flat ground colour per
 * step, a geometric gloved presenter whose body holds while his hand, eye and
 * brow act on the narrator's words, objects printed off-register from a
 * broken ink line, numbered step medallions, a press of the glove with a ring
 * burst, and a summary card. The agent never writes this file's kind of code:
 * it writes `props.midcenturyHowTo` (steps, shots and events timed to the
 * narration, objects from a fixed library or drawn for the video), which the
 * MCP server validates against ./midcenturyHowTo/contract.ts before render.
 *
 * Kept cheap on the CPU renderer (software GL):
 * - The presenter, every object, the hose arm and the medallions are cached
 *   bitmaps (./characterKit/sprite.tsx). Their wobble steps through three fixed
 *   phases on twos, so a held picture has three looks to cache and a cache hit
 *   costs nothing measurable.
 * - No SVG filters and no CSS gradients; the sunburst is flat wedges that never
 *   turn. No paper grain: measured, a tiled grain cost about 0.24 CPU-seconds
 *   per frame on top or underneath, and as one cached full-frame bitmap about
 *   as much (a full-frame image is the cost, whatever it shows). The
 *   off-register fills carry the printed look without it.
 * Measured over the whole example video: 0.35 CPU-seconds per frame, against
 * 0.25 for System Flow's example rendered the same day.
 * Text the layout audit must measure (the title, the step header, tags, labels
 * and insets) is HTML.
 */
import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { useCustomDrawings } from "./characterKit/customProps";
import { useStyleFonts } from "./characterKit/fonts";
import { FONTS } from "./midcenturyHowTo/fonts";
import { clamp01, ease, mix, onTwos, phaseOf, type Pt } from "./characterKit/geometry";
import { Sprite, type SpriteBox } from "./characterKit/sprite";
import {
  ALFA, Asterisk, CORAL, CREAM, Cel, INK, JOST, OLEO, PAPER, REG, Sparkle, TEAL, ellP, fitFont, jitter,
  type ObjectDrawProps,
} from "./midcenturyHowTo/cel";
import {
  GEOMETRY, GROUNDS, H, LIMITS, TIMING, W, objectSize, presenterFeetX,
  type MCCustomProp, type MidcenturyData,
} from "./midcenturyHowTo/contract";
import { DRAWINGS } from "./midcenturyHowTo/objects";
import {
  HoseArm, Presenter, presenterBoxFor, armToward, blendArm, poseArm, presenterKey, type ArmState,
} from "./midcenturyHowTo/presenter";
import { aimPoint, pressReach, stageAt, toPresenter, type ObjectState, type StageState } from "./midcenturyHowTo/stage";


type Drawing = React.FC<ObjectDrawProps>;
const FLOOR = GEOMETRY.floorY;

const drawingOf = (id: string, custom: Record<string, Drawing>): Drawing | undefined =>
  (DRAWINGS as Record<string, Drawing>)[id] ?? custom[id];

/** Frames since an act started, stepped on twos and frozen once it has played. */
const actFrames = (o: ObjectState, frame: number) =>
  o.actAt < 0 ? -1 : Math.min(onTwos(frame) - o.actAt, TIMING.actFrames + 2);

// ── ground ────────────────────────────────────────────────────────────────────
const Ground: React.FC<{ color: string; burst: boolean; burstAt: Pt }> = ({ color, burst, burstAt }) => {
  const tint = mix(color, PAPER, 0.22);
  const floor = mix(color, INK, 0.12);
  const n = 28;
  const [cx, cy] = burstAt;
  return (
    <svg width={W} height={H} style={{ position: "absolute", left: 0, top: 0 }}>
      <rect width={W} height={H} fill={color} />
      {burst &&
        Array.from({ length: n / 2 }, (_, k) => {
          const i = k * 2;
          const a0 = (i / n) * Math.PI * 2;
          const a1 = ((i + 1) / n) * Math.PI * 2;
          const R = 2400;
          return <path key={i} d={`M${cx} ${cy} L${cx + Math.cos(a0) * R} ${cy + Math.sin(a0) * R} L${cx + Math.cos(a1) * R} ${cy + Math.sin(a1) * R} Z`} fill={tint} />;
        })}
      <rect y={FLOOR} width={W} height={H - FLOOR} fill={floor} />
      <rect y={FLOOR + 210} width={W} height={H - FLOOR - 210} fill={mix(floor, INK, 0.08)} />
      <rect y={FLOOR - 2} width={W} height={5} fill={INK} />
    </svg>
  );
};

// ── an object on stage ───────────────────────────────────────────────────────
const ObjectSprite: React.FC<{ o: ObjectState; frame: number; fps: number; custom: Record<string, Drawing>; customSpecs: MCCustomProp[] }> = ({
  o, frame, custom, customSpecs,
}) => {
  const Draw = drawingOf(o.object, custom);
  if (!Draw) return null;
  const size = objectSize(o.object, customSpecs);
  const t = onTwos(frame) - o.since;
  const k = clamp01(t / TIMING.objectIn);
  let dx = 0, dy = 0, s = 1, op = 1;
  if (o.enter === "drop") dy = -1400 * (1 - k * k);
  else if (o.enter === "slide") dx = (o.x < W / 2 ? -1 : 1) * (W / 2 + size.w) * (1 - ease.out(k));
  else if (o.enter === "rise") {
    dy = 160 * (1 - ease.out(k));
    op = k;
  } else s = k >= 1 ? 1 : Math.max(0.01, ease.outBack(k));
  const actT = actFrames(o, frame);
  const phase = phaseOf(frame);
  const box: SpriteBox = { left: -size.w / 2 - 12, top: -size.h / 2 - 12, width: size.w + 24, height: size.h + 24 };
  const transform = dx || dy || s !== 1 ? `translate(${dx}px, ${dy}px) scale(${s})` : undefined;
  return (
    <Sprite
      id={`mc-obj|${o.object}|${o.text}|${o.act}|${actT}|${phase}`}
      draw={() => <Draw phase={phase} act={o.act} actT={actT} text={o.text} />}
      box={box} x={o.x} y={o.y} scale={o.scale} transform={transform} opacity={op} fonts={FONTS}
    />
  );
};

// ── the presenter ────────────────────────────────────────────────────────────
function presenterArm(state: StageState, frame: number): { arm: ArmState; back: ReturnType<typeof poseArm>["back"] } | null {
  const p = state.presenter;
  if (!p) return null;
  const aimNow = aimPoint(state, p.at);
  const aimPrev = aimPoint(state, p.prevAt);
  const cur = poseArm(p.pose, aimNow ? toPresenter(p.side, aimNow) : null, p.pose === "wave" ? onTwos(frame) - p.poseAt : -1);
  const prev = poseArm(p.prevPose, aimPrev ? toPresenter(p.side, aimPrev) : null);
  let arm = blendArm(prev.arm, cur.arm, p.poseT);
  const press = state.presses.find((q) => !q.hose);
  if (press) {
    const r = pressReach(press, frame);
    const tip = toPresenter(p.side, press.tip);
    const reach = armToward(tip, "point");
    if (r < 0) {
      // anticipation: the hand pulls back along its line
      const back = armToward([tip[0] + (tip[0] - 52) * r, tip[1] + (tip[1] + 588) * r], "point");
      arm = blendArm(arm, back, 1);
    } else arm = blendArm(arm, reach, r);
  }
  return { arm, back: cur.back };
}

const PresenterSprite: React.FC<{ data: MidcenturyData; state: StageState; frame: number }> = ({ data, state, frame }) => {
  const p = state.presenter;
  const pa = presenterArm(state, frame);
  if (!p || !pa) return null;
  const aim = aimPoint(state, p.at) ?? state.presses[0]?.tip ?? null;
  const look: Pt = aim ? [Math.sign(toPresenter(p.side, aim)[0]) * 4, Math.sign(toPresenter(p.side, aim)[1] + 700) * 3] : [3, 0];
  const look2 = {
    arm: pa.arm, back: pa.back, face: p.face, blink: p.blink, look,
    outfit: data.presenter?.outfit ?? "coral", hair: data.presenter?.hair ?? "dark", phase: phaseOf(frame),
  };
  return (
    <Sprite
      id={presenterKey(look2)}
      draw={() => <Presenter {...look2} />}
      box={presenterBoxFor(pa.arm, pa.back)}
      x={presenterFeetX(p.side)}
      y={FLOOR}
      flip={p.side === "right"}
    />
  );
};

const HoseSprite: React.FC<{ state: StageState; frame: number; outfit: MidcenturyData["presenter"] }> = ({ state, frame, outfit }) => {
  const press = state.presses.find((q) => q.hose);
  if (!press) return null;
  const r = pressReach(press, frame);
  const k = r < 0 ? 0.55 : 0.55 + 0.45 * r;
  const tip: Pt = [press.from[0] + (press.tip[0] - press.from[0]) * k, press.from[1] + (press.tip[1] - press.from[1]) * k];
  const left = Math.min(press.from[0], tip[0]) - 160;
  const top = Math.min(press.from[1], tip[1]) - 200;
  const box: SpriteBox = { left, top, width: Math.abs(press.from[0] - tip[0]) + 320, height: Math.abs(press.from[1] - tip[1]) + 400 };
  const phase = phaseOf(frame);
  const id = `mc-hose|${Math.round(press.from[0])}|${Math.round(press.from[1])}|${Math.round(tip[0] / 2) * 2}|${Math.round(tip[1] / 2) * 2}|${phase}|${outfit?.outfit ?? "coral"}`;
  return (
    <Sprite id={id} draw={() => <HoseArm from={press.from} tip={tip} phase={phase} outfit={outfit?.outfit ?? "coral"} />} box={box} x={0} y={0} />
  );
};

const RingBurst: React.FC<{ state: StageState; frame: number }> = ({ state, frame }) => (
  <svg width={W} height={H} style={{ position: "absolute", left: 0, top: 0 }}>
    {state.presses.map((p, i) => {
      const ring = onTwos(frame) - p.at;
      if (ring < 0 || ring >= 14) return null;
      const [x, y] = p.tip;
      return (
        <g key={i}>
          <g fill="none" stroke={CORAL} strokeWidth={6}>
            <circle cx={x} cy={y} r={20 + ring * 6} opacity={1 - ring / 14} />
            <circle cx={x} cy={y} r={6 + ring * 3.5} opacity={1 - ring / 14} />
          </g>
          {ring < 10 &&
            [200, 235, 270, 305, 340].map((a) => {
              const r0 = 52 + ring * 4;
              const rad = (a * Math.PI) / 180;
              return <line key={a} x1={x + Math.cos(rad) * r0} y1={y + Math.sin(rad) * r0} x2={x + Math.cos(rad) * (r0 + 22)} y2={y + Math.sin(rad) * (r0 + 22)} stroke={INK} strokeWidth={5} strokeLinecap="round" />;
            })}
        </g>
      );
    })}
  </svg>
);

// ── medallions, insets, labels ───────────────────────────────────────────────
const BADGE_BOX: SpriteBox = { left: -80, top: -80, width: 160, height: 160 };
const Badge: React.FC<{ kind: "check" | "cross"; phase: number }> = ({ kind, phase }) => (
  <g>
    <Cel d={ellP(0, 0, 64, 64)} fill={kind === "check" ? TEAL : CORAL} phase={phase} seed={kind === "check" ? 116 : 117} sw={5} />
    {kind === "check" ? (
      <path d="M-28 2 L-8 22 L30 -20" stroke={CREAM} strokeWidth={14} fill="none" strokeLinecap="round" strokeLinejoin="round" />
    ) : (
      <path d="M-22 -22 L22 22 M22 -22 L-22 22" stroke={CREAM} strokeWidth={14} fill="none" strokeLinecap="round" />
    )}
  </g>
);

const popScale = (frame: number, since: number) => {
  const k = clamp01((onTwos(frame) - since) / TIMING.pop);
  return k >= 1 ? 1 : Math.max(0.01, ease.outBack(k));
};

const Badges: React.FC<{ state: StageState; frame: number; customSpecs: MCCustomProp[] }> = ({ state, frame, customSpecs }) => (
  <>
    {state.badges.map((b, i) => {
      const o = state.objects.find((q) => q.key === b.target);
      if (!o) return null;
      const size = objectSize(o.object, customSpecs);
      const x = o.x + (size.w * o.scale) / 2 - 20;
      const y = o.y - (size.h * o.scale) / 2 + 20;
      const s = popScale(frame, b.since);
      const phase = phaseOf(frame);
      return (
        <Sprite key={i} id={`mc-badge|${b.kind}|${phase}`} draw={() => <Badge kind={b.kind} phase={phase} />} box={BADGE_BOX}
          x={x} y={y} transform={s !== 1 ? `scale(${s})` : undefined} />
      );
    })}
  </>
);

const OffCard: React.FC<{ seed: number; phase: number; fill: string; radius: number; border?: number; style?: React.CSSProperties; children: React.ReactNode }> = ({
  seed, phase, fill, radius, border = 4, style, children,
}) => {
  const [jx, jy] = jitter(seed, phase);
  return (
    <div style={{ position: "relative", ...style }}>
      <div style={{ position: "absolute", inset: 0, background: fill, borderRadius: radius, transform: `translate(${REG[0] + jx}px, ${REG[1] + jy}px)` }} />
      <div style={{ position: "relative", border: `${border}px solid ${INK}`, borderRadius: radius }}>{children}</div>
    </div>
  );
};

/** Where the line from an object's centre toward `to` leaves the object's box. */
function boxExit(o: ObjectState, size: { w: number; h: number }, to: Pt): Pt {
  const dx = to[0] - o.x, dy = to[1] - o.y;
  const hw = (size.w * o.scale) / 2, hh = (size.h * o.scale) / 2;
  const t = Math.min(dx ? hw / Math.abs(dx) : Infinity, dy ? hh / Math.abs(dy) : Infinity, 1);
  return [o.x + dx * t, o.y + dy * t];
}

const Insets: React.FC<{ state: StageState; frame: number; customSpecs: MCCustomProp[] }> = ({ state, frame, customSpecs }) => (
  <>
    {state.insets.map((n, i) => {
      const o = state.objects.find((q) => q.key === n.target);
      const from = o ? boxExit(o, objectSize(o.object, customSpecs), [n.x, n.y]) : null;
      const s = popScale(frame, n.since);
      const r = GEOMETRY.insetRadius;
      const phase = phaseOf(frame);
      return (
        <React.Fragment key={i}>
          {from && (
            <svg width={W} height={H} style={{ position: "absolute", left: 0, top: 0, opacity: s >= 1 ? undefined : s }}>
              <path d={`M${from[0]} ${from[1]} L${n.x} ${n.y}`} stroke={INK} strokeWidth={4} strokeDasharray="12 10" />
            </svg>
          )}
          <Sprite id={`mc-inset|${phase}`} box={{ left: -r - 16, top: -r - 16, width: 2 * r + 32, height: 2 * r + 32 }}
            draw={() => (
              <g>
                <Cel d={ellP(0, 0, r, r)} fill={CREAM} phase={phase} seed={210} sw={6} />
                <circle r={r - 14} fill="none" stroke={INK} strokeWidth={3} strokeDasharray="10 8" />
              </g>
            )}
            x={n.x} y={n.y} transform={s !== 1 ? `scale(${s})` : undefined} />
          <div style={{
            position: "absolute", left: n.x - r, width: 2 * r, top: n.y - 40, height: 80, display: "flex", alignItems: "center",
            justifyContent: "center", fontFamily: ALFA, fontSize: Math.min(60, (2 * r - 50) / Math.max(n.text.length * 0.7, 1)), color: INK,
            transform: s !== 1 ? `scale(${s})` : undefined, whiteSpace: "nowrap",
          }}>{n.text}</div>
        </React.Fragment>
      );
    })}
  </>
);

const Labels: React.FC<{ state: StageState; frame: number }> = ({ state, frame }) => (
  <>
    {state.labels.map((l) => {
      const s = popScale(frame, l.since);
      return (
        <div key={l.key} style={{ position: "absolute", left: l.x - 400, width: 800, top: l.y - GEOMETRY.labelHeightPx / 2, display: "flex", justifyContent: "center", transform: s !== 1 ? `scale(${s})` : undefined }}>
          <OffCard seed={310 + l.key.length} phase={phaseOf(frame)} fill={CREAM} radius={12}>
            <div style={{ display: "flex", alignItems: "center", gap: 12, height: GEOMETRY.labelHeightPx - 8, padding: "0 20px 0 14px", fontFamily: JOST, fontWeight: 500, fontSize: GEOMETRY.labelFontPx, color: INK, whiteSpace: "nowrap" }}>
              <svg width={30} height={30}><Asterisk x={15} y={15} r={13} rot={phaseOf(frame) * 15} /></svg>
              {l.text}
            </div>
          </OffCard>
        </div>
      );
    })}
  </>
);

// ── header, intro, summary, progress ─────────────────────────────────────────
const RunningHead: React.FC<{ title: string }> = ({ title }) => (
  <div style={{ position: "absolute", left: 66, right: 66, top: 196, fontFamily: OLEO, fontWeight: 700, fontSize: 70, color: INK, textShadow: `4px 4px 0 ${CORAL}`, lineHeight: 1.1, whiteSpace: "nowrap" }}>
    {title}
  </div>
);

const Medallion: React.FC<{ n: number; phase: number; size?: number; fill?: string }> = ({ n, phase, size = 62, fill = INK }) => {
  const [mx, my] = jitter(300 + n, phase);
  return (
    <g>
      <circle cx={REG[0] + mx} cy={REG[1] + my} r={size} fill={fill} />
      <circle r={size} fill="none" stroke={INK} strokeWidth={5} />
      <circle r={size - 10} fill="none" stroke={PAPER} strokeWidth={3} strokeDasharray="10 7" />
      <text y={size * 0.44} textAnchor="middle" fontFamily={ALFA} fontSize={size * 1.22} fill={PAPER}>{n}</text>
    </g>
  );
};

const StepHeader: React.FC<{ data: MidcenturyData; index: number; frame: number }> = ({ data, index, frame }) => {
  const step = data.steps[index];
  const t = onTwos(frame) - step.start;
  const pop = index === 0 && step.start === 0 ? 1 : ease.outBack(clamp01(t / TIMING.pop));
  const slide = -70 * (1 - ease.out(clamp01((t - 2) / (TIMING.headerIn - 2))));
  const tagPop = ease.outBack(clamp01((t - 8) / TIMING.pop));
  const phase = phaseOf(frame);
  return (
    <>
      <svg width={150} height={150} style={{ position: "absolute", left: 52, top: 322, overflow: "visible" }}>
        <g transform={`translate(75 75) scale(${Math.max(0.01, pop)})`}><Medallion n={index + 1} phase={phase} /></g>
      </svg>
      <div style={{ position: "absolute", left: 218 + slide, top: 334, right: 40 }}>
        <div style={{ fontFamily: JOST, fontWeight: 600, fontSize: 40, letterSpacing: 7, color: INK, lineHeight: 1 }}>
          STEP {index + 1} OF {data.steps.length}
        </div>
        <div style={{ fontFamily: ALFA, fontSize: fitFont(step.header, 780, 78, true), color: INK, lineHeight: 1.08, marginTop: 6, textShadow: `4px 4px 0 ${CREAM}`, whiteSpace: "nowrap" }}>
          {step.header}
        </div>
      </div>
      {step.tag && tagPop > 0.01 && (
        <div style={{ position: "absolute", left: 66, top: 498, transform: tagPop < 1 ? `scale(${tagPop})` : undefined, transformOrigin: "left center" }}>
          <OffCard seed={320 + index} phase={phase} fill={CREAM} radius={12}>
            <div style={{ display: "flex", alignItems: "center", gap: 14, padding: "6px 22px 8px 16px", fontFamily: JOST, fontWeight: 500, fontSize: 42, color: INK, whiteSpace: "nowrap" }}>
              <svg width={34} height={34}><Asterisk x={17} y={17} r={15} rot={phase * 15} /></svg>
              {step.tag}
            </div>
          </OffCard>
        </div>
      )}
    </>
  );
};

const IntroTitle: React.FC<{ data: MidcenturyData; frame: number }> = ({ data, frame }) => {
  const k = ease.outBack(clamp01(onTwos(frame) / TIMING.pop));
  return (
    <div style={{ position: "absolute", left: 66, right: 66, top: 236, transform: frame < TIMING.pop ? `scale(${Math.max(0.01, k)})` : undefined, transformOrigin: "left top" }}>
      {data.kicker && <div style={{ fontFamily: OLEO, fontWeight: 700, fontSize: fitFont(data.kicker, 940, 80), color: INK, textShadow: `4px 4px 0 ${CREAM}`, lineHeight: 1.1, whiteSpace: "nowrap" }}>{data.kicker}</div>}
      <div style={{ fontFamily: ALFA, fontSize: fitFont(data.title, 940, 104, true), color: INK, lineHeight: 1.04, marginTop: 10, textShadow: `5px 5px 0 ${CORAL}`, whiteSpace: "nowrap" }}>{data.title}</div>
    </div>
  );
};

const Summary: React.FC<{ data: MidcenturyData; frame: number }> = ({ data, frame }) => {
  const start = data.summary ?? 0;
  const phase = phaseOf(frame);
  // The list sits left of the presenter (he stands on the right) and below his raised hand.
  const top = 680;
  const gap = Math.min(140, 600 / Math.max(data.steps.length, 1));
  return (
    <>
      <svg width={W} height={H} style={{ position: "absolute", left: 0, top: 0 }}>
        {data.steps.slice(1).map((_, i) => (
          <path key={i} d={`M127 ${top + i * gap + 70} V${top + (i + 1) * gap - 70}`} stroke={INK} strokeWidth={5} strokeDasharray="10 10" />
        ))}
        {data.steps.map((_, i) => {
          const s = ease.outBack(clamp01((onTwos(frame) - start - i * 4) / TIMING.pop));
          return (
            <g key={i} transform={`translate(127 ${top + i * gap}) scale(${Math.max(0.01, s * 0.82)})`}>
              <Medallion n={i + 1} phase={phase} fill={TEAL} />
            </g>
          );
        })}
      </svg>
      {data.steps.map((st, i) => {
        const s = clamp01((onTwos(frame) - start - i * 4 - 2) / TIMING.pop);
        return (
          <div key={i} style={{ position: "absolute", left: 210, top: top + i * gap - 44, opacity: s, fontFamily: ALFA, fontSize: Math.min(gap * 0.5, fitFont(st.header, 440, 60, true)), color: INK, lineHeight: 1.3, whiteSpace: "nowrap", textShadow: `3px 3px 0 ${CREAM}` }}>
            {st.header}
          </div>
        );
      })}
    </>
  );
};

const Progress: React.FC<{ data: MidcenturyData; current: number; done: boolean; phase: number }> = ({ data, current, done, phase }) => {
  const n = data.steps.length;
  const gap = 130;
  const x0 = W / 2 - ((n - 1) * gap) / 2;
  return (
    <svg width={W} height={160} style={{ position: "absolute", left: 0, top: 1610 }}>
      {Array.from({ length: n - 1 }, (_, i) => (
        <path key={i} d={`M${x0 + i * gap + 40} 70 H${x0 + (i + 1) * gap - 40}`} stroke={INK} strokeWidth={4} strokeDasharray="8 8" opacity={0.6} />
      ))}
      {Array.from({ length: n }, (_, i) => {
        const isDone = i < current || done;
        const cur = i === current && !done;
        const [jx, jy] = jitter(400 + i, phase, 1.2);
        return (
          <g key={i} transform={`translate(${x0 + i * gap} 70)`}>
            <circle cx={REG[0] + jx} cy={REG[1] + jy} r={36} fill={isDone ? TEAL : cur ? INK : mix(PAPER, INK, 0.1)} />
            <circle r={36} fill="none" stroke={INK} strokeWidth={4} />
            <text y={15} textAnchor="middle" fontFamily={ALFA} fontSize={42} fill={cur || isDone ? PAPER : INK}>{i + 1}</text>
          </g>
        );
      })}
    </svg>
  );
};

const Sparkles: React.FC<{ state: StageState; frame: number }> = ({ state, frame }) => {
  // Sparkles turn on twos around each check that has landed; they settle after a second.
  const marks = state.badges.filter((b) => b.kind === "check");
  if (!marks.length) return null;
  return (
    <svg width={W} height={H} style={{ position: "absolute", left: 0, top: 0 }}>
      {marks.map((b, i) => {
        const o = state.objects.find((q) => q.key === b.target);
        if (!o) return null;
        const t = onTwos(frame) - b.since;
        const rot = Math.min(t, 30) * 6;
        const s = clamp01(t / 6);
        return (
          <g key={i} opacity={s}>
            <Sparkle x={o.x + 190} y={o.y - 190} r={26} color={CREAM} rot={rot} />
            <Sparkle x={o.x - 170} y={o.y - 120} r={18} color={CORAL} rot={-rot} />
          </g>
        );
      })}
    </svg>
  );
};

// ── the scene ─────────────────────────────────────────────────────────────────
export default function MidcenturyHowTo({ midcenturyHowTo, durationInFrames }: { midcenturyHowTo?: MidcenturyData; durationInFrames: number }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  useStyleFonts("MidcenturyHowTo", FONTS);
  const data: MidcenturyData = midcenturyHowTo ?? { title: "", steps: [], shots: [] };
  const customSpecs = data.customProps ?? [];
  const custom = useCustomDrawings<ObjectDrawProps>("MidcenturyHowTo", customSpecs) ?? {};
  const state = stageAt(data, durationInFrames, frame);
  const seg = state?.segment;
  const stepIndex = seg?.kind === "step" ? seg.index : -1;
  const ground = seg?.kind === "step" ? GROUNDS[data.steps[seg.index].ground] ?? GROUNDS.mustard : GROUNDS.mustard;
  const burst = seg?.kind !== "step";
  const phase = phaseOf(frame);
  const progressStep = seg?.kind === "intro" ? -1 : seg?.kind === "summary" ? data.steps.length : stepIndex;
  return (
    <AbsoluteFill style={{ background: PAPER, width: W, height: H, overflow: "hidden" }}>
      <Ground color={ground} burst={burst} burstAt={seg?.kind === "summary" ? [880, 1100] : [700, 1150]} />
      {state && (
        <>
          {state.objects.map((o) => <ObjectSprite key={o.key} o={o} frame={frame} fps={fps} custom={custom} customSpecs={customSpecs} />)}
          <PresenterSprite data={data} state={state} frame={frame} />
          <HoseSprite state={state} frame={frame} outfit={data.presenter} />
          <RingBurst state={state} frame={frame} />
          <Badges state={state} frame={frame} customSpecs={customSpecs} />
          <Sparkles state={state} frame={frame} />
          <Insets state={state} frame={frame} customSpecs={customSpecs} />
          <Labels state={state} frame={frame} />
        </>
      )}
      {seg?.kind === "intro" ? <IntroTitle data={data} frame={frame} /> : <RunningHead title={data.title.slice(0, LIMITS.titleChars)} />}
      {seg?.kind === "step" && <StepHeader data={data} index={seg.index} frame={frame} />}
      {seg?.kind === "summary" && <Summary data={data} frame={frame} />}
      {data.steps.length > 0 && <Progress data={data} current={progressStep} done={seg?.kind === "summary"} phase={phase} />}
    </AbsoluteFill>
  );
}
