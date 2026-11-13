/*
 * ComicPanels: the whole of a Comic Panels video, as one scene.
 *
 * The narration is told as comic pages built on screen: each page holds 3 or 4
 * panels on cream newsprint under a title bar. A panel inks in on its word
 * (the border, then the art wiping in, then its halftone), and the camera
 * reads panel by panel, holding still on each, punching in and shaking on a
 * hit, and pulls back to the whole page at the splash. Inside a panel, the cast
 * (a house hero, invented people, a villain silhouette) and props appear on
 * words, with balloons, caption boxes, drawn sound effects and speed lines.
 * The agent never writes this file's kind of code: it writes
 * `props.comicPanels`, which the MCP server validates against
 * ./comicPanels/contract.ts before render.
 *
 * Kept cheap on the CPU renderer (software GL): every panel ground, character,
 * prop, balloon and sound effect is a cached bitmap
 * (./characterKit/sprite.tsx), and the camera is one transform on the page
 * layer. Measured over the whole example video: 0.43 CPU-seconds per frame,
 * against 0.24 for System Flow's example rendered under the same load; the
 * camera layer is most of the difference. What got it down from 0.67: the
 * camera holds still between panels instead of pushing in on every frame, a
 * panel is clipped only while it wipes in, panels not reached yet are blank
 * paper (pencil sketches of them cost about 0.07), and the bitmaps are drawn at
 * 1.2 pixels per page unit. Halftone dots sit on a fixed grid inside each
 * bitmap, so a camera move never makes them crawl.
 */
import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { useCustomDrawings } from "./characterKit/customProps";
import { useStyleFonts } from "./characterKit/fonts";
import { hashSeed } from "./characterKit/geometry";
import { Sprite, type SpriteBox } from "./characterKit/sprite";
import { BUST_BOX, Bust, bustKey, type BustLook } from "./comicPanels/cast";
import {
  ACTOR, LAYOUTS, PAGE, PROPS, TONES, W, H, balloonSize, sfxBurst, sfxSize,
  type CPActor, type CPItem, type CPPage, type ComicPanelsData,
} from "./comicPanels/contract";
import { FONTS } from "./comicPanels/fonts";
import { BANG, COMIC, Dots, INK, PAPER, RED, SpeedLines, WHITE, YEL, starPoints, wrap, type PropDrawProps } from "./comicPanels/ink";
import { PROP_DRAWINGS } from "./comicPanels/props";
import { cameraAt, inkAt, itemsAt, pageAt, popAt } from "./comicPanels/stage";

// Bitmaps are drawn at this many pixels per page unit. The closest framing is about 1.4, so the art
// is upscaled a little there; at 1.6 every frame cost about 10% more for the larger layer.
const R = 1.2;
type PropDrawing = React.FC<PropDrawProps>;

