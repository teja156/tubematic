// A smoke alarm, drawn for one video: an object the library lacks, modelled on
// the library's objects. Centred on (0, 0) inside a 260 x 260 box. Its "beep"
// act lights the lamp and sends three sound arcs out over 20 frames, then holds.
// {"id": "alarm", "w": 260, "h": 260, "acts": ["beep"]}
import React from "react";
import { CORAL, CREAM, Cel, INK, MUSTARD, actProgress, ellP, type ObjectDrawProps } from "../../installed/midcenturyHowTo/cel";

export default function SmokeAlarm({ phase, act, actT }: ObjectDrawProps) {
  const k = act === "beep" ? actProgress(actT) : 0;
  return (
    <g>
      <Cel d={ellP(0, 0, 96, 96)} fill={CREAM} phase={phase} seed={501} sw={5} />
      <Cel d={ellP(0, 0, 62, 62)} fill={CREAM} phase={phase} seed={502} sw={4} broken={false} />
      {[-30, -10, 10, 30].map((x) => (
        <rect key={x} x={x - 4} y={-22} width={8} height={44} rx={4} fill={INK} opacity={0.6} />
      ))}
      <Cel d={ellP(52, -52, 14, 14)} fill={k > 0 ? CORAL : MUSTARD} phase={phase} seed={503} sw={3.5} broken={false} />
      {k > 0 &&
        [0, 1, 2].map((i) => {
          const r = 104 + i * 10 * k;
          return <path key={i} d={`M ${r * 0.7} ${-r * 0.7} A ${r} ${r} 0 0 1 ${r * 0.7} ${r * 0.7}`} stroke={CORAL} strokeWidth={6} fill="none" strokeLinecap="round" opacity={k} />;
        })}
    </g>
  );
}
