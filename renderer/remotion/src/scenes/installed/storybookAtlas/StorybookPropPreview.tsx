/*
 * The picture render_storybook_props returns: each prop the agent drew for a
 * video, in every state, on the book's paper, its declared box outlined in red
 * with a line saying whether the drawing fits it, and the guide beside each at
 * the same scale for size.
 *
 * It imports neither the scene nor the library's index, so a preview bundles
 * only this video's prop files (storybook-tools/render-props.mjs).
 */
import React from "react";
import { AbsoluteFill } from "remotion";
import { Bitmap, CanvasBitmap } from "./bitmap";
import { paperDrawing } from "./backdrops";
import { useStorybookFonts } from "./fonts";
import { GUIDE_BOX, guideDrawing } from "./guide";
import { SERIF, TEXT } from "./palette";
import { BoxCheck, propDrawing } from "./props/draw";
import type { PropDrawing, PropEntry, PropSpec } from "./props/types";

type Spec = PropSpec & { id: string; src: string };

const PAPER = paperDrawing();
const CELL_W = 540, CELL_H = 470, TOP = 20;
/** Room in each cell for the guide, drawn at the prop's scale to show its size. */
const GUIDE_ROOM = 150;

export const StorybookPropPreview: React.FC<{ specs: Spec[]; drawings: Record<string, PropDrawing> }> = ({ specs, drawings }) => {
  useStorybookFonts("StorybookPropPreview");
  return (
    <AbsoluteFill>
      <CanvasBitmap d={PAPER} />
      {specs.slice(0, 8).map((spec, i) => {
        const draw = drawings[spec.id];
        if (!draw) return null;
        const entry: PropEntry = { ...spec, label: spec.id, draw };
        const [w, h] = spec.box;
        const cx = (i % 2) * CELL_W + CELL_W / 2 + GUIDE_ROOM / 2, base = TOP + Math.floor(i / 2) * CELL_H + 360;
        const gap = 16;
        const s = Math.min(1, (CELL_W - GUIDE_ROOM - 30) / (w * spec.states + gap * (spec.states - 1)), 330 / Math.max(h, GUIDE_BOX.height));
        const total = (w * spec.states + gap * (spec.states - 1)) * s;
        const gx = cx - total / 2 - 20 - (GUIDE_BOX.width - GUIDE_BOX.footX) * s;
        return (
          <React.Fragment key={spec.id}>
            {Array.from({ length: spec.states }, (_, st) => {
              const left = cx - total / 2 + st * (w + gap) * s;
              return (
                <React.Fragment key={st}>
                  <div style={{ position: "absolute", left, top: base - h * s, width: w * s, height: h * s, outline: "2px solid #C0201C" }} />
                  <Bitmap d={propDrawing(spec.id, entry, st)} left={left} top={base - h * s} transform={s === 1 ? undefined : `scale(${s})`} origin={[0, 0]} />
                </React.Fragment>
              );
            })}
            <Bitmap d={guideDrawing("stand", "blue")} left={gx - GUIDE_BOX.footX} top={base - GUIDE_BOX.footY}
              transform={s === 1 ? undefined : `scale(${s})`} origin={[GUIDE_BOX.footX, GUIDE_BOX.footY]} opacity={0.55} />
            <div style={{ position: "absolute", left: cx - 250, width: 500, top: base + 8, textAlign: "center", fontFamily: SERIF, fontSize: 28, color: TEXT }}>
              {spec.id} ({spec.place}, {spec.states} state{spec.states > 1 ? "s" : ""})
            </div>
            <BoxCheck entry={entry} x={cx} y={base + 46} />
          </React.Fragment>
        );
      })}
    </AbsoluteFill>
  );
};
