import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import ImageFX from "./ImageFX";

// Ready-to-use full-bleed image scene with a Ken Burns move (TMDEV-29).
//
// Reference it straight from scene-config.json — no scene file to author:
//
//   {
//     "type": "generated", "src": "KenBurnsImage", "source": "installed",
//     "startFrame": 150, "durationInFrames": 120,
//     "props": {
//       "src": "/public/{video_id}/images/skyline.png",
//       "scaleFrom": 1.2, "panFrom": [-0.06, 0], "panTo": [0.06, 0],
//       "vignette": 0.4, "caption": "Every request starts here"
//     }
//   }
//
// For an image inside a scene you're authoring yourself, import ImageFX
// directly instead and put your own content in its children.

interface Props {
  durationInFrames: number;
  /** The `public_path` returned by generate_image, copied verbatim. */
  src: string;
  scaleFrom?: number;
  scaleTo?: number;
  panFrom?: [number, number];
  panTo?: [number, number];
  anchor?: [number, number];
  vignette?: number;
  backgroundColor?: string;
  /** Optional lower-third caption. Omit for a bare image. */
  caption?: string;
}

export default function KenBurnsImage({
  durationInFrames,
  src,
  scaleFrom,
  scaleTo,
  panFrom,
  panTo,
  anchor,
  vignette = 0.35,
  backgroundColor,
  caption,
}: Props) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Second independently animated element (the image move is the first), so
  // the scene meets the skill's two-moving-elements requirement on its own.
  const captionY = spring({
    frame,
    fps,
    config: { damping: 16, stiffness: 110 },
    from: 60,
    to: 0,
  });
  const captionOpacity = interpolate(frame, [0, 18], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <ImageFX
      src={src}
      durationInFrames={durationInFrames}
      scaleFrom={scaleFrom}
      scaleTo={scaleTo}
      panFrom={panFrom}
      panTo={panTo}
      anchor={anchor}
      vignette={vignette}
      backgroundColor={backgroundColor}
    >
      {caption ? (
        <AbsoluteFill
          style={{
            // Inside the Shorts safe zone (x 60–1020, y 150–1750).
            padding: "0 60px",
            justifyContent: "flex-end",
            paddingBottom: 260,
            transform: `translateY(${captionY}px)`,
            opacity: captionOpacity,
          }}
        >
          <span
            style={{
              fontFamily: "sans-serif",
              fontSize: 56,
              fontWeight: 800,
              color: "#ffffff",
              lineHeight: 1.2,
              textShadow: "0 4px 24px rgba(0,0,0,0.8)",
            }}
          >
            {caption}
          </span>
        </AbsoluteFill>
      ) : null}
    </ImageFX>
  );
}
