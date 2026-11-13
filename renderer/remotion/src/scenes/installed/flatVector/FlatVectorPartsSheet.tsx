/*
 * The picture render_style_parts returns for a Flat Vector Science video: each
 * prop the agent drew for it (customProps), rasterised exactly as the scene
 * does, on the abyss, its declared box outlined in red, the library's person
 * beside it at size `m` for scale, and its id under it. A drawing that runs
 * past its box is cut off in the video. Up to eight props, two a row.
 *
 * It imports only the drawing helpers, the library's person and the video's
 * own prop files (flatvector-tools via style-tools/render-parts.mjs), never
 * the scene.
 */
import React, { useLayoutEffect, useRef, useState } from "react";
import { AbsoluteFill, cancelRender, continueRender, delayRender } from "remotion";
import { LIMITS, type CustomProp } from "./contract";
import { useFlatVectorFonts, LABEL } from "./fonts";
import { PROPS } from "./props";
import { halo, rasterise } from "./sprites";

const CELL_W = 540, CELL_H = 470, ROOM = 360;

export const FlatVectorPartsSheet: React.FC<{ specs: CustomProp[]; drawings: Record<string, React.FC> }> = ({ specs, drawings }) => {
  useFlatVectorFonts("FlatVectorPartsSheet");
  const ref = useRef<HTMLCanvasElement>(null);
  const [handle] = useState(() => delayRender("FlatVectorPartsSheet: drawing"));
  useLayoutEffect(() => {
    const ctx = ref.current?.getContext("2d");
    if (!ctx) return;
    (async () => {
      ctx.fillStyle = "#030c0f";
      ctx.fillRect(0, 0, 1080, 1920);
      const person = await rasterise(PROPS.person.draw(), PROPS.person.box[0], PROPS.person.box[1], 1);
      const list = specs.slice(0, LIMITS.maxCustomProps);
      for (let i = 0; i < list.length; i++) {
        const c = list[i];
        const D = drawings[c.id];
        if (!D) continue;
        const [w, h] = c.box;
        const s = Math.min(1, ROOM / Math.max(w, h));
        const sp = await rasterise(React.createElement(D), w, h, s);
        const cx = (i % 2) * CELL_W + CELL_W / 2 + 50, cy = Math.floor(i / 2) * CELL_H + 240;
        if (c.light) ctx.drawImage(halo(c.light), cx - w * s * 0.75, cy - w * s * 0.75, w * s * 1.5, w * s * 1.5);
        ctx.drawImage(sp.canvas, cx - (w * s) / 2, cy - (h * s) / 2, w * s, h * s);
        ctx.strokeStyle = "#C0201C";
        ctx.lineWidth = 2;
        ctx.strokeRect(cx - (w * s) / 2, cy - (h * s) / 2, w * s, h * s);
        // a person at size m, at the same scale as this prop at size m
        const ps = (460 / Math.max(...PROPS.person.box)) / (460 / Math.max(w, h)) * s;
        ctx.globalAlpha = 0.5;
        ctx.drawImage(person.canvas, cx - (w * s) / 2 - 60 - 40 * ps, cy + (h * s) / 2 - 340 * ps, 120 * ps, 340 * ps);
        ctx.globalAlpha = 1;
        ctx.font = `800 32px ${LABEL}`;
        ctx.fillStyle = "#F9FCFB";
        ctx.textAlign = "center";
        ctx.fillText(c.id, cx, cy + Math.max(h * s / 2, 60) + 44);
      }
    })()
      .then(() => continueRender(handle))
      .catch((err) => cancelRender(err));
  }, [specs, drawings, handle]);
  return (
    <AbsoluteFill style={{ background: "#030c0f" }}>
      <canvas ref={ref} width={1080} height={1920} />
    </AbsoluteFill>
  );
};
