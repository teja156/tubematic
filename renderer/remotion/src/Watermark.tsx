import React from "react";
import { Img, staticFile } from "remotion";

// The "Made with tubematic.ai" mark (TMDEV-141).
//
// NOT a scene, for the reasons Subtitles.tsx gives: CompositionBuilder draws
// it above every scene, outside any Sequence, so it is never crossfaded at a
// scene boundary and never counts as a scene.
//
// IT TAKES NO PROPS, AND THAT IS THE FEATURE. The agent authors
// scene-config.json, so anything expressed there the agent could move, dim or
// delete. Size, place and opacity are constants here; whether it is drawn at
// all is a human-only setting the worker passes to CompositionBuilder, never
// a config key.
//
// The artwork is the `smoke` variant, which carries its own translucent grey
// plate. The plate is why there is no colour derivation from the canvas
// (unlike Subtitles): it puts something dark behind the white text on every
// frame. The plate-less `shadow` variant was tried in real renders and its two
// text lines all but vanished on a white canvas and on pale backgrounds.
//
// The file is baked into the image under public/ and loaded with staticFile().
// Never fetch it over the network: this is on the path of every render, and a
// renderer with no egress would stall on it.

// The asset is 480x630. Drawn at about 27%, on the 1080x1920 canvas.
const WIDTH = 130;
// Top-right, because the bottom of the frame belongs to the captions. Tucked
// into the corner, deliberately OUTSIDE the Shorts safe zone (top 150, sides
// 60): the safe zone is where scenes put content, and the mark is meant to
// stay out of their way, not to be read through the platform's own UI.
const TOP = 32;
const RIGHT = 32;
// Low enough that the scene shows through it.
const OPACITY = 0.6;
// Being last in the DOM is not enough to be on top. Scenes are not isolated
// stacking contexts, so a positioned scene element with any positive z-index
// paints above a later sibling whose z-index is auto — a full-frame layered
// background would hide the mark completely. This is the largest z-index a
// browser honours (larger values clamp to it), and on a tie the later element
// wins, which is this one. Nothing a scene declares can get above it.
const Z_INDEX = 2147483647;

const Watermark: React.FC = () => (
  <Img
    src={staticFile("watermark.png")}
    style={{
      position: "absolute",
      top: TOP,
      right: RIGHT,
      width: WIDTH,
      height: "auto",
      opacity: OPACITY,
      zIndex: Z_INDEX,
      pointerEvents: "none",
    }}
  />
);

export default Watermark;
