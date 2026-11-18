/*
 * Card: one beat of the template style. A headline and up to three short lines
 * that come in on their own frames, over a flat background. Replace it with the
 * style you studied; keep what the renderer relies on:
 *
 * - The component's default export gets `durationInFrames`, `words` (the
 *   whole video's word timings, in frames of the video) and the scene's props
 *   under the pack's `props_key` (here `card`).
 * - Everything is a pure function of `useCurrentFrame()`, which counts from this
 *   scene's start. No timers, no Math.random(), no network.
 * - Text stays out of the watermark's box (KEEP_OUT_X and the WATERMARK_* box
 *   from @tubematic/scene-api) and above the captions' band.
 * - Import the rest of the renderer only through "@tubematic/scene-api", plus
 *   react and remotion.
 */
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { fitFontSize, WATERMARK_BOTTOM } from "@tubematic/scene-api";
import { PALETTES, type CardProps } from "./card/contract";

export default function Card({ card }: { card: CardProps }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const palette = PALETTES[card.palette];
  const titleSize = fitFontSize(card.title, 900, 132, 64);
  const enter = spring({ frame, fps, config: { damping: 200 } });
  return (
    <AbsoluteFill style={{ background: palette.ground, padding: `${WATERMARK_BOTTOM + 120}px 90px 0` }}>
      <div style={{
        fontFamily: "system-ui, sans-serif", fontWeight: 900, fontSize: titleSize, lineHeight: 1.02,
        color: palette.ink, transform: `translateY(${interpolate(enter, [0, 1], [40, 0])}px)`, opacity: enter,
      }}>
        {card.title}
      </div>
      <div style={{ height: 14, width: interpolate(enter, [0, 1], [0, 320]), background: palette.accent, margin: "36px 0" }} />
      {card.lines.map((line, i) => {
        const at = card.lineAt[i] ?? 0;
        const t = interpolate(frame, [at, at + 8], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
        return (
          <div key={i} style={{
            fontFamily: "system-ui, sans-serif", fontWeight: 600, fontSize: 58, lineHeight: 1.2, color: palette.ink,
            opacity: t, transform: `translateX(${(1 - t) * -30}px)`, marginBottom: 22,
          }}>
            {line}
          </div>
        );
      })}
    </AbsoluteFill>
  );
}
