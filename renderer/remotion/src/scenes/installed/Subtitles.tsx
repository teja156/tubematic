import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { loadFont as loadInter } from "@remotion/google-fonts/Inter";
import { loadFont as loadOswald } from "@remotion/google-fonts/Oswald";
import { loadFont as loadRoboto } from "@remotion/google-fonts/Roboto";
import { loadFont as loadMontserrat } from "@remotion/google-fonts/Montserrat";

// Burned-in subtitles (TMDEV-101).
//
// NOT a scene. CompositionBuilder renders this above every scene from the
// top-level `subtitles` key in scene-config.json, for the same reason `canvas`
// lives there: it is a property of the whole video, not of a beat. As a scene
// entry it would be crossfaded by SceneWithFades, would have to be ordered
// last to sit on top, and would count against the four-scene minimum.
//
// It reads `timeline.words`, which CompositionBuilder already threads to every
// scene and which nothing used until now. Those timings are already in FRAMES,
// straight from the ElevenLabs alignment — there is no seconds-to-frames
// conversion here and so no rounding drift to accumulate.
//
// WHY THIS EXISTS: so scenes stop carrying the narration as on-screen text.
// A caption that repeats what is being said is the most common way one of
// these videos gets cluttered. The words are handled here; the scene's job is
// to show, not to write.

export interface TimelineWord {
  word: string;
  startFrame: number;
  endFrame: number;
}

/**
 * Webfonts are a fixed menu, not a free string, because Remotion's font
 * loaders are static imports — a family named at render time cannot be
 * fetched. Anything not on the menu is passed through as a plain CSS family,
 * which covers whatever the renderer container has installed.
 *
 * THE DEFAULT IS DELIBERATELY NOT ONE OF THESE. Subtitles are on by default,
 * so their default font is on the critical path of every render in the
 * project. A Google font is fetched from fonts.gstatic.com by the render
 * browser; a renderer with no egress would stall waiting for it, turning a
 * cosmetic default into a pipeline outage. `system-ui, sans-serif` is the
 * family every existing installed scene already uses, so it is the one family
 * proven to resolve in that container. Naming a webfont here is a considered
 * opt-in, not the fallback.
 *
 * EACH LOADER IS PINNED TO ONE STYLE, ONE WEIGHT AND TWO SUBSETS, and that is
 * not a micro-optimisation. Called bare, `loadFont()` fetches every style,
 * every weight and every subset the family publishes — for Inter that is two
 * styles x nine weights x seven subsets, over a hundred files, to draw one
 * line of captions. It also stops working outright in Remotion v5, which
 * throws unless weights and subsets are given; since this component renders on
 * every video, an unpinned loader would turn a Remotion upgrade into a
 * pipeline-wide render failure rather than a slow font fetch.
 *
 * THE WEIGHT IS PER FAMILY because they do not offer the same range. Oswald
 * stops at 700 while the others reach 900, and asking a family for a weight it
 * does not publish THROWS ("does not have a weight 800 in style normal") — so
 * a single shared weight would have broken one of the four options outright.
 * Each entry therefore carries the weight it is actually loaded at, and the
 * caption renders at that weight rather than at a constant the font may not
 * have.
 */
interface Webfont {
  /** Loads the face and returns the CSS family name. */
  load: () => string;
  /** The single weight fetched above — never ask the CSS for another. */
  weight: number;
}

// Present in all four families; enough for English plus accented names.
const SUBTITLE_SUBSETS = ["latin", "latin-ext"] as const;

