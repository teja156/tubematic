/*
 * The news strap: a dateline, a lemon kicker and the headline on a paper strap,
 * with its source as a citation line (no outlet name or logo of its own: a
 * headline with no source is made up and carries the EXAMPLE tag), words of it
 * highlighted as they are read, and an optional split-flap board where a value
 * flips from one figure to another.
 */
import React from "react";
import { LAYOUT, TIMING, WRAP, TOP_TEXT_RIGHT, type StrapData } from "./contract";
import { MONO, SANS } from "./fonts";
import { arrival, clamp01, easeOut, type Look } from "./draw";
import { ExampleTag, MarkedText } from "./parts";

const TILE_W = 76;
const TILE_H = 110;

export const Strap: React.FC<{ data: StrapData; frame: number; origin: number; P: Look }> = ({
  data, frame, origin, P,
}) => {
  const width = LAYOUT.right - LAYOUT.left;
  const marks = (data.marks ?? []).filter((m) => frame >= m.at).map((m) => ({
    match: m.match, kind: "highlight" as const, k: easeOut((frame - m.at) / TIMING.mark),
  }));
  return (
    <div style={{ position: "absolute", left: LAYOUT.left, top: LAYOUT.titleY + 24, width }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", height: 44,
        width: TOP_TEXT_RIGHT.exampleTag - LAYOUT.left }}>
        <div style={{ fontFamily: MONO, fontWeight: 400, fontSize: 28, letterSpacing: 2, color: P.muted,
          textTransform: "uppercase" }}>
          {data.date}
        </div>
        {data.source ? null : <ExampleTag P={P} style={{ position: "relative" }} />}
      </div>
      <div style={{ display: "inline-block", marginTop: 24, background: P.lemon, color: P.cardInk, fontFamily: SANS,
        fontWeight: 700, fontSize: 40, lineHeight: "52px", letterSpacing: 2, textTransform: "uppercase",
        padding: "2px 18px", borderRadius: 6 }}>
        {data.kicker}
      </div>
      <div style={{ display: "flex", marginTop: 14 }}>
        <div style={{ width: 14, background: P.lemon, borderRadius: "6px 0 0 6px" }} />
        <div style={{ flex: 1, background: P.card, color: P.cardInk, border: `2px solid ${P.optionBorder}`,
          borderLeft: "none", borderRadius: "0 18px 18px 0", padding: "26px 34px", fontFamily: SANS, fontWeight: 700,
          fontSize: 60, lineHeight: "70px" }}>
          {/* The headline wraps in WRAP.headline so it ends left of the watermark's keep-out line. */}
          <div style={{ maxWidth: WRAP.headline[1] }}>
            <MarkedText text={data.headline} marks={marks} color={P.cardInk} P={P} />
          </div>
        </div>
      </div>
      {data.source ? (
        <div style={{ marginTop: 16, fontFamily: MONO, fontWeight: 400, fontSize: 26, letterSpacing: 1,
          color: P.muted }}>
          {`SOURCE: ${data.source}`}
        </div>
      ) : null}
      {data.flap ? <Flap flap={data.flap} frame={frame} origin={origin} P={P} /> : null}
    </div>
  );
};

const Flap: React.FC<{ flap: NonNullable<StrapData["flap"]>; frame: number; origin: number; P: Look }> = ({
  flap, frame, origin, P,
}) => {
  const n = Math.max(flap.from.length, flap.to.length);
  const from = flap.from.padStart(n, " ");
  const to = flap.to.padStart(n, " ");
  return (
    <div style={{ marginTop: 56 }}>
      <div style={{ fontFamily: SANS, fontWeight: 600, fontSize: 34, letterSpacing: 2, color: P.muted,
        textTransform: "uppercase", marginBottom: 14 }}>
        {flap.label}
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        {Array.from({ length: n }, (_, i) => {
          const k = from[i] === to[i] ? 1 : arrival(frame, flap.at + i * TIMING.flipPerTile, TIMING.flip, origin);
          return <Tile key={i} from={from[i]} to={to[i]} k={frame < flap.at && flap.at > origin ? 0 : k} P={P} />;
        })}
      </div>
    </div>
  );
};

/** One split-flap tile: the top half of the old character falls away to show
 *  the new one's top, then the new one's bottom half falls into place. */
const Tile: React.FC<{ from: string; to: string; k: number; P: Look }> = ({ from, to, k, P }) => {
  const half = TILE_H / 2;
  const glyph = (ch: string, top: boolean) => (
    <div style={{ position: "absolute", left: 0, right: 0, top: top ? 0 : -half, height: TILE_H, textAlign: "center",
      fontFamily: MONO, fontWeight: 700, fontSize: 76, lineHeight: `${TILE_H}px`, color: P.boardInk }}>
      {ch}
    </div>
  );
  const halfBox = (ch: string, top: boolean, extra?: React.CSSProperties) => (
    <div style={{ position: "absolute", left: 0, right: 0, top: top ? 0 : half, height: half, overflow: "hidden",
      background: P.board, ...extra }}>
      {glyph(ch, top)}
    </div>
  );
  const t = clamp01(k);
  return (
    <div style={{ position: "relative", width: TILE_W, height: TILE_H, borderRadius: 8, overflow: "hidden" }}>
      {halfBox(t > 0 ? to : from, true)}
      {halfBox(t >= 1 ? to : from, false)}
      {t > 0 && t < 0.5 ? halfBox(from, true, { transformOrigin: "50% 100%", transform: `scaleY(${1 - 2 * t})` }) : null}
      {t >= 0.5 && t < 1 ? halfBox(to, false, { transformOrigin: "50% 0%", transform: `scaleY(${2 * t - 1})` }) : null}
      <div style={{ position: "absolute", left: 0, right: 0, top: half - 1, height: 2, background: P.canvas }} />
    </div>
  );
};
