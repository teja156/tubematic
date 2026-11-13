/*
 * The picture render_style_parts returns for a Night Signal video: each of the
 * video's own parts (customParts), drawn exactly as the scene draws it, in its
 * box (outlined), standing on a ground line beside a person for size, its id
 * under it, and a second time in red, as the threat. Up to six parts, two a row.
 *
 * It imports only the drawing routine, so a sheet bundles nothing of the scene.
 */
import React, { useLayoutEffect, useRef, useState } from "react";
import { AbsoluteFill, continueRender, delayRender } from "remotion";
import { LIMITS, type CustomPart } from "./contract";
import { COLORS, FONT, drawShapes } from "./draw";
import { useNightSignalFonts } from "./fonts";
import { personShapes } from "./parts";

const CELL_W = 540, CELL_H = 600, SCALE = 0.95;

export const NightSignalPartsSheet: React.FC<{ parts: CustomPart[] }> = ({ parts }) => {
  const ready = useNightSignalFonts("NightSignalPartsSheet");
  const ref = useRef<HTMLCanvasElement>(null);
  const [handle] = useState(() => delayRender("NightSignalPartsSheet: drawing"));
  useLayoutEffect(() => {
    const ctx = ref.current?.getContext("2d");
    if (!ctx || !ready) return;
    ctx.fillStyle = COLORS.bg;
    ctx.fillRect(0, 0, 1080, 1920);
    const half = LIMITS.partBox / 2;
    parts.slice(0, LIMITS.maxCustomParts).forEach((p, i) => {
      const cx = (i % 2) * CELL_W + CELL_W / 2 + 40;
      const ground = Math.floor(i / 2) * CELL_H + 520;
      ctx.strokeStyle = "#C0201C";
      ctx.lineWidth = 2;
      const s = SCALE * 0.5;
      ctx.strokeRect(cx - 80 - half * s, ground - LIMITS.partBox * s, LIMITS.partBox * s, LIMITS.partBox * s);
      ctx.strokeStyle = COLORS.ink;
      ctx.globalAlpha = 0.85;
      ctx.lineWidth = 4;
      ctx.beginPath();
      ctx.moveTo(cx - 250, ground);
      ctx.lineTo(cx + 230, ground);
      ctx.stroke();
      ctx.globalAlpha = 1;
      // the part as the scene draws it, at half size, a person beside it for scale, then in red
      drawShapes(ctx, p.shapes, cx - 80, ground, SCALE * 0.5, 1);
      drawShapes(ctx, personShapes("stand"), cx - 200, ground, SCALE * 0.5, 1, { alpha: 0.5 });
      drawShapes(ctx, p.shapes, cx + 120, ground, SCALE * 0.5, 1, { red: 1 });
      ctx.font = `700 34px ${FONT}`;
      ctx.fillStyle = COLORS.grey;
      ctx.textAlign = "center";
      ctx.fillText(p.id, cx - 20, ground + 50);
    });
    continueRender(handle);
  }, [ready, parts, handle]);
  return (
    <AbsoluteFill style={{ background: COLORS.bg }}>
      <canvas ref={ref} width={1080} height={1920} />
    </AbsoluteFill>
  );
};
