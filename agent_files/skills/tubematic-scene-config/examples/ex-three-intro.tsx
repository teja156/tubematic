/**
 * EXAMPLE SCENE — @remotion/three 3D scene (opt-in; render-heavy)
 *
 * Demonstrates:
 *  - ThreeCanvas from @remotion/three: the correct way to embed React Three Fiber
 *  - useCurrentFrame() used for ALL animation (NOT useFrame from R3F, which breaks)
 *  - spring() driving 3D rotation for an organic, non-mechanical feel
 *  - A mesh that enters with a spring scale and rotates continuously
 *
 * WHEN TO USE: only when 3D clearly elevates the topic — e.g. a rotating globe
 * for a networking explainer, a 3D cube for a data-structure video, a spinning
 * model for a product breakdown. 3D takes longer to render in headless Chromium
 * (software WebGL). Don't use it just for decoration.
 *
 * REQUIRED: renderer must have @remotion/three, three, @react-three/fiber installed.
 * remotion.config.ts must set: Config.setChromiumOpenGlRenderer("swangle") — the renderer
 * container has no GPU, so "swangle" (software ANGLE/SwiftShader) is required; "angle" fails
 * to acquire a WebGL context on a GPU-less machine.
 */
import React from "react";
import { ThreeCanvas } from "@remotion/three";
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import * as THREE from "three";

// ── 3D mesh component — animation driven by frame prop, NOT useFrame ─────────
// The hard rule: never drive animation with useFrame from @react-three/fiber —
// it breaks render-time determinism (flicker). Use the Remotion frame instead.
// By convention here we pass frame/fps in as props and use them directly, which
// keeps mesh components pure and easy to test. (Calling useCurrentFrame()
// directly inside a component under <ThreeCanvas> also works — ThreeCanvas
// bridges Remotion's context across the R3F boundary — but the prop pattern is
// the one this skill standardizes on.)
const RotatingCube: React.FC<{ frame: number; fps: number }> = ({ frame, fps }) => {
  // Spring-in scale: cube grows from nothing to full size
  const scale = spring({
    frame,
    fps,
    config: { damping: 12, stiffness: 90, mass: 1.2 },
  });

  // Continuous rotation — purely frame-driven
  const rotY = (frame / fps) * Math.PI * 0.6;  // 0.3 full rotations/sec
  const rotX = (frame / fps) * Math.PI * 0.25;

  return (
    <mesh
      scale={[scale * 2.8, scale * 2.8, scale * 2.8]}
      rotation={[rotX, rotY, 0]}
    >
      <boxGeometry args={[1, 1, 1]} />
      <meshStandardMaterial
        color={new THREE.Color("#6366f1")}
        roughness={0.3}
        metalness={0.7}
        wireframe={false}
      />
    </mesh>
  );
};

interface Props {
  durationInFrames: number;
  headline?: string;
  subtext?: string;
}

export default function ThreeIntroScene({
  durationInFrames,
  headline = "How It Works",
  subtext = "Under the hood",
}: Props) {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();

  // ── Text entrance — spring slide-up ─────────────────────────────────────
  const textY = spring({
    frame: Math.max(0, frame - 20),
    fps,
    config: { damping: 16, stiffness: 120 },
    from: 80,
    to: 0,
  });
  const textOpacity = interpolate(frame, [20, 38], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // ── Background gradient that slowly shifts (noise-like via sin) ──────────
  const bgHue = 240 + Math.sin(frame * 0.015) * 20;

  return (
    <AbsoluteFill
      style={{
        backgroundColor: `hsl(${bgHue}, 30%, 6%)`,
      }}
    >
      {/* 3D canvas — occupies the upper half */}
      <ThreeCanvas
        width={width}
        height={Math.floor(height * 0.55)}
        style={{ position: "absolute", top: 200 }}
      >
        {/* Lighting */}
        <ambientLight intensity={0.4} />
        <pointLight position={[5, 5, 5]} intensity={1.2} color="#a855f7" />
        <pointLight position={[-5, -3, 2]} intensity={0.6} color="#3b82f6" />

        {/* Animated mesh — frame and fps passed as props */}
        <RotatingCube frame={frame} fps={fps} />
      </ThreeCanvas>

      {/* Overlay text — bottom half */}
      <div
        style={{
          position: "absolute",
          bottom: 280,
          left: 80,
          right: 80,
          textAlign: "center",
          transform: `translateY(${textY}px)`,
          opacity: textOpacity,
        }}
      >
        <div
          style={{
            fontFamily: "sans-serif",
            fontSize: 80,
            fontWeight: 800,
            color: "#ffffff",
            lineHeight: 1.1,
          }}
        >
          {headline}
        </div>
        <div
          style={{
            fontFamily: "sans-serif",
            fontSize: 44,
            color: "#94a3b8",
            marginTop: 20,
          }}
        >
          {subtext}
        </div>
      </div>
    </AbsoluteFill>
  );
}