const FONTS: Record<string, Webfont> = {
  Inter: {
    weight: 800,
    load: () => loadInter("normal", { weights: ["800"], subsets: [...SUBTITLE_SUBSETS] }).fontFamily,
  },
  Oswald: {
    // 700 is Oswald's heaviest; 800 does not exist and would throw.
    weight: 700,
    load: () => loadOswald("normal", { weights: ["700"], subsets: [...SUBTITLE_SUBSETS] }).fontFamily,
  },
  Roboto: {
    weight: 800,
    load: () => loadRoboto("normal", { weights: ["800"], subsets: [...SUBTITLE_SUBSETS] }).fontFamily,
  },
  Montserrat: {
    weight: 800,
    load: () => loadMontserrat("normal", { weights: ["800"], subsets: [...SUBTITLE_SUBSETS] }).fontFamily,
  },
};

const DEFAULT_FONT = "system-ui, sans-serif";
/** What a container-local family is drawn at; no file is fetched for it. */
const DEFAULT_WEIGHT = 800;

/** "outline": bold text with a thick dark stroke and no plate — the standard
 *  look of narrated cartoon Shorts, readable over any picture.
 *  "label": a printed ivory label hugging the phrase, a diamond each side,
 *  every word at full strength and no rise: the Storybook Atlas caption.
 *  "log": a terminal log strip — left-aligned, each word typed on as it is
 *  spoken behind a prompt, a block caret, the word being spoken in `accent`.
 *  The Terminal Doc style uses it. */
export type SubtitleBackground = "pill" | "shadow" | "outline" | "label" | "none" | "log";

export interface SubtitleConfig {
  enabled?: boolean;
  /** Words on screen at once. 1-7; anything outside is clamped. */
  maxWords?: number;
  /**
   * A CSS family, or one of the webfont names in FONTS. Absent means the
   * container-local default — see FONTS for why that is not a webfont.
   */
  fontFamily?: string;
  fontSize?: number;
  /** Null or absent derives from the canvas — black on light, white on dark. */
  color?: string | null;
  background?: SubtitleBackground;
  /** Vertical centre as a fraction of frame height. */
  position?: number;
  uppercase?: boolean;
  /**
   * Indexes into the timeline's words that are drawn on a red box once
   * spoken: the key word of a line. Optional and empty by default; the Bean
   * Explainer style uses it.
   */
  emphasis?: number[];
  /** The colour of the word being spoken in the "log" look; absent means the
   *  text colour. Ignored by the other looks. */
  accent?: string | null;
}

/** The "label" plate: ivory paper, ink rule and text, a flat offset shadow. */
const LABEL_PAPER = "#EBE5D2";
const LABEL_INK = "#2F2218";
const LABEL_TEXT = "#2A2F33";

/** The key-word box: white text on red, scaling in with a little overshoot. */
const EMPHASIS_BG = "#D0201C";
const EMPHASIS_IN = 8;

interface Props extends SubtitleConfig {
  words: TimelineWord[];
  /** The video's canvas, used only to derive a default colour. */
  canvas?: "dark" | "light";
}

/** A gap this long between two words is a natural break to cut a chunk on. */
const SILENCE_FRAMES = 8; // ~0.27s at 30fps

/**
 * How long a chunk may linger after its last word once the narration has
 * clearly stopped.
 *
 * A chunk normally holds until the next one starts, so captions never blink
 * out between phrases. That is right for the ordinary sub-second gap between
 * clauses, and wrong for a deliberate pause: `<break time="1.5s"/>` produces
 * getting on for two seconds of silence, and holding the previous words across
 * all of it leaves a caption on screen with nothing being said. Capping the
 * hold keeps the no-blink behaviour for short gaps — the cap simply never
 * binds there — and clears the line through a real pause.
 */
const MAX_HOLD_FRAMES = 12; // ~0.4s at 30fps

