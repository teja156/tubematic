/*
 * EditorialCollage: the whole of an Editorial Collage video, as one scene.
 *
 * A news or incident story told on a paper desk larger than the frame. Each
 * station is a headline (a torn newspaper clipping, a black label bar or a
 * black card) over one hero: a taped halftone print, a cut-out sticker, a
 * typed index card, a big figure counting up, or a small stack of prints.
 * One camera glides diagonally from station to station along a zig-zag the
 * code lays out, a sagging red string drawing from the last station to the
 * new one, and red pen circles, underlines, strikes, highlighter bars, rubber
 * stamps and paper arrows land on the narration's words. Pieces move on
 * twelve steps a second; the camera is smooth. The captions are the shared
 * Subtitles layer in its "highlight" look.
 *
 * The agent never writes this file's kind of code: it writes `props.collage`
 * (stations and events timed to the narration), which the MCP server
 * validates against ./editorialCollage/contract.ts before the video can
 * render. A print always carries the note "Illustration" and a recreation
 * index card "Recreation" (painted into the piece; no field hides them).
 *
 * Kept cheap on the CPU renderer (software GL): the desk, every paper piece,
 * every print and sticker and the arrow are painted ONCE onto canvases
 * (./editorialCollage/paint.ts) and only moved; the desk layer is translated
 * (never scaled) and only while the camera glides, otherwise it is placed with
 * left/top and carries no transform; pen strokes are point lists that grow,
 * never stroke-dasharray; no <img>, SVG filter or blend mode. Only the
 * current station (and the one the camera is leaving, during a glide) is
 * mounted with its text.
 *
 * Measured in CPU-seconds per frame over the whole skill example (1,023
 * frames, rendered from a prebuilt bundle with software GL, concurrency 2):
 * 0.51 here, 0.23 for System Flow's example on the same day by the same
 * method (2.2x, with the host busier by the end). The detailed desk, captured
 * and encoded on every frame, and the glides are most of it.
 */
import React, { useEffect, useState } from "react";
import { AbsoluteFill, cancelRender, continueRender, delayRender, useCurrentFrame } from "remotion";
import {
  COLORS, DESK, H, HEADLINE, KICKER_H, TIMING, W, ZONES,
  type CollageData, type CollageEvent, type FigureHero, type Headline, type Hero, type IndexHero, type Station,
} from "./editorialCollage/contract";
import {
  cameraAt, cleanWord, clamp01, countProgress, figureSize, figureText, fired, gliding, glideProgress, headlineLayout,
  heroBox, indexSize, INDEX, landScale, layoutKind, penEllipse, PRINT_BOX, quartOut, seeded, stackCells, stationCenter,
  stationIndexAt, stepped, stringPoints, tiltOf, typedChars, upTo, fitBox,
} from "./editorialCollage/stage";
import {
  ARROW_TIP, GROTESK, SERIF, TYPED, paintArrow, paintBlack, paintClipping, paintDesk, paintIndex, paintLowScrap, paintPrint,
  paintScrap,
  paintSticker,
} from "./editorialCollage/paint";
import { loadFonts, type FontFile } from "./paper/fonts";
import { PaperFinish } from "./paper/PaperFinish";

export const COLLAGE_FONTS: FontFile[] = [
  ["Source Serif 4", "fonts/source-serif-4-latin-700-normal.woff2", "700"],
  ["Bricolage Grotesque", "fonts/bricolage-grotesque-latin-800-normal.woff2", "800"],
  ["Special Elite", "fonts/special-elite-latin-400-normal.woff2", "400"],
];

export interface EditorialCollageProps {
  collage: CollageData;
}

type Sprite = { canvas: HTMLCanvasElement; x: number; y: number };
interface Assets {
  desk: HTMLCanvasElement;
  aspects: Record<string, number>;
  sprites: Map<string, Sprite>;
}

const f1 = (n: number) => n.toFixed(1);
const isSticker = (src: string) => src.endsWith(".sticker.png");

