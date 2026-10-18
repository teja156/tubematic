import React from "react";
import {
  AbsoluteFill,
  Easing,
  Img,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

// Ken Burns wrapper for a full-bleed image (TMDEV-29).
//
// A generated (agent-authored) scene imports this to give a still image
// continuous motion, which the scene-authoring skill requires of every scene:
//
//   import ImageFX from "../../installed/ImageFX";
//
// TWO levels up: generated scenes live at generated/{video_id}/{scene_name}.tsx,
// so installed/ is two directories above the importing file, not one.
//
// Import it WITHOUT the .tsx extension — renderer/remotion/tsconfig.json has no
// allowImportingTsExtensions, so a suffixed import fails `tsc --noEmit`, which
// is what validate_job runs. It resolves from ../generated/ even though that
// directory is bind-mounted and this one is baked into the image: both live in
// the same filesystem namespace inside the container, and webpack's dynamic
// import context only governs the scene entry module, not its static imports.
//
// Deliberately no blur — a `filter: blur()` over a full-bleed photo for 300+
// frames is expensive on this renderer (software GL via swangle, PNG frames,
// no GPU) and a slow render doesn't fail cleanly: it hits RENDER_TIMEOUT_SECS
// and bounces back to RENDER_QUEUED for a retry. Tracked separately.

/**
 * Maps a point in the image to where that point currently sits on screen.
 *
 * Handed to `children` when it is written as a function (see ImageFXProps.children).
 * This exists because overlay content is a SIBLING of the <Img>, not a child of
 * it — the pan/zoom transform below applies to the image alone, so anything
 * drawn on top stays in fixed frame coordinates while the photo moves beneath
 * it. An arrow with a hardcoded position is correct at one instant of the scene
 * and drifting for the rest of it. Route it through `project` instead and it
 * stays glued to the feature it points at.
 */
export interface ImageAnchor {
  /**
   * Map a normalized image-space point to on-screen frame pixels.
   *
   * `u` and `v` run 0 → 1 left→right and top→bottom across the IMAGE, which is
   * the same space the `read_image` MCP tool's grid overlay is labelled in — so
   * a coordinate read off that grid can be passed straight in here.
   *
   * `visible` is false once the point has been pushed outside the frame by the
   * zoom and pan. Fade the annotation out rather than leave it pointing at
   * something off-screen. It is an exact frame-bounds test; add your own margin
   * if you want the annotation to retreat earlier.
   */
  project: (u: number, v: number) => { x: number; y: number; visible: boolean };
  /**
   * The image's current on-screen zoom. Multiply stroke widths and marker radii
   * by this if you want an annotation to grow with the image; leave them alone
   * to keep them a constant size on screen.
   */
  scale: number;
}

export interface ImageFXProps {
  /**
   * The `public_path` returned by the `generate_image` MCP tool, copied
   * verbatim — e.g. "/public/{video_id}/images/skyline.png".
   *
   * Do NOT wrap this in staticFile(). Remotion's static base is literally
   * "/public", so this string is already exactly what staticFile() would
   * return, and passing an already-prefixed path into it throws.
   */
  src: string;
  durationInFrames: number;
  /** Zoom at the first frame. Values below 1 are clamped up — see below. */
  scaleFrom?: number;
  /** Zoom at the last frame. */
  scaleTo?: number;
  /** Pan start, as [x, y] fractions of the frame. Positive x moves right. */
  panFrom?: [number, number];
  /** Pan end, as [x, y] fractions of the frame. */
  panTo?: [number, number];
  /** Zoom anchor as [x, y] fractions, 0 = left/top, 1 = right/bottom. */
  anchor?: [number, number];
  /**
   * Which point of the SOURCE IMAGE survives the cover-crop, as [u, v]
   * fractions. Defaults to the centre, which is CSS's own default.
   *
   * This is not `anchor`, and the difference has already cost one video.
   * `anchor` is the transform origin for the zoom; at scale 1 the pan clamp
   * collapses to zero, so `anchor` cannot move what the crop keeps. This maps
   * to `object-position`, which is the only thing that can.
   *
   * It barely matters full-bleed — a 0.571 image in a 0.5625 frame loses ~8px
   * a side — but it matters enormously inside a PanelImage, where a tall
   * portrait in a squarer panel loses nearly half its height and takes the
   * subject's head with it. Read the subject's position off `read_image`'s UV
   * grid and pass it.
   */
  focus?: [number, number];
  /** Darkened-edge overlay strength, 0 (off) to 1. */
  vignette?: number;
  backgroundColor?: string;
  /**
   * Overlay content drawn above the image (captions, callouts).
   *
   * Pass plain elements for content that doesn't depend on the picture — a
   * caption, a lower third. Pass a FUNCTION to receive an {@link ImageAnchor}
   * and pin content to a feature *in* the image; see `ex-hybrid-anchored.tsx`
   * in the scene-config skill's examples for the worked pattern.
   */
  children?: React.ReactNode | ((anchor: ImageAnchor) => React.ReactNode);
}

const EASE = Easing.bezier(0.4, 0, 0.2, 1);

export default function ImageFX({
  src,
  durationInFrames,
  scaleFrom = 1.15,
  scaleTo = 1.0,
  panFrom = [0, 0],
  panTo = [0, 0],
  anchor = [0.5, 0.5],
  focus = [0.5, 0.5],
  vignette = 0,
  backgroundColor = "#000000",
  children,
}: ImageFXProps) {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  // interpolate() requires a strictly increasing input range.
  const span = Math.max(1, durationInFrames);

  const ramp = (from: number, to: number) =>
    interpolate(frame, [0, span], [from, to], {
      easing: EASE,
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });

  // Never scale below 1: at scale 1 the image exactly fills the frame, so any
  // smaller value letterboxes it. Clamping here rather than validating means a
  // scene author cannot produce that frame at all.
  const scale = Math.max(1, ramp(scaleFrom, scaleTo));

  const [ax, ay] = anchor;
  const rawX = ramp(panFrom[0], panTo[0]);
  const rawY = ramp(panFrom[1], panTo[1]);

  // Clamp the pan to the overhang the current zoom actually produces, so a pan
  // can never drag an image edge into frame (which reads as a glitch, not a
  // camera move). Scaling by `s` about anchor fraction `a` leaves an overhang
  // of a*(s-1) on the near side and (1-a)*(s-1) on the far side, in frame
  // widths — so at scale 1 the permitted range collapses to zero and the image
  // simply holds still.
  const clampPan = (v: number, a: number) =>
    Math.max(-(1 - a) * (scale - 1), Math.min(a * (scale - 1), v));

  const x = clampPan(rawX, ax);
  const y = clampPan(rawY, ay);

  // Inverse of the transform applied to the <Img> below, so overlay content can
  // be pinned to a feature in the picture instead of to the frame.
  //
  // CSS applies `translate(...) scale(s)` right-to-left about the origin
  // (ax*W, ay*H) — scale first, then translate — which for a normalized image
  // point [u, v] gives:
  //
  //   fx = ax*W + s*(u*W - ax*W) + x*W  =  W * (ax + s*(u - ax) + x)
  //
  // Note `scale`, `x` and `y` here are the CLAMPED values computed just above,
  // not the raw ramps: the pan a scene asks for is routinely reduced by the
  // clamp (ex-ken-burns.tsx's own panTo of 0.05 lands at 0.04), so projecting
  // through rawX/rawY would drift by exactly the amount that was clamped away.
  //
  // Assumes the image's aspect ratio matches the frame's, which makes the
  // `objectFit: cover` fit an identity. generate_image returns Gemini's 9:16
  // bucket, 768x1344 — an aspect of 0.5714 against the canvas's 0.5625 — so
  // cover actually paints 1097px of width into 1080, and the residual error is
  // ~8.6px per side at scale 1, under 1% of the frame. Well below the precision
  // of anything upstream; revisit only if a genuinely different aspect ships.
  const imageAnchor: ImageAnchor = {
    scale,
    project: (u: number, v: number) => {
      const px = width * (ax + scale * (u - ax) + x);
      const py = height * (ay + scale * (v - ay) + y);
      return {
        x: px,
        y: py,
        visible: px >= 0 && px <= width && py >= 0 && py <= height,
      };
    },
  };

  return (
    <AbsoluteFill style={{ backgroundColor, overflow: "hidden" }}>
      <Img
        src={src}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          objectPosition: `${focus[0] * 100}% ${focus[1] * 100}%`,
          transformOrigin: `${ax * 100}% ${ay * 100}%`,
          // translate() percentages resolve against the element's own
          // untransformed box, which is exactly the frame — so `x`/`y` are in
          // frame widths/heights, matching the clamp above.
          transform: `translate(${x * 100}%, ${y * 100}%) scale(${scale})`,
        }}
      />

      {vignette > 0 ? (
        <AbsoluteFill
          style={{
            pointerEvents: "none",
            background:
              "radial-gradient(ellipse at center, rgba(0,0,0,0) 45%, rgba(0,0,0,1) 100%)",
            opacity: vignette,
          }}
        />
      ) : null}

      {typeof children === "function" ? children(imageAnchor) : children}
    </AbsoluteFill>
  );
}
