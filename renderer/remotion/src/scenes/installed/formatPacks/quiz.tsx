/*
 * The quiz board: the question on a paper card, two to four lettered options
 * that pop in as they are read, then the answer locks: it turns amber and the
 * others fall back.
 */
import React from "react";
import { LAYOUT, TIMING, type QuizData } from "./contract";
import { MONO, SANS } from "./fonts";
import { arrival, backOut, clamp01, easeOut, type Look } from "./draw";

export const Quiz: React.FC<{ data: QuizData; frame: number; origin: number; P: Look }> = ({
  data, frame, origin, P,
}) => {
  const width = LAYOUT.right - LAYOUT.left;
  const lock = data.lockAt <= origin ? 1 : easeOut((frame - data.lockAt) / TIMING.lock);
  return (
    <div style={{ position: "absolute", left: LAYOUT.left, top: LAYOUT.titleY, width, display: "flex",
      flexDirection: "column", gap: 22 }}>
      <div style={{ background: P.card, borderRadius: 26, padding: "28px 34px 34px", border: `2px solid ${P.optionBorder}` }}>
        <div style={{ fontFamily: MONO, fontWeight: 700, fontSize: 26, letterSpacing: 4, color: P.cardLead,
          lineHeight: "34px", marginBottom: 10 }}>
          QUESTION
        </div>
        <div style={{ fontFamily: SANS, fontWeight: 700, fontSize: 52, lineHeight: "62px", color: P.cardInk }}>
          {data.question}
        </div>
      </div>
      {data.options.map((o, i) => {
        if (frame < o.at && o.at > origin) return <div key={i} style={{ height: 110 }} />;
        const k = arrival(frame, o.at, TIMING.optionIn, origin);
        const right = i === data.answer;
        const fade = right ? 1 : 1 - 0.55 * lock;
        const bg = right && lock > 0 ? mix(P.optionBg, P.amber, lock) : P.optionBg;
        const ink = right && lock > 0.5 ? P.cardInk : P.optionText;
        return (
          <div key={i} style={{ position: "relative", height: 110, display: "flex", alignItems: "center", gap: 26,
            padding: "0 28px", borderRadius: 24, background: bg,
            border: `3px solid ${right && lock > 0 ? P.amber : P.optionBorder}`, opacity: clamp01(k * 1.5) * fade,
            transform: k < 1 ? `scale(${0.9 + 0.1 * backOut(k)})` : undefined }}>
            <div style={{ flex: "0 0 auto", width: 70, height: 70, borderRadius: 35, background: right && lock > 0.5 ? P.cardInk : P.accent,
              color: "#FFFFFF", fontFamily: SANS, fontWeight: 700, fontSize: 40, lineHeight: "70px", textAlign: "center" }}>
              {"ABCD"[i]}
            </div>
            <div style={{ fontFamily: SANS, fontWeight: 700, fontSize: 44, lineHeight: "52px", color: ink,
              whiteSpace: "nowrap" }}>
              {o.text}
            </div>
            {right && lock > 0 ? (
              <div style={{ position: "absolute", right: 24, top: -20, fontFamily: MONO, fontWeight: 700, fontSize: 24,
                letterSpacing: 3, background: P.cardInk, color: P.amber, borderRadius: 8, padding: "0 12px",
                lineHeight: "34px", opacity: lock }}>
                ANSWER
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
};

function mix(a: string, b: string, t: number): string {
  const pa = [1, 3, 5].map((i) => parseInt(a.slice(i, i + 2), 16));
  const pb = [1, 3, 5].map((i) => parseInt(b.slice(i, i + 2), 16));
  return `rgb(${pa.map((v, i) => Math.round(v + (pb[i] - v) * t)).join(",")})`;
}
