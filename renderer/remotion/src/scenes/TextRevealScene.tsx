import { AbsoluteFill, useCurrentFrame } from "remotion";

export interface TimelineWord {
  word: string;
  startFrame: number;
  endFrame: number;
}

interface TextRevealSceneProps {
  words: TimelineWord[];
  startFrame: number;
  durationInFrames: number;
  fontSize?: number;
  lineHeight?: number;
  color?: string;
  backgroundColor?: string;
}

// Safe-zone padding (px). Keep in sync with SAFE_ZONE in mcp/text_audit.py and
// SAFE_ZONE_TOP/BOTTOM in renderer/api/ai_review.py. (This comment used to cite
// scripts/config.py, which has never contained a SAFE_ZONE.)
const SAFE = { top: 150, bottom: 170, left: 60, right: 60 };
const MAX_WORDS_PER_LINE = 5;

export const TextRevealScene: React.FC<TextRevealSceneProps> = ({
  words,
  startFrame,
  fontSize = 64,
  lineHeight = 1.4,
  color = "#ffffff",
  backgroundColor = "#0f0f0f",
}) => {
  // All animation is a pure function of frame — no CSS transitions or @keyframes.
  const frame = useCurrentFrame();
  const absoluteFrame = frame + startFrame;

  // Words visible at this frame
  const visibleWords = words.filter((w) => absoluteFrame >= w.startFrame);

  // Group into lines of MAX_WORDS_PER_LINE
  const lines: TimelineWord[][] = [];
  for (let i = 0; i < visibleWords.length; i += MAX_WORDS_PER_LINE) {
    lines.push(visibleWords.slice(i, i + MAX_WORDS_PER_LINE));
  }

  // Show only the last 3 lines so text doesn't scroll off-screen
  const displayLines = lines.slice(-3);

  const lineHeightPx = fontSize * lineHeight;
  const totalTextHeight = displayLines.length * lineHeightPx;
  const availableHeight = 1920 - SAFE.top - SAFE.bottom;
  // Vertically center the text block within the safe area
  const topOffset = SAFE.top + (availableHeight - totalTextHeight) / 2;

  return (
    <AbsoluteFill style={{ backgroundColor }}>
      <div
        style={{
          position: "absolute",
          top: topOffset,
          left: SAFE.left,
          right: SAFE.right,
          display: "flex",
          flexDirection: "column",
          gap: lineHeightPx * 0.2,
        }}
      >
        {displayLines.map((lineWords, lineIdx) => (
          <div
            key={lineIdx}
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: fontSize * 0.25,
              minHeight: lineHeightPx,
              alignItems: "center",
            }}
          >
            {lineWords.map((w, wordIdx) => {
              // Fade-in over 3 frames from the word's startFrame
              const fadeFrames = 3;
              const opacity = Math.min(
                1,
                Math.max(0, (absoluteFrame - w.startFrame) / fadeFrames)
              );
              return (
                <span
                  key={wordIdx}
                  style={{
                    fontSize,
                    fontFamily: "system-ui, sans-serif",
                    fontWeight: 700,
                    color,
                    opacity,
                    lineHeight,
                    letterSpacing: "-0.02em",
                  }}
                >
                  {w.word}
                </span>
              );
            })}
          </div>
        ))}
      </div>
    </AbsoluteFill>
  );
};
