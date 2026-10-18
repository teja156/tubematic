import React from "react";
import { AbsoluteFill, Easing, interpolate, useCurrentFrame } from "remotion";

// Entrance primitives for the Stick Explainer register (TMDEV-101).
//
// A module of helpers, NOT a scene — there is no default export and nothing
// here can be referenced from scene-config.json. Import them into a scene you
// author:
//
//   import { PopIn, SlideIn, Swap } from "../../installed/Entrances";
//
// Two levels up, because a generated scene lives in generated/{video_id}/.
//
// These are the register's only three ways for something to arrive, and the
// durations are the spec's, not preferences: a 6-frame pop, an 8-frame slide,
// a 1-frame swap. The point of the register is that things appear and hold,
// rather than easing continuously — so drive them from narration timestamps
// (get_timeline(video_id, include_words=true)) and let them sit.
//
// They are usable outside the stick register too; nothing here is white- or
// black-specific.
//
// ONE TRAP, hit for real on the first hybrid video. `PopIn` and `SlideIn`
// apply a CSS `transform`, and a transformed element becomes the containing
// block for every `position: absolute` descendant. So anything inside them
// that positions itself in FRAME coordinates — `StickFigure`, `PanelImage`, or
// your own absolutely-positioned overlay — is silently re-based onto the
// wrapper's box instead of the 1080x1920 frame, and lands somewhere else
// entirely. It typechecks and renders; it is just wrong.
//
// Two ways out, both fine:
//   - Wrap a *relatively* positioned element, or one whose position you do not
//     care about, and let the entrance move it.
//   - Or drive the entrance yourself inside the scene: read `useCurrentFrame()`
//     and apply the same scale/translate to the element directly, leaving the
//     absolute coordinates on an untransformed ancestor.

const SNAP = Easing.bezier(0.16, 1, 0.3, 1);

interface EntranceProps {
  /** Frame, relative to the scene's own start, at which this arrives. */
  at: number;
  children: React.ReactNode;
}

interface PopInProps extends EntranceProps {
  /**
   * The child's own anchor point in frame coordinates.
   *
   * An AbsoluteFill scales about the centre of the whole 1080x1920 frame, so
   * without this an off-centre element visibly travels across the frame while
   * it pops instead of growing where it sits. Pass the centre of whatever you
   * are popping in.
   */
  originX?: number;
  originY?: number;
}

/** Scale 0 → 105% → 100% over 6 frames. The register's default arrival. */
export const PopIn: React.FC<PopInProps> = ({
  at,
  originX = 540,
  originY = 960,
  children,
}) => {
  const frame = useCurrentFrame();
  if (frame < at) return null;
  const scale = interpolate(frame - at, [0, 4, 6], [0, 1.05, 1], {
    extrapolateRight: "clamp",
    easing: SNAP,
  });
  return (
    <AbsoluteFill
      style={{ transform: `scale(${scale})`, transformOrigin: `${originX}px ${originY}px` }}
    >
      {children}
    </AbsoluteFill>
  );
};

interface SlideInProps extends EntranceProps {
  /** Pixels to travel, along one axis only. Negative comes from the other side. */
  distance?: number;
  /** Which axis. The register slides on one axis at a time, never diagonally. */
  axis?: "x" | "y";
}

/** A single-axis slide over 8 frames with a hard ease-out. */
export const SlideIn: React.FC<SlideInProps> = ({
  at,
  distance = 240,
  axis = "y",
  children,
}) => {
  const frame = useCurrentFrame();
  if (frame < at) return null;
  const offset = interpolate(frame - at, [0, 8], [distance, 0], {
    extrapolateRight: "clamp",
    easing: SNAP,
  });
  const transform = axis === "x" ? `translateX(${offset}px)` : `translateY(${offset}px)`;
  return <AbsoluteFill style={{ transform }}>{children}</AbsoluteFill>;
};

interface SwapProps {
  /** Frame at which `after` replaces `before`, with no transition at all. */
  at: number;
  before: React.ReactNode;
  after: React.ReactNode;
}

/**
 * A one-frame replacement. No crossfade, no tween — that is the register.
 *
 * For a StickFigure you usually do not need this: change its `pose` or
 * `expression` prop on a frame threshold and you get the same instant swap
 * with less nesting. Swap is for replacing one whole element with a different
 * one.
 */
export const Swap: React.FC<SwapProps> = ({ at, before, after }) => {
  const frame = useCurrentFrame();
  return <>{frame < at ? before : after}</>;
};
