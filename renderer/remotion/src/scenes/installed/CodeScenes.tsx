/**
 * CodeScenes: a Code Scenes insert (TMDEV-239). A code card whose tokens morph
 * from one version of the code to the next (unchanged tokens hold still), a
 * highlight on the lines the narration is about with the others dimmed, an
 * error squiggle with a ruled callout, and a small pane with what the code
 * prints. Insert-only: it never makes a whole video.
 *
 * All data, timed on the video's frames (the insert's `origin` is its first
 * frame). The contract is codeScenes/contract.ts; mcp/code_scenes.py checks
 * the same rules before the config is written.
 */
import React, { useMemo } from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import {
  ADVANCE, BAND, HEADER_RIGHT, LAYOUT, TIMING, codeAt, codeLines, insertFontSize, lineHeightFor, outputAt, typeFrames,
  type CodeScenesData, type CodeStep,
} from "./codeScenes/contract";
import { morphAt, matchPieces, still, type Drawn } from "./codeScenes/morph";
import { PALETTES, tokenize, type Palette, type Piece } from "./codeScenes/tokens";
import { MONO, SANS, useCodeFonts } from "./codeScenes/fonts";
import { fitFontSize } from "./fitText";

/** Where an insert sits on the video (TMDEV-224); see CompositionBuilder's InsertPlacement. */
type Placement = { origin: number; lead?: number; palette: "dark" | "light"; shift: number };

const clamp01 = (v: number) => Math.max(0, Math.min(1, v));
const easeOut = (t: number) => 1 - Math.pow(1 - clamp01(t), 3);

/** The step on screen at `frame`: the last one that has started. */
export function stepIndexAt(steps: CodeStep[], frame: number): number {
  let idx = 0;
  steps.forEach((s, i) => {
    if (s.at <= frame) idx = i;
  });
  return idx;
}

function focusOpacity(step: CodeStep | undefined, row: number): number {
  if (!step?.focus || step.focus.length === 0) return 1;
  return step.focus.includes(row + 1) ? 1 : 0.3;
}

/** Characters typed so far on a typed first step, or Infinity. The first line
 *  is there from the first frame, so an insert never opens on an empty card. */
function typedChars(step: CodeStep, frame: number, firstLine: number): number {
  if (step.reveal !== "type") return Infinity;
  return firstLine + Math.max(0, Math.floor((frame - step.at) / TIMING.typePerChar));
}