// ── a panel's ground, border and tone ─────────────────────────────────────────
const PanelGround: React.FC<{ w: number; h: number; tone: string; dark: boolean }> = ({ w, h, tone, dark }) => (
  <g>
    <Dots id="cp-tone" color={dark ? "#3c4152" : INK} r={2.6} gap={13} />
    <rect width={w} height={h} fill={tone} />
    <rect width={w} height={h} fill="url(#cp-tone)" opacity={dark ? 0.6 : 0.1} />
  </g>
);
const PanelBorder: React.FC<{ w: number; h: number }> = ({ w, h }) => (
  <rect x={3} y={3} width={w - 6} height={h - 6} fill="none" stroke={INK} strokeWidth={7} />
);
// ── items ─────────────────────────────────────────────────────────────────────
const Balloon: React.FC<{ text: string; kind: string; w: number; h: number; tip: [number, number]; seed: number }> = ({ text, kind, w, h, tip, seed }) => {
  const lines = wrap(text.toUpperCase(), 16, 3);
  // the balloon is sized for 16 characters a line: a longer line (a long word, a merged third line) sets smaller
  const size = 40 * Math.min(1, 16 / Math.max(1, ...lines.map((l) => l.length)));
  const ang = Math.atan2(tip[1], tip[0]);
  const b1 = [Math.cos(ang - 0.25) * w * 0.36, Math.sin(ang - 0.25) * h * 0.36];
  const b2 = [Math.cos(ang + 0.25) * w * 0.36, Math.sin(ang + 0.25) * h * 0.36];
  const tail = `${b1[0]},${b1[1]} ${tip[0]},${tip[1]} ${b2[0]},${b2[1]}`;
  const lh = size * 1.06;
  const y0 = -((lines.length - 1) * lh) / 2 + size * 0.36;
  return (
    <g>
      {kind === "thought" ? (
        [0.35, 0.6, 0.82].map((k, i) => <circle key={i} cx={tip[0] * k} cy={tip[1] * k} r={14 - i * 4} fill={WHITE} stroke={INK} strokeWidth={5} />)
      ) : (
        <polygon points={tail} fill={WHITE} stroke={INK} strokeWidth={6} strokeLinejoin="round" />
      )}
      {kind === "shout" ? (
        <polygon points={starPoints(0, 0, 14, w * 0.46, w * 0.58, seed, h / w)} fill={WHITE} stroke={INK} strokeWidth={6} />
      ) : (
        <ellipse cx={0} cy={0} rx={w / 2} ry={h / 2} fill={WHITE} stroke={INK} strokeWidth={6} />
      )}
      {kind !== "thought" && <polygon points={tail} fill={WHITE} transform={`translate(${-tip[0] * 0.03} ${-tip[1] * 0.03})`} />}
      {lines.map((l, i) => (
        <text key={i} x={0} y={y0 + i * lh} textAnchor="middle" fontFamily={COMIC} fontWeight={700} fontSize={size} fill={INK}>{l}</text>
      ))}
    </g>
  );
};

const Sfx: React.FC<{ text: string; seed: number }> = ({ text, seed }) => {
  const size = 92;
  const rot = ((seed % 21) - 10) * 0.9;
  const r = sfxBurst(text);
  const base = size * 0.34; // the capitals' baseline, so they sit centred on (0, 0) with the burst
  return (
    <g transform={`rotate(${rot})`}>
      <polygon points={starPoints(0, 0, 12, r * 0.6, r, seed)} fill={INK} transform="translate(7 7)" />
      <polygon points={starPoints(0, 0, 12, r * 0.6, r, seed)} fill={YEL} stroke={INK} strokeWidth={5} />
      <text x={6} y={base + 6} textAnchor="middle" fontFamily={BANG} fontSize={size} fill={INK} stroke={INK} strokeWidth={size * 0.16} strokeLinejoin="round" letterSpacing={2}>{text}</text>
      <text x={0} y={base} textAnchor="middle" fontFamily={BANG} fontSize={size} fill={RED} stroke={INK} strokeWidth={size * 0.12} strokeLinejoin="round" paintOrder="stroke" letterSpacing={2}>{text}</text>
    </g>
  );
};

const CaptionBox: React.FC<{ text: string; w: number }> = ({ text, w }) => {
  const per = Math.max(10, Math.floor((w - 40) / 22));
  const lines = wrap(text.toUpperCase(), per, 2);
  // a line longer than the box takes (the second line takes the rest of the text) sets smaller
  const size = 34 * Math.min(1, per / Math.max(1, ...lines.map((l) => l.length)));
  return (
    <g>
      <rect x={0} y={0} width={w} height={lines.length * 42 + 28} fill={YEL} stroke={INK} strokeWidth={5} />
      {lines.map((l, i) => (
        <text key={i} x={18} y={46 + i * 42} fontFamily={COMIC} fontWeight={700} fontSize={size} fill={INK}>{l}</text>
      ))}
    </g>
  );
};

function bustLook(cast: CPActor | undefined, it: Extract<CPItem, { type: "actor" }>, blink: boolean): BustLook {
  return {
    kind: cast?.kind ?? "person", hair: cast?.hair ?? (cast?.kind === "hero" ? "spiky" : "short"),
    outfit: cast?.outfit ?? "blue", skin: cast?.skin ?? "light", pose: it.pose, face: it.face, blink,
  };
}

/** Where an item named by id stands in its panel (page units), for a balloon's tail. */
function anchorOf(items: readonly CPItem[], id: string, rect: readonly number[]): [number, number] | null {
  for (const it of items) {
    if ((it.type === "actor" && (it.id ?? it.who) === id) || (it.type === "prop" && (it.id ?? it.prop) === id)) {
      const top = it.type === "actor" ? ACTOR.h * (it.scale ?? 1) * 0.7 : 0;
      return [rect[0] + it.x * rect[2], rect[1] + it.y * rect[3] - top];
    }
  }
  return null;
}

