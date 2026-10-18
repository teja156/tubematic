import { AbsoluteFill, useCurrentFrame } from "remotion";

// Phase 0 placeholder. Replaced by CompositionBuilder.tsx in Phase 1.
export const PlaceholderComposition: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill
      style={{
        background: "#0f0f0f",
        justifyContent: "center",
        alignItems: "center",
        flexDirection: "column",
        gap: 16,
      }}
    >
      <div style={{ color: "#4ade80", fontSize: 64, fontFamily: "monospace", fontWeight: 700 }}>
        tubematic
      </div>
      <div style={{ color: "#6b7280", fontSize: 32, fontFamily: "monospace" }}>
        renderer ready · frame {frame}
      </div>
    </AbsoluteFill>
  );
};
