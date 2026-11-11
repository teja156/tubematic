/*
 * CaseFileStory: the whole of a Case File Story video, as one scene.
 *
 * A second-person suspense story told in painted stills. Each shot is a
 * generated painting pushed in slowly, with an optional hard punch-in to a
 * tighter crop on a word. A row of meters near the top (the HUD) changes with
 * the plot. Between shots, cards make the numbers physical: a grid of icons
 * that counts up, bars under a dashed threshold, a defined term with a tilted
 * stamp. The video ends on the last painting with two choice buttons. The
 * captions are the shared Subtitles layer in its "fill" look, at 72%.
 *
 * The agent never writes this file's kind of code: it writes `props.caseFile`
 * (meters and beats timed to the narration), which the MCP server validates
 * against ./caseFileStory/contract.ts before the video can render.
 *
 * Kept cheap on the CPU renderer (software GL): a still is an <image> in an
 * SVG the size of the frame whose viewBox selects the part on screen (a
 * scaled-up <Img> is dropped past about 3000 px a side, which a punch-in on a
 * push reaches); no SVG filter, gradient, pattern or stroke-dasharray (the
 * threshold's dashes are rectangles); the count grid is one Canvas 2D layer;
 * cards are flat colour.
 *
 * Measured in CPU-seconds per frame over the whole skill example (1441 frames,
 * rendered from a prebuilt bundle with software GL, concurrency 2): 0.41
 * here, 0.26 for System Flow's example on the same day by the same method
 * (1.6x, the ratio Under the Hood measured). The slow push makes every frame
 * a new full-frame painting to capture and encode; the cards cost little.
 */
import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import { AbsoluteFill, cancelRender, continueRender, delayRender, useCurrentFrame, useVideoConfig } from "remotion";
import {
  ACCENTS, GEOMETRY, H, TIMING, W, barLayout, fitFontSize, hudCells, partFrames, termFontSize,
  type BarsCard, type Beat, type CaseFileData, type Choice, type CountCard, type Shot, type TermCard,
} from "./caseFileStory/contract";
import { MONO, SANS, useCaseFileFonts } from "./caseFileStory/fonts";
import { ICON_DRAW, ICON_FILL } from "./caseFileStory/icons";
import { barsAt, beatIndexAt, clamp01, countAt, easeOut, gridCellAt, hudAt, panelAt, viewAt } from "./caseFileStory/stage";

const INK = "#16130F";
const CREAM = "#F0EADE";
const WHITE = "#FFFFFF";
const HUD_FILL = "rgba(26,23,20,0.8)";
const HUD_LABEL = "#88837E";
const KICKER = "#908A80";
const GHOST = "rgba(22,19,15,0.10)";

const G = GEOMETRY;
const T = TIMING;
const f1 = (n: number) => n.toFixed(2);

// ── the painting ────────────────────────────────────────────────────────────
/**
 * Every still the video uses, loaded and decoded before the first frame. A
 * still that will not load fails the render, as a missing <Img> does: a shot
 * with no picture under its meters must never ship.
 */
