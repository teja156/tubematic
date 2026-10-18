import React from "react";
import { AbsoluteFill } from "remotion";

// Scaffold for a Stick Explainer scene (TMDEV-101) — the white ground, the
// comic banner title and the panel framing the register uses.
//
// A wrapper component, NOT a scene: it takes your content as children, so it
// cannot be referenced from scene-config.json. Import it into a scene you
// author:
//
//   import StickScene from "../../installed/StickScene";
//   import StickFigure from "../../installed/StickFigure";
//
//   export default function MyScene({ durationInFrames }) {
//     const frame = useCurrentFrame();
//     return (
//       <StickScene title="WHEN THE ALERT FIRES">
//         <StickFigure pose={frame < 90 ? "type" : "panic"} x={540} y={1100} />
//       </StickScene>
//     );
//   }
//
// `transparent` defaults to true and should almost always stay that way: under
// the stick register CompositionBuilder already paints the white canvas for
// the whole video, and a scene that paints its own opaque background is how a
// video ends up flashing between scenes that disagree by a shade. Set it false
// only for a deliberately tinted panel scene.

/** Matches StickFigure's StickTheme. The banner inverts with the canvas. */
export type StickSceneTheme = "light" | "dark";

const THEMES: Record<StickSceneTheme, {
  ink: string;
  paper: string;
  bannerBg: string;
  bannerFg: string;
  bannerRule: boolean;
}> = {
  // On white, the banner is a solid ink bar with paper-coloured type — the
  // comic masthead the register is built around.
  light: {
    ink: "#000000", paper: "#ffffff",
    bannerBg: "#000000", bannerFg: "#ffffff", bannerRule: false,
  },
  // On dark it is NOT simply the inverse. A solid white bar inverts the
  // contrast correctly and still looks wrong: it lands as a slab of light at
  // the top of a dark frame and pulls the eye off the content for the whole
  // scene. A ruled title on the canvas keeps the masthead reading as chrome.
  dark: {
    ink: "#ffffff", paper: "#0f0f0f",
    bannerBg: "transparent", bannerFg: "#ffffff", bannerRule: true,
  },
};

interface Props {
  /** Which canvas this scene sits on. Sets the banner and frame colours. */
  theme?: StickSceneTheme;
  /** Optional comic banner across the top. Uppercase reads best. */
  title?: string;
  /** Banner height. Only used when `title` is set. */
  bannerHeight?: number;
  /**
   * Draw a black rectangular frame inset from the edges — the register's
   * comic-cell framing. Off by default; a full-bleed white ground is the norm.
   */
  framed?: boolean;
  /** Inset of the frame from the canvas edge, in px. */
  frameInset?: number;
  /**
   * Paint an opaque background of `background` instead of letting the video's
   * canvas show through. See the note above before turning this on.
   */
  transparent?: boolean;
  background?: string;
  /** Line colour for the banner and frame. */
  ink?: string;
  children?: React.ReactNode;
}

export default function StickScene({
  theme = "light",
  title,
  bannerHeight = 150,
  framed = false,
  frameInset = 40,
  transparent = true,
  background,
  ink,
  children,
}: Props) {
  const palette = THEMES[theme] ?? THEMES.light;
  // The banner is ink-filled with paper-coloured type, so both have to come
  // from the same palette — a black banner on a dark canvas is invisible.
  const line = ink ?? palette.ink;
  const paper = background ?? palette.paper;
  return (
    <AbsoluteFill style={transparent ? undefined : { backgroundColor: paper }}>
      {framed && (
        <div
          style={{
            position: "absolute",
            left: frameInset,
            top: title ? bannerHeight + frameInset : frameInset,
            right: frameInset,
            bottom: frameInset,
            border: `6px solid ${line}`,
            boxSizing: "border-box",
          }}
        />
      )}

      {children}

      {/* Drawn last so nothing can cover the title — in this register the
          banner is chrome, not a layer in the scene. */}
      {title && (
        <div
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            height: bannerHeight,
            background: palette.bannerBg === "transparent" ? undefined : line,
            color: palette.bannerBg === "transparent" ? palette.bannerFg : paper,
            borderBottom: palette.bannerRule ? `6px solid ${line}` : undefined,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "0 40px",
            boxSizing: "border-box",
            fontFamily: "system-ui, sans-serif",
            fontWeight: 800,
            fontSize: 62,
            lineHeight: 1.05,
            letterSpacing: "0.02em",
            textAlign: "center",
          }}
        >
          {title}
        </div>
      )}
    </AbsoluteFill>
  );
}
