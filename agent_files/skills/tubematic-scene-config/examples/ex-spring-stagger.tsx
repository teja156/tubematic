/**
 * EXAMPLE SCENE — Spring entrance + staggered list reveal
 *
 * Demonstrates:
 *  - spring() for organic, bouncy entrances (replaces linear interpolate)
 *  - Easing.bezier for fine-tuned custom curves
 *  - Staggered reveals: each item enters with its own spring, delayed by index
 *  - Continuous motion throughout: title bounces in, items cascade in one-by-one,
 *    a progress bar fills as the list completes
 *
 * Every animation is driven purely by useCurrentFrame() — no CSS, no transitions,
 * no setTimeout.
 */
import {
  AbsoluteFill,
  Easing,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

interface Props {
  durationInFrames: number;
  title?: string;
  items?: string[];
}

export default function SpringStaggerList({
  durationInFrames,
  title = "Key Concepts",
  items = ["Step one: analyse", "Step two: design", "Step three: build", "Step four: ship"],
}: Props) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // ── Title entrance — spring bounce from below ────────────────────────────
  const titleY = spring({
    frame,
    fps,
    config: { damping: 14, stiffness: 120, mass: 0.8 },
    from: 120,
    to: 0,
  });
  const titleOpacity = interpolate(frame, [0, 10], [0, 1], {
    extrapolateRight: "clamp",
  });

  // ── Progress bar — fills over the full duration ──────────────────────────
  const barProgress = interpolate(frame, [20, durationInFrames - 20], [0, 1], {
    easing: Easing.bezier(0.25, 0.46, 0.45, 0.94),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // ── Staggered list items — each enters 18 frames after the previous ──────
  const ITEM_DELAY = 18; // frames between each item's spring
  const ITEM_START = 25; // first item starts at frame 25

  return (
    <AbsoluteFill
      style={{
        backgroundColor: "#0a0a14",
        justifyContent: "center",
        alignItems: "center",
        padding: "0 80px",
      }}
    >
      {/* Accent line */}
      <div
        style={{
          position: "absolute",
          top: 200,
          left: 80,
          width: `${barProgress * (1080 - 160)}px`,
          height: 4,
          borderRadius: 2,
          background: "linear-gradient(90deg, #6366f1, #a855f7)",
        }}
      />

      {/* Title */}
      <div
        style={{
          position: "absolute",
          top: 230,
          left: 80,
          right: 80,
          transform: `translateY(${titleY}px)`,
          opacity: titleOpacity,
        }}
      >
        <span
          style={{
            fontFamily: "sans-serif",
            fontSize: 72,
            fontWeight: 700,
            color: "#ffffff",
            letterSpacing: "-1px",
            lineHeight: 1.1,
          }}
        >
          {title}
        </span>
      </div>

      {/* Staggered list */}
      <div
        style={{
          position: "absolute",
          top: 380,
          left: 80,
          right: 80,
          display: "flex",
          flexDirection: "column",
          gap: 32,
        }}
      >
        {items.map((item, idx) => {
          const itemFrame = frame - (ITEM_START + idx * ITEM_DELAY);

          const itemY = spring({
            frame: Math.max(0, itemFrame),
            fps,
            config: { damping: 16, stiffness: 130 },
            from: 60,
            to: 0,
          });

          const itemOpacity = interpolate(
            itemFrame,
            [0, 12],
            [0, 1],
            { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
          );

          // Dot pulses when item arrives (Math.sin for continuous micro-motion)
          const dotScale = itemOpacity > 0.5
            ? 1 + 0.08 * Math.sin((frame - (ITEM_START + idx * ITEM_DELAY)) * 0.18)
            : 0;

          return (
            <div
              key={idx}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 24,
                transform: `translateY(${itemY}px)`,
                opacity: itemOpacity,
              }}
            >
              {/* Dot */}
              <div
                style={{
                  width: 20,
                  height: 20,
                  borderRadius: "50%",
                  background: "#6366f1",
                  flexShrink: 0,
                  transform: `scale(${dotScale})`,
                }}
              />
              <span
                style={{
                  fontFamily: "sans-serif",
                  fontSize: 52,
                  color: "#e2e8f0",
                  fontWeight: 400,
                }}
              >
                {item}
              </span>
            </div>
          );
        })}
      </div>

      {/* Counter in bottom-right: shows how many items are visible */}
      {(() => {
        const visibleCount = items.filter(
          (_, idx) => frame >= ITEM_START + idx * ITEM_DELAY
        ).length;
        return (
          <div
            style={{
              position: "absolute",
              bottom: 220,
              right: 80,
              fontFamily: "monospace",
              fontSize: 40,
              color: "#6366f1",
              opacity: interpolate(frame, [ITEM_START, ITEM_START + 12], [0, 1], {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
              }),
            }}
          >
            {visibleCount}/{items.length}
          </div>
        );
      })()}
    </AbsoluteFill>
  );
}
