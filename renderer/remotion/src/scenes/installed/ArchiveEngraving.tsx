/*
 * ArchiveEngraving: the whole of an Archive and Engraving video, as one scene.
 *
 * A grave, scholarly history told as a museum page: warm parchment with a
 * ruled border and a small-caps running header, a dated serif title with one
 * word in red, and one cream museum card per beat: an engraved plate (a
 * generated still baked to ink on laid paper), an antique chart whose route
 * is drawn in red dots, a person's name card with an engraved roundel (an
 * emblem or initials, never a face), a row of such cards joined in red, or a
 * recreated document whose lines write on. Strikes, underlines, stamps, a
 * magnifying roundel and a timeline ruler land on the narration's words. The
 * captions are the shared Subtitles layer in its "fill" look on a cream chip.
 *
 * The agent never writes this file's kind of code: it writes `props.archive`
 * (beats and events timed to the narration), which the MCP server validates
 * against ./archiveEngraving/contract.ts before the video can render.
 *
 * Every plate and chart card carries the footnote "Illustration" and every
 * document card "Recreation" (contract.ts FOOTNOTES); the data has no field
 * that hides them.
 *
 * Kept cheap on the CPU renderer (software GL): a still is an <image> in an
 * SVG whose viewBox selects the part on screen (Case File Story's way); the
 * parchment grain and vignette are one canvas painted once (PaperFinish); no
 * SVG filter, blend mode, live gradient or stroke-dasharray (a route is a row
 * of dots, a strike or underline a box that grows).
 *
 * Measured in CPU-seconds per frame over the whole skill example (1,218
 * frames, rendered from a prebuilt bundle with software GL, concurrency 2):
 * 0.47 here, 0.23 for System Flow's example on the same day by the same
 * method (2.1x). Nearly all of it is the plate's slow push, a new picture on
 * every frame; a beat with no plate costs about what System Flow does.
 */
import React, { useEffect, useState } from "react";
import { AbsoluteFill, cancelRender, continueRender, delayRender, useCurrentFrame, useVideoConfig } from "remotion";
import {
  COLORS, FOOTNOTES, H, TIMING, W, ZONES,
  type ArchiveData, type ArchiveEvent, type Beat, type ChartCard, type DocumentCard, type Emblem, type PeopleCard,
  type Person, type PlateCard, type UV,
} from "./archiveEngraving/contract";
import {
  beatEnd, beatIndexAt, clamp01, cleanWord, documentSize, dotsAlong, easeOut, peopleBoxes, plateView, pushScale,
  magnifierOnRight, rulerMarker, rulerScale, rulerX, titleLayout, toWindow, writtenChars,
} from "./archiveEngraving/stage";
import { emblemShapes, roundelShapes, SIZE, type Shape } from "./archiveEngraving/emblems";
import { useFonts, type FontFile } from "./paper/fonts";
import { PaperFinish } from "./paper/PaperFinish";

export const ARCHIVE_FONTS: FontFile[] = [
  ["Cormorant Upright", "fonts/cormorant-upright-latin-600-normal.woff2", "600"],
  ["Bodoni Moda SC", "fonts/bodoni-moda-sc-latin-500-normal.woff2", "500"],
  ["EB Garamond", "fonts/eb-garamond-latin-400-normal.woff2", "400"],
  ["EB Garamond", "fonts/eb-garamond-latin-400-italic.woff2", "400", "italic"],
  ["EB Garamond", "fonts/eb-garamond-latin-500-normal.woff2", "500"],
  ["Inter", "fonts/inter-latin-800-normal.woff2", "800"],
  ["Kalam", "fonts/kalam-latin-700-normal.woff2", "700"],
];

const TITLE = "'Cormorant Upright', 'Cormorant Garamond', Georgia, serif";
const SMALLCAPS = "'Bodoni Moda SC', 'Bodoni Moda', Didot, Georgia, serif";
const GARAMOND = "'EB Garamond', Garamond, Georgia, serif";
const SANS = "Inter, 'Helvetica Neue', Arial, sans-serif";
const HAND = "Kalam, 'Comic Neue', cursive";
const CARD_SHADOW = "0 1px 0 rgba(60,45,25,0.18), 0 8px 18px rgba(60,45,25,0.16)";
const Z = ZONES;

