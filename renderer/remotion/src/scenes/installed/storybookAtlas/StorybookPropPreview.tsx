/*
 * The picture render_storybook_props returns: each prop the agent drew for a
 * video, in every state, on the book's paper, its declared box outlined in red
 * with a line saying whether the drawing fits it, the guide beside it at the
 * same scale for size, and its first drawing again on a night-navy swatch, to
 * show how it reads on the dark backdrops. One prop a row while there are at
 * most four, so they are shown near their size in the video; two a row above.
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
import { NAVY, SERIF, TEXT } from "./palette";
import { BoxCheck, propDrawing } from "./props/draw";
import type { PropDrawing, PropEntry, PropSpec } from "./props/types";

type Spec = PropSpec & { id: string; src: string };

const PAPER = paperDrawing();
const ROW_H = 470, TOP = 20, DARK_W = 0.4;
/** Room in each cell for the guide, drawn at the prop's scale to show its size. */
const GUIDE_ROOM = 240;

export const StorybookPropPreview: React.FC<{ specs: Spec[]; drawings: Record<string, PropDrawing> }> = ({ specs, drawings }) => {
  useStorybookFonts("StorybookPropPreview");
  return (
    <AbsoluteFill>
      <CanvasBitmap d={PAPER} />
      {specs.slice(0, 8).map((raw, i, all) => {
        // the validator reads a missing `states` as 1
        const spec = { ...raw, states: raw.states ?? 1 };
        const cols = all.length <= 4 ? 1 : 2;
        const CELL_W = 1080 / cols;
        const draw = drawings[spec.id];
        if (!draw) return null;
        const entry: PropEntry = { ...spec, label: spec.id, draw };
        const [w, h] = spec.box;
        const cellLeft = (i % cols) * CELL_W, darkW = CELL_W * DARK_W * (cols === 1 ? 0.6 : 1);
        const room = CELL_W - darkW - GUIDE_ROOM - 30;
        const cx = cellLeft + GUIDE_ROOM + room / 2, base = TOP + Math.floor(i / cols) * ROW_H + 360;
        const gap = 16;
        const s = Math.min(1, room / (w * spec.states + gap * (spec.states - 1)), 330 / Math.max(h, GUIDE_BOX.height));
        const ds = Math.min(s, (darkW - 20) / w);
        const darkLeft = cellLeft + CELL_W - darkW;
        const total = (w * spec.states + gap * (spec.states - 1)) * s;
        const gx = cellLeft + 20 + GUIDE_BOX.footX * s;
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
            <div style={{ position: "absolute", left: darkLeft, top: base - 350, width: darkW - 8, height: 360, background: NAVY }} />
            <Bitmap d={propDrawing(spec.id, entry, 0)} left={darkLeft + (darkW - 8) / 2 - w / 2} top={base - h}
              transform={ds === 1 ? undefined : `scale(${ds})`} origin={[w / 2, h]} />
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
