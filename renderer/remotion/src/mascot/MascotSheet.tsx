// One model sheet of a mascot, as a still: the picture a person reviews before the mascot can be used. The mascot's
// own page (public/mascot/frame.html) draws the sheet in `?sheet=` mode inside a full-frame iframe; the still is
// taken once its window.renderSheet(name) has finished. Rendered by mascot-tools/render-sheet.mjs, on software GL.
import React, { useRef, useState } from "react";
import { cancelRender, Composition, continueRender, delayRender, IFrame, staticFile, useVideoConfig } from "remotion";

export type SheetName = "turn" | "feels" | "act";

// The size of the picture sheet.js leaves in the page's #out canvas: turn and feels are one 1920x1080 frame, act is
// a contact sheet of eight 480x270 cells in two rows. Keep in sync with public/mascot/sheet.js.
export const SHEET_SIZE: Record<SheetName, { width: number; height: number }> = {
  turn: { width: 1920, height: 1080 },
  feels: { width: 1920, height: 1080 },
  act: { width: 1920, height: 540 },
};

// A sheet on software GL takes minutes (act draws eight frames). Kept under the 1200 s that
// mcp/mascot_sheets.py::render_sheet allows the whole command, so a hung page fails here, with a message.
export const SHEET_TIMEOUT_MS = 1_080_000;
const READY_TIMEOUT_MS = 120_000;

type SheetWindow = Window & { ready?: boolean; MASCOT?: unknown; renderSheet?: (name: string) => Promise<void> };

type SheetProps = { code: string; sheet: SheetName };

export const MascotSheet: React.FC<SheetProps> = ({ code, sheet }) => {
  const { width, height } = useVideoConfig();
  const ref = useRef<HTMLIFrameElement>(null);
  const [handle] = useState(() => delayRender(`mascot sheet: ${sheet}`, { timeoutInMilliseconds: SHEET_TIMEOUT_MS }));

  const onLoad = () => {
    const win = ref.current?.contentWindow as SheetWindow | null;
    if (!win) return;
    if (typeof win.MASCOT !== "function") {
      cancelRender(new Error("the mascot code did not load or did not set window.MASCOT (see the browser errors above)"));
      return;
    }
    const started = Date.now();
    const wait = () => {
      if (!win.ready) {
        if (Date.now() - started > READY_TIMEOUT_MS) cancelRender(new Error("the mascot page never became ready (p5 setup failed?)"));
        else setTimeout(wait, 50);
        return;
      }
      win.renderSheet!(sheet).then(() => continueRender(handle), (err) => cancelRender(err));
    };
    wait();
  };

  const src = `${staticFile("mascot/frame.html")}?code=${encodeURIComponent(staticFile(code))}&sheet=${sheet}`;
  return (
    <IFrame
      ref={ref}
      src={src}
      onLoad={onLoad}
      delayRenderTimeoutInMilliseconds={READY_TIMEOUT_MS}
      style={{ position: "absolute", left: 0, top: 0, width, height, border: 0 }}
    />
  );
};

// `code` is the mascot's drawing code as a path under public/ (the sheet renderer stages it there).
export const MascotSheetComposition: React.FC = () => (
  <Composition
    id="MascotSheet"
    component={MascotSheet as unknown as React.ComponentType<Record<string, unknown>>}
    fps={30}
    durationInFrames={1}
    width={SHEET_SIZE.turn.width}
    height={SHEET_SIZE.turn.height}
    defaultProps={{ code: "sheet/mascot.js", sheet: "turn" }}
    calculateMetadata={({ props }) => SHEET_SIZE[(props as SheetProps).sheet] ?? SHEET_SIZE.turn}
  />
);
