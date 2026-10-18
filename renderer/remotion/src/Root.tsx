import "./index.css";
import { AbsoluteFill, Composition } from "remotion";
import { CompositionBuilder } from "./CompositionBuilder";
import { PlaceholderComposition } from "./Composition";
import { TextLayoutProbe } from "./audit/TextLayoutProbe";

// Text-layout audit composition (VQA-9). Renders exactly what "Composition"
// renders, plus a measurement probe. A separate composition rather than a prop
// on CompositionBuilder, so the real render path stays untouched — the audit
// runs pre-render from validate_job and must not be able to change what a
// render produces.
const TextLayoutAudit: React.FC<{
  sceneConfigPath: string;
  timelinePath: string;
  audioPath: string;
}> = (props) => {
  return (
    <AbsoluteFill>
      <CompositionBuilder {...props} />
      <TextLayoutProbe />
    </AbsoluteFill>
  );
};

// calculateMetadata is duplicated between the two compositions below rather
// than shared, because the audit must resolve its duration from the same
// timeline.json the render does — a divergence here would sample frames that
// don't exist in the real video. Keep the two bodies identical.
const durationFromTimeline = async ({
  props,
}: {
  props: Record<string, unknown>;
}) => {
  try {
    const timelinePath = (props as { timelinePath: string }).timelinePath;
    const res = await fetch(timelinePath);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const timeline = await res.json();
    return { durationInFrames: timeline.totalFrames as number };
  } catch {
    return { durationInFrames: 900 };
  }
};

export const RemotionRoot: React.FC = () => {
  return (
    <>
      {/* Phase 1+: JSON-driven composition. Props injected via --props by server.py. */}
      <Composition
        id="Composition"
        component={CompositionBuilder as unknown as React.ComponentType<Record<string, unknown>>}
        fps={30}
        width={1080}
        height={1920}
        durationInFrames={900}
        defaultProps={{
          sceneConfigPath: "/public/preview/scene-config.json",
          timelinePath: "/public/preview/timeline.json",
          audioPath: "/public/preview/audio.mp3",
        }}
        // Read totalFrames from the timeline so duration matches the audio.
        calculateMetadata={durationFromTimeline}
      />

      {/* Text-layout audit (VQA-9) — same tree as "Composition" plus the
          measurement probe. Driven by audit/run-text-layout-audit.mjs via the
          Remotion Node API; never rendered to a video. */}
      <Composition
        id="TextLayoutAudit"
        component={TextLayoutAudit as unknown as React.ComponentType<Record<string, unknown>>}
        fps={30}
        width={1080}
        height={1920}
        durationInFrames={900}
        defaultProps={{
          sceneConfigPath: "/public/preview/scene-config.json",
          timelinePath: "/public/preview/timeline.json",
          audioPath: "/public/preview/audio.mp3",
        }}
        calculateMetadata={durationFromTimeline}
      />

      {/* Phase 0 placeholder — smoke-test the container without real assets */}
      <Composition
        id="Placeholder"
        component={PlaceholderComposition}
        durationInFrames={90}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={{}}
      />
    </>
  );
};
