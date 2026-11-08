// Draws a video's mascot over its scenes, under the captions. The mascot is p5.js drawing code that runs in its own
// page (public/mascot/frame.html) inside an iframe, isolated from this React tree. Each frame asks that page to draw
// time t and holds the frame (delayRender) until it has, then moves the iframe to where the cue track puts the
// mascot. While the mascot is off screen the page draws nothing and the iframe is hidden.
//
// The per-video data is scene-config.json's `mascot` key: a bare list of cues, never code. The code is the mascot
// version pinned to the video, staged by the render worker and named by the `mascotPath` render prop. Nothing here
// reads the narration's word timings: the mascot reacts, it never talks.
import React, { useEffect, useMemo, useRef, useState } from "react";
import { cancelRender, continueRender, delayRender, IFrame, staticFile, useCurrentFrame, useVideoConfig } from "remotion";

/** One cue (renderer/remotion/public/mascot/driver.js; checked by tubematic_core/mascots.py::cue_errors). */
export interface MascotCue {
  frame: number;
  emotion?: string;
  x?: number;
  y?: number;
  scale?: number;
  look?: "up" | "down" | "left" | "right" | "none";
  facing?: "left" | "right" | "front";
  jump?: boolean;
  on?: boolean;
}

type MascotWindow = Window & {
  ready?: boolean;
  MASCOT?: unknown;
  TRACK?: { fps: number; width: number; height: number; cues: MascotCue[] };
  renderMascot?: (t: number) => Promise<{ left: number; top: number } | null>;
};

// The overlay box the page draws into. Keep in sync with frame.html's KIT_W/KIT_H and
// tubematic_core/mascots.py's BOX_W/BOX_H.
const BOX_W = 560;
const BOX_H = 640;
// Loading p5 and building the page's paper and grain takes well under this on a GPU.
const BOOT_TIMEOUT_MS = 60000;
const FRAME_TIMEOUT_MS = 60000;

export const MascotLayer: React.FC<{ mascotPath: string; cues: MascotCue[] }> = ({ mascotPath, cues }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const ref = useRef<HTMLIFrameElement>(null);
  const track = useMemo(() => ({ fps, width, height, cues }), [fps, width, height, cues]);
  const [boot] = useState(() => {
    let resolve!: (w: MascotWindow) => void;
    const promise = new Promise<MascotWindow>((r) => (resolve = r));
    return { promise, resolve, handle: delayRender("mascot: load the mascot page", { timeoutInMilliseconds: BOOT_TIMEOUT_MS }) };
  });

  const onLoad = () => {
    const win = ref.current?.contentWindow as MascotWindow | null;
    if (!win) return;
    if (typeof win.MASCOT !== "function") {
      cancelRender(new Error(`the mascot code at ${mascotPath} did not load or did not set window.MASCOT`));
      return;
    }
    win.TRACK = track; // before the first renderMascot: the driver compiles the track once, on first use
    const wait = () => (win.ready ? (boot.resolve(win), continueRender(boot.handle)) : setTimeout(wait, 20));
    wait();
  };

  useEffect(() => {
    const h = delayRender(`mascot: frame ${frame}`, { timeoutInMilliseconds: FRAME_TIMEOUT_MS });
    boot.promise
      .then(async (win) => {
        const place = await win.renderMascot!(frame / fps);
        const el = ref.current;
        if (el) {
          el.style.visibility = place ? "visible" : "hidden";
          if (place) el.style.transform = `translate(${place.left}px, ${place.top}px)`;
        }
        continueRender(h);
      })
      .catch((err) => cancelRender(err));
  }, [frame, fps, boot]);

  return (
    <IFrame
      ref={ref}
      src={`${staticFile("mascot/frame.html")}?code=${encodeURIComponent(mascotPath)}`}
      onLoad={onLoad}
      delayRenderTimeoutInMilliseconds={BOOT_TIMEOUT_MS}
      style={{
        position: "absolute",
        left: 0,
        top: 0,
        width: BOX_W,
        height: BOX_H,
        border: 0,
        background: "transparent",
        pointerEvents: "none",
        colorScheme: "normal",
        visibility: "hidden",
      }}
    />
  );
};