// ── a page ────────────────────────────────────────────────────────────────────
const Page: React.FC<{ data: ComicPanelsData; page: CPPage; pi: number; frame: number; custom: Record<string, PropDrawing> }> = ({ data, page, pi, frame, custom }) => {
  const rects = LAYOUTS[page.layout];
  const customSpecs = data.customProps ?? [];
  const out: React.ReactNode[] = [];
  out.push(<div key="paper" style={{ position: "absolute", left: 0, top: 0, width: PAGE.w * R, height: PAGE.h * R, background: PAPER }} />);
  if (page.title) {
    const words = page.title.toUpperCase().split(" ");
    out.push(
      <div key="title" style={{ position: "absolute", left: 24 * R, top: 22 * R, width: 952 * R, height: 96 * R, display: "flex", alignItems: "center", justifyContent: "center", gap: 18 * R, fontFamily: BANG, fontSize: 84 * R, color: INK, letterSpacing: 3 * R, whiteSpace: "nowrap" }}>
        {words.map((w, i) => <span key={i} style={{ color: i === words.length - 1 ? RED : INK, WebkitTextStroke: `${2 * R}px ${INK}` }}>{w}</span>)}
      </div>,
    );
  }
  page.panels.forEach((panel, i) => {
    const [x, y, w, h] = rects[i];
    const ink = inkAt(panel.start, frame);
    const key = `p${pi}-${i}`;
    if (ink <= 0) return;
    const tone = TONES[panel.tone] ?? TONES.cream;
    const wipe = Math.min(1, ink * 1.6);
    const items = itemsAt(panel.items, frame);
    const panelNodes: React.ReactNode[] = [];
    panelNodes.push(<Sprite key="g" id={`cp-ground|${w}|${h}|${panel.tone}`} box={{ left: 0, top: 0, width: w, height: h }} x={0} y={0} scale={R} draw={() => <PanelGround w={w} h={h} tone={tone} dark={panel.tone === "dark"} />} />);
    for (const it of items) {
      if (it.type !== "lines") continue;
      panelNodes.push(<Sprite key={`l${it.frame}`} id={`cp-lines|${it.kind}|${w}|${h}`} box={{ left: 0, top: 0, width: w, height: h }} x={0} y={0} scale={R}
        draw={() => <SpeedLines cx={w / 2} cy={h / 2} n={it.kind === "focus" ? 54 : 40} ri={Math.min(w, h) * 0.38} ro={Math.max(w, h)} seed={it.frame} width={it.kind === "focus" ? 0.02 : 0.03} />} />);
    }
    items.forEach((it, k) => {
      const p = popAt(it.frame, frame);
      const s = p < 1 ? `scale(${p})` : undefined;
      const ix = (v: number) => v * w * R, iy = (v: number) => v * h * R;
      if (it.type === "actor") {
        const cast = data.cast.find((c) => c.id === it.who);
        const look = bustLook(cast, it, (frame + hashSeed(it.who)) % 97 < 2);
        const sc = it.scale ?? 1;
        panelNodes.push(<Sprite key={`a${k}`} id={bustKey(look)} box={BUST_BOX} x={ix(it.x)} y={iy(it.y) + (ACTOR.h * sc * R) / 2} scale={sc * R}
          draw={() => <Bust {...look} />} flip={it.flip} transform={s} />);
      } else if (it.type === "prop") {
        const Draw: PropDrawing | undefined = (PROP_DRAWINGS as Record<string, PropDrawing>)[it.prop] ?? custom[it.prop];
        const size = it.prop in PROPS ? PROPS[it.prop as keyof typeof PROPS] : customSpecs.find((c) => c.id === it.prop) ?? { w: 0, h: 0 };
        if (!Draw) return;
        const box: SpriteBox = { left: -size.w / 2 - 8, top: -size.h / 2 - 8, width: size.w + 16, height: size.h + 16 };
        panelNodes.push(<Sprite key={`p${k}`} id={`cp-prop|${it.prop}|${it.text ?? ""}`} box={box} x={ix(it.x)} y={iy(it.y)} scale={(it.scale ?? 1) * R}
          draw={() => <Draw text={it.text ?? ""} />} fonts={FONTS} transform={s} />);
      } else if (it.type === "balloon") {
        const size = balloonSize(it.text);
        const anchor = anchorOf(items, it.to, [0, 0, w, h]);
        const tip: [number, number] = anchor ? [anchor[0] - it.x * w, anchor[1] - it.y * h] : [0, size.h];
        const len = Math.hypot(tip[0], tip[1]) || 1;
        const reach = Math.min(len, size.h * 0.95);
        const t: [number, number] = [(tip[0] / len) * reach, (tip[1] / len) * reach];
        const box: SpriteBox = { left: -size.w / 2 - Math.max(0, -t[0]) - 30, top: -size.h / 2 - Math.max(0, -t[1]) - 30, width: size.w + Math.abs(t[0]) + 60, height: size.h + Math.abs(t[1]) + 60 };
        panelNodes.push(<Sprite key={`b${k}`} id={`cp-balloon|${it.kind}|${it.text}|${Math.round(t[0])}|${Math.round(t[1])}`} box={box} x={ix(it.x)} y={iy(it.y)} scale={R}
          draw={() => <Balloon text={it.text} kind={it.kind} w={size.w} h={size.h} tip={t} seed={it.frame} />} fonts={FONTS} transform={s} />);
      } else if (it.type === "caption") {
        const cw = Math.min(w - 40, 520);
        panelNodes.push(<Sprite key={`c${k}`} id={`cp-caption|${it.text}|${cw}`} box={{ left: -4, top: -4, width: cw + 8, height: 120 }} x={16 * R} y={16 * R} scale={R}
          draw={() => <CaptionBox text={it.text} w={cw} />} fonts={FONTS} transform={s} />);
      } else if (it.type === "sfx") {
        const size = sfxSize(it.text);
        const seed = hashSeed(it.text + it.frame) % 997;
        panelNodes.push(<Sprite key={`s${k}`} id={`cp-sfx|${it.text}|${seed}`} box={{ left: -size.w / 2 - 40, top: -size.h / 2 - 40, width: size.w + 80, height: size.h + 80 }}
          x={ix(it.x)} y={iy(it.y)} scale={R} draw={() => <Sfx text={it.text} seed={seed} />} fonts={FONTS} transform={p < 1 ? `scale(${1 + (1 - p) * 1.1})` : undefined} />);
      }
    });
    panelNodes.push(<Sprite key="border" id={`cp-border|${w}|${h}`} box={{ left: 0, top: 0, width: w, height: h }} x={0} y={0} scale={R} draw={() => <PanelBorder w={w} h={h} />} />);
    out.push(
      <div key={key} style={{ position: "absolute", left: x * R, top: y * R, width: w * R * wipe, height: h * R, overflow: wipe < 1 ? "hidden" : "visible" }}>
        {panelNodes}
      </div>,
    );
  });
  return <>{out}</>;
};

