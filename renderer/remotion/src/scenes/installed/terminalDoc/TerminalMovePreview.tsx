/*
 * The picture preview_terminal_moves returns: every move an agent wrote for one
 * video, four moments of each (its first frame, a third, two thirds, its last),
 * each cropped to the slot box the move draws in and outlined, on the video's
 * skin. Ink past the outline will run into the next slot.
 *
 * Rendered by terminal-tools/render-moves.mjs from its own entry, which imports
 * only this file and the video's move files, never the scene.
 */
import React from "react";
import { AbsoluteFill } from "remotion";
import { SLOTS, W, type SlotName } from "./contract";
import { useTerminalFonts } from "./fonts";
import { seedOf, skinTokens, type MoveProps } from "./kit";

export interface PreviewMove {
  id: string;
  frames: number;
  slot: SlotName;
  text: string;
}

const K = 0.5;
const GAP = 24;
const LABEL = 44;

const boxOf = (slot: SlotName) => {
  const s = SLOTS[slot] ?? SLOTS.b;
  return { x: 60, y: s.top, w: 960, h: s.bottom - s.top };
};

/** The sheet's height for a list of moves: two rows of two moments each. */
export const previewHeight = (moves: PreviewMove[]) =>
  GAP + moves.reduce((h, m) => h + LABEL + 2 * (boxOf(m.slot).h * K + GAP), 0);

export const TerminalMovePreview: React.FC<{ moves: PreviewMove[]; draws: Record<string, React.FC<MoveProps>>; skin: string }> = ({ moves, draws, skin: skinName }) => {
  useTerminalFonts("TerminalMovePreview");
  const skin = skinTokens(skinName === "crt" ? "crt" : "house");
  let y = GAP;
  const blocks = moves.map((m) => {
    const Draw = draws[m.id];
    const box = boxOf(m.slot);
    const top = y;
    y += LABEL + 2 * (box.h * K + GAP);
    const moments = [0, 1, 2, 3].map((i) => Math.round((m.frames * i) / 3));
    return (
      <div key={m.id} style={{ position: "absolute", left: 0, top, width: W }}>
        <div style={{ position: "absolute", left: 30, top: 0, height: LABEL, fontFamily: skin.font, fontSize: 30, color: skin.tones.grey }}>
          {`${m.id} · slot ${m.slot} · ${m.frames} frames`}
        </div>
        {moments.map((t, i) => (
          <div
            key={i}
            style={{
              position: "absolute",
              left: 30 + (i % 2) * (box.w * K + 30),
              top: LABEL + Math.floor(i / 2) * (box.h * K + GAP),
              width: box.w * K,
              height: box.h * K,
              overflow: "visible",
              outline: "2px solid #ff3b30",
            }}
          >
            <div style={{ position: "absolute", left: -box.x * K, top: -box.y * K, width: W, height: 1920, transform: `scale(${K})`, transformOrigin: "0 0" }}>
              {Draw ? <Draw t={t} frames={m.frames} text={m.text} box={box} skin={skin} seed={seedOf(m.id)} /> : null}
            </div>
            <div style={{ position: "absolute", right: 6, bottom: 4, fontFamily: skin.font, fontSize: 22, color: skin.tones.dim }}>{`t=${t}`}</div>
          </div>
        ))}
      </div>
    );
  });
  return <AbsoluteFill style={{ background: skin.canvas, overflow: "hidden" }}>{blocks}</AbsoluteFill>;
};