function useStills(srcs: string[]) {
  const key = srcs.join("|");
  const [handle] = useState(() => (srcs.length ? delayRender("CaseFileStory: loading the stills") : null));
  useEffect(() => {
    if (handle === null) return;
    Promise.all(
      srcs.map((src) => {
        const img = new Image();
        img.src = src;
        return img.decode();
      }),
    )
      .then(() => continueRender(handle))
      .catch((err) => cancelRender(err));
    // the stills are fixed for the whole render
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [handle, key]);
}

/** One still, covering the frame; `view` is the part of it on screen. */
const Still: React.FC<{ src: string; view: [number, number, number, number] }> = ({ src, view }) => {
  const [handle] = useState(() => delayRender(`CaseFileStory: drawing ${src}`));
  return (
    <svg width={W} height={H} viewBox={view.map(f1).join(" ")} preserveAspectRatio="none" style={{ position: "absolute", left: 0, top: 0 }}>
      <image href={src} x={0} y={0} width={W} height={H} preserveAspectRatio="xMidYMid slice"
        onLoad={() => continueRender(handle)}
        onError={() => cancelRender(new Error(`CaseFileStory: the still ${src} did not load`))} />
    </svg>
  );
};

// ── the meter row ───────────────────────────────────────────────────────────
const Hud: React.FC<{ data: CaseFileData; frame: number; accent: string }> = ({ data, frame, accent }) => {
  const cells = hudAt(data, frame);
  if (!cells) return null;
  const boxes = hudCells(cells.length);
  return (
    <>
      {cells.map((cell, i) => {
        const percent = data.hud[i].kind === "percent";
        const value: React.CSSProperties = {
          position: "absolute", left: 0, top: 0, fontFamily: SANS, fontWeight: 700, fontSize: 46, lineHeight: 1,
          color: percent ? accent : WHITE, whiteSpace: "nowrap",
        };
        return (
          <div key={cell.id} style={{
            position: "absolute", left: boxes[i][0], top: G.hudTop, width: boxes[i][1], height: G.hudHeight,
            borderRadius: G.hudRadius, background: HUD_FILL, padding: "17px 22px 0", boxSizing: "border-box",
          }}>
            <div style={{ fontFamily: MONO, fontSize: 24, letterSpacing: "0.14em", color: HUD_LABEL, lineHeight: 1, whiteSpace: "nowrap" }}>
              {cell.label}
            </div>
            <div style={{ position: "relative", marginTop: 10, height: 46 }}>
              {cell.from !== null && <span style={{ ...value, opacity: 1 - cell.mix }}>{cell.from}</span>}
              <span style={{ ...value, opacity: cell.mix }}>{cell.text}</span>
            </div>
          </div>
        );
      })}
    </>
  );
};

/** The large panel for one meter, over a shot. */
const Panel: React.FC<{ data: CaseFileData; shot: Shot; frame: number; accent: string }> = ({ data, shot, frame, accent }) => {
  const p = panelAt(data, shot, frame);
  if (!p) return null;
  return (
    <div style={{
      position: "absolute", left: G.safeLeft, top: G.hudTop + G.hudHeight + 28, width: 690, height: 250, borderRadius: 18,
      background: "rgba(26,23,20,0.82)", padding: "26px 34px", boxSizing: "border-box",
    }}>
      <div style={{ fontFamily: MONO, fontSize: 28, letterSpacing: "0.16em", color: HUD_LABEL, lineHeight: 1 }}>{p.label}</div>
      <div style={{ fontFamily: SANS, fontWeight: 700, fontSize: 124, lineHeight: 1, color: accent, marginTop: 8, letterSpacing: "-0.02em" }}>{p.text}</div>
      <div style={{ position: "absolute", left: 34, right: 34, bottom: 30, height: 14, borderRadius: 7, background: "#3A3431" }}>
        <div style={{ width: `${Math.max(2, p.fill * 100)}%`, height: "100%", borderRadius: 7, background: accent }} />
      </div>
    </div>
  );
};

// ── cards ───────────────────────────────────────────────────────────────────
const cardText: React.CSSProperties = {
  position: "absolute", left: G.safeLeft, width: G.safeRight - G.safeLeft, textAlign: "center", fontFamily: SANS, fontWeight: 700, lineHeight: 1.05,
};
/** One line of card text at `size`, drawn smaller when it would not fit the card's width. */
const line = (text: string, size: number): React.CSSProperties => ({
  ...cardText, fontSize: fitFontSize(text, size, G.lineWidth), whiteSpace: "nowrap",
});

/** A cream panel down to the caption band, on the near-black frame. */
const CreamCard: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <AbsoluteFill style={{ background: INK }}>
    <div style={{ position: "absolute", left: 0, top: 0, width: W, height: G.cardBottom, background: CREAM }} />
    {children}
  </AbsoluteFill>
);

const CountGrid: React.FC<{ card: CountCard; total: number; cells: number }> = ({ card, total, cells }) => {
  const ref = useRef<HTMLCanvasElement>(null);
  const w = G.gridCols * G.gridCell, h = G.gridRows * G.gridCell;
  // Before paint, so the frame captured after this render already has the grid.
  useLayoutEffect(() => {
    const c = ref.current?.getContext("2d");
    if (!c) return;
    c.clearRect(0, 0, w, h);
    const draw = ICON_DRAW[card.icon];
    for (let i = 0; i < total; i++) {
      const [cx, cy] = gridCellAt(i, total);
      if (i < cells) draw(c, cx, cy, G.gridCell * 0.86, ICON_FILL[card.icon], INK);
      else draw(c, cx, cy, G.gridCell * 0.86, GHOST, "rgba(22,19,15,0.0)");
    }
  }, [card.icon, total, cells, w, h]);
  return <canvas ref={ref} width={w} height={h} style={{ position: "absolute", left: G.gridLeft, top: G.gridTop }} />;
};

