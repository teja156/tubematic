/*
 * The book's frame and its chapter plaque.
 *
 * The frame (a dark edge band, a thin grey rule inside it and a soft
 * vignette) is drawn into each backdrop's bitmap, never as a layer of its own.
 * There is no paper grain: on the CPU renderer a frame costs in proportion to
 * how much fine detail it holds (every frame is screenshotted and encoded),
 * and noise grain over the hatching cost about 0.18 CPU-seconds per frame on
 * its own. Measured in StorybookAtlas.tsx's header comment.
 *
 * The plaque's plate and seal are bitmaps; its numeral, title and byline are
 * HTML, so the text-layout audit can measure them and the title can type on.
 */
import React from "react";
import { Easing, interpolate } from "remotion";
import { Bitmap, type Drawing } from "./bitmap";
import { PEN } from "./ink";
import { BANDS, CREAM, H, INK, PINK, RULE, SEAL, SEAL_DARK, SERIF, TEXT, W } from "./palette";

/** The vignette and double-rule frame, drawn over a backdrop inside the backdrop's own bitmap. */
export const FrameInk: React.FC = () => (
      <g>
        <defs>
          <radialGradient id="vig" cx="50%" cy="48%" r="75%">
            <stop offset="62%" stopColor="#6b5a46" stopOpacity={0} />
            <stop offset="100%" stopColor="#6b5a46" stopOpacity={0.3} />
          </radialGradient>
        </defs>
        <rect width={W} height={H} fill="url(#vig)" />
        <rect x={3.25} y={3.25} width={W - 6.5} height={H - 6.5} fill="none" stroke={INK} strokeWidth={6.5} />
        <rect x={BANDS.frameInset} y={BANDS.frameInset} width={W - 2 * BANDS.frameInset} height={H - 2 * BANDS.frameInset}
          fill="none" stroke={RULE} strokeWidth={2.2} />
      </g>
);

/** Roman numerals for chapters 1 to 5. */
export const NUMERALS = ["I", "II", "III", "IV", "V"] as const;

/** Plaque geometry: centred in the plaque band. */
export const PLAQUE = { x: 200, y: 236, w: 640, h: 160, numW: 130 } as const;
/** Characters per frame the title types at, and the frames each part waits. */
export const PLAQUE_TIMING = { drop: 6, typeDelay: 2, typeRate: 2.2, bylineFade: 5, sealDelay: 7, sealPop: 9 } as const;

function plateDrawing(): Drawing {
  const { w, h, numW } = PLAQUE;
  return {
    key: "plaque-plate",
    width: w + 12,
    height: h + 12,
    render: () => (
      <g>
        <rect x={6} y={8} width={w} height={h} fill={INK} opacity={0.18} />
        <rect x={1.5} y={1.5} width={w} height={h} fill={CREAM} stroke={INK} strokeWidth={3} />
        <rect x={10.5} y={10.5} width={numW} height={h - 18} fill={PINK} />
        <rect x={10.5} y={10.5} width={numW} height={h - 18} fill={`url(#${PEN})`} opacity={0.18} />
        <rect x={10.5} y={10.5} width={w - 18} height={h - 18} fill="none" stroke={INK} strokeWidth={1.6} />
        <line x1={10.5 + numW} y1={10.5} x2={10.5 + numW} y2={h - 7.5} stroke={INK} strokeWidth={1.6} />
      </g>
    ),
  };
}

function sealDrawing(): Drawing {
  return {
    key: "plaque-seal",
    width: 80,
    height: 80,
    render: () => (
      <g transform="translate(40 40)">
        <path d="M-30 2 Q-31 -24 -6 -30 Q20 -33 29 -10 Q35 12 18 25 Q-2 36 -20 25 Q-32 16 -30 2Z" fill={SEAL} stroke={SEAL_DARK} strokeWidth={2} />
        <circle r={18} fill="none" stroke="#B35A4E" strokeWidth={2.2} />
        <circle r={9} fill="none" stroke="#E9C9BC" strokeWidth={2.2} />
        <circle r={2.6} fill="#E9C9BC" />
      </g>
    ),
  };
}

const PLATE = plateDrawing();
const SEAL_D = sealDrawing();

/** The frame at which the plaque has fully arrived (title typed, byline in, seal settled). */
export function plaqueSettledAt(title: string): number {
  const t = PLAQUE_TIMING;
  return t.typeDelay + Math.ceil(title.length / t.typeRate) + t.sealDelay + t.sealPop;
}

/** The chapter plaque, `t` frames after its chapter began; `out` fades it (0..1 remaining). */
export const Plaque: React.FC<{ t: number; numeral: string; title: string; byline: string; out?: number }> = ({
  t, numeral, title, byline, out = 1,
}) => {
  const T = PLAQUE_TIMING;
  const drop = interpolate(t, [0, T.drop], [-20, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.bezier(0.2, 0.8, 0.3, 1) });
  const op = interpolate(t, [0, 4], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) * out;
  const typed = Math.max(0, Math.floor((t - T.typeDelay) * T.typeRate));
  const typeEnd = T.typeDelay + Math.ceil(title.length / T.typeRate);
  const bylineOp = interpolate(t, [typeEnd, typeEnd + T.bylineFade], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const sealT = t - (typeEnd + T.sealDelay);
  const seal = interpolate(sealT, [0, 4, 7, T.sealPop], [0, 1.08, 0.98, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  if (op <= 0) return null;
  const { x, y, w, h, numW } = PLAQUE;
  return (
    <div style={{ position: "absolute", left: 0, top: 0, width: W, height: BANDS.plaqueBottom, opacity: op, transform: drop ? `translateY(${drop}px)` : undefined }}>
      <Bitmap d={PLATE} left={x - 1.5} top={y - 1.5} />
      {seal > 0 && <Bitmap d={SEAL_D} left={x + w + 8} top={y - 4} transform={seal === 1 ? undefined : `scale(${seal})`} origin={[40, 40]} />}
      <div style={{
        position: "absolute", left: x + 9, top: y + 9, width: numW, height: h - 18, display: "flex",
        alignItems: "center", justifyContent: "center", fontFamily: SERIF, fontSize: 66, color: TEXT,
      }}>{numeral}</div>
      <div style={{
        position: "absolute", left: x + 9 + numW, top: y + 12, width: w - 18 - numW, height: h - 24, display: "flex",
        flexDirection: "column", alignItems: "center", justifyContent: "center", fontFamily: SERIF, color: TEXT, textAlign: "center",
      }}>
        <div style={{ fontSize: 54, lineHeight: 1.02, fontWeight: 500 }}>{title.slice(0, typed) || " "}</div>
        <div style={{ fontSize: 36, fontStyle: "italic", lineHeight: 1.15, opacity: bylineOp, color: "#4E4136" }}>{byline}</div>
      </div>
    </div>
  );
};