function headlineBox(h: Headline, hasHero: boolean) {
  const lk = layoutKind(h.kind, hasHero);
  const spec = HEADLINE[lk];
  const { size, lines } = headlineLayout(h.text, lk, !!h.kicker);
  const kick = h.kicker ? KICKER_H : 0;
  const textH = lines.length * size * spec.line;
  // the paper hugs the words (the layout's width estimate is generous), never narrower than the kicker
  const longest = Math.max(...lines.map((l) => l.length)) * size * spec.charW;
  const inner = lk === "blackFull" ? spec.width : Math.min(spec.width, Math.max(longest, (h.kicker?.length ?? 0) * 30 * 0.74, 300));
  const width = inner + 2 * spec.pad;
  const height = lk === "blackFull" ? spec.zone : 2 * spec.pad + kick + textH;
  return { lk, spec, size, lines, kick, textH, inner, width, height, left: (W - width) / 2, top: ZONES.headTop };
}

/** Every picture loaded and every paper piece painted, before the first frame. */
function useAssets(data: CollageData): Assets | null {
  const [assets, setAssets] = useState<Assets | null>(null);
  const [handle] = useState(() => delayRender("EditorialCollage: painting the desk"));
  useEffect(() => {
    const srcs = new Set<string>();
    for (const s of data.stations) {
      const h = s.hero;
      if (h?.kind === "print" || h?.kind === "sticker") srcs.add(h.image);
      if (h?.kind === "stack") h.items.forEach((it) => srcs.add(it.image));
    }
    const images = new Map<string, HTMLImageElement>();
    const loads = [...srcs].map((src) => new Promise<void>((resolve, reject) => {
      const im = new Image();
      im.onload = () => {
        images.set(src, im);
        resolve();
      };
      // a picture that will not load fails the render, as a missing <Img> does
      im.onerror = () => reject(new Error(`EditorialCollage: ${src} did not load`));
      im.src = src;
    }));
    Promise.all([
      loadFonts(COLLAGE_FONTS).catch((err) => console.error("EditorialCollage: font load failed", err)),
      ...loads,
    ]).then(() => {
      const aspects: Record<string, number> = {};
      images.forEach((im, src) => (aspects[src] = im.naturalWidth / Math.max(1, im.naturalHeight)));
      const sprites = new Map<string, Sprite>();
      data.stations.forEach((s, i) => {
        sprites.set(`scrap${i}`, paintScrap(i));
        sprites.set(`low${i}`, paintLowScrap(i));
        const hero = s.hero;
        if (s.headline && s.headline.kind !== "label") {
          const b = headlineBox(s.headline, !!hero);
          const canvas = s.headline.kind === "clipping"
            ? paintClipping(b.width, b.height, 21 + i, s.headline.kicker ? b.spec.pad + 34 : null)
            : paintBlack(b.width, b.height, 61 + i);
          sprites.set(`head${i}`, { canvas, x: b.left - 24, y: b.top - 24 });
        }
        if (!hero) return;
        const [bx, by, bw, bh] = heroBox(hero, aspects);
        if (hero.kind === "print") {
          const canvas = paintPrint(images.get(hero.image)!, bw, bh, tiltOf(i), hero.caption, 300 + i);
          const cy = by + (bh + (hero.caption ? PRINT_BOX.captionH : 0)) / 2;
          sprites.set(`hero${i}`, { canvas, x: bx + bw / 2 - canvas.width / 2, y: cy - canvas.height / 2 });
        } else if (hero.kind === "sticker") {
          const canvas = paintSticker(images.get(hero.image)!, bw, bh);
          sprites.set(`hero${i}`, { canvas, x: bx - 10, y: by - 10 });
        } else if (hero.kind === "index") {
          const { lineH } = indexSize(hero.lines.map((l) => l.text));
          sprites.set(`hero${i}`, { canvas: paintIndex(bw, bh, INDEX.head, lineH, !!hero.recreation), x: bx - 20, y: by - 20 });
        } else if (hero.kind === "stack") {
          stackCells(hero.items.length).forEach(([cx, cy, cw, ch], k) => {
            const it = hero.items[k];
            const im = images.get(it.image)!;
            const a = aspects[it.image] ?? 1;
            if (isSticker(it.image)) {
              const [, , fw, fh] = fitBox(a, cx, cy, cw - 20, ch - (it.caption ? 56 : 0));
              const canvas = paintSticker(im, fw, fh, it.caption);
              sprites.set(`hero${i}.${k}`, { canvas, x: cx - canvas.width / 2, y: cy - canvas.height / 2 });
            } else {
              const capH = it.caption ? 50 : 0;
              const [, , fw, fh] = fitBox(a, cx, cy, cw - 40, ch - capH - 30);
              const canvas = paintPrint(im, fw, fh, tiltOf(i, k + 1), it.caption, 400 + i * 5 + k, true);
              sprites.set(`hero${i}.${k}`, { canvas, x: cx - canvas.width / 2, y: cy - canvas.height / 2 });
            }
          });
        }
      });
      sprites.set("arrowR", { canvas: paintArrow(false), x: 0, y: 0 });
      sprites.set("arrowL", { canvas: paintArrow(true), x: 0, y: 0 });
      setAssets({ desk: paintDesk(), aspects, sprites });
      continueRender(handle);
    }).catch((err) => cancelRender(err));
  }, [data, handle]);
  return assets;
}

