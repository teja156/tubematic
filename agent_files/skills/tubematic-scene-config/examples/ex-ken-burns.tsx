/**
 * EXAMPLE SCENE — AI-generated image with a Ken Burns move
 *
 * Demonstrates:
 *  - Composing the installed ImageFX wrapper around your own overlay content
 *  - Passing an image path returned by the generate_image MCP tool
 *  - Layering spring-animated text over a slowly drifting photograph
 *
 * When to reach for this: a beat whose SUBJECT is something the viewer wants to
 * see rather than track — a named character or real person, a creature, a real
 * place or structure, or one specific dramatic/historical moment. Decide from the
 * subject, not from the wording of the `visual` brief: a brief that says "tactical
 * map" or "split diagram" about an ambush between named characters is still a
 * subject beat, and this pattern is the answer to it. Reach for a pure SVG scene
 * only when the beat's subject is a relation: a process, a comparison, a
 * mechanism, counts, timing, code output.
 *
 * THIS IS THE DEFAULT SHAPE FOR AN IMAGE BEAT. What goes over the picture here is
 * TYPOGRAPHY — a headline springing in, a subhead trailing it, a figure counting
 * up, a lower third. Not annotation of the picture itself. Drawing arrows, labels
 * or markers onto the photograph is the HYBRID case, it lives in
 * ex-hybrid-anchored.tsx, and it has to pass the test in the skill's Images
 * section first; most image beats don't and shouldn't. Marks the viewer didn't
 * need cover the subject this image was generated for.
 *
 * If all you need is the image plus a caption, don't author a scene at all —
 * reference the installed KenBurnsImage scene directly from scene-config.json
 * with "source": "installed". That is a complete answer to a PHOTO beat, not a
 * shortcut. Write a scene like this one when the beat wants more type than a
 * single caption carries.
 *
 * Two rules that are easy to get wrong, both shown below:
 *
 *  1. Import ImageFX as "../../installed/ImageFX" — two levels up, and WITHOUT
 *     the .tsx extension. Your scene is written to
 *     generated/{video_id}/{scene_name}.tsx, so installed/ is two directories
 *     above it; and the renderer's tsconfig has no allowImportingTsExtensions,
 *     so a suffixed import fails `tsc --noEmit` — which means either mistake
 *     fails validate_job, not the render.
 *
 *  2. Pass `src` as the raw public_path string generate_image returned. Do not
 *     wrap it in staticFile(): Remotion's static base is literally "/public",
 *     so the string is already what staticFile() would produce, and passing an
 *     already-prefixed path into it throws.
 *
 * A src that doesn't resolve is not a blank frame — <Img> retries twice and
 * then aborts the whole render. Always run validate_job before submit_render.
 */
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
// This is the path as written from a scene in generated/{video_id}/ — which is
// where write_scene_file puts your scene, and the only place this import
// resolves. (It resolves across the bind-mount boundary because generated/ and
// installed/ are siblings inside the container, whatever their host origin.)
import ImageFX from "../../installed/ImageFX";

interface Props {
  durationInFrames: number;
  /** The `public_path` from generate_image, e.g. "/public/<video_id>/images/harbour.png". */
  imageSrc: string;
  headline?: string;
  subhead?: string;
}

export default function KenBurnsHook({
  durationInFrames,
  imageSrc,
  headline = "Ninety percent of traffic never reaches the server",
  subhead = "The cache answered first",
}: Props) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Headline springs in; the image is already drifting underneath, so the scene
  // has two independently animated elements from frame 0.
  const headlineY = spring({
    frame,
    fps,
    config: { damping: 15, stiffness: 105 },
    from: 70,
    to: 0,
  });
  const headlineOpacity = interpolate(frame, [0, 20], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Subhead trails the headline — same spring, offset frame.
  const subheadOpacity = interpolate(frame, [18, 40], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <ImageFX
      src={imageSrc}
      durationInFrames={durationInFrames}
      // Start zoomed in and slowly pull back while drifting right — the pan is
      // clamped to whatever overhang the zoom leaves, so an edge can never
      // creep into frame no matter what you ask for here.
      scaleFrom={1.28}
      scaleTo={1.08}
      panFrom={[-0.05, 0]}
      panTo={[0.05, 0]}
      anchor={[0.5, 0.45]}
      vignette={0.5}
    >
      <AbsoluteFill
        style={{
          // Shorts safe zone: x 60–1020, y 150–1750.
          padding: "0 60px",
          justifyContent: "flex-end",
          paddingBottom: 300,
        }}
      >
        <span
          style={{
            fontFamily: "sans-serif",
            fontSize: 68,
            fontWeight: 800,
            color: "#ffffff",
            lineHeight: 1.15,
            textShadow: "0 4px 28px rgba(0,0,0,0.85)",
            transform: `translateY(${headlineY}px)`,
            opacity: headlineOpacity,
          }}
        >
          {headline}
        </span>
        <span
          style={{
            fontFamily: "sans-serif",
            fontSize: 36,
            fontWeight: 500,
            color: "#cbd5e1",
            marginTop: 20,
            textShadow: "0 2px 16px rgba(0,0,0,0.85)",
            opacity: subheadOpacity,
          }}
        >
          {subhead}
        </span>
      </AbsoluteFill>
    </ImageFX>
  );
}
