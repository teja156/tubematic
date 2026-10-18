import { AbsoluteFill } from "remotion";
import ImageFX from "./ImageFX";

// A generated image contained in a comic panel (TMDEV-101).
//
// This is the Stick Explainer register's answer to a beat whose subject is a
// real, specific person, creature or place. Such a beat still gets a real
// generated image — forcing the stick register does not ban photographs — but
// full-bleed it would replace the white ground and the video would cut between
// two different-looking worlds. Framing it in a panel on the same white ground
// keeps one canvas for the whole video, which is the register's one
// non-negotiable rule.
//
// Reference it straight from scene-config.json — no scene file to author:
//
//   {
//     "type": "generated", "src": "PanelImage", "source": "installed",
//     "startFrame": 150, "durationInFrames": 180,
//     "props": {
//       "src": "/public/{video_id}/images/dragonpit.png",
//       "label": "THE DRAGONPIT",
//       "caption": "Built to hold what could not be held"
//     }
//   }
//
// Under the motion-graphics register use KenBurnsImage instead: there the
// image IS the frame, and a panel around it would be decoration.

interface Props {
  durationInFrames: number;
  /** The `public_path` returned by generate_image, copied verbatim. */
  src: string;
  /** Panel width and height in px. Defaults suit a 1080x1920 frame. */
  width?: number;
  height?: number;
  /** Panel centre in frame coordinates. */
  x?: number;
  y?: number;
  /** Optional black tab across the panel's top-left, comic-cell style. */
  label?: string;
  /** Optional line of type below the panel, on the canvas. */
  caption?: string;
  /** Line colour and weight for the panel border. */
  ink?: string;
  border?: number;
  /**
   * Which point of the source image survives the crop, as [u, v] fractions.
   *
   * **Prefer sizing the panel to the image's aspect so nothing is cropped at
   * all** — `generate_image` and `generate_character` return the real pixel
   * dimensions, so the shape is knowable. Use this when the composition fixes
   * the panel's shape and a crop is unavoidable: read the subject's position
   * off `read_image`'s UV grid and pass it here. The default centre-crop is
   * what silently beheads a tall portrait squeezed into a squarer panel.
   */
  focus?: [number, number];
  /**
   * Ken Burns move inside the panel. The image still drifts — a motionless
   * picture is the most common way one of these scenes looks cheap — it just
   * drifts inside the frame rather than being the frame.
   */
  scaleFrom?: number;
  scaleTo?: number;
  panFrom?: [number, number];
  panTo?: [number, number];
}

export default function PanelImage({
  durationInFrames,
  src,
  width = 900,
  height = 1000,
  x = 540,
  y = 900,
  label,
  caption,
  ink = "#000000",
  border = 6,
  focus,
  scaleFrom = 1.18,
  scaleTo = 1.0,
  panFrom = [-0.04, 0],
  panTo = [0.04, 0],
}: Props) {
  return (
    <AbsoluteFill>
      <div
        style={{
          position: "absolute",
          left: x - width / 2,
          top: y - height / 2,
          width,
          height,
          border: `${border}px solid ${ink}`,
          boxSizing: "border-box",
          // Without this the ImageFX camera move paints outside the panel and
          // the frame stops meaning anything.
          overflow: "hidden",
        }}
      >
        {/* ImageFX is an AbsoluteFill, so it fills this box rather than the
            frame — which is exactly the containment this component is for. */}
        <ImageFX
          src={src}
          durationInFrames={durationInFrames}
          scaleFrom={scaleFrom}
          scaleTo={scaleTo}
          panFrom={panFrom}
          panTo={panTo}
          focus={focus}
        />
      </div>

      {label && (
        <div
          style={{
            position: "absolute",
            left: x - width / 2,
            top: y - height / 2,
            background: ink,
            color: "#ffffff",
            padding: "10px 22px",
            fontFamily: "system-ui, sans-serif",
            fontWeight: 700,
            fontSize: 30,
            letterSpacing: "0.02em",
          }}
        >
          {label}
        </div>
      )}

      {caption && (
        <div
          style={{
            position: "absolute",
            left: x - width / 2,
            top: y + height / 2 + 28,
            width,
            textAlign: "center",
            fontFamily: "system-ui, sans-serif",
            fontWeight: 600,
            fontSize: 38,
            lineHeight: 1.25,
            color: ink,
          }}
        >
          {caption}
        </div>
      )}
    </AbsoluteFill>
  );
}
