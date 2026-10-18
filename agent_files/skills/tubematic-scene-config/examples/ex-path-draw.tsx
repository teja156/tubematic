/**
 * EXAMPLE SCENE — Self-drawing SVG diagram with evolvePath
 *
 * Demonstrates:
 *  - @remotion/paths evolvePath: draws a line/arrow progressively over time
 *  - spring() driving the path draw progress for an organic feel
 *  - Node circles that spring in when the connecting line reaches them
 *  - Continuous motion: lines draw, nodes pop in, labels fade in sequentially
 *
 * This replaces the old "static diagram remounted with different props" anti-pattern.
 * Instead of mounting dns-hop-diagram with step=1, step=2, step=3 (no real animation),
 * one scene draws the full flow with continuous, satisfying motion.
 */
import { evolvePath } from "@remotion/paths";
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

interface Node {
  x: number;
  y: number;
  label: string;
  sublabel?: string;
}

interface Props {
  durationInFrames: number;
  title?: string;
}

export default function PathDrawDiagram({ durationInFrames, title = "Request Flow" }: Props) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Diagram nodes — spaced vertically inside safe zone (y 150–1750, x 60–1020)
  const nodes: Node[] = [
    { x: 540, y: 320,  label: "Browser",   sublabel: "sends request" },
    { x: 540, y: 620,  label: "DNS",        sublabel: "resolves IP" },
    { x: 540, y: 920,  label: "Server",     sublabel: "handles request" },
    { x: 540, y: 1220, label: "Database",   sublabel: "returns data" },
    { x: 540, y: 1520, label: "Response",   sublabel: "back to browser" },
  ];

  const NODE_RADIUS = 64;

  // Each connection draws after the previous one finishes
  const DRAW_PER_CONNECTION = Math.floor((durationInFrames - 20) / (nodes.length - 1));

  // SVG paths connecting the nodes (straight vertical lines)
  const paths = nodes.slice(0, -1).map((n, i) => {
    const next = nodes[i + 1];
    return `M ${n.x} ${n.y + NODE_RADIUS} L ${next.x} ${next.y - NODE_RADIUS}`;
  });

  return (
    <AbsoluteFill style={{ backgroundColor: "#050c1a" }}>
      {/* Title */}
      {(() => {
        const titleOpacity = interpolate(frame, [0, 15], [0, 1], {
          extrapolateRight: "clamp",
        });
        const titleY = interpolate(frame, [0, 15], [30, 0], {
          extrapolateRight: "clamp",
        });
        return (
          <div
            style={{
              position: "absolute",
              top: 160,
              left: 0,
              right: 0,
              textAlign: "center",
              opacity: titleOpacity,
              transform: `translateY(${titleY}px)`,
              fontFamily: "sans-serif",
              fontSize: 56,
              fontWeight: 700,
              color: "#e2e8f0",
            }}
          >
            {title}
          </div>
        );
      })()}

      <svg
        width={1080}
        height={1920}
        style={{ position: "absolute", top: 0, left: 0 }}
      >
        {/* Draw each connecting line using evolvePath */}
        {paths.map((pathD, i) => {
          const lineStart = 10 + i * DRAW_PER_CONNECTION;

          const rawProgress = spring({
            frame: Math.max(0, frame - lineStart),
            fps,
            config: { damping: 18, stiffness: 100 },
          });
          // spring overshoots slightly; clamp so evolvePath always gets 0–1
          const progress = Math.min(1, Math.max(0, rawProgress));
          const { strokeDasharray, strokeDashoffset } = evolvePath(progress, pathD);

          return (
            <path
              key={i}
              d={pathD}
              stroke="#3b82f6"
              strokeWidth={4}
              fill="none"
              strokeDasharray={strokeDasharray}
              strokeDashoffset={strokeDashoffset}
              strokeLinecap="round"
            />
          );
        })}

        {/* Arrowhead dots that appear when the line reaches the target node */}
        {nodes.map((node, i) => {
          const arriveFrame = i === 0 ? 0 : 10 + (i - 1) * DRAW_PER_CONNECTION + 10;

          const dotScale = spring({
            frame: Math.max(0, frame - arriveFrame),
            fps,
            config: { damping: 12, stiffness: 150, mass: 0.6 },
          });

          return (
            <circle
              key={i}
              cx={node.x}
              cy={node.y}
              r={NODE_RADIUS * dotScale}
              fill={i === 0 ? "#1e40af" : i === nodes.length - 1 ? "#065f46" : "#1e3a5f"}
              stroke={i === nodes.length - 1 ? "#10b981" : "#3b82f6"}
              strokeWidth={3}
            />
          );
        })}
      </svg>

      {/* Node labels — fade in with the node */}
      {nodes.map((node, i) => {
        const arriveFrame = i === 0 ? 0 : 10 + (i - 1) * DRAW_PER_CONNECTION + 10;

        const labelOpacity = interpolate(
          frame,
          [arriveFrame + 5, arriveFrame + 20],
          [0, 1],
          { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
        );
        const labelY = interpolate(
          frame,
          [arriveFrame + 5, arriveFrame + 20],
          [node.y + 10, node.y],
          { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
        );

        return (
          <div
            key={i}
            style={{
              position: "absolute",
              top: labelY - 22,
              left: node.x - 200,
              width: 400,
              textAlign: "center",
              opacity: labelOpacity,
            }}
          >
            <div
              style={{
                fontFamily: "sans-serif",
                fontSize: 38,
                fontWeight: 700,
                color: "#f1f5f9",
              }}
            >
              {node.label}
            </div>
            {node.sublabel && (
              <div
                style={{
                  fontFamily: "sans-serif",
                  fontSize: 26,
                  color: "#94a3b8",
                  marginTop: 4,
                }}
              >
                {node.sublabel}
              </div>
            )}
          </div>
        );
      })}
    </AbsoluteFill>
  );
}