/** A painted canvas copied once onto a canvas of its own, then only moved. */
const Bitmap: React.FC<{ src: HTMLCanvasElement; style: React.CSSProperties }> = ({ src, style }) => {
  const ref = React.useRef<HTMLCanvasElement>(null);
  React.useLayoutEffect(() => {
    const g = ref.current?.getContext("2d");
    if (g) {
      g.clearRect(0, 0, src.width, src.height);
      g.drawImage(src, 0, 0);
    }
  }, [src]);
  return <canvas ref={ref} width={src.width} height={src.height} style={{ position: "absolute", ...style }} />;
};

const SpriteAt: React.FC<{ s?: Sprite; transform?: string; origin?: string; opacity?: number }> = ({ s, transform, origin, opacity }) =>
  s ? <Bitmap src={s.canvas} style={{ left: s.x, top: s.y, transform, transformOrigin: origin, opacity }} /> : null;

// ── the headline ─────────────────────────────────────────────────────────────
const HeadlineLayer: React.FC<{ station: Station; i: number; age: number; frame: number; sprite?: Sprite }> = ({ station, i, age, frame, sprite }) => {
  const h = station.headline!;
  const b = headlineBox(h, !!station.hero);
  const ev = fired(station.events, frame);
  const marks = (word: string) => {
    const w = cleanWord(word);
    const find = (kind: string) => ev.find((e) => e.do === kind && cleanWord(e.word ?? "") === w);
    return { under: find("underline"), high: find("highlight"), strike: find("strike") };
  };
  const used = new Set<string>();
  const grow = (e: CollageEvent | undefined, dur: number) => (e ? clamp01(stepped(frame - e.at) / dur) : 0);
  const tilt = (seeded(i * 7 + 3)() * 2 - 1) * (h.kind === "label" ? 1.2 : 1.6);
  const k = quartOut(age / TIMING.headLand);
  const landing = age < TIMING.headLand;
  const dark = h.kind !== "clipping";
  const ink = dark ? "#F2EEE6" : COLORS.ink;
  const full = b.lk === "blackFull";
  // the headline's own layer: the band it sits in, so its tilt turns no more of the frame than the headline
  const oy = b.top - 60;
  const textTop = (full ? b.top + (b.height - b.textH - b.kick) / 2 + b.kick : b.top + b.spec.pad + b.kick) - oy;
  const kicker = h.kicker && (
    <div style={{
      position: "absolute", left: b.left + b.spec.pad, top: textTop - b.kick + (h.kind === "label" ? -8 : -12), whiteSpace: "nowrap",
      fontFamily: GROTESK, fontWeight: 800, fontSize: 30, letterSpacing: "0.1em", textTransform: "uppercase",
      color: h.kind === "black" ? COLORS.highlight : COLORS.redDark,
    }}>{h.kicker}</div>
  );
  const labelW = Math.max(...b.lines.map((l) => l.length)) * b.size * b.spec.charW * 0.92 + 2 * b.spec.pad;
  return (
    <div style={{
      position: "absolute", left: 0, top: oy, width: W, height: b.height + 120, transformOrigin: `${W / 2}px ${60 + b.height / 2}px`,
      transform: `translateY(${f1(landing ? -60 * (1 - k) : 0)}px) rotate(${(tilt + (landing ? 5 * (1 - k) : 0)).toFixed(2)}deg)`,
    }}>
      {sprite && <SpriteAt s={{ ...sprite, y: sprite.y - oy }} />}
      {h.kind === "label" && (
        <div style={{
          position: "absolute", left: b.left, top: textTop - b.spec.pad, width: Math.min(b.width, labelW),
          height: b.textH + 2 * b.spec.pad, background: COLORS.ink, boxShadow: "5px 7px 0 rgba(23,23,22,0.28)",
        }} />
      )}
      {kicker}
      <div style={{
        position: "absolute", left: b.left + b.spec.pad, top: textTop, width: b.inner,
        fontFamily: h.kind === "label" ? GROTESK : SERIF, fontWeight: h.kind === "label" ? 800 : 700, fontSize: b.size,
        lineHeight: b.spec.line, color: ink, letterSpacing: h.kind === "label" ? "0.02em" : "-0.01em",
        textTransform: h.kind === "label" ? "uppercase" : "none", textAlign: full ? "center" : "left",
      }}>
        {b.lines.map((line, li) => (
          <div key={li} style={{ whiteSpace: "nowrap" }}>
            {line.split(" ").map((word, wi) => {
              const w = cleanWord(word);
              const m = used.has(w) ? { under: undefined, high: undefined, strike: undefined } : marks(word);
              used.add(w);
              const hp = grow(m.high, TIMING.highlight), up = grow(m.under, TIMING.underline), sp = grow(m.strike, TIMING.strike);
              return (
                <React.Fragment key={wi}>
                  {wi > 0 && " "}
                  <span style={{ position: "relative", display: "inline-block" }}>
                    {hp > 0 && (
                      <span style={{
                        position: "absolute", left: "-0.08em", top: "0.3em", height: "0.62em", width: `calc(${f1(hp * 100)}% + ${(0.16 * hp).toFixed(3)}em)`,
                        background: COLORS.highlight, opacity: 0.92, transform: "skewX(-8deg) rotate(-1deg)", borderRadius: "3px 8px 5px 2px",
                      }} />
                    )}
                    <span style={{ position: "relative" }}>{word}</span>
                    {up > 0 && (
                      <span style={{
                        position: "absolute", left: "-0.04em", top: "1.0em", height: Math.max(6, b.size * 0.075), width: `${f1(up * 104)}%`,
                        background: COLORS.red, borderRadius: 6, transform: "rotate(-1.2deg)", transformOrigin: "left center",
                      }} />
                    )}
                    {sp > 0 && (
                      <span style={{
                        position: "absolute", left: "-0.08em", top: "0.52em", height: Math.max(6, b.size * 0.08), width: `calc(${f1(sp * 100)}% + 0.16em)`,
                        background: COLORS.red, borderRadius: 6, transform: "rotate(-2deg)", transformOrigin: "left center",
                      }} />
                    )}
                  </span>
                </React.Fragment>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
};

// ── the hero ─────────────────────────────────────────────────────────────────
const IndexLines: React.FC<{ hero: IndexHero; box: [number, number, number, number]; frame: number }> = ({ hero, box, frame }) => {
  const { size, lineH } = indexSize(hero.lines.map((l) => l.text));
  return (
    <>
      {hero.lines.map((line, k) => {
        const n = typedChars(line.text, line.at, frame);
        if (n <= 0) return null;
        const typing = n < line.text.length;
        return (
          <div key={k} style={{
            position: "absolute", left: box[0] + 78, top: box[1] + INDEX.head - 30 + k * lineH + lineH - size * 1.18 - 4,
            fontFamily: TYPED, fontSize: size, lineHeight: 1.18, color: COLORS.ink, whiteSpace: "pre",
          }}>
            {line.text.slice(0, n)}
            {typing && <span style={{ display: "inline-block", width: size * 0.5, height: size * 0.85, marginLeft: 2, verticalAlign: "-0.1em", background: COLORS.ink, opacity: 0.8 }} />}
          </div>
        );
      })}
    </>
  );
};

const Figure: React.FC<{ hero: FigureHero; box: [number, number, number, number]; frame: number }> = ({ hero, box, frame }) => {
  const final = figureText(hero.value, hero.prefix, hero.suffix);
  const size = figureSize(final);
  const text = figureText(hero.value, hero.prefix, hero.suffix, countProgress(hero.countAt, frame));
  const pillW = Math.min(box[2], final.length * size * 0.6 + size * 0.7);
  const cx = box[0] + box[2] / 2;
  return (
    <>
      <div style={{
        position: "absolute", left: cx - pillW / 2, top: box[1], width: pillW, height: size * 1.2, borderRadius: size * 0.6,
        background: COLORS.highlight, boxShadow: "6px 9px 0 rgba(23,23,22,0.25)", display: "flex", alignItems: "center",
        justifyContent: "center", fontFamily: GROTESK, fontWeight: 800, fontSize: size, lineHeight: 1, color: COLORS.ink,
        whiteSpace: "nowrap", letterSpacing: "-0.01em",
      }}>{text}</div>
      <div style={{
        position: "absolute", left: cx, top: box[1] + size * 1.2 + 40, transform: "translateX(-50%) rotate(-1.5deg)",
        background: COLORS.ink, color: COLORS.edge, padding: "12px 30px 14px", whiteSpace: "nowrap",
        fontFamily: GROTESK, fontWeight: 800, fontSize: 52, letterSpacing: "0.04em", textTransform: "uppercase",
        boxShadow: "5px 7px 0 rgba(23,23,22,0.28)",
      }}>{hero.label}</div>
    </>
  );
};

const HeroLayer: React.FC<{
  hero: Hero; i: number; age: number; frame: number; box: [number, number, number, number]; sprites: Map<string, Sprite>; live: boolean;
}> = ({ hero, i, age, frame, box, sprites, live }) => {
  const a = age - TIMING.heroDelay;
  if (a < 0) return null;
  const cx = box[0] + box[2] / 2, cy = box[1] + box[3] / 2;
  const landT = (t: number, from = 1.16) => (t < TIMING.heroLand ? `scale(${landScale(t, TIMING.heroLand, from).toFixed(3)})` : undefined);
  const origin = `${f1(cx)}px ${f1(cy)}px`;
  if (hero.kind === "print") {
    const s = sprites.get(`hero${i}`)!;
    return <SpriteAt s={s} transform={landT(a, 1.12)} origin={`${f1(cx - s.x)}px ${f1(cy - s.y)}px`} />;
  }
  if (hero.kind === "sticker") {
    const s = sprites.get(`hero${i}`)!;
    const sway = TIMING.sway * Math.sin((2 * Math.PI * stepped(frame)) / TIMING.swayPeriod);
    const scale = a < TIMING.heroLand ? landScale(a, TIMING.heroLand, 1.25) : 1;
    const la = a - TIMING.labelDelay;
    return (
      <>
        <SpriteAt s={s} transform={`rotate(${sway.toFixed(2)}deg)${scale !== 1 ? ` scale(${scale.toFixed(3)})` : ""}`}
          origin={`${f1(cx - s.x)}px ${f1(cy - s.y)}px`} />
        {live && hero.label && la >= 0 && (
          <div style={{
            position: "absolute", left: Math.max(ZONES.left - 20, box[0] - 30), top: box[1] + box[3] - 70,
            transform: `translateX(${f1(-420 * (1 - quartOut(la / TIMING.labelLand)))}px) rotate(-2deg)`,
            background: COLORS.ink, color: COLORS.edge, padding: "10px 26px 12px", whiteSpace: "nowrap",
            fontFamily: GROTESK, fontWeight: 800, fontSize: 52, letterSpacing: "0.04em", textTransform: "uppercase",
            boxShadow: "5px 7px 0 rgba(23,23,22,0.3)",
          }}>{hero.label}</div>
        )}
      </>
    );
  }
  if (hero.kind === "index") {
    const s = sprites.get(`hero${i}`)!;
    return (
      <div style={{ position: "absolute", left: 0, top: 0, width: W, height: H, transform: landT(a, 1.08), transformOrigin: origin }}>
        <SpriteAt s={s} />
        {live && <IndexLines hero={hero} box={box} frame={frame} />}
      </div>
    );
  }
  if (hero.kind === "figure") {
    return live ? (
      <div style={{ position: "absolute", left: 0, top: 0, width: W, height: H, transform: landT(a), transformOrigin: origin }}>
        <Figure hero={hero} box={box} frame={frame} />
      </div>
    ) : null;
  }
  return (
    <>
      {hero.items.map((_, k) => {
        const t = a - k * TIMING.stackStagger;
        if (t < 0) return null;
        const s = sprites.get(`hero${i}.${k}`)!;
        return <SpriteAt key={k} s={s} transform={landT(t, 1.2)} origin="50% 50%" />;
      })}
    </>
  );
};

// ── the events on the hero ───────────────────────────────────────────────────
const Circle: React.FC<{ e: CollageEvent; box: [number, number, number, number]; frame: number; seed: number }> = ({ e, box, frame, seed }) => {
  const pts = upTo(penEllipse(box[0] + box[2] / 2, box[1] + box[3] / 2, Math.min(510, box[2] / 2 + 46), box[3] / 2 + 40, seed),
    stepped(frame - e.at) / TIMING.circle);
  if (pts.length < 2) return null;
  return (
    <svg width={W} height={H} style={{ position: "absolute", left: 0, top: 0, overflow: "visible" }}>
      <polyline points={pts.map(([x, y]) => `${f1(x)},${f1(y)}`).join(" ")} fill="none" stroke={COLORS.red} strokeWidth={11}
        strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
};

/** Where a stamp lands: on a picture's upper right, and off the words of a card or a figure. */
export function stampAt(hero: Hero | undefined, box: [number, number, number, number]): [number, number] {
  if (hero?.kind === "figure") return [ZONES.right - 150, box[1] + box[3] + 30];
  if (hero?.kind === "index") return [Math.min(box[0] + box[2] - 90, ZONES.right - 150), box[1] - 6];
  return [Math.min(box[0] + box[2] - 60, ZONES.right - 150), box[1] + 70];
}

const Stamp: React.FC<{ e: CollageEvent; hero?: Hero; box: [number, number, number, number]; frame: number }> = ({ e, hero, box, frame }) => {
  const age = stepped(frame - e.at);
  const s = age < TIMING.stamp ? 1.6 - 0.6 * (age / TIMING.stamp) : 1;
  const [x, y] = stampAt(hero, box);
  return (
    <div style={{
      position: "absolute", left: x, top: y,
      transform: `translate(-50%, -50%) rotate(-9deg) scale(${s.toFixed(3)})`,
      border: `6px solid ${COLORS.red}`, borderRadius: 10, padding: 4, opacity: 0.94,
    }}>
      <div style={{
        border: `2.5px solid ${COLORS.red}`, borderRadius: 6, padding: "8px 22px 6px", color: COLORS.red, whiteSpace: "nowrap",
        fontFamily: GROTESK, fontWeight: 800, fontSize: 56, letterSpacing: "0.06em", lineHeight: 1,
      }}>{e.text}</div>
    </div>
  );
};

const Arrow: React.FC<{ e: CollageEvent; box: [number, number, number, number]; frame: number; sprites: Map<string, Sprite> }> = ({ e, box, frame, sprites }) => {
  const fromLeft = e.from !== "right";
  const s = sprites.get(fromLeft ? "arrowR" : "arrowL")!;
  const age = stepped(frame - e.at);
  const k = quartOut(age / TIMING.arrow);
  const tip = fromLeft ? ARROW_TIP.right : ARROW_TIP.left;
  const tx = fromLeft ? Math.max(box[0] + 40, 300) : Math.min(box[0] + box[2] - 40, W - 300);
  const ty = box[1] + box[3] / 2 + 40;
  const dx = (fromLeft ? -50 : 50) * (1 - k);
  const tf = age < TIMING.arrow ? `translateX(${f1(dx)}px) rotate(${f1((fromLeft ? 10 : -10) * (1 - k))}deg) scale(${(1.25 - 0.25 * k).toFixed(3)})` : undefined;
  return <SpriteAt s={{ canvas: s.canvas, x: tx - tip[0], y: ty - tip[1] }} transform={tf} origin={`${tip[0]}px ${tip[1]}px`} />;
};

const Pin: React.FC<{ x: number; y: number }> = ({ x, y }) => (
  <svg width={40} height={40} style={{ position: "absolute", left: x - 20, top: y - 20 }}>
    <circle cx={22} cy={24} r={11} fill="rgba(23,23,22,0.3)" />
    <circle cx={20} cy={20} r={11} fill={COLORS.red} />
    <circle cx={16} cy={16} r={4} fill="#FFFFFF" opacity={0.5} />
  </svg>
);

// ── a station and the string into it ─────────────────────────────────────────
/** The string into station i: from the bottom of the last station's hero to the near side of this one's, in desk pixels. */
function stringEnds(stations: Station[], i: number, aspects: Record<string, number>): [[number, number], [number, number]] {
  const [px, py] = stationCenter(i - 1), [nx, ny] = stationCenter(i);
  const pb = heroBox(stations[i - 1].hero, aspects), nb = heroBox(stations[i].hero, aspects);
  const a: [number, number] = [px + (pb[0] + pb[2] / 2) - W / 2, py + Math.min(pb[1] + pb[3], ZONES.heroBottom) - 14 - H / 2];
  const near = nx > px ? nb[0] + 10 : nb[0] + nb[2] - 10;
  const b: [number, number] = [nx + near - W / 2, ny + nb[1] + nb[3] * 0.32 - H / 2];
  return [a, b];
}

const StringLayer: React.FC<{ stations: Station[]; i: number; frame: number; aspects: Record<string, number> }> = ({ stations, i, frame, aspects }) => {
  const start = stations[i].start;
  const [a, b] = stringEnds(stations, i, aspects);
  const pts = upTo(stringPoints(a, b), glideProgress(start, start + stepped(frame - start)));
  const xs = [a[0], b[0]], ys = [a[1], b[1]];
  const left = Math.min(...xs) - 200, top = Math.min(...ys) - 200;
  const w = Math.abs(b[0] - a[0]) + 400, h = Math.abs(b[1] - a[1]) + 400;
  return (
    <svg width={w} height={h} style={{ position: "absolute", left, top }}>
      {pts.length > 1 && (
        <polyline points={pts.map(([x, y]) => `${f1(x - left)},${f1(y - top)}`).join(" ")} fill="none" stroke={COLORS.red}
          strokeWidth={5} strokeLinecap="round" strokeLinejoin="round" />
      )}
      <circle cx={a[0] - left + 2} cy={a[1] - top + 4} r={11} fill="rgba(23,23,22,0.3)" />
      <circle cx={a[0] - left} cy={a[1] - top} r={11} fill={COLORS.red} />
    </svg>
  );
};

const StationLayer: React.FC<{
  stations: Station[]; i: number; frame: number; assets: Assets; live: boolean;
}> = ({ stations, i, frame, assets, live }) => {
  const st = stations[i];
  const [sx, sy] = stationCenter(i);
  // the first station is on the desk, settled, from frame 0
  const age = i === 0 ? 1e6 : stepped(frame - st.start);
  const box = heroBox(st.hero, assets.aspects);
  const ev = fired(st.events, frame);
  const stamp = ev.find((e) => e.do === "stamp");
  const kickAge = stamp ? frame - stamp.at : 99;
  const kick = kickAge < TIMING.kick ? (TIMING.kick - kickAge) * 3 : 0;
  const circle = ev.find((e) => e.do === "circle");
  const arrow = ev.find((e) => e.do === "arrow");
  const glideDone = i > 0 && frame >= st.start + TIMING.glide;
  const [, b] = i > 0 ? stringEnds(stations, i, assets.aspects) : [[0, 0], [0, 0]];
  return (
    <div style={{ position: "absolute", left: sx - W / 2, top: sy - H / 2, width: W, height: H }}>
      <SpriteAt s={assets.sprites.get(`low${i}`)} />
      <SpriteAt s={assets.sprites.get(`scrap${i}`)} />
      {st.hero && (
        <div style={{ position: "absolute", left: 0, top: 0, width: W, height: H, transform: kick ? `translateY(${kick}px)` : undefined }}>
          <HeroLayer hero={st.hero} i={i} age={age} frame={frame} box={box} sprites={assets.sprites} live={live} />
        </div>
      )}
      {st.headline && <HeadlineLayer station={st} i={i} age={age} frame={frame} sprite={assets.sprites.get(`head${i}`)} />}
      {glideDone && <Pin x={b[0] - sx + W / 2} y={b[1] - sy + H / 2} />}
      {circle && <Circle e={circle} box={box} frame={frame} seed={i + 5} />}
      {arrow && <Arrow e={arrow} box={box} frame={frame} sprites={assets.sprites} />}
      {live && stamp && <Stamp e={stamp} hero={st.hero} box={box} frame={frame} />}
    </div>
  );
};

export default function EditorialCollage({ collage }: EditorialCollageProps) {
  const frame = useCurrentFrame();
  const data = collage;
  const assets = useAssets(data);
  if (!assets) return <AbsoluteFill style={{ background: COLORS.desk }} />;
  const starts = data.stations.map((s) => s.start);
  const k = stationIndexAt(data.stations, frame);
  const moving = gliding(starts, frame);
  const [camX, camY] = cameraAt(starts, frame);
  const ox = Math.round(W / 2 - camX), oy = Math.round(H / 2 - camY);
  const P = DESK.tile;
  const dx = -(((Math.round(camX) % P) + P) % P), dy = -(((Math.round(camY) % P) + P) % P);
  // a layer carries a transform only while the camera moves; at rest it is placed with left/top
  const place = (x: number, y: number): React.CSSProperties =>
    moving ? { left: 0, top: 0, transform: `translate(${x}px, ${y}px)` } : { left: x, top: y };
  return (
    <AbsoluteFill style={{ background: COLORS.desk, overflow: "hidden" }}>
      <Bitmap src={assets.desk} style={place(dx, dy)} />
      <PaperFinish grain={0.2} vignette={0.55} edge="#6E5E44" seed={2017} />
      <div style={{ position: "absolute", width: 1, height: 1, ...place(ox, oy) }}>
        {k > 0 && <StationLayer stations={data.stations} i={k - 1} frame={frame} assets={assets} live={moving} />}
        {k > 0 && <StringLayer stations={data.stations} i={k} frame={frame} aspects={assets.aspects} />}
        <StationLayer stations={data.stations} i={k} frame={frame} assets={assets} live />
      </div>
    </AbsoluteFill>
  );
}
