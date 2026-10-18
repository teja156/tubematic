import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
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

export type SubtitleBackground = "pill" | "shadow" | "none";

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
}

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
}: Props) {
  const frame = useCurrentFrame();
  const webfont = FONTS[fontFamily];
  const family = webfont ? webfont.load() : fontFamily;
  const weight = webfont ? webfont.weight : DEFAULT_WEIGHT;

  const chunks = React.useMemo(() => chunkWords(words ?? [], maxWords), [words, maxWords]);
  if (!enabled || chunks.length === 0) return null;

  const index = visibleChunkIndex(chunks, frame);
  if (index === null) return null;
  const chunk = chunks[index];

  const ink = color ?? (canvas === "light" ? "#0f0f0f" : "#ffffff");
  const paper = canvas === "light" ? "rgba(255,255,255,0.92)" : "rgba(0,0,0,0.55)";

  // A short rise on entry. Deliberately small and over in 4 frames: at this
  // size anything larger reflows the line and makes fast captions unreadable.
  const age = frame - chunk[0].startFrame;
  const rise = interpolate(age, [0, 4], [14, 0], { extrapolateRight: "clamp" });
  const fade = interpolate(age, [0, 3], [0, 1], { extrapolateRight: "clamp" });

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
          ...(background === "shadow"
            ? { textShadow: canvas === "light" ? "0 2px 10px rgba(255,255,255,0.9)" : "0 2px 12px rgba(0,0,0,0.85)" }
            : {}),
        }}
      >
        {chunk.map((w, i) => {
          // The word being spoken is full strength, its neighbours dimmed.
          // Nothing moves or resizes — the emphasis travels along a line that
          // is otherwise completely still, which is what keeps a 1-7 word
          // caption legible at speed.
          const active = frame >= w.startFrame && frame <= w.endFrame;
          const spoken = frame > w.endFrame;
          return (
            <span
              key={`${i}-${w.word}`}
              style={{ opacity: active ? 1 : spoken ? 0.62 : 0.42 }}
            >
              {w.word}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
}