// ── the scene ─────────────────────────────────────────────────────────────────
export default function ComicPanels({ comicPanels }: { comicPanels?: ComicPanelsData; durationInFrames: number }) {
  const frame = useCurrentFrame();
  useStyleFonts("ComicPanels", FONTS);
  const data: ComicPanelsData = comicPanels ?? { cast: [], pages: [] };
  const custom = useCustomDrawings<PropDrawProps>("ComicPanels", data.customProps ?? []) ?? {};
  const pi = pageAt(data, frame);
  const cam = cameraAt(data, frame);
  const k = cam.scale / R;
  const tx = W / 2 - cam.cx * cam.scale + cam.shakeX;
  const ty = 820 - cam.cy * cam.scale + cam.shakeY;
  return (
    <AbsoluteFill style={{ background: "#d9cfb6", width: W, height: H, overflow: "hidden" }}>
      {pi >= 0 && (
        <div style={{ position: "absolute", left: 0, top: 0, width: PAGE.w * R, height: PAGE.h * R, transformOrigin: "0 0", transform: `translate(${tx}px, ${ty}px) scale(${k})` }}>
          <Page data={data} page={data.pages[pi]} pi={pi} frame={frame} custom={custom} />
        </div>
      )}
    </AbsoluteFill>
  );
}
