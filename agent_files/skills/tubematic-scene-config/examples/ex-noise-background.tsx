/**
 * EXAMPLE SCENE — @remotion/noise organic animated background + animated stat cards
 *
 * Demonstrates:
 *  - noise2D from @remotion/noise: creates organic, non-repetitive motion
 *    (particle drift, background grid shimmer) — never looks mechanical
 *  - @remotion/shapes makeCircle / makePolygon: animated SVG shapes
 *  - Spring-in content cards over the organic background
 *  - Number ticker: a value that animates from 0 to target
 *
 * Use this pattern for: abstract intro hooks, concept visualisations,
 * statistics reveals, anything that needs a "live" feeling background.
 */
import { noise2D } from "@remotion/noise";
import { makeCircle } from "@remotion/shapes";
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

interface Props {
  durationInFrames: number;
  headline?: string;
  statValue?: number;
  statLabel?: string;
}

const PARTICLE_COUNT = 22;

export default function NoiseBackground({
  durationInFrames,
  headline = "Why This Matters",
  statValue = 94,
  statLabel = "% of breaches involve credentials",
}: Props) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // ── Particles drifting via 2D noise ─────────────────────────────────────
  // Each particle uses a unique seed so they move independently.
  const particles = Array.from({ length: PARTICLE_COUNT }, (_, i) => {
    // noise2D returns [-1, 1]; map to pixel offsets
    const nx = noise2D(`px-${i}`, frame / 80, 0) * 120;
    const ny = noise2D(`py-${i}`, 0, frame / 80) * 200;
    // Base positions spread across the canvas
    const baseX = 80 + ((i * 43) % 920);
    const baseY = 150 + ((i * 97) % 1400);
    const radius = 6 + (i % 4) * 4;
    const opacity = 0.12 + noise2D(`alpha-${i}`, frame / 120, i * 0.5) * 0.08;
    return { x: baseX + nx, y: baseY + ny, radius, opacity };
  });

  // Decorative accent shape via @remotion/shapes — demonstrates makeCircle usage
  const accentShape = makeCircle({ radius: 8 });

  // ── Card spring entrance ─────────────────────────────────────────────────
  const cardScale = spring({
    frame,
    fps,
    config: { damping: 14, stiffness: 100, mass: 0.9 },
    from: 0.7,
    to: 1,
  });
  const cardOpacity = interpolate(frame, [0, 18], [0, 1], {
    extrapolateRight: "clamp",
  });

  // ── Number ticker ────────────────────────────────────────────────────────
  const tickerStart = 20;
  const tickerEnd   = Math.min(90, durationInFrames - 20);
  const displayValue = Math.round(
    interpolate(frame, [tickerStart, tickerEnd], [0, statValue], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: (t) => 1 - Math.pow(1 - t, 3), // ease-out cubic
    })
  );

  // ── Headline slide in ────────────────────────────────────────────────────
  const headlineY = spring({
    frame,
    fps,
    config: { damping: 16, stiffness: 110 },
    from: -60,
    to: 0,
  });

  // ── Pulsing accent ring ──────────────────────────────────────────────────
  const ringScale = 1 + 0.04 * Math.sin(frame * 0.05);
  const ringOpacity = interpolate(frame, [0, 25], [0, 0.35], {
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ backgroundColor: "#03071e" }}>
      {/* Organic particle field */}
      <svg
        width={1080}
        height={1920}
        style={{ position: "absolute", top: 0, left: 0 }}
      >
        {particles.map((p, i) => (
          <circle
            key={i}
            cx={p.x}
            cy={p.y}
            r={p.radius}
            fill="#e63946"
            opacity={p.opacity}
          />
        ))}

        {/* @remotion/shapes example: makeCircle path used as a decorative dot cluster */}
        {[200, 880, 840].map((cx, i) => (
          <path
            key={`shape-${i}`}
            d={accentShape.path}
            fill="#e63946"
            opacity={0.25}
            transform={`translate(${cx - accentShape.width / 2}, ${300 + i * 40 - accentShape.height / 2})`}
          />
        ))}

        {/* Pulsing accent ring behind the stat card */}
        <circle
          cx={540}
          cy={960}
          r={280 * ringScale}
          fill="none"
          stroke="#e63946"
          strokeWidth={2}
          opacity={ringOpacity}
        />
      </svg>

      {/* Headline */}
      <div
        style={{
          position: "absolute",
          top: 220,
          left: 80,
          right: 80,
          textAlign: "center",
          transform: `translateY(${headlineY}px)`,
          opacity: cardOpacity,
        }}
      >
        <span
          style={{
            fontFamily: "sans-serif",
            fontSize: 64,
            fontWeight: 800,
            color: "#ffffff",
            lineHeight: 1.15,
          }}
        >
          {headline}
        </span>
      </div>

      {/* Stat card */}
      <div
        style={{
          position: "absolute",
          top: 760,
          left: 120,
          right: 120,
          background: "rgba(255,255,255,0.06)",
          borderRadius: 32,
          border: "1.5px solid rgba(230,57,70,0.4)",
          padding: "80px 60px",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 20,
          opacity: cardOpacity,
          transform: `scale(${cardScale})`,
        }}
      >
        {/* Big number */}
        <span
          style={{
            fontFamily: "monospace",
            fontSize: 160,
            fontWeight: 900,
            color: "#e63946",
            lineHeight: 1,
          }}
        >
          {displayValue}%
        </span>

        {/* Stat label */}
        <span
          style={{
            fontFamily: "sans-serif",
            fontSize: 38,
            color: "#cbd5e1",
            textAlign: "center",
            lineHeight: 1.4,
          }}
        >
          {statLabel}
        </span>
      </div>
    </AbsoluteFill>
  );
}
