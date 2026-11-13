/*
 * Pieces every format shares: the EXAMPLE tag, and text with marks (a ring, an
 * underline or a highlight) drawn on around words of it.
 */
import React from "react";
import { MONO } from "./fonts";
import { clamp01, ringPath, underlinePath, type Look } from "./draw";

/** The tag on every made-up thread or headline. Drawn by the component, so no
 *  data can remove it. */
export const ExampleTag: React.FC<{ P: Look; style?: React.CSSProperties }> = ({ P, style }) => (
  <div data-tm-example="1" style={{ position: "absolute", fontFamily: MONO, fontWeight: 700, fontSize: 26,
    letterSpacing: 4, color: P.accent, border: `3px solid ${P.accent}`, borderRadius: 10, padding: "2px 14px",
    lineHeight: "36px", whiteSpace: "nowrap", ...style }}>
    EXAMPLE
  </div>
);

export type TextMark = {
  match: string;
  kind: "underline" | "ring" | "highlight";
  /** 0 to 1: how far the mark has drawn on. */
  k: number;
};

const RING = ringPath(100, 100);
const UNDER = underlinePath(100);

/** `text` with each mark's first occurrence wrapped and drawn on. Marks must
 *  not overlap; a match the text does not hold is skipped. */
export const MarkedText: React.FC<{ text: string; marks: TextMark[]; color: string; P: Look }> = ({
  text, marks, color, P,
}) => {
  const spans: { from: number; to: number; mark: TextMark }[] = [];
  for (const m of marks) {
    const i = m.match ? text.indexOf(m.match) : -1;
    if (i < 0 || spans.some((s) => i < s.to && i + m.match.length > s.from)) continue;
    spans.push({ from: i, to: i + m.match.length, mark: m });
  }
  spans.sort((a, b) => a.from - b.from);
  const out: React.ReactNode[] = [];
  let pos = 0;
  spans.forEach((s, n) => {
    if (s.from > pos) out.push(text.slice(pos, s.from));
    out.push(<Marked key={n} text={text.slice(s.from, s.to)} mark={s.mark} color={color} P={P} />);
    pos = s.to;
  });
  if (pos < text.length) out.push(text.slice(pos));
  return <>{out}</>;
};

const Marked: React.FC<{ text: string; mark: TextMark; color: string; P: Look }> = ({ text, mark, color, P }) => {
  const k = clamp01(mark.k);
  return (
    <span style={{ position: "relative", color, whiteSpace: "nowrap" }}>
      {mark.kind === "highlight" && k > 0 ? (
        <span style={{ position: "absolute", left: -4, top: "18%", height: "70%", width: `calc(${k * 100}% + 8px)`,
          background: P.highlight, opacity: 0.9, borderRadius: 4 }} />
      ) : null}
      <span style={{ position: "relative", color: mark.kind === "highlight" && k > 0.3 ? P.cardInk : color }}>{text}</span>
      {mark.kind === "underline" && k > 0 ? (
        <span style={{ position: "absolute", left: 0, bottom: -10, height: 14, width: `${k * 100}%`, overflow: "hidden" }}>
          <svg viewBox="0 0 100 12" preserveAspectRatio="none" style={{ position: "absolute", left: 0, top: 0,
            width: `${100 / Math.max(k, 0.01)}%`, height: 14 }}>
            <path d={UNDER} fill="none" stroke={P.accent} strokeWidth={4} vectorEffect="non-scaling-stroke"
              strokeLinecap="round" />
          </svg>
        </span>
      ) : null}
      {mark.kind === "ring" && k > 0 ? (
        <span style={{ position: "absolute", left: -18, top: -14, right: -18, bottom: -14, overflow: "hidden",
          clipPath: `inset(0 ${(1 - k) * 100}% 0 0)` }}>
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" style={{ width: "100%", height: "100%" }}>
            <path d={RING} fill="none" stroke={P.accent} strokeWidth={5} vectorEffect="non-scaling-stroke"
              strokeLinecap="round" />
          </svg>
        </span>
      ) : null}
    </span>
  );
};