const CountView: React.FC<{ card: CountCard; frame: number; accent: string }> = ({ card, frame, accent }) => {
  const s = countAt(card, frame);
  const pop = easeOut((frame - partFrames(card)[2]) / 4);
  return (
    <CreamCard>
      <div style={{ ...line(card.title, 60), top: 250, color: INK }}>{card.title}</div>
      {card.unit && <div style={{ ...line(card.unit, 44), top: 338, color: accent }}>{card.unit}</div>}
      <CountGrid card={card} total={s.total} cells={s.cells} />
      <div style={{ ...cardText, top: 978, fontSize: 124, color: INK, letterSpacing: "-0.02em" }}>{s.text}</div>
      {s.result && (
        <div style={{ ...line(card.result, 68), top: 1118, color: accent, transform: `scale(${1.25 - 0.25 * pop})` }}>{card.result}</div>
      )}
    </CreamCard>
  );
};

const BarsView: React.FC<{ card: BarsCard; frame: number; accent: string }> = ({ card, frame, accent }) => {
  const s = barsAt(card, frame);
  const { bars, lineY } = barLayout(card.bars.map((b) => b.value), card.threshold.value);
  const dashes: React.ReactNode[] = [];
  for (let x = G.chartLeft - 30; x < G.chartRight + 30; x += 34) dashes.push(<rect key={x} x={x} y={lineY - 3} width={20} height={6} fill={accent} />);
  return (
    <CreamCard>
      <div style={{ ...line(card.title, 60), top: 250, color: INK }}>{card.title}</div>
      <svg width={W} height={G.cardBottom} style={{ position: "absolute", left: 0, top: 0 }}>
        {bars.slice(0, s.shown).map(([x, y, w, h], i) => <rect key={i} x={x} y={y} width={w} height={h} rx={6} fill={INK} />)}
        {dashes}
      </svg>
      <div style={{
        position: "absolute", right: W - G.chartRight - 30, top: lineY - 48, fontFamily: MONO, fontWeight: 700, fontSize: 26,
        letterSpacing: "0.1em", color: accent, lineHeight: 1, whiteSpace: "nowrap",
      }}>{card.threshold.label}</div>
      {bars.slice(0, s.shown).map(([x, , w], i) => (
        <div key={i} style={{
          position: "absolute", left: x, width: w, top: G.chartBottom + 16, textAlign: "center", fontFamily: MONO, fontWeight: 700,
          fontSize: 26, color: KICKER, lineHeight: 1, whiteSpace: "nowrap",
        }}>{card.bars[i].label}</div>
      ))}
      {s.payoff && <div style={{ ...cardText, top: 1112, fontSize: 56, color: INK }}>{card.payoff}</div>}
    </CreamCard>
  );
};

const TermView: React.FC<{ card: TermCard; frame: number; accent: string }> = ({ card, frame, accent }) => {
  const [, definitionAt, stampAt, citationAt] = partFrames(card);
  const slam = clamp01((frame - stampAt + 1) / T.stampIn);
  return (
    <AbsoluteFill style={{ background: INK }}>
      <div style={{ ...cardText, top: 400, fontSize: termFontSize(card.term), color: accent, letterSpacing: "0.01em", whiteSpace: "nowrap" }}>{card.term}</div>
      {frame >= definitionAt && (
        <div style={{ ...cardText, left: 110, width: W - 220, top: 580, fontSize: 50, lineHeight: 1.28, color: WHITE }}>{card.definition}</div>
      )}
      {frame >= stampAt && (
        <div style={{ position: "absolute", left: 0, width: W, top: 930, display: "flex", justifyContent: "center" }}>
          <div style={{
            border: `8px solid ${accent}`, borderRadius: 14, padding: "18px 38px", fontFamily: SANS, fontWeight: 700, fontSize: 66,
            letterSpacing: "0.06em", color: accent, lineHeight: 1, whiteSpace: "nowrap", opacity: 0.4 + 0.6 * slam,
            transform: `rotate(-5deg) scale(${1.7 - 0.7 * slam})`,
          }}>{card.stamp}</div>
        </div>
      )}
      {card.citation && frame >= citationAt && (
        <div style={{ ...cardText, top: 1128, fontFamily: MONO, fontWeight: 400, fontSize: 28, letterSpacing: "0.08em", color: KICKER }}>{card.citation}</div>
      )}
    </AbsoluteFill>
  );
};

