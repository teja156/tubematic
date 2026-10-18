import React, { useEffect, useState } from "react";
import {
  AbsoluteFill,
  Audio,
  Sequence,
  continueRender,
  delayRender,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { TextRevealScene, TimelineWord } from "./scenes/TextRevealScene";
import Subtitles, { SubtitleConfig } from "./scenes/installed/Subtitles";
import Watermark from "./Watermark";

// ── Types (the shape of scene-config.json; docs/developer/09-remotion-project.md) ───

interface MusicConfig {
  src: string;
  volume: number;
  startFrame: number;
  fadeOutFrames: number;
}

interface SfxEntry {
  src: string;
  startFrame: number;
  volume: number;
}

/** Controls the crossfade OUT of this scene into the next. */
interface TransitionConfig {
  /** Frames for the crossfade. Default: 8. Set to 0 to hard-cut. */
  durationInFrames?: number;
}

interface TextRevealSceneConfig {
  type: "TextReveal";
  startFrame: number;
  durationInFrames: number;
  fontSize?: number;
  lineHeight?: number;
  color?: string;
  backgroundColor?: string;
}

interface GeneratedSceneConfig {
  type: "generated";
  src: string;
  startFrame: number;
  durationInFrames: number;
  props?: Record<string, unknown>;
  /**
   * Which scenes/ subdirectory `src` resolves against.
   * "generated" (default) — agent-authored, bind-mounted, per-video.
   * "installed" — curated, committed library, baked into the image.
   */
  source?: "generated" | "installed";
  /**
   * Crossfade transition OUT of this scene into the next.
   * Omit for the default 8-frame fade. Set durationInFrames: 0 to hard-cut.
   */
  transitionToNext?: TransitionConfig;
}

type SceneConfig = TextRevealSceneConfig | GeneratedSceneConfig;

/**
 * The ground painted under every scene (TMDEV-101). A whole-video property,
 * never a per-scene one: alternating white and dark scenes flashes. Omitted
 * means "dark", which is what every video produced before the Stick Explainer
 * register used. Keep in sync: mcp/server.py's VALID_CANVASES /
 * CANVAS_BY_STYLE.
 */
type Canvas = "dark" | "light";

const CANVAS_COLOR: Record<Canvas, string> = {
  dark: "#0f0f0f",
  light: "#ffffff",
};

const DEFAULT_CANVAS: Canvas = "dark";

interface SceneConfigFile {
  totalFrames: number;
  fps: number;
  canvas?: Canvas;
  /**
   * Burned-in captions. Whole-video, like `canvas`, and ON when the key is
   * absent — an old scene-config.json written before this existed still gets
   * subtitles. Opting out is an explicit `{"enabled": false}`.
   */
  subtitles?: SubtitleConfig;
  music?: MusicConfig;
  scenes: SceneConfig[];
  sfx: SfxEntry[];
}

interface Timeline {
  totalFrames: number;
  fps: number;
  audioDurationSeconds: number;
  words: TimelineWord[];
}

// ── Props passed in via --props from server.py ─────────────────────────────

interface CompositionBuilderProps {
  sceneConfigPath: string;
  timelinePath: string;
  audioPath: string;
  /**
   * The watermark_enabled setting, passed by the render worker. Drawn unless
   * this is exactly false, so a caller that sends nothing (Studio preview, the
   * text audit) gets the mark. Deliberately a render prop and NOT a
   * scene-config.json key: that file is the agent's.
   */
  watermark?: boolean;
}

// ── Crossfade wrapper ───────────────────────────────────────────────────────
//
// Fades a scene in at its start and out at its end, using Remotion's
// useCurrentFrame() (which is rebased to 0 inside each <Sequence>).
// This gives every scene-boundary a smooth dissolve without touching the
// absolute startFrame positions, so audio sync is preserved exactly.

const DEFAULT_FADE = 8; // frames

const SceneWithFades: React.FC<{
  children: React.ReactNode;
  durationInFrames: number;
  fadeInFrames: number;
  fadeOutFrames: number;
}> = ({ children, durationInFrames, fadeInFrames, fadeOutFrames }) => {
  const frame = useCurrentFrame();

  // Each ramp only calls interpolate() when its own fade is non-zero, so the
  // input range is always strictly increasing (no degenerate [0,0,...] or
  // [...,N,N] case — this is what crashed before whenever a scene had no
  // preceding/following scene to fade from/into, i.e. almost always).
  // Math.min() combines the two ramps into one envelope and naturally handles
  // overlapping ramps on very short scenes too — no separate clamp needed.
  const fadeInOpacity =
    fadeInFrames > 0
      ? interpolate(
          frame,
          [0, Math.min(fadeInFrames, durationInFrames)],
          [0, 1],
          { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
        )
      : 1;

  const fadeOutOpacity =
    fadeOutFrames > 0
      ? interpolate(
          frame,
          [durationInFrames - Math.min(fadeOutFrames, durationInFrames), durationInFrames],
          [1, 0],
          { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
        )
      : 1;

  const opacity = Math.min(fadeInOpacity, fadeOutOpacity);

  return <AbsoluteFill style={{ opacity }}>{children}</AbsoluteFill>;
};

// ── Generated scene registry / lazy loader ─────────────────────────────────

const GeneratedScene: React.FC<{
  src: string;
  source?: "generated" | "installed";
  durationInFrames: number;
  props?: Record<string, unknown>;
  words: TimelineWord[];
}> = ({ src, source = "generated", durationInFrames, props = {}, words }) => {
  const [Component, setComponent] = useState<React.ComponentType<Record<string, unknown>> | null>(null);
  const [handle] = useState(() => delayRender(`Loading ${source} scene: ${src}`));

  useEffect(() => {
    // Two explicit import() calls, one per source directory — webpack requires a
    // statically analyzable path per context; a single `${dir}/${src}` template
    // does not bundle both directories.
    const load =
      source === "installed"
        ? import(`./scenes/installed/${src}.tsx`)
        : import(`./scenes/generated/${src}.tsx`);

    load
      .then((mod) => {
        const comp = mod.default ?? Object.values(mod)[0];
        setComponent(() => comp as React.ComponentType<Record<string, unknown>>);
        continueRender(handle);
      })
      .catch((err) => {
        console.error(`Failed to load ${source} scene "${src}":`, err);
        continueRender(handle);
      });
  }, [src, source, handle]);

  // Transparent, not dark: the canvas below already paints the video's own
  // ground, and hardcoding a dark fill here would punch a black rectangle
  // through a light-canvas video. Under the dark canvas this looks identical
  // to what it always did.
  if (!Component) return <AbsoluteFill />;
  return <Component durationInFrames={durationInFrames} words={words} {...props} />;
};

// ── Main composition ────────────────────────────────────────────────────────

export const CompositionBuilder: React.FC<CompositionBuilderProps> = ({
  sceneConfigPath,
  timelinePath,
  audioPath,
  watermark,
}) => {
  const [sceneConfig, setSceneConfig] = useState<SceneConfigFile | null>(null);
  const [timeline, setTimeline] = useState<Timeline | null>(null);
  // delayRender tells Remotion to pause frame rendering until continueRender is called.
  // Without this, all frames render before useEffect fires, showing only black.
  const [handle] = useState(() => delayRender("Loading scene config and timeline"));
  const { durationInFrames } = useVideoConfig();

  useEffect(() => {
    Promise.all([
      fetch(sceneConfigPath).then((r) => r.json()),
      fetch(timelinePath).then((r) => r.json()),
    ])
      .then(([cfg, tl]) => {
        setSceneConfig(cfg as SceneConfigFile);
        setTimeline(tl as Timeline);
        continueRender(handle);
      })
      .catch((err) => {
        console.error("CompositionBuilder: failed to load assets", err);
        continueRender(handle);
      });
  }, [sceneConfigPath, timelinePath, handle]);

  if (!sceneConfig || !timeline) {
    return <AbsoluteFill style={{ backgroundColor: "#0f0f0f" }} />;
  }

  // Painted under every scene. A scene that sets its own opaque background
  // still covers this, so nothing that predates the canvas key changes; a
  // scene built for the light register simply leaves its background alone.
  const canvasColor = CANVAS_COLOR[sceneConfig.canvas ?? DEFAULT_CANVAS];

  return (
    <AbsoluteFill style={{ backgroundColor: canvasColor }}>
      {/* Voice audio — always mounted; audioPath is a direct prop */}
      <Audio src={audioPath} volume={1} />

      {/* ── Background music ─────────────────────────────────────────────── */}
      {sceneConfig.music && (
        <Sequence from={sceneConfig.music.startFrame}>
          <Audio
            src={sceneConfig.music.src}
            volume={(f) => {
              const music = sceneConfig.music!;
              const fadeStart = durationInFrames - music.fadeOutFrames;
              if (f < fadeStart) return music.volume;
              return music.volume * Math.max(0, 1 - (f - fadeStart) / music.fadeOutFrames);
            }}
            endAt={durationInFrames - (sceneConfig.music.startFrame ?? 0)}
          />
        </Sequence>
      )}

      {/* ── SFX ──────────────────────────────────────────────────────────── */}
      {(sceneConfig.sfx ?? []).map((sfx, i) => (
        <Sequence key={i} from={sfx.startFrame}>
          <Audio src={sfx.src} volume={sfx.volume ?? 0.6} />
        </Sequence>
      ))}

      {/* ── Scenes ───────────────────────────────────────────────────────── */}
      {sceneConfig.scenes.map((scene, i) => {
        if (scene.type === "TextReveal") {
          return (
            <Sequence
              key={i}
              from={scene.startFrame}
              durationInFrames={scene.durationInFrames}
            >
              <TextRevealScene
                words={timeline.words}
                startFrame={scene.startFrame}
                durationInFrames={scene.durationInFrames}
                fontSize={scene.fontSize}
                lineHeight={scene.lineHeight}
                color={scene.color}
                backgroundColor={scene.backgroundColor}
              />
            </Sequence>
          );
        }

        if (scene.type === "generated") {
          // Crossfade: fade-in duration comes from the PREVIOUS scene's
          // transitionToNext (they share the same overlap window).
          // Fade-out duration comes from THIS scene's transitionToNext.
          const prev = sceneConfig.scenes[i - 1];
          const fadeInFrames =
            prev?.type === "generated"
              ? (prev.transitionToNext?.durationInFrames ?? DEFAULT_FADE)
              : 0;
          const fadeOutFrames =
            i < sceneConfig.scenes.length - 1
              ? (scene.transitionToNext?.durationInFrames ?? DEFAULT_FADE)
              : 0; // no fade-out on the last scene

          return (
            <Sequence
              key={i}
              from={scene.startFrame}
              durationInFrames={scene.durationInFrames}
            >
              <SceneWithFades
                durationInFrames={scene.durationInFrames}
                fadeInFrames={fadeInFrames}
                fadeOutFrames={fadeOutFrames}
              >
                <GeneratedScene
                  src={scene.src}
                  source={scene.source}
                  durationInFrames={scene.durationInFrames}
                  props={scene.props}
                  words={timeline.words}
                />
              </SceneWithFades>
            </Sequence>
          );
        }

        return null;
      })}

      {/* ── Subtitles ────────────────────────────────────────────────────── */}
      {/*
        Last, so it paints over every scene, and deliberately NOT inside a
        Sequence: a Sequence would rebase useCurrentFrame() while the word
        timings stay absolute, and SceneWithFades would dissolve the captions
        at every scene boundary. Default-on — an absent key is enabled.
      */}
      <Subtitles
        words={timeline.words}
        canvas={sceneConfig.canvas ?? DEFAULT_CANVAS}
        {...(sceneConfig.subtitles ?? {})}
      />

      {/* ── Watermark ────────────────────────────────────────────────────── */}
      {/* Last and outside any Sequence, like the captions. Takes nothing from
          scene-config.json — see Watermark.tsx. */}
      {watermark !== false && <Watermark />}
    </AbsoluteFill>
  );
};
