/**
 * EXAMPLE SCENE — HYBRID (the EXCEPTION path): an arrow that stays glued to a
 * feature in the photo
 *
 * Demonstrates:
 *  - ImageFX's anchor render-prop: overlay content pinned to a point in the
 *    IMAGE rather than to the frame
 *  - Reading that point off read_image's [u, v] grid instead of guessing it
 *  - evolvePath drawing the leader line on, with the spring-overshoot clamp
 *  - Keeping the label inside the safe zone while the arrow tip is free to
 *    land anywhere
 *
 * When to reach for this: RARELY. A HYBRID beat is a real subject the viewer
 * wants to SEE, plus structure they have to TRACK *and cannot get from the
 * narration* — "the army marched on this castle from the north", "the breach was
 * at this wall, not that one". Before writing a scene like this, say in one
 * sentence what the overlay tells the viewer that the words and the picture do
 * not. If you can't, the beat is PHOTO: `ex-ken-burns.tsx` (or the installed
 * KenBurnsImage scene) is the answer, and it is a finished scene, not a lighter
 * fallback.
 *
 * PHOTO is the default for an image beat and HYBRID is the exception. An arrow
 * that merely restates the narration, or that exists to make the beat feel
 * animated, makes the video worse: it covers the subject the image was generated
 * for. The ImageFX camera move already animates every frame.
 *
 * When it IS warranted, draw the minimum — one anchored element and, if the thing
 * it points at needs naming, a label. That is exactly what this file draws, and
 * it is the ceiling, not a starting point to build on: no reticles, corner
 * brackets, stage badges or counters layered on top.
 *
 * THE PROBLEM THIS SOLVES. ImageFX pans and zooms the photograph every frame,
 * but overlay content is a SIBLING of the image, not a child of it — so an
 * arrow at a hardcoded x/y is correct at one instant and sliding off-target for
 * the rest of the scene. Writing `children` as a FUNCTION hands you a `project`
 * that converts image coordinates to on-screen ones for the current frame, so
 * the arrow tracks the feature through the whole camera move.
 *
 * WHERE THE COORDINATES COME FROM. Call read_image(video_id, image_name) and
 * look at the picture. Its grid is labelled in exactly the [u, v] units
 * `project` takes — u left-to-right, v top-to-bottom, both 0 → 1. Read the
 * subject's position off that grid. Do NOT infer it from the prompt you wrote:
 * the model may not have composed it where you asked, and an arrow pointing at
 * empty sky is a defect the AI review will catch after a whole render is spent.
 *
 * KEEP THE TARGET CENTRAL. At scaleFrom 1.28 only ~78% of the image is on
 * screen at once, and the pan slides that window around — so a subject at
 * u = 0.1 genuinely leaves the frame partway through. Anchor to roughly
 * u, v in 0.22–0.78, and say so in the generate_image prompt ("subject centred,
 * filling the middle third") — the prompt is the only lever that actually
 * controls where the subject lands.
 */
import { evolvePath } from "@remotion/paths";
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
// TWO dots up, then two more: your scene is written to
// generated/{video_id}/{scene_name}.tsx, so installed/ is two levels above it,
// not one. Extensionless as well — the renderer's tsconfig has no
// allowImportingTsExtensions, so a suffixed import fails `tsc --noEmit`, which
// is what validate_job runs.
import ImageFX from "../../installed/ImageFX";

interface Props {
  durationInFrames: number;
  /** The `public_path` from generate_image, copied verbatim. */
  imageSrc: string;
  /**
   * Where the subject sits IN THE IMAGE, as [u, v] read off read_image's grid.
   * Not a screen position — ImageFX converts it every frame.
   */
  target?: [number, number];
  label?: string;
}

// Shorts safe zone: x 60–1020, y 150–1750. The LABEL has to live in here.
// The arrow TIP does not — it goes wherever the subject is, which is the whole
// point, and may legitimately sit under the platform UI.
const LABEL_X = 60;
const LABEL_Y = 1470;