export default function CodeScenes({
  codeScenes,
  durationInFrames,
  insert,
}: {
  codeScenes?: CodeScenesData;
  durationInFrames: number;
  insert?: Placement;
}) {
  useCodeFonts("CodeScenes");
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
  const data: CodeScenesData = codeScenes ?? { lang: "python", steps: [] };
  const steps = data.steps ?? [];

  const fs = insertFontSize(data);
  const lh = lineHeightFor(fs);
  const adv = fs * ADVANCE;
  const pieces: Piece[][] = useMemo(
    () => steps.map((_, i) => tokenize(codeAt(data, i), data.lang, palette)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [codeScenes, palette],
  );
  const maxLines = Math.max(1, ...steps.map((_, i) => codeLines(codeAt(data, i)).length));
  const anyError = steps.some((s) => s.error);

  if (steps.length === 0) return <AbsoluteFill style={{ background: P.canvas }} />;

  const si = stepIndexAt(steps, frame);
  const step = steps[si];
  const prev = si > 0 ? steps[si - 1] : undefined;
  const since = frame - step.at;

  // The code: a morph into this step's code, or the code at rest.
  let drawn: Drawn[];
  const morphing = si > 0 && typeof step.code === "string" && since < TIMING.morph;
  if (morphing) {
    drawn = morphAt(matchPieces(pieces[si - 1], pieces[si]), since / TIMING.morph);
  } else {
    drawn = still(pieces[si]);
  }
  // A typed first step shows its pieces as their characters are reached.
  let cursor: { row: number; col: number } | null = null;
  if (si === 0 && step.reveal === "type") {
    const lines = codeLines(codeAt(data, 0));
    const typed = typedChars(step, frame, lines[0].length);
    const offsets: number[] = [];
    let acc = 0;
    lines.forEach((l) => {
      offsets.push(acc);
      acc += l.length;
    });
    const out: Drawn[] = [];
    for (const d of drawn) {
      const start = offsets[Math.round(d.row)] + Math.round(d.col);
      if (start >= typed) continue;
      out.push({ ...d, text: d.text.slice(0, typed - start) });
    }
    drawn = out;
    if (since < typeFrames(codeAt(data, 0)) + 30) {
      let r = 0;
      while (r + 1 < lines.length && offsets[r + 1] <= typed) r++;
      cursor = { row: r, col: Math.min(lines[r].length, typed - offsets[r]) };
    }
  }

  // Focus: every line's opacity eases from the last step's focus to this one's.
  // The first step's focus is in place from the insert's first frame.
  const kFocus = si === 0 ? 1 : easeOut(since / TIMING.focus);
  const rowOpacity = (row: number) => {
    const to = focusOpacity(step, Math.round(row));
    const from = prev ? focusOpacity(prev, Math.round(row)) : to;
    return from + (to - from) * kFocus;
  };

  // The error callout opens under its line and pushes the lines below it down.
  const err = step.error;
  const prevErr = prev?.error;
  let calloutOpen = 0;
  let calloutError = err ?? null;
  if (err) {
    const sameAsBefore = prevErr && prevErr.line === err.line && prevErr.text === err.text;
    calloutOpen = sameAsBefore ? 1 : easeOut(since / TIMING.callout);
  } else if (prevErr) {
    calloutOpen = 1 - easeOut(since / TIMING.callout);
    calloutError = prevErr;
  }
  const errRow = calloutError ? calloutError.line - 1 : -1;
  const rowY = (row: number) => {
    const below = calloutError ? clamp01(row - errRow) : 0;
    return row * lh + below * calloutOpen * LAYOUT.calloutH;
  };

  // Layout, top to bottom. The card keeps one size for the whole insert.
  const codeTop = LAYOUT.cardY + LAYOUT.titleH + LAYOUT.codePad;
  const cardH = LAYOUT.titleH + 2 * LAYOUT.codePad + maxLines * lh + (anyError ? LAYOUT.calloutH : 0);
  const gutter = Math.round(adv * 2.6 + 16);
  const textLeft = LAYOUT.cardX + 24 + gutter;
  const paneTop = LAYOUT.cardY + cardH + LAYOUT.paneGap;

  // The output pane: this step's output, or an earlier one while the code is unchanged.
  const shown = outputAt(data, si);
  const prevShown = si > 0 ? outputAt(data, si - 1) : null;
  let paneOpacity = 0;
  let pane = shown;
  if (shown) {
    // A new pane fades in; a pane replacing another keeps its place and its
    // lines arrive again.
    paneOpacity = shown.from === si && !prevShown ? easeOut(since / TIMING.outputIn) : 1;
  } else if (prevShown) {
    paneOpacity = 1 - easeOut(since / TIMING.outputIn);
    pane = prevShown;
  }
  const paneFrom = pane ? steps[pane.from].at : 0;

  const lineCount = codeLines(codeAt(data, si)).length;
  const squiggle = calloutError ? squiggleFor(calloutError, codeLines(codeAt(data, prev && !err ? si - 1 : si))) : null;

  return (
    <AbsoluteFill style={{ background: P.canvas, overflow: "hidden" }}>
      {/* The insert moves clear of the main style's captions: a positioned
          offset, never a CSS transform. */}
      <div style={{ position: "absolute", left: 0, top: shift, width: 1080, height: 1920 }}>
        <Header data={data} si={si} since={since} P={P} />

        <div style={{ position: "absolute", left: LAYOUT.cardX, top: LAYOUT.cardY, width: LAYOUT.cardW, height: cardH,
          background: P.card, borderRadius: 26, border: `2px solid ${P.chrome}`, overflow: "hidden" }}>
          <div style={{ height: LAYOUT.titleH, background: P.chrome, display: "flex", alignItems: "center", paddingLeft: 28 }}>
            {P.dots.map((c) => (
              <div key={c} style={{ width: 16, height: 16, borderRadius: 8, background: c, marginRight: 12 }} />
            ))}
            {data.file ? (
              <div style={{ marginLeft: 18, fontFamily: MONO, fontWeight: 500, fontSize: 28, color: P.muted }}>{data.file}</div>
            ) : null}
          </div>
        </div>

        {/* Focus bars behind the code. */}
        {Array.from({ length: lineCount }, (_, row) => {
          const op = step.focus?.includes(row + 1) ? kFocus : prev?.focus?.includes(row + 1) ? 1 - kFocus : 0;
          if (op <= 0.01) return null;
          return (
            <div key={`bar${row}`} style={{ position: "absolute", left: LAYOUT.cardX + 2, width: LAYOUT.cardW - 4,
              top: codeTop + rowY(row) - (lh - fs) / 2 + 2, height: lh, background: P.focusBar,
              borderLeft: `4px solid ${P.focusEdge}`, opacity: op }} />
          );
        })}

        {/* Line numbers. */}
        {Array.from({ length: lineCount }, (_, row) => (
          <div key={`n${row}`} style={{ position: "absolute", left: LAYOUT.cardX + 24, width: gutter - 16,
            textAlign: "right", top: codeTop + rowY(row), fontFamily: MONO, fontWeight: 500, fontSize: fs,
            lineHeight: `${fs}px`, color: P.lineNo, opacity: rowOpacity(row) }}>
            {row + 1}
          </div>
        ))}

        {/* The code, one positioned piece per token. */}
        {drawn.map((d) => (
          <div key={d.key} style={{ position: "absolute", left: textLeft + d.col * adv, top: codeTop + rowY(d.row),
            fontFamily: MONO, fontWeight: 500, fontSize: fs, lineHeight: `${fs}px`, whiteSpace: "pre", color: d.color,
            opacity: d.opacity * rowOpacity(d.row) }}>
            {d.text}
          </div>
        ))}

        {cursor && Math.floor(frame / 15) % 2 === 0 ? (
          <div style={{ position: "absolute", left: textLeft + cursor.col * adv, top: codeTop + rowY(cursor.row) - 4,
            width: Math.max(3, fs * 0.12), height: fs + 8, background: P.focusEdge }} />
        ) : null}

        {squiggle && calloutOpen > 0.01 ? (
          <div style={{ position: "absolute", left: textLeft + squiggle.col * adv,
            top: codeTop + rowY(errRow) + fs + 4, width: squiggle.len * adv * clamp01(calloutOpen * 1.4),
            height: 12, overflow: "hidden" }}>
            <svg width={squiggle.len * adv} height={12} style={{ display: "block" }}>
              <path d={wave(squiggle.len * adv)} fill="none" stroke={P.error} strokeWidth={3} />
            </svg>
          </div>
        ) : null}

        {calloutError && calloutOpen > 0.01 ? (
          <div style={{ position: "absolute", left: textLeft - 14, width: LAYOUT.cardX + LAYOUT.cardW - textLeft - 10,
            top: codeTop + rowY(errRow) + lh + 2, height: (LAYOUT.calloutH - 14) * calloutOpen, overflow: "hidden",
            background: P.calloutBg, borderLeft: `6px solid ${P.error}`, opacity: Math.min(1, calloutOpen * 1.5) }}>
            <div style={{ padding: "16px 20px", fontFamily: SANS, fontWeight: 700, color: P.errorText,
              whiteSpace: "nowrap",
              // One line in a fixed box: the size comes down for a wide message.
              fontSize: fitFontSize(calloutError.text, LAYOUT.cardX + LAYOUT.cardW - textLeft - 10 - 40, 34, LAYOUT.calloutMinFont) }}>
              {calloutError.text}
            </div>
          </div>
        ) : null}

        {pane && paneOpacity > 0.01 ? (
          <OutputPane top={paneTop} output={pane.output} since={frame - paneFrom} opacity={paneOpacity} P={P} />
        ) : null}
      </div>
    </AbsoluteFill>
  );
}

function squiggleFor(error: { line: number; match: string }, lines: string[]): { col: number; len: number } | null {
  const text = lines[error.line - 1] ?? "";
  const col = text.indexOf(error.match);
  if (col < 0 || !error.match) return null;
  return { col, len: error.match.length };
}

function wave(width: number): string {
  const step = 8;
  let d = `M0 6`;
  for (let x = 0, up = true; x < width; x += step, up = !up) d += ` Q${x + step / 2} ${up ? 0 : 12} ${x + step} 6`;
  return d;
}

const Header: React.FC<{ data: CodeScenesData; si: number; since: number; P: (typeof PALETTES)[Palette] }> = ({
  data, si, since, P,
}) => {
  const steps = data.steps;
  const n = steps.length;
  const label = steps[si]?.label;
  const segW = n > 1 ? (LAYOUT.cardW - (n - 1) * 14) / n : LAYOUT.cardW;
  return (
    <>
      <div style={{ position: "absolute", left: LAYOUT.cardX, top: BAND.top, width: HEADER_RIGHT - LAYOUT.cardX, height: LAYOUT.headerH,
        display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ fontFamily: SANS, fontWeight: 700, fontSize: 40, letterSpacing: 2, color: P.accent,
          textTransform: "uppercase", whiteSpace: "nowrap" }}>
          {data.tag ?? ""}
        </div>
        {n > 1 || label ? (
          <div style={{ fontFamily: SANS, fontWeight: 600, fontSize: 36, color: P.muted, whiteSpace: "nowrap" }}>
            {n > 1 ? <span style={{ color: P.text, fontWeight: 700 }}>{`${si + 1}/${n}`}</span> : null}
            {label ? `${n > 1 ? " · " : ""}${label}` : ""}
          </div>
        ) : null}
      </div>
      {n > 1
        ? steps.map((s, i) => {
          const fill = i < si ? 1 : i === si ? easeOut(since / 10) : 0;
          return (
            <div key={i} style={{ position: "absolute", left: LAYOUT.cardX + i * (segW + 14), top: LAYOUT.progressY,
              width: segW, height: 6, borderRadius: 3, background: P.track, overflow: "hidden" }}>
              <div style={{ width: `${fill * 100}%`, height: 6, background: P.fill }} />
            </div>
          );
        })
        : null}
    </>
  );
};

const OutputPane: React.FC<{
  top: number;
  output: { lines: string[]; label?: string };
  since: number;
  opacity: number;
  P: (typeof PALETTES)[Palette];
}> = ({ top, output, since, opacity, P }) => {
  const h = LAYOUT.paneHeadH + Math.max(1, output.lines.length) * LAYOUT.paneLineH + LAYOUT.panePad;
  return (
    <div style={{ position: "absolute", left: LAYOUT.cardX, top, width: LAYOUT.cardW, height: h, opacity,
      background: P.pane, borderRadius: 22, border: `2px solid ${P.chrome}`, overflow: "hidden" }}>
      <div style={{ height: LAYOUT.paneHeadH, display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "0 28px", fontFamily: SANS, fontWeight: 600, fontSize: 28, color: P.muted, letterSpacing: 1 }}>
        <span>OUTPUT</span>
        {output.label ? (
          <span style={{ color: P.accent, fontWeight: 700, border: `2px solid ${P.accent}`, borderRadius: 20,
            padding: "0 14px", lineHeight: "34px" }}>{output.label}</span>
        ) : null}
      </div>
      {output.lines.map((line, i) => {
        const k = easeOut((since - i * TIMING.outputStagger) / 6);
        return (
          <div key={i} style={{ position: "absolute", left: 28, top: LAYOUT.paneHeadH + i * LAYOUT.paneLineH,
            fontFamily: MONO, fontWeight: 500, fontSize: 30, lineHeight: `${LAYOUT.paneLineH}px`, whiteSpace: "pre",
            color: P.text, opacity: k }}>
            {line}
          </div>
        );
      })}
    </div>
  );
};
