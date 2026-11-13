/**
 * FormatPacks: a Format Packs insert (TMDEV-240). One phone-native format per
 * insert, all text and data: a chat thread, a short numbered list, a quiz
 * board or a news strap. Insert-only: it never makes a whole video.
 *
 * Nothing in it passes for a real app: a plain phone with no notch or status
 * bar, no app or brand names, no verified marks, and an EXAMPLE tag on every
 * made-up thread or headline that the data cannot remove. The contract is
 * formatPacks/contract.ts; mcp/format_packs.py checks the same rules before
 * the config is written.
 */
import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import type { FormatPacksData } from "./formatPacks/contract";
import { PALETTES, type Palette } from "./formatPacks/draw";
import { useFormatFonts } from "./formatPacks/fonts";
import { Chat } from "./formatPacks/chat";
import { List } from "./formatPacks/list";
import { Quiz } from "./formatPacks/quiz";
import { Strap } from "./formatPacks/strap";

/** Where an insert sits on the video (TMDEV-224); see CompositionBuilder's InsertPlacement. */
type Placement = { origin: number; lead?: number; palette: "dark" | "light"; shift: number };

export default function FormatPacks({
  formatPacks,
  durationInFrames,
  insert,
}: {
  formatPacks?: FormatPacksData;
  durationInFrames: number;
  insert?: Placement;
}) {
  useFormatFonts("FormatPacks");
  const origin = insert?.origin ?? 0;
  const end = origin + durationInFrames;
  // The Sequence starts `lead` frames early for the way in and runs as long
  // after the window for the way out; the scene holds its first and last
  // frame through them.
  const raw = useCurrentFrame() + origin - (insert?.lead ?? 0);
  const frame = Math.min(Math.max(raw, origin), end - 1);
  const palette: Palette = insert?.palette === "light" ? "light" : "dark";
  const P = PALETTES[palette];
  const shift = insert?.shift ?? 0;
  const data = formatPacks;

  let body: React.ReactNode = null;
  if (data?.format === "chat") body = <Chat data={data} frame={frame} origin={origin} P={P} />;
  else if (data?.format === "list") body = <List data={data} frame={frame} origin={origin} P={P} />;
  else if (data?.format === "quiz") body = <Quiz data={data} frame={frame} origin={origin} P={P} />;
  else if (data?.format === "strap") body = <Strap data={data} frame={frame} origin={origin} P={P} />;

  return (
    <AbsoluteFill style={{ background: P.canvas, overflow: "hidden" }}>
      {/* The insert moves clear of the main style's captions: a positioned
          offset, never a CSS transform. */}
      <div style={{ position: "absolute", left: 0, top: shift, width: 1080, height: 1920 }}>{body}</div>
    </AbsoluteFill>
  );
}
