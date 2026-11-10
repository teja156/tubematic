/*
 * The preview of the props an agent drew for one video, rendered by
 * bean-tools/render-props.mjs for the render_bean_props tool so the agent can
 * look at its drawings before it submits. Each prop is shown at rest and, when
 * it has acts, with four moments of its first act drawn over one another (an
 * act can carry a drawing past its box late in the act), on the video's
 * field, with its declared box outlined in red: ink outside the red line is a
 * drawing bigger than the box the layout checks use. A library prop sits in the corner as
 * the reference for line weight and size.
 *
 * Not used by any video. The drawings come in as components from the entry
 * the script writes, so nothing here imports generated/.
 */
import React from "react";
import { AbsoluteFill } from "remotion";
import { INK, RED } from "./bean";
import { FIELDS, GEOMETRY, type BECustomProp, type FieldId } from "./contract";
import { HAND, ROUND, useBeanFonts } from "./fonts";
import type { Drawing } from "./kit";
import { DRAWINGS, WHOLE_PROP_ACTS, wholePropMotion } from "./props";

export type PreviewSpec = BECustomProp & { sample?: string };

const CELL_W = 540;
const CELL_H = 440;
const TOP = 220;

const ACT_MOMENTS = [6, 20, 40, 59];

const Copy: React.FC<{ Draw: Drawing; spec: PreviewSpec; cx: number; cy: number; k: number; act: string }> = ({ Draw, spec, cx, cy, k, act }) => {
  const whole = act !== "" && (WHOLE_PROP_ACTS as readonly string[]).includes(act);
  const text = spec.text ? spec.sample || "Sample text" : "";
  const moments = act ? ACT_MOMENTS : [-1];
  return (
    <g>
      {moments.map((t, i) => {
        const [mx, my, mr, ms, pivot] = whole ? wholePropMotion(act, t, spec.h) : [0, 0, 0, 1, 0];
        return (
          <g key={t} opacity={i === moments.length - 1 ? 1 : 0.45}
            transform={`translate(${cx + mx * k} ${cy + my * k}) scale(${k * ms}) rotate(${mr} 0 ${pivot})`}>
            <Draw frame={t < 0 ? 0 : t} actT={act && !whole ? t : -1} text={text} round={ROUND} hand={HAND} />
          </g>
        );
      })}
      <rect x={cx - (spec.w * k) / 2} y={cy - (spec.h * k) / 2} width={spec.w * k} height={spec.h * k} fill="none" stroke={RED} strokeWidth={3} />
    </g>
  );
};

export const BeanPropPreview: React.FC<{ specs: PreviewSpec[]; drawings: Record<string, Drawing>; field?: FieldId }> = ({ specs, drawings, field }) => {
  useBeanFonts("BeanPropPreview");
  const Ref = DRAWINGS.phone;
  return (
    <AbsoluteFill style={{ background: FIELDS[field ?? "yellow"] ?? FIELDS.yellow }}>
      <svg width={1080} height={1920}>
        <text x={40} y={90} fontSize={52} fontWeight={700} fill={INK} style={{ fontFamily: ROUND }}>this video&apos;s props</text>
        <text x={40} y={140} fontSize={34} fill={INK} style={{ fontFamily: HAND }}>red line: the declared box. Ink outside it is too big for its box.</text>
        {specs.map((spec, i) => {
          const Draw = drawings[spec.id];
          const x0 = (i % 2) * CELL_W, y0 = TOP + Math.floor(i / 2) * CELL_H;
          const act = spec.acts?.[0] ?? "";
          const copies = act ? 2 : 1;
          const k = Math.min(1, (CELL_W / copies - 40) / spec.w, (CELL_H - 110) / spec.h);
          const label = `${spec.id} · ${spec.w}x${spec.h}${k < 1 ? ` · shown at ${k.toFixed(2)}x` : ""}`;
          const second = act ? `left: at rest · right: ${act}, four moments` : "";
          return (
            <g key={spec.id}>
              <rect x={x0 + 8} y={y0 + 8} width={CELL_W - 16} height={CELL_H - 16} rx={16} fill="none" stroke={INK} strokeWidth={2} opacity={0.25} />
              {Draw ? (
                <>
                  <Copy Draw={Draw} spec={spec} cx={x0 + CELL_W / (2 * copies)} cy={y0 + (CELL_H - 80) / 2 + 10} k={k} act="" />
                  {act && <Copy Draw={Draw} spec={spec} cx={x0 + (3 * CELL_W) / 4} cy={y0 + (CELL_H - 80) / 2 + 10} k={k} act={act} />}
                </>
              ) : (
                <text x={x0 + CELL_W / 2} y={y0 + CELL_H / 2} textAnchor="middle" fontSize={34} fill={RED} style={{ fontFamily: HAND }}>no drawing loaded</text>
              )}
              <text x={x0 + CELL_W / 2} y={y0 + CELL_H - (second ? 52 : 30)} textAnchor="middle" fontSize={28} fill={INK} style={{ fontFamily: HAND }}>
                {label}
              </text>
              {second && (
                <text x={x0 + CELL_W / 2} y={y0 + CELL_H - 20} textAnchor="middle" fontSize={26} fill={INK} style={{ fontFamily: HAND }}>
                  {second}
                </text>
              )}
            </g>
          );
        })}
        <g transform={`translate(110 ${TOP + 4 * CELL_H + 150}) scale(0.4)`}>
          <Ref frame={0} actT={-1} text="" round={ROUND} hand={HAND} />
        </g>
        <text x={110} y={TOP + 4 * CELL_H + 260} textAnchor="middle" fontSize={26} fill={INK} style={{ fontFamily: HAND }}>library phone, 0.4x</text>
        <text x={600} y={TOP + 4 * CELL_H + 40} textAnchor="middle" fontSize={30} fill={INK} style={{ fontFamily: HAND }}>
          {`a bean on stage is ${Math.round(GEOMETRY.beanHalfWidth * 2 * GEOMETRY.beanScale)} px wide and ${Math.round(GEOMETRY.beanHeight * GEOMETRY.beanScale)} px tall`}
        </text>
      </svg>
    </AbsoluteFill>
  );
};
