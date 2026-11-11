import "./index.css";
import { AbsoluteFill, Composition } from "remotion";
import { CompositionBuilder } from "./CompositionBuilder";
import { PlaceholderComposition } from "./Composition";
import { TextLayoutProbe } from "./audit/TextLayoutProbe";
import { MascotSheetComposition } from "./mascot/MascotSheet";
import { BeanPropSheet, SHEET_PAGES } from "./scenes/installed/beanExplainer/BeanPropSheet";
import { StorybookSheet, SHEET_PAGES as STORYBOOK_SHEET_PAGES } from "./scenes/installed/storybookAtlas/StorybookSheet";
import { PresenterSheet } from "./scenes/installed/underTheHood/PresenterSheet";

// Text-layout audit composition (VQA-9). Renders exactly what "Composition"
// renders, plus a measurement probe. A separate composition rather than a prop
// on CompositionBuilder, so the real render path stays untouched — the audit
// runs pre-render from validate_job and must not be able to change what a
// render produces. The props are named, never spread: a mascotPath must not
// reach the audit, which measures text and never boots the mascot's page.
const TextLayoutAudit: React.FC<{
  sceneConfigPath: string;
  timelinePath: string;
  audioPath: string;
}> = ({ sceneConfigPath, timelinePath, audioPath }) => {
  return (
    <AbsoluteFill>
      <CompositionBuilder sceneConfigPath={sceneConfigPath} timelinePath={timelinePath} audioPath={audioPath} />
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

      {/* A mascot's model sheet (turn, feels or act), rendered as a still by
          mascot-tools/render-sheet.mjs through its own entry point
          (src/mascot/sheet-index.ts); listed here so Studio can show it. */}
      <MascotSheetComposition />

      {/* The Bean Explainer model sheet: one page per frame (poses, faces,
          accessories and marks, then the prop library), for a person to
          approve the style's fixed cast and props. No video uses it. */}
      <Composition
        id="BeanPropSheet"
        component={BeanPropSheet}
        durationInFrames={SHEET_PAGES}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={{}}
      />

      {/* The Storybook Atlas model sheet: one page per frame (the guide, the
          people and their knobs, the backdrops as chapter frames, the prop
          library), for a person to approve the style's fixed cast and kit. No
          video uses it. */}
      <Composition
        id="StorybookSheet"
        component={StorybookSheet}
        durationInFrames={STORYBOOK_SHEET_PAGES}
        calculateMetadata={({ props }) => ({ durationInFrames: props.hold === undefined ? STORYBOOK_SHEET_PAGES : ((props.frames as number | undefined) ?? 90) })}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={{}}
      />

      {/* The Under the Hood presenter's model sheet: every pose, mouth and
          blink, for a person to approve the fixed presenter. No video uses it. */}
      <Composition
        id="PresenterSheet"
        component={PresenterSheet}
        durationInFrames={1}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={{}}
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
