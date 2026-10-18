import { AbsoluteFill, useCurrentFrame } from "remotion";

// Generic step-flow diagram — reusable for any linear process with discrete,
// nameable stages (e.g. "browser -> resolver -> root -> TLD -> auth server",
// or any other hop/pipeline/state-machine explainer). Pass the stage data via
// scene-config `props` — no per-topic edits needed. Generalized from the
// original `dns-hop-diagram` example scene.

export interface StepFlowStep {
  label: string;
  icon: string;
}

interface Props {
  durationInFrames: number;
  steps: StepFlowStep[];
  connections: [number, number][];
  /** Node indices highlighted at each stage; `highlightStage` selects which entry is active. */
  activeStages: number[][];
  highlightStage?: number;
  /**
   * Which visual register this diagram is drawn for (TMDEV-101).
   *
   * "dark" is the original palette and stays the default, so every existing
   * scene-config entry renders exactly as before. "light" is black line art on
   * the white ground the Stick Explainer register paints — needed because
   * forcing that register does NOT ban diagrams, and a diagram that paints its
   * own near-black slab on a white canvas is the mixed-canvas failure the
   * register exists to prevent.
   */
  theme?: "dark" | "light";
}

/**
 * Two complete palettes rather than per-colour props. A diagram is only
 * legible if its background, its two node states and its two connection
 * states agree; exposing them individually invites a caller to change one and
 * produce grey-on-grey.
 */
const PALETTES = {
  dark: {
    background: "#0a0a0f",
    lineIdle: "#334155",
    lineActive: "#60a5fa",
    nodeIdle: "#1e293b",
    nodeActive: "#1e3a5f",
    icon: "#ffffff",
    labelIdle: "#94a3b8",
    labelActive: "#93c5fd",
  },
  light: {
    // Transparent: under the light register CompositionBuilder already paints
    // the white canvas, and a scene painting its own white is one stray hex
    // away from a visible seam between scenes.
    background: "transparent",
    lineIdle: "#9aa4b2",
    lineActive: "#c62828",
    nodeIdle: "#ffffff",
    nodeActive: "#ffe9e9",
    icon: "#000000",
    labelIdle: "#000000",
    labelActive: "#c62828",
  },
} as const;

const NODE_WIDTH = 180;
const NODE_HEIGHT = 80;
const CANVAS_WIDTH = 960; // safe-zone width (1080 - 60*2 margins)
const ROW_HEIGHT = 110;

/** Zigzag layout: every other row splits left/right, the rest stay centered — readable in a vertical frame. */
function layoutPositions(count: number): { x: number; y: number }[] {
  const positions: { x: number; y: number }[] = [];
  let row = 0;
  for (let i = 0; i < count; i++) {
    const isSplitRow = row % 2 === 1;
    if (isSplitRow && i + 1 < count) {
      positions.push({ x: 60, y: row * ROW_HEIGHT });
      positions.push({ x: CANVAS_WIDTH - NODE_WIDTH - 60, y: row * ROW_HEIGHT });
      i += 1;
    } else {
      positions.push({ x: CANVAS_WIDTH / 2 - NODE_WIDTH / 2, y: row * ROW_HEIGHT });
    }
    row += 1;
  }
  return positions;
}

export default function StepFlowDiagram({
  durationInFrames,
  steps,
  connections,
  activeStages,
  highlightStage = 0,
  theme = "dark",
}: Props) {
  const palette = PALETTES[theme] ?? PALETTES.dark;
  // The light register is line art: everything is an outline of uniform
  // weight, so the stroke widths change with the palette, not just the hues.
  const idleWidth = theme === "light" ? 3 : 1.5;
  const activeWidth = theme === "light" ? 5 : 3;
  const frame = useCurrentFrame();
  // Animate in over first 15 frames
  const progress = Math.min(1, frame / 15);
  const activeNodes = activeStages[Math.min(highlightStage, activeStages.length - 1)] ?? [];
  const positions = layoutPositions(steps.length);
  const canvasHeight = Math.max(0, ...positions.map((p) => p.y)) + NODE_HEIGHT + 40;

  return (
    <AbsoluteFill
      style={{
        backgroundColor: palette.background,
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <svg
        width={CANVAS_WIDTH}
        height={canvasHeight}
        style={{ opacity: progress, overflow: "visible" }}
        viewBox={`0 0 ${CANVAS_WIDTH} ${canvasHeight}`}
      >
        {/* Connections */}
        {connections.map(([from, to], i) => {
          const f = positions[from];
          const t = positions[to];
          if (!f || !t) return null;
          const isActive = activeNodes.includes(from) && activeNodes.includes(to);
          return (
            <line
              key={i}
              x1={f.x + NODE_WIDTH / 2}
              y1={f.y + NODE_HEIGHT / 2}
              x2={t.x + NODE_WIDTH / 2}
              y2={t.y + NODE_HEIGHT / 2}
              stroke={isActive ? palette.lineActive : palette.lineIdle}
              strokeWidth={isActive ? activeWidth : idleWidth}
              strokeDasharray={isActive ? "none" : "6 4"}
            />
          );
        })}

        {/* Nodes */}
        {steps.map((step, i) => {
          const pos = positions[i];
          if (!pos) return null;
          const active = activeNodes.includes(i);
          const fillCol = active ? palette.nodeActive : palette.nodeIdle;
          const stroke = active ? palette.lineActive : palette.lineIdle;
          return (
            <g key={i} transform={`translate(${pos.x},${pos.y})`}>
              <rect
                width={NODE_WIDTH}
                height={NODE_HEIGHT}
                rx={12}
                fill={fillCol}
                stroke={stroke}
                strokeWidth={active ? activeWidth : idleWidth}
              />
              <text
                x={NODE_WIDTH / 2}
                y={28}
                textAnchor="middle"
                fontSize={22}
                fill={palette.icon}
              >
                {step.icon}
              </text>
              <text
                x={NODE_WIDTH / 2}
                y={56}
                textAnchor="middle"
                fontSize={14}
                fill={active ? palette.labelActive : palette.labelIdle}
                fontFamily="system-ui, sans-serif"
                fontWeight={active ? "700" : "400"}
              >
                {step.label}
              </text>
            </g>
          );
        })}
      </svg>
    </AbsoluteFill>
  );
}
