/*
 * The picture render_style_parts returns for an Isometric Infographic video:
 * each of the video's own props (customProps, compositions of the kit's
 * solids), drawn as the board draws them on a patch of ground, beside a
 * library house for scale, its id under it. Up to six props, two a row.
 */
import React, { useLayoutEffect, useRef, useState } from "react";
import { AbsoluteFill, continueRender, delayRender } from "remotion";
import { LIMITS, type CustomProp } from "./contract";
import { colorOf } from "./draw";
import { JOST, useIsometricFonts } from "./fonts";
import { AREA_COLORS, PALETTE, PAPER, PROPS, drawSolid, poly, project, tones } from "./kit";

export const IsometricPartsSheet: React.FC<{ parts: CustomProp[] }> = ({ parts }) => {
  const ready = useIsometricFonts("IsometricPartsSheet");
  const ref = useRef<HTMLCanvasElement>(null);
  const [handle] = useState(() => delayRender("IsometricPartsSheet: drawing"));
  useLayoutEffect(() => {
    const ctx = ref.current?.getContext("2d");
    if (!ctx || !ready) return;
    ctx.fillStyle = PAPER;
    ctx.fillRect(0, 0, 1080, 1920);
    parts.slice(0, LIMITS.maxCustomProps).forEach((p, i) => {
      const pr = { k: 150, cx: (i % 2) * 540 + 270, cy: Math.floor(i / 2) * 600 + 160 };
      poly(ctx, [project(pr, 0, 0), project(pr, 2, 0), project(pr, 2, 2), project(pr, 0, 2)], tones(AREA_COLORS.city).top);
      const house = PROPS.house;
      for (const sd of house.solids) drawSolid(ctx, pr, sd, 0.5, 1.5, 0, 1, { main: house.main, accent: house.accent, fade: 0.4, spread: 0 });
      for (const sd of p.solids) drawSolid(ctx, pr, sd, 1.3, 0.9, 0, 1, { main: colorOf(p.main, PALETTE.cream), accent: PALETTE.slate, fade: 0, spread: 0 });
      ctx.font = `600 34px ${JOST}`;
      ctx.fillStyle = "#231A2C";
      ctx.textAlign = "center";
      ctx.fillText(p.id, pr.cx, pr.cy + 360);
    });
    continueRender(handle);
  }, [ready, parts, handle]);
  return (
    <AbsoluteFill>
      <canvas ref={ref} width={1080} height={1920} />
    </AbsoluteFill>
  );
};
