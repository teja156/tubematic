/*
 * The numbered list: a title on a lemon block and two to four paper rows, each
 * sliding in as the narration reads it; the row being read stays full, the
 * ones before it ease back.
 */
import React from "react";
import { LAYOUT, TIMING, WRAP, type ListData } from "./contract";
import { SANS } from "./fonts";
import { arrival, clamp01, expoOut, type Look } from "./draw";

export const List: React.FC<{ data: ListData; frame: number; origin: number; P: Look }> = ({
  data, frame, origin, P,
}) => {
  const width = LAYOUT.right - LAYOUT.left;
  const shown = data.items.filter((it) => frame >= it.at || it.at <= origin);
  const current = shown.length - 1;
  return (
    <div style={{ position: "absolute", left: LAYOUT.left, top: LAYOUT.titleY, width, display: "flex",
      flexDirection: "column", gap: LAYOUT.rowGap }}>
      <div style={{ alignSelf: "flex-start", background: P.highlight, color: P.cardInk, fontFamily: SANS,
        fontWeight: 700, fontSize: 56, lineHeight: `${LAYOUT.titleLine}px`, textTransform: "uppercase",
        padding: "8px 22px", borderRadius: 8, marginBottom: 20, maxWidth: WRAP.title[1] + 44 }}>
        {data.title}
      </div>
      {shown.map((it, i) => {
        const k = expoOut(arrival(frame, it.at, TIMING.rowIn, origin));
        const back = i < current ? 0.78 : 1;
        return (
          <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: 26, background: P.card,
            border: `2px solid ${P.optionBorder}`, borderRadius: 22, padding: "22px 28px",
            transform: k < 1 ? `translateX(${(1 - k) * 80}px)` : undefined, opacity: clamp01(k * 1.4) * back }}>
            <div style={{ flex: "0 0 auto", width: 72, height: 72, borderRadius: 36, background: P.accent,
              color: "#FFFFFF", fontFamily: SANS, fontWeight: 700, fontSize: 42, lineHeight: "72px",
              textAlign: "center" }}>
              {i + 1}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontFamily: SANS, fontWeight: 700, fontSize: 44, lineHeight: "52px", color: P.cardLead }}>
                {it.lead}
              </div>
              <div style={{ fontFamily: SANS, fontWeight: 600, fontSize: 36, lineHeight: `${LAYOUT.itemLine}px`,
                color: P.cardInk, overflowWrap: "anywhere" }}>
                {it.text}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
};