const ChoiceButtons: React.FC<{ beat: Choice; frame: number; accent: string }> = ({ beat, frame, accent }) => {
  const frames = partFrames(beat);
  const width = (G.safeRight - G.safeLeft - G.optionGap) / 2;
  return (
    <>
      <div style={{ position: "absolute", left: 0, top: G.optionTop - 60, width: W, height: H - G.optionTop + 60, background: "rgba(22,19,15,0.6)" }} />
      {beat.options.map((label, i) => {
        const at = frames[i + 1];
        if (frame < at) return null;
        const ghost = frame === at;
        return (
          <div key={i} style={{
            position: "absolute", left: G.safeLeft + i * (width + G.optionGap), top: G.optionTop, width, height: G.optionHeight,
            borderRadius: 24, background: i === 1 ? accent : "#26221E", border: i === 1 ? "none" : "3px solid rgba(255,255,255,0.85)",
            boxSizing: "border-box", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: SANS, fontWeight: 700,
            fontSize: fitFontSize(label, 64, width - 64), letterSpacing: "0.03em", whiteSpace: "nowrap", color: WHITE, opacity: ghost ? 0.5 : 1, transform: ghost ? "scale(1.1)" : undefined,
          }}>{label}</div>
        );
      })}
    </>
  );
};

// ── one beat ────────────────────────────────────────────────────────────────
const BeatView: React.FC<{ data: CaseFileData; beat: Beat; frame: number; fps: number; accent: string }> = ({ data, beat, frame, fps, accent }) => {
  switch (beat.type) {
    case "shot":
      return (
        <AbsoluteFill>
          <Still key={beat.image} src={beat.image} view={viewAt(beat, frame, fps)} />
          {beat.panel && beat.hud !== false && <Panel data={data} shot={beat} frame={frame} accent={accent} />}
        </AbsoluteFill>
      );
    case "choice":
      return (
        <AbsoluteFill>
          <Still key={beat.image} src={beat.image} view={viewAt(beat, frame, fps)} />
          <ChoiceButtons beat={beat} frame={frame} accent={accent} />
        </AbsoluteFill>
      );
    case "count":
      return <CountView card={beat} frame={frame} accent={accent} />;
    case "bars":
      return <BarsView card={beat} frame={frame} accent={accent} />;
    case "term":
      return <TermView card={beat} frame={frame} accent={accent} />;
  }
};

export interface CaseFileStoryProps {
  caseFile: CaseFileData;
}

export default function CaseFileStory({ caseFile }: CaseFileStoryProps) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  useCaseFileFonts("CaseFileStory");
  const stills = React.useMemo(
    () => Array.from(new Set(caseFile.beats.flatMap((b) => (b.type === "shot" || b.type === "choice" ? [b.image] : [])))),
    [caseFile],
  );
  useStills(stills);

  const accent = ACCENTS[caseFile.accent] ?? ACCENTS.pink;
  const i = beatIndexAt(caseFile, frame);
  const beat = caseFile.beats[i];
  if (!beat) return <AbsoluteFill style={{ background: INK }} />;
  // A card cross-fades over the last frame of the beat before it; shots cut.
  const isCard = beat.type === "count" || beat.type === "bars" || beat.type === "term";
  const fade = isCard && i > 0 ? clamp01((frame - beat.start + 1) / T.cardFade) : 1;
  const under = fade < 1 ? caseFile.beats[i - 1] : null;

  return (
    <AbsoluteFill style={{ background: INK }}>
      {under && <BeatView data={caseFile} beat={under} frame={beat.start - 1} fps={fps} accent={accent} />}
      <AbsoluteFill style={{ opacity: fade < 1 ? fade : undefined }}>
        <BeatView data={caseFile} beat={beat} frame={frame} fps={fps} accent={accent} />
      </AbsoluteFill>
      <Hud data={caseFile} frame={frame} accent={accent} />
    </AbsoluteFill>
  );
}