const HARD_BREAK = /[.?!]["')\]]?$/;
const SOFT_BREAK = /[,;:]["')\]]?$/;

/**
 * Group words into readable runs.
 *
 * Order matters: punctuation first, then silence, then the cap. Capping first
 * would cut mid-clause and leave a chunk starting with "and" — the cap is a
 * ceiling on how much is on screen, not the thing that decides where to break.
 */
export function chunkWords(words: TimelineWord[], maxWords: number): TimelineWord[][] {
  const cap = Math.max(1, Math.min(7, Math.round(maxWords)));
  const chunks: TimelineWord[][] = [];
  let cur: TimelineWord[] = [];

  words.forEach((w, i) => {
    cur.push(w);
    const next = words[i + 1];
    const gap = next ? next.startFrame - w.endFrame : Infinity;
    const shouldBreak =
      HARD_BREAK.test(w.word) ||
      cur.length >= cap ||
      gap >= SILENCE_FRAMES ||
      (SOFT_BREAK.test(w.word) && cur.length >= 2);
    if (shouldBreak) {
      chunks.push(cur);
      cur = [];
    }
  });
  if (cur.length) chunks.push(cur);

  // A trailing single word reads as a mistake rather than emphasis. Pull one
  // back from the previous chunk when there is room.
  const last = chunks[chunks.length - 1];
  const prev = chunks[chunks.length - 2];
  if (last && prev && last.length === 1 && prev.length > 2 && prev.length < cap) {
    chunks[chunks.length - 1] = [prev.pop() as TimelineWord, ...last];
  }
  return chunks;
}

/**
 * Which chunk is on screen at `frame`, or null for none.
 *
 * A chunk holds until the NEXT one starts, so there is never a frame with no
 * subtitle mid-sentence — a caption that blinks out between phrases reads as a
 * dropped frame. But it holds only up to MAX_HOLD_FRAMES past its OWN last
 * word, so a deliberate pause is silent on screen as well as in the audio.
 * The two rules do not fight: on an ordinary between-clause gap the next chunk
 * starts first and the cap never binds, so the no-blink property is intact;
 * the cap only shows up across a real silence.
 *
 * Exported, and separate from the component, purely so this is reachable
 * without a React renderer — it is the part of the caption behaviour most
 * likely to regress and the hardest to see by eye in a finished video.
 */
export function visibleChunkIndex(
  chunks: TimelineWord[][],
  frame: number,
): number | null {
  let index = -1;
  for (let i = 0; i < chunks.length; i++) {
    if (frame >= chunks[i][0].startFrame) index = i;
    else break;
  }
  if (index < 0) return null;
  const chunk = chunks[index];
  const held = chunk[chunk.length - 1].endFrame + MAX_HOLD_FRAMES;
  const next = chunks[index + 1];
  const tail = next ? Math.min(next[0].startFrame, held) : held;
  return frame >= tail ? null : index;
}

export default function Subtitles({
  words,
  canvas = "dark",
  enabled = true,
  maxWords = 4,
  fontFamily = DEFAULT_FONT,
  fontSize = 62,
  color = null,
  background = "pill",
  position = 0.78,
  uppercase = false,
  emphasis = [],
  accent = null,
}: Props) {
  const frame = useCurrentFrame();
  const webfont = FONTS[fontFamily];
  const family = webfont ? webfont.load() : fontFamily;
  // a printed label is set in the regular weight its serif ships, never a synthetic bold
  const weight = webfont ? webfont.weight : background === "label" ? 500 : DEFAULT_WEIGHT;

  const chunks = React.useMemo(() => chunkWords(words ?? [], maxWords), [words, maxWords]);
  const emphasised = React.useMemo(() => new Set((emphasis ?? []).map((i) => (words ?? [])[i]).filter(Boolean)), [emphasis, words]);
  if (!enabled || chunks.length === 0) return null;

  const index = visibleChunkIndex(chunks, frame);
  if (index === null) return null;
  const chunk = chunks[index];

  const label = background === "label";
  const ink = color ?? (label ? LABEL_TEXT : canvas === "light" ? "#0f0f0f" : "#ffffff");
  if (background === "log") {
    return <LogStrip chunk={chunk} frame={frame} family={family} fontSize={fontSize} position={position} ink={ink} accent={accent ?? ink} uppercase={uppercase} />;
  }
  const paper = canvas === "light" ? "rgba(255,255,255,0.92)" : "rgba(0,0,0,0.55)";

  // A short rise on entry. Deliberately small and over in 4 frames: at this
  // size anything larger reflows the line and makes fast captions unreadable.
  const age = frame - chunk[0].startFrame;
  // A label cross-fades in 2 frames and does not move: it is printed, not spoken.
  const rise = label ? 0 : interpolate(age, [0, 4], [14, 0], { extrapolateRight: "clamp" });
  const fade = interpolate(age, [0, label ? 2 : 3], [0, 1], { extrapolateRight: "clamp" });

  const diamond = (
    <span style={{ flex: "none", width: fontSize * 0.2, height: fontSize * 0.2, background: ink, transform: "rotate(45deg)" }} />
  );

  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      <div
        style={{
          position: "absolute",
          left: 60,
          right: 60,
          top: `${position * 100}%`,
          transform: `translateY(calc(-50% + ${rise}px))`,
          opacity: fade,
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "center",
          alignItems: "center",
          gap: "0 0.32em",
          fontFamily: family,
          fontSize,
          fontWeight: weight,
          lineHeight: 1.15,
          textAlign: "center",
          color: ink,
          textTransform: uppercase ? "uppercase" : "none",
          ...(background === "pill"
            ? { background: paper, padding: "14px 28px", borderRadius: 16 }
            : {}),
          ...(label
            ? {
                left: "50%", right: "auto", width: "max-content", maxWidth: 900, flexWrap: "nowrap",
                transform: `translate(-50%, calc(-50% + ${rise}px))`, gap: fontSize * 0.36,
                background: LABEL_PAPER, border: `2px solid ${LABEL_INK}`, boxShadow: "5px 6px 0 rgba(47,34,24,0.22)",
                padding: `${Math.round(fontSize * 0.22)}px ${Math.round(fontSize * 0.55)}px ${Math.round(fontSize * 0.3)}px`,
                lineHeight: 1.12,
              }
            : {}),
          ...(background === "shadow"
            ? { textShadow: canvas === "light" ? "0 2px 10px rgba(255,255,255,0.9)" : "0 2px 12px rgba(0,0,0,0.85)" }
            : {}),
          ...(background === "outline"
            ? {
                WebkitTextStroke: `${Math.round(fontSize * 0.16)}px ${canvas === "light" ? "#ffffff" : "#101010"}`,
                paintOrder: "stroke fill",
                textShadow: canvas === "light" ? "0 3px 10px rgba(255,255,255,0.6)" : "0 4px 10px rgba(0,0,0,0.45)",
                letterSpacing: "0.01em",
              }
            : {}),
        }}
      >
        {label && diamond}
        <span style={label ? {
          display: "flex", flexWrap: "wrap", justifyContent: "center", gap: "0 0.28em", minWidth: 0,
        } : { display: "contents" }}>
        {chunk.map((w, i) => {
          // The word being spoken is full strength, its neighbours dimmed.
          // Nothing moves or resizes — the emphasis travels along a line that
          // is otherwise completely still, which is what keeps a 1-7 word
          // caption legible at speed.
          const active = frame >= w.startFrame && frame <= w.endFrame;
          const spoken = frame > w.endFrame;
          if (emphasised.has(w) && frame >= w.startFrame) {
            const k = Math.min(1, (frame - w.startFrame) / EMPHASIS_IN);
            const pop = 0.55 + 0.45 * (1 + 2.2 * (k - 1) ** 3 + 1.2 * (k - 1) ** 2);
            return (
              <span key={`${i}-${w.word}`} style={{ position: "relative", display: "inline-block", isolation: "isolate", color: "#ffffff", padding: "0 0.18em" }}>
                <span style={{ position: "absolute", inset: "-0.06em 0 -0.1em 0", background: EMPHASIS_BG, border: `${Math.max(3, Math.round(fontSize * 0.08))}px solid #1E1C1A`, borderRadius: fontSize * 0.22, transform: `scale(${pop}) rotate(-2deg)`, zIndex: -1 }} />
                <span style={{ position: "relative" }}>{w.word}</span>
              </span>
            );
          }
          return (
            <span
              key={`${i}-${w.word}`}
              // outlined words have no plate behind them, so a dimmed word
              // reads as a muddy grey: keep them near full strength there
              style={{ opacity: active || label ? 1 : background === "outline" ? (spoken ? 0.92 : 0.8) : spoken ? 0.62 : 0.42 }}
            >
              {w.word}
            </span>
          );
        })}
        </span>
        {label && diamond}
      </div>
    </AbsoluteFill>
  );
}

/** The "log" look's typing speed, in characters per frame. */
const LOG_TYPE_RATE = 1.8;

/**
 * The "log" look: a strip with a LOG label and a running clock over a
 * hairline, and the current chunk typed on behind a prompt, word by word as
 * each is spoken. The word being spoken is in the accent colour with a block
 * caret after it; words already spoken stay, dimmed. Left-aligned, like a
 * terminal, so a line never shifts as words arrive.
 */
const LogStrip: React.FC<{
  chunk: TimelineWord[]; frame: number; family: string; fontSize: number; position: number;
  ink: string; accent: string; uppercase: boolean;
}> = ({ chunk, frame, family, fontSize, position, ink, accent, uppercase }) => {
  const top = position * 1920;
  const meta = Math.round(fontSize * 0.62);
  let last = -1;
  chunk.forEach((w, i) => {
    if (frame >= w.startFrame) last = i;
  });
  const { fps } = useVideoConfig();
  const elapsed = frame / fps;
  const clock = `${String(Math.floor(elapsed / 60)).padStart(2, "0")}:${(elapsed % 60).toFixed(1).padStart(4, "0")}`;
  const lastWord = last >= 0 ? chunk[last] : null;
  const lastText = lastWord ? lastWord.word : "";
  const lastTyped = lastWord ? Math.min(lastText.length, Math.floor((frame - lastWord.startFrame) * LOG_TYPE_RATE) + 1) : 0;
  const caretOn = lastTyped < lastText.length || Math.floor(frame / 15) % 2 === 0;
  return (
    <AbsoluteFill style={{ pointerEvents: "none", fontFamily: family, fontSynthesis: "none" }}>
      <div style={{ position: "absolute", left: 66, right: 66, top: top - fontSize * 1.05 - meta * 1.3, display: "flex", justifyContent: "space-between", fontSize: meta, lineHeight: `${meta * 1.2}px`, color: ink, opacity: 0.32, letterSpacing: "0.08em" }}>
        <span>LOG</span>
        <span>T+{clock}</span>
      </div>
      <div style={{ position: "absolute", left: 66, right: 66, top: top - fontSize * 1.05, height: 2, background: ink, opacity: 0.16 }} />
      <div
        style={{
          position: "absolute", left: 66, right: 66, top: top - fontSize * 0.75,
          fontSize, lineHeight: 1.2, fontWeight: 700, color: ink, whiteSpace: "pre-wrap",
          textTransform: uppercase ? "uppercase" : "none",
        }}
      >
        <span style={{ opacity: 0.3 }}>{"\u203a "}</span>
        {chunk.map((w, i) => {
          if (i > last) return null;
          const isLast = i === last;
          const text = isLast ? w.word.slice(0, lastTyped) : w.word;
          const speaking = isLast && frame <= w.endFrame + 6;
          return (
            <span key={`${i}-${w.word}`} style={{ color: speaking ? accent : ink, opacity: speaking ? 1 : 0.62 }}>
              {i > 0 ? " " : ""}
              {text}
              {isLast && caretOn && (
                <span style={{ display: "inline-block", width: "0.55em", height: "0.82em", marginLeft: "0.08em", verticalAlign: "-0.1em", background: speaking ? accent : ink, opacity: 0.75 }} />
              )}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