export default function AnchoredCallout({
  durationInFrames,
  imageSrc,
  target = [0.5, 0.42],
  label = "Rook's Rest",
}: Props) {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();

  const [u, v] = target;

  // spring() overshoots past 1; evolvePath needs 0–1 exactly, so clamp it.
  const draw = Math.min(
    1,
    Math.max(
      0,
      spring({
        frame: Math.max(0, frame - 10),
        fps,
        config: { damping: 18, stiffness: 90 },
      }),
    ),
  );

  const appear = interpolate(frame, [6, 24], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <ImageFX
      src={imageSrc}
      durationInFrames={durationInFrames}
      scaleFrom={1.22}
      scaleTo={1.05}
      panFrom={[-0.04, 0.02]}
      panTo={[0.04, -0.02]}
      anchor={[0.5, 0.45]}
      vignette={0.45}
    >
      {/* A FUNCTION, not elements — this is what opts into the anchor API. */}
      {({ project, scale }) => {
        const tip = project(u, v);

        // Soften the edge case rather than letting the arrow pop out of
        // existence: `tip.visible` is the boolean shortcut, but fading over the
        // last stretch before the frame edge reads far better.
        const MARGIN = 90;
        const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
        const edgeFade = Math.min(
          interpolate(tip.x, [0, MARGIN], [0, 1], clamp),
          interpolate(tip.x, [width - MARGIN, width], [1, 0], clamp),
          interpolate(tip.y, [0, MARGIN], [0, 1], clamp),
          interpolate(tip.y, [height - MARGIN, height], [1, 0], clamp),
        );
        const opacity = appear * (tip.visible ? edgeFade : 0);

        const fromX = LABEL_X + 30;
        const fromY = LABEL_Y - 16;
        const leader = `M ${fromX} ${fromY} L ${tip.x} ${tip.y}`;
        const { strokeDasharray, strokeDashoffset } = evolvePath(draw, leader);
        const angle = (Math.atan2(tip.y - fromY, tip.x - fromX) * 180) / Math.PI;

        return (
          <AbsoluteFill style={{ opacity }}>
            <svg
              width={width}
              height={height}
              viewBox={`0 0 ${width} ${height}`}
              style={{ position: "absolute", top: 0, left: 0 }}
            >
              <path
                d={leader}
                stroke="#fbbf24"
                strokeWidth={6}
                strokeLinecap="round"
                fill="none"
                strokeDasharray={strokeDasharray}
                strokeDashoffset={strokeDashoffset}
              />
              {/* Arrowhead rides the end of the line, rotated to match it, and
                  only appears once the line has finished drawing. */}
              <polygon
                points="0,0 -38,-16 -38,16"
                fill="#fbbf24"
                opacity={draw > 0.98 ? 1 : 0}
                transform={`translate(${tip.x} ${tip.y}) rotate(${angle})`}
              />
              {/* `scale` lets an annotation grow with the image instead of
                  staying a fixed size on screen — subtle, but it sells the
                  marker as sitting ON the photo rather than above it. */}
              <circle
                cx={tip.x}
                cy={tip.y}
                r={26 * scale}
                stroke="#fbbf24"
                strokeWidth={4}
                fill="none"
                opacity={0.55}
              />
            </svg>

            <div
              style={{
                position: "absolute",
                left: LABEL_X,
                top: LABEL_Y,
                maxWidth: 900,
                padding: "16px 28px",
                borderRadius: 14,
                background: "rgba(15,23,42,0.86)",
                borderLeft: "6px solid #fbbf24",
                fontFamily: "sans-serif",
                fontSize: 44,
                fontWeight: 700,
                color: "#ffffff",
              }}
            >
              {label}
            </div>
          </AbsoluteFill>
        );
      }}
    </ImageFX>
  );
}