export interface ArchiveEngravingProps {
  archive: ArchiveData;
}

const ROMAN: [number, string][] = [[10, "X"], [9, "IX"], [5, "V"], [4, "IV"], [1, "I"]];
export function roman(n: number): string {
  let out = "";
  let rest = n;
  for (const [v, s] of ROMAN) while (rest >= v) {
    out += s;
    rest -= v;
  }
  return out;
}

/** Every still the video uses, loaded and decoded before the first frame; one that will not load fails the render. */
function useStills(srcs: string[]) {
  const key = srcs.join("|");
  const [handle] = useState(() => (srcs.length ? delayRender("ArchiveEngraving: loading the plates") : null));
  useEffect(() => {
    if (handle === null) return;
    Promise.all(srcs.map((src) => {
      const img = new Image();
      img.src = src;
      return img.decode();
    }))
      .then(() => continueRender(handle))
      .catch((err) => cancelRender(err));
    // the stills are fixed for the whole render
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [handle, key]);
}

const f1 = (n: number) => n.toFixed(2);

// ── the roundel ──────────────────────────────────────────────────────────────
const ShapeEl: React.FC<{ s: Shape }> = ({ s }) => {
  const fill = s.fill === "ink" ? COLORS.ink : s.fill === "card" ? COLORS.card : "none";
  const w = s.w ?? 2;
  const stroke = w > 0 ? COLORS.ink : "none";
  if (s.t === "circle") return <circle cx={f1(s.cx)} cy={f1(s.cy)} r={f1(s.r)} fill={fill} stroke={stroke} strokeWidth={w} />;
  if (s.t === "ellipse") {
    return <ellipse cx={f1(s.cx)} cy={f1(s.cy)} rx={s.rx} ry={s.ry} transform={`rotate(${f1(s.rot)} ${f1(s.cx)} ${f1(s.cy)})`}
      fill={fill} stroke={stroke} strokeWidth={w} />;
  }
  const pts = s.pts.map(([x, y]) => `${f1(x)},${f1(y)}`).join(" ");
  return s.closed
    ? <polygon points={pts} fill={fill} stroke={stroke} strokeWidth={w} strokeLinejoin="round" />
    : <polyline points={pts} fill="none" stroke={stroke} strokeWidth={w} strokeLinecap="round" strokeLinejoin="round" opacity={w < 1 ? 0.5 : 1} />;
};

export const Roundel: React.FC<{ size: number; emblem?: Emblem; initials?: string }> = ({ size, emblem, initials }) => (
  <div style={{ position: "relative", width: size, height: size }}>
    <svg width={size} height={size} viewBox={`0 0 ${SIZE} ${SIZE}`} style={{ position: "absolute", left: 0, top: 0 }}>
      {roundelShapes().map((s, i) => <ShapeEl key={`r${i}`} s={s} />)}
      {emblem ? emblemShapes(emblem).map((s, i) => <ShapeEl key={`e${i}`} s={s} />) : (
        <circle cx={100} cy={100} r={52} fill={COLORS.card} stroke={COLORS.ink} strokeWidth={1.4} />
      )}
    </svg>
    {!emblem && initials && (
      <div style={{
        position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center",
        fontFamily: SMALLCAPS, fontWeight: 500, color: COLORS.ink, letterSpacing: "0.02em",
        fontSize: size * (initials.length > 2 ? 0.2 : 0.26), paddingBottom: size * 0.03,
      }}>{initials}</div>
    )}
  </div>
);

// ── the header and the ruler ─────────────────────────────────────────────────
const Header: React.FC<{ text: string; plate: number }> = ({ text, plate }) => (
  <>
    <div style={{
      position: "absolute", left: Z.titleLeft, right: Z.titleLeft, top: Z.headerY - 44, display: "flex",
      justifyContent: "space-between", fontFamily: SMALLCAPS, fontWeight: 500, fontSize: 30, letterSpacing: "0.08em",
      color: COLORS.inkSoft, whiteSpace: "nowrap",
    }}>
      <span>{text}</span>
      <span>Pl. {roman(plate)}</span>
    </div>
    <div style={{ position: "absolute", left: Z.titleLeft, width: W - 2 * Z.titleLeft, top: Z.headerY, height: 2, background: COLORS.rule }} />
    <div style={{ position: "absolute", left: Z.titleLeft, width: W - 2 * Z.titleLeft, top: Z.headerY + 6, height: 1, background: COLORS.rule }} />
  </>
);

const Ruler: React.FC<{ data: ArchiveData; frame: number }> = ({ data, frame }) => {
  const events = data.beats.flatMap((b) => b.events ?? []).filter((e) => e.do === "timeline");
  const scale = rulerScale(events.flatMap((e) => [e.from ?? 0, e.to ?? 0]));
  const first = events.reduce((m, e) => Math.min(m, e.at), Infinity);
  const year = rulerMarker(events, frame);
  if (!scale || year === null) return null;
  const ticks: number[] = [];
  for (let y = scale.start; y <= scale.end; y += scale.step) ticks.push(y);
  const x = rulerX(year, scale);
  return (
    <div style={{ position: "absolute", left: 0, top: 0, width: W, height: H, opacity: clamp01((frame - first) / TIMING.rulerFade) }}>
      <div style={{ position: "absolute", left: Z.rulerLeft - 20, width: Z.rulerRight - Z.rulerLeft + 40, top: Z.rulerY, height: 2, background: COLORS.rule }} />
      {ticks.map((t) => (
        <React.Fragment key={t}>
          <div style={{ position: "absolute", left: rulerX(t, scale) - 1, top: Z.rulerY - 7, width: 2, height: 16, background: COLORS.rule }} />
          <div style={{
            position: "absolute", left: rulerX(t, scale) - 60, width: 120, top: Z.rulerY + 16, textAlign: "center",
            fontFamily: GARAMOND, fontSize: 28, color: Math.round(year) === t ? COLORS.ink : COLORS.inkSoft,
          }}>{t}</div>
        </React.Fragment>
      ))}
      <div style={{ position: "absolute", left: x - 7, top: Z.rulerY - 6, width: 14, height: 14, borderRadius: 7, background: COLORS.red }} />
      <div style={{ position: "absolute", left: x - 1.5, top: Z.rulerY - 34, width: 3, height: 30, background: COLORS.red }} />
      <div style={{
        position: "absolute", left: x, top: Z.rulerY - 76, transform: "translateX(-50%)", background: COLORS.red,
        color: COLORS.card, fontFamily: SANS, fontWeight: 800, fontSize: 26, letterSpacing: "0.06em", padding: "4px 12px 5px",
      }}>{Math.round(year)}</div>
    </div>
  );
};

// ── the title ────────────────────────────────────────────────────────────────
const Title: React.FC<{ beat: Beat; frame: number }> = ({ beat, frame }) => {
  const { size, lines } = titleLayout(beat.title.text);
  const fired = (beat.events ?? []).filter((e) => e.at <= frame);
  const strike = fired.find((e) => e.do === "strike");
  const underlines = fired.filter((e) => e.do === "underline");
  const red = cleanWord(beat.title.red);
  let redDone = false;
  let strikeDone = false;
  const seen = new Set<string>();
  const mark = (word: string) => {
    const w = cleanWord(word);
    const isRed = !redDone && w === red;
    if (isRed) redDone = true;
    const isStrike = !!strike && !strikeDone && w === cleanWord(strike.word ?? "");
    if (isStrike) strikeDone = true;
    const under = !seen.has(w) ? underlines.find((e) => cleanWord(e.word ?? "") === w) : undefined;
    seen.add(w);
    return { isRed, isStrike, under };
  };
  return (
    <>
      {beat.date && (
        <div style={{ position: "absolute", left: Z.titleLeft, top: Z.dateTop, display: "flex", alignItems: "center", gap: 18 }}>
          <div style={{ width: 34, height: 3, background: COLORS.red }} />
          <div style={{ fontFamily: SANS, fontWeight: 800, fontSize: 30, letterSpacing: "0.14em", color: COLORS.ink, textTransform: "uppercase", whiteSpace: "nowrap" }}>
            {beat.date.slice(0, Math.ceil(beat.date.length * clamp01((frame - beat.start + 1) / TIMING.dateType)))}
          </div>
        </div>
      )}
      <div style={{ position: "absolute", left: Z.titleLeft, top: Z.titleTop, fontFamily: TITLE, fontWeight: 600, fontSize: size, lineHeight: 1.06, color: COLORS.ink }}>
        {lines.map((line, li) => (
          <div key={li} style={{ whiteSpace: "nowrap" }}>
            {line.split(" ").map((word, wi) => {
              const m = mark(word);
              return (
                <React.Fragment key={wi}>
                  {wi > 0 && " "}
                  <span style={{ position: "relative", color: m.isRed ? COLORS.red : m.isStrike ? COLORS.inkSoft : COLORS.ink }}>
                    {word}
                    {m.isStrike && strike && (
                      <span style={{
                        position: "absolute", left: -4, top: "56%", height: Math.max(4, size * 0.05), background: COLORS.red,
                        width: `calc(${f1(100 * easeOut((frame - strike.at) / TIMING.strike))}% + 8px)`,
                      }} />
                    )}
                    {m.under && (
                      <span style={{
                        position: "absolute", left: 0, top: "96%", height: Math.max(3, size * 0.04), background: COLORS.red,
                        width: `${f1(100 * easeOut((frame - m.under.at) / TIMING.underline))}%`,
                      }} />
                    )}
                  </span>
                </React.Fragment>
              );
            })}
          </div>
        ))}
      </div>
      {strike && strike.with && (
        <div style={{
          position: "absolute", left: Z.titleLeft, top: Math.min(Z.withTop, Z.titleTop + lines.length * size * 1.06 + 4), fontFamily: GARAMOND, fontStyle: "italic", fontSize: 66,
          lineHeight: 1, color: COLORS.red, whiteSpace: "nowrap",
          opacity: clamp01((frame - strike.at - 4) / 6),
          transform: `translateY(${f1(30 * (1 - easeOut((frame - strike.at - 4) / TIMING.withRise)))}px)`,
        }}>{strike.with}</div>
      )}
    </>
  );
};

// ── the cards ────────────────────────────────────────────────────────────────
const Footnote: React.FC<{ text: string }> = ({ text }) => (
  <div style={{
    position: "absolute", right: W - Z.cardRight + 22, top: Z.cardBottom - 36, fontFamily: GARAMOND, fontStyle: "italic",
    fontSize: 22, color: COLORS.inkSoft, whiteSpace: "nowrap",
  }}>{text}</div>
);

const cardBox: React.CSSProperties = {
  position: "absolute", left: Z.cardLeft, top: Z.cardTop, width: Z.cardRight - Z.cardLeft, height: Z.cardBottom - Z.cardTop,
  background: COLORS.card, boxShadow: CARD_SHADOW,
};

const PlateLayer: React.FC<{ card: PlateCard | ChartCard; beat: Beat; frame: number; end: number; figure: number }> = ({
  card, beat, frame, end, figure,
}) => {
  const focus: UV = card.focus ?? [0.5, 0.5];
  const view = plateView(pushScale(frame, beat.start, end), focus);
  const events = (beat.events ?? []).filter((e) => e.at <= frame);
  const route = card.kind === "chart" ? events.find((e) => e.do === "route") : undefined;
  const magnify = events.find((e) => e.do === "magnify" && e.point);
  return (
    <>
      <div style={cardBox} />
      <svg width={Z.winW} height={Z.winH} viewBox={view.map(f1).join(" ")} preserveAspectRatio="none"
        style={{ position: "absolute", left: Z.winLeft, top: Z.winTop }}>
        <image href={card.image} x={0} y={0} width={W} height={H} preserveAspectRatio="xMidYMid slice" />
      </svg>
      <div style={{ position: "absolute", left: Z.winLeft - 1, top: Z.winTop - 1, width: Z.winW, height: Z.winH, border: `1.5px solid ${COLORS.ink}` }} />
      {route && card.kind === "chart" && (
        <svg width={W} height={H} style={{ position: "absolute", left: 0, top: 0 }}>
          {dotsAlong(card.route.map((p) => toWindow(view, p)), (frame - route.at) / TIMING.route).map(([x, y], i) => (
            <circle key={i} cx={f1(x)} cy={f1(y)} r={i === 0 ? 9 : 5.5} fill={COLORS.red} />
          ))}
        </svg>
      )}
      {magnify && magnify.point && <Magnifier card={card} view={view} point={magnify.point} age={frame - magnify.at} figure={figure} />}
      <div style={{
        position: "absolute", left: Z.cardLeft, width: Z.cardRight - Z.cardLeft, top: Z.winTop + Z.winH + 12, textAlign: "center",
        fontFamily: SMALLCAPS, fontWeight: 500, fontSize: 40, letterSpacing: "0.06em", color: COLORS.ink, whiteSpace: "nowrap",
      }}>{card.name}</div>
      {card.note && (
        <div style={{
          position: "absolute", left: Z.cardLeft, width: Z.cardRight - Z.cardLeft, top: Z.winTop + Z.winH + 60, textAlign: "center",
          fontFamily: GARAMOND, fontStyle: "italic", fontSize: 28, color: COLORS.inkSoft, whiteSpace: "nowrap",
        }}>{card.note}</div>
      )}
      <Footnote text={FOOTNOTES[card.kind]} />
    </>
  );
};

export const MAGNIFIER = 340;

const Magnifier: React.FC<{ card: PlateCard | ChartCard; view: [number, number, number, number]; point: UV; age: number; figure: number }> = ({
  card, view, point, age, figure,
}) => {
  const [px, py] = toWindow(view, point);
  const tx = magnifierOnRight(view, point) ? Z.winLeft + Z.winW - MAGNIFIER / 2 - 24 : Z.winLeft + MAGNIFIER / 2 + 24;
  const ty = Z.winTop + Z.winH / 2;
  const k = easeOut(age / TIMING.magnify);
  const cx = px + (tx - px) * k, cy = py + (ty - py) * k;
  const s = 0.15 + 0.85 * k;
  const span = (MAGNIFIER * (view[2] / Z.winW)) / TIMING.magnifyZoom;
  const vb = [point[0] * W - span / 2, point[1] * H - span / 2, span, span];
  return (
    <>
      <div style={{ position: "absolute", left: px - 30, top: py - 30, width: 60, height: 60, borderRadius: 30, border: `4px solid ${COLORS.red}`, opacity: clamp01(age / 4) }} />
      <div style={{
        position: "absolute", left: cx - MAGNIFIER / 2, top: cy - MAGNIFIER / 2, width: MAGNIFIER, height: MAGNIFIER,
        transform: `scale(${f1(s)})`, borderRadius: "50%", overflow: "hidden", background: COLORS.card,
        border: `6px solid ${COLORS.ink}`, boxShadow: `0 0 0 5px ${COLORS.card}, 0 0 0 7px ${COLORS.ink}, ${CARD_SHADOW}`,
      }}>
        <svg width={MAGNIFIER} height={MAGNIFIER} viewBox={vb.map(f1).join(" ")} preserveAspectRatio="none" style={{ position: "absolute", left: -6, top: -6 }}>
          <image href={card.image} x={0} y={0} width={W} height={H} preserveAspectRatio="xMidYMid slice" />
        </svg>
      </div>
      <div style={{
        position: "absolute", left: cx - MAGNIFIER / 2 + 6, top: cy - MAGNIFIER / 2 - 2, opacity: clamp01((age - TIMING.magnify + 4) / 4),
        background: COLORS.card, border: `1.5px solid ${COLORS.ink}`, padding: "2px 10px", fontFamily: SMALLCAPS, fontWeight: 500,
        fontSize: 24, color: COLORS.ink, whiteSpace: "nowrap",
      }}>Fig. {figure}</div>
    </>
  );
};

const PEOPLE_ROUNDEL_TOP = 60;

const PersonLayer: React.FC<{
  person: Person; box: [number, number, number, number]; size: number; nameSize: number; small: boolean; top?: number;
}> = ({ person, box, size, nameSize, small, top: roundelTop }) => {
  const [left, top, width, height] = box;
  return (
    <div style={{
      position: "absolute", left, top, width, height, background: COLORS.card, boxShadow: CARD_SHADOW, textAlign: "center",
      display: "flex", flexDirection: "column", alignItems: "center", justifyContent: roundelTop === undefined ? "center" : "flex-start",
      padding: `${roundelTop ?? 0}px 16px 0`, boxSizing: "border-box",
    }}>
      <Roundel size={size} emblem={person.emblem} initials={person.initials} />
      <div style={{
        marginTop: small ? 22 : 34, fontFamily: SMALLCAPS, fontWeight: 500, fontSize: nameSize, lineHeight: 1.08,
        letterSpacing: "0.04em", color: COLORS.ink,
      }}>{person.name}</div>
      <div style={{ marginTop: small ? 16 : 22, width: small ? 28 : 40, height: 3, background: COLORS.red }} />
      <div style={{
        marginTop: small ? 14 : 20, fontFamily: SANS, fontWeight: 800, fontSize: small ? 22 : 30, letterSpacing: "0.14em",
        color: COLORS.ink, whiteSpace: "nowrap",
      }}>{person.dates}</div>
      <div style={{
        marginTop: small ? 10 : 14, fontFamily: GARAMOND, fontStyle: "italic", fontSize: small ? 28 : 40, lineHeight: 1.1,
        color: COLORS.inkSoft,
      }}>{person.role}</div>
    </div>
  );
};

export function nameSize(name: string, width: number, max: number): number {
  // a Bodoni small-caps character is about 0.62 of its size wide; a name may take two lines
  const longest = Math.max(1, ...name.split(/\s+/).map((w) => w.length));
  return Math.max(22, Math.min(max, Math.floor((width - 28) / (longest * 0.62)), Math.floor(((width - 28) * 2) / (name.length * 0.62))));
}

const PeopleLayer: React.FC<{ card: PeopleCard; frame: number }> = ({ card, frame }) => {
  const boxes = peopleBoxes(card.people.length);
  const top = Z.cardTop + 20, height = Z.cardBottom - Z.cardTop - 30;
  const size = Math.min(210, Math.round(boxes[0][1] - 60));
  // the connectors join the roundels, which sit at a fixed height in every card of the row
  const ry = top + PEOPLE_ROUNDEL_TOP + size / 2;
  return (
    <>
      {card.people.map((p, i) => {
        const age = frame - p.at;
        if (age < 0) return null;
        const k = easeOut(age / TIMING.person);
        return (
          <div key={i} style={{ opacity: clamp01(age / TIMING.person), transform: `translateY(${f1(24 * (1 - k))}px)` }}>
            <PersonLayer person={p} box={[boxes[i][0], top, boxes[i][1], height]} size={size}
              nameSize={nameSize(p.name, boxes[i][1], 40)} small top={PEOPLE_ROUNDEL_TOP} />
          </div>
        );
      })}
      <svg width={W} height={H} style={{ position: "absolute", left: 0, top: 0 }}>
        {card.people.slice(1).map((p, i) => {
          const age = frame - p.at;
          if (age < 0) return null;
          const x0 = boxes[i][0] + boxes[i][1] / 2 + size / 2 + 4;
          const x1 = boxes[i + 1][0] + boxes[i + 1][1] / 2 - size / 2 - 4;
          const x = x0 + (x1 - x0) * easeOut(age / TIMING.connector);
          return (
            <g key={i}>
              <line x1={f1(x0)} y1={f1(ry)} x2={f1(x)} y2={f1(ry)} stroke={COLORS.red} strokeWidth={3.5} strokeLinecap="round" />
              <circle cx={f1(x0)} cy={f1(ry)} r={5} fill={COLORS.red} />
              {age >= TIMING.connector && <polygon points={`${f1(x1)},${f1(ry)} ${f1(x1 - 14)},${f1(ry - 8)} ${f1(x1 - 14)},${f1(ry + 8)}`} fill={COLORS.red} />}
            </g>
          );
        })}
      </svg>
    </>
  );
};

const DocumentLayer: React.FC<{ card: DocumentCard; frame: number }> = ({ card, frame }) => {
  const hand = !!card.hand;
  const size = documentSize(card.lines.map((l) => l.text), hand);
  const lineH = Math.round(size * 1.6);
  const top = Z.cardTop + 40;
  const rows = Math.floor((Z.cardBottom - top - 50) / lineH);
  return (
    <div style={{ ...cardBox, transform: "rotate(-0.8deg)" }}>
      <svg width={Z.cardRight - Z.cardLeft} height={Z.cardBottom - Z.cardTop} style={{ position: "absolute", left: 0, top: 0 }}>
        {Array.from({ length: 22 }, (_, i) => <rect key={`c${i}`} x={20 + i * 40} y={0} width={1} height={Z.cardBottom - Z.cardTop} fill={COLORS.ink} opacity={0.05} />)}
        {Array.from({ length: rows }, (_, i) => <rect key={`l${i}`} x={30} y={40 + (i + 1) * lineH - 4} width={Z.cardRight - Z.cardLeft - 60} height={1.5} fill={COLORS.rule} opacity={0.45} />)}
        <rect x={86} y={0} width={2} height={Z.cardBottom - Z.cardTop} fill={COLORS.red} opacity={0.55} />
      </svg>
      {card.lines.map((line, i) => {
        const n = writtenChars(line.text, line.at, frame, hand);
        return (
          <div key={i} style={{
            position: "absolute", left: 110, top: 40 + i * lineH + (lineH - size * 1.2) - 6, fontFamily: hand ? HAND : GARAMOND,
            fontWeight: hand ? 700 : 500, fontSize: size, lineHeight: 1.2, color: hand ? "#2B2620" : COLORS.ink, whiteSpace: "nowrap",
          }}>{line.text.slice(0, n)}</div>
        );
      })}
      <div style={{ position: "absolute", right: 22, bottom: 12, fontFamily: GARAMOND, fontStyle: "italic", fontSize: 22, color: COLORS.inkSoft }}>
        {FOOTNOTES.document}
      </div>
    </div>
  );
};

const Stamp: React.FC<{ e: ArchiveEvent; frame: number; x: number }> = ({ e, frame, x }) => {
  const age = frame - e.at;
  const s = age < TIMING.stamp ? 1.6 - 0.6 * (age / TIMING.stamp) : 1;
  return (
    <div style={{
      position: "absolute", left: x, top: Z.stampY, transform: `translate(-50%, -50%) rotate(-8deg) scale(${f1(s)})`,
      border: `5px solid ${COLORS.red}`, padding: 4, opacity: 0.94, background: "rgba(241,232,210,0.86)",
    }}>
      <div style={{
        border: `2px solid ${COLORS.red}`, padding: "6px 20px", color: COLORS.red, whiteSpace: "nowrap",
        fontFamily: SANS, fontWeight: 800, fontSize: 38, letterSpacing: "0.1em", lineHeight: 1,
      }}>{e.text}</div>
    </div>
  );
};

/** The stamp sits at the card's lower right, or lower left when a magnifying roundel takes the right side. */
function stampX(beat: Beat, frame: number, end: number): number {
  const card = beat.card;
  const magnify = (beat.events ?? []).find((e) => e.do === "magnify" && e.point);
  if ((card.kind !== "plate" && card.kind !== "chart") || !magnify?.point) return Z.stampX;
  const view = plateView(pushScale(frame, beat.start, end), card.focus ?? [0.5, 0.5]);
  return magnifierOnRight(view, magnify.point) ? W - Z.stampX : Z.stampX;
}

// ── a beat ───────────────────────────────────────────────────────────────────
const BeatLayer: React.FC<{ beat: Beat; frame: number; end: number; figure: number; first: boolean }> = ({ beat, frame, end, figure, first }) => {
  const age = frame - beat.start;
  const k = first ? 1 : easeOut(age / TIMING.enter);
  const fired = (beat.events ?? []).filter((e) => e.at <= frame);
  const stamp = fired.find((e) => e.do === "stamp");
  const kickAge = stamp ? frame - stamp.at : 99;
  const kick = kickAge < TIMING.kick ? (TIMING.kick - kickAge) * 2 : 0;
  const card = beat.card;
  return (
    <AbsoluteFill style={{ opacity: first ? 1 : clamp01(age / TIMING.enter) }}>
      <Title beat={beat} frame={frame} />
      {/* a transform only while the card moves: an idle transformed layer is recomposited every frame */}
      <div style={{ position: "absolute", left: 0, top: 0, width: W, height: H, transform: 26 * (1 - k) + kick ? `translateY(${f1(26 * (1 - k) + kick)}px)` : undefined }}>
        {(card.kind === "plate" || card.kind === "chart") && <PlateLayer card={card} beat={beat} frame={frame} end={end} figure={figure} />}
        {card.kind === "person" && (
          <PersonLayer person={card} box={[Z.cardLeft + 70, Z.cardTop, Z.cardRight - Z.cardLeft - 140, Z.cardBottom - Z.cardTop]} size={240}
            nameSize={nameSize(card.name, Z.cardRight - Z.cardLeft - 140, 62)} small={false} />
        )}
        {card.kind === "people" && <PeopleLayer card={card} frame={frame} />}
        {card.kind === "document" && <DocumentLayer card={card} frame={frame} />}
        {stamp && <Stamp e={stamp} frame={frame} x={stampX(beat, frame, end)} />}
      </div>
    </AbsoluteFill>
  );
};

export default function ArchiveEngraving({ archive }: ArchiveEngravingProps) {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const data = archive;
  useFonts("ArchiveEngraving", ARCHIVE_FONTS);
  const stills = React.useMemo(
    () => Array.from(new Set(data.beats.flatMap((b) => (b.card.kind === "plate" || b.card.kind === "chart" ? [b.card.image] : [])))),
    [data],
  );
  useStills(stills);
  const i = beatIndexAt(data.beats, frame);
  const beat = data.beats[i];
  // a magnifying roundel's figure number counts every magnify up to this beat
  const figure = data.beats.slice(0, i + 1).reduce((n, b) => n + (b.events ?? []).filter((e) => e.do === "magnify").length, 0);
  return (
    <AbsoluteFill style={{ background: COLORS.parchment, overflow: "hidden" }}>
      {/* under the page, never over it: a full-frame canvas over changing content is blended again on every
          frame, which measured about two thirds of a System Flow frame on its own */}
      <PaperFinish grain={0.45} vignette={1} edge={COLORS.edge} seed={1947} />
      <div style={{ position: "absolute", left: 34, top: 34, right: 34, bottom: 34, border: `1.5px solid ${COLORS.rule}` }} />
      <div style={{ position: "absolute", left: 44, top: 44, right: 44, bottom: 44, border: `0.75px solid ${COLORS.rule}` }} />
      <Header text={data.header} plate={i + 1} />
      {beat && <BeatLayer key={i} beat={beat} frame={frame} end={beatEnd(data.beats, i, durationInFrames)} figure={figure} first={i === 0} />}
      <Ruler data={data} frame={frame} />
    </AbsoluteFill>
  );
}
