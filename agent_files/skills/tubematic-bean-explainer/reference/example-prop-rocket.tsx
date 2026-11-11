// A custom Bean Explainer prop: a rocket, which the library does not have.
// Written to generated/<video_id>/prop-rocket.tsx with write_scene_file, and
// listed in the config's customProps as
//   {"id": "rocket", "src": "<video_id>/prop-rocket", "w": 220, "h": 530, "acts": ["launch"]}
//
// Modelled on the library props (read them with read_scene_file, source
// "installed", e.g. "beanExplainer/props/thingProps"): centred on (0, 0) inside
// its w x h box at scale 1, the bean's ink line (`ink` = 8 px, round joins),
// flat fills from the shared palette, no filters, gradients or dashes. `actT` is
// the frames since its act started (-1 before); the act here is drawn by the
// prop itself (flames and a lift), so it is not one of the whole-prop acts.
import { BLUE, GREY, INK, ORANGE, RED, WHITE, YELLOW, actRamp, ink, type PropDrawProps } from "../../installed/beanExplainer/props/common";

export default function Rocket({ actT, frame }: PropDrawProps) {
  const lift = actRamp(actT, 40);
  const flicker = actT >= 0 ? 0.85 + 0.15 * Math.sin(frame * 1.7) : 0;
  return (
    <g transform={`translate(0 ${-60 * lift})`}>
      {flicker > 0 && (
        <g transform={`translate(0 140) scale(1 ${flicker})`}>
          <path d="M -40,0 Q 0,120 40,0 Z" fill={ORANGE} {...ink} />
          <path d="M -20,0 Q 0,70 20,0 Z" fill={YELLOW} />
        </g>
      )}
      <path d="M -60,60 L -100,140 L -50,120 Z" fill={RED} {...ink} />
      <path d="M 60,60 L 100,140 L 50,120 Z" fill={RED} {...ink} />
      <path d="M 0,-190 C 70,-130 70,60 50,140 L -50,140 C -70,60 -70,-130 0,-190 Z" fill={WHITE} {...ink} />
      <path d="M 0,-190 C 30,-165 46,-140 54,-110 L -54,-110 C -46,-140 -30,-165 0,-190 Z" fill={RED} {...ink} />
      <circle cx={0} cy={-30} r={30} fill={BLUE} stroke={INK} strokeWidth={8} />
      <circle cx={-8} cy={-38} r={8} fill={WHITE} opacity={0.8} />
      <rect x={-36} y={100} width={72} height={18} rx={6} fill={GREY} stroke={INK} strokeWidth={6} />
    </g>
  );
}
