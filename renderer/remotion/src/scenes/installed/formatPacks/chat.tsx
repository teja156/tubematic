/*
 * The chat thread: a plain rounded phone (no notch, no status bar, no app
 * name), a generic contact, bubbles that arrive one per voiced line (typing
 * dots first for the other side), red marks drawn on around the tells, and an
 * EXAMPLE tag. Bubbles flow down the screen; the validator keeps the whole
 * thread inside it.
 */
import React from "react";
import { fitFontSize } from "../fitText";
import { LAYOUT, ONE_LINE, TIMING, type ChatData } from "./contract";
import { MONO, SANS } from "./fonts";
import { arrival, backOut, clamp01, easeOut, type Look } from "./draw";
import { ExampleTag, MarkedText, type TextMark } from "./parts";

export const Chat: React.FC<{ data: ChatData; frame: number; origin: number; P: Look }> = ({
  data, frame, origin, P,
}) => {
  const phoneW = LAYOUT.right - LAYOUT.left;
  const screenInset = 10;
  const marks = data.marks ?? [];
  const anyMark = marks.some((m) => frame >= m.at);
  // The next message from the other side shows typing dots before it lands.
  const typing = data.messages.find(
    (m, i) => i > 0 && m.from === "them" && frame >= m.at - TIMING.dots && frame < m.at,
  );

  return (
    <>
      {data.title ? (
        <div style={{ position: "absolute", left: LAYOUT.left, top: LAYOUT.titleY, width: phoneW - 220,
          fontFamily: SANS, fontWeight: 700, lineHeight: `${LAYOUT.titleLine}px`, color: P.title,
          textTransform: "uppercase", letterSpacing: 1, whiteSpace: "nowrap",
          // One line above the phone: the size comes down for a wide title.
          fontSize: fitFontSize(data.title.toUpperCase(), ONE_LINE.chatTitle[1], 56, ONE_LINE.chatTitle[0], ONE_LINE.chatTitle[2]) }}>
          {data.title}
        </div>
      ) : null}
      <ExampleTag P={P} style={{ right: 1080 - LAYOUT.right, top: LAYOUT.titleY + 12 }} />

      {/* The phone: a plain slab with a screen. */}
      <div style={{ position: "absolute", left: LAYOUT.left, top: LAYOUT.phoneTop, width: phoneW,
        height: LAYOUT.phoneBottom - LAYOUT.phoneTop, borderRadius: 64, background: P.frame }}>
        {/* No overflow clip on the screen: a rounded clip over this much area
            is slow in software GL, and the header rounds its own corners. */}
        <div style={{ position: "absolute", inset: screenInset, borderRadius: 54, background: P.screen }}>
          <div style={{ height: LAYOUT.headerH, background: P.header, borderBottom: `2px solid ${P.hair}`,
            borderRadius: "54px 54px 0 0",
            display: "flex", alignItems: "center", padding: "0 34px" }}>
            <Avatar P={P} />
            <div style={{ marginLeft: 24 }}>
              <div style={{ fontFamily: SANS, fontWeight: 700, fontSize: 40, lineHeight: "46px", color: P.title }}>
                {data.contact.name}
              </div>
              {data.contact.number ? (
                <div style={{ fontFamily: MONO, fontWeight: 400, fontSize: 28, lineHeight: "34px", color: P.muted }}>
                  {data.contact.number}
                </div>
              ) : null}
            </div>
          </div>
          {/* The input bar: generic, no app wording. */}
          <div style={{ position: "absolute", left: 30, right: 112, bottom: 26, height: 68, borderRadius: 34,
            border: `2px solid ${P.hair}`, background: P.input }} />
          <div style={{ position: "absolute", right: 30, bottom: 26, width: 68, height: 68, borderRadius: 34,
            background: P.hair }} />
        </div>
      </div>

      <div style={{ position: "absolute", left: LAYOUT.left + 40, width: phoneW - 80, top: LAYOUT.threadTop,
        display: "flex", flexDirection: "column", gap: LAYOUT.bubbleGap }}>
        {data.messages.map((m, i) => {
          if (frame < m.at && !(m.at <= origin)) return null;
          const k = arrival(frame, m.at, TIMING.bubbleIn, origin);
          const mine = m.from === "me";
          const msgMarks = marks.filter((mk) => mk.message === i && frame >= mk.at);
          const onIt: TextMark[] = msgMarks.map((mk) => ({
            match: mk.match, kind: mk.kind, k: easeOut((frame - mk.at) / TIMING.mark),
          }));
          // A message's one label sits on its top edge, in the gap above it,
          // and settles a few frames after its stroke lands. It starts at the
          // bubble's inner corner (left on theirs, right on yours) and grows
          // toward the middle, so a label wider than a short bubble stays on screen.
          const labelled = msgMarks.find((mk) => mk.label);
          const labelK = labelled ? easeOut((frame - labelled.at - TIMING.mark + 3) / 6) : 0;
          const dim = anyMark && onIt.length === 0 ? 0.5 : 1;
          return (
            <div key={i} style={{ alignSelf: mine ? "flex-end" : "flex-start", maxWidth: LAYOUT.bubbleMaxW,
              transformOrigin: mine ? "100% 100%" : "0% 100%",
              transform: k < 1 ? `translateY(${(1 - k) * 24}px) scale(${0.86 + 0.14 * backOut(k)})` : undefined,
              opacity: clamp01(k * 1.6) * dim }}>
              <div style={{ position: "relative", background: mine ? P.outgoing : P.incoming,
                color: mine ? P.outgoingText : P.incomingText, borderRadius: 36, padding: `${LAYOUT.bubblePadY}px 30px`,
                fontFamily: SANS, fontWeight: 600, fontSize: 44, lineHeight: `${LAYOUT.bubbleLine}px`,
                overflowWrap: "anywhere" }}>
                <MarkedText text={m.text} marks={onIt} color={mine ? P.outgoingText : P.incomingText} P={P} />
                {labelled && labelK > 0 ? (
                  <div style={{ position: "absolute", top: -19, [mine ? "right" : "left"]: 22, opacity: labelK,
                    transform: `translateY(${(1 - labelK) * 6}px)`, fontFamily: SANS, fontWeight: 700, fontSize: 26,
                    letterSpacing: 1, lineHeight: "34px", textTransform: "uppercase", color: "#FFFFFF",
                    background: P.accent, borderRadius: 8, padding: "0 12px", whiteSpace: "nowrap" }}>
                    {labelled.label}
                  </div>
                ) : null}
              </div>
            </div>
          );
        })}
        {typing ? <Dots frame={frame} P={P} /> : null}
      </div>
    </>
  );
};

const Avatar: React.FC<{ P: Look }> = ({ P }) => (
  <div style={{ position: "relative", width: 76, height: 76, borderRadius: 38, background: P.avatar,
    overflow: "hidden", flex: "0 0 auto" }}>
    <div style={{ position: "absolute", left: 25, top: 14, width: 26, height: 26, borderRadius: 13,
      background: P.avatarInk }} />
    <div style={{ position: "absolute", left: 14, top: 46, width: 48, height: 40, borderRadius: 24,
      background: P.avatarInk }} />
  </div>
);

const Dots: React.FC<{ frame: number; P: Look }> = ({ frame, P }) => (
  <div style={{ alignSelf: "flex-start", background: P.incoming, borderRadius: 34, padding: "26px 30px",
    display: "flex", gap: 12 }}>
    {[0, 1, 2].map((d) => {
      const bob = Math.sin((frame - d * 4) / 3.2);
      return (
        <div key={d} style={{ width: 16, height: 16, borderRadius: 8, background: P.muted,
          opacity: 0.55 + 0.45 * Math.max(0, bob), transform: `translateY(${-Math.max(0, bob) * 6}px)` }} />
      );
    })}
  </div>
);
