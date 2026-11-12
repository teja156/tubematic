/*
 * Tech, time and feeling props. Each is centred on (0, 0) in its contract.ts
 * box; the acts drawn here change the drawing (a lock opening, a bulb lighting,
 * rain falling), the whole-prop ones are applied by the stage.
 */
import React from "react";
import {
  BLUE, CREAM, DARK, GREEN, GREY, INK, RED, Shadow, Vibration, WHITE, YELLOW, actRamp, ink,
  type PropDrawProps,
} from "./common";

export const Lock: React.FC<PropDrawProps> = ({ actT }) => {
  const open = actRamp(actT, 8);
  return (
    <g>
      <path d={`M -70,-20 V -80 A 70,70 0 0 1 70,-80 V ${-20 - 60 * open}`} transform={`translate(0 ${-40 * open})`}
        fill="none" stroke={INK} strokeWidth={44} strokeLinecap="round" />
      <path d={`M -70,-20 V -80 A 70,70 0 0 1 70,-80 V ${-20 - 60 * open}`} transform={`translate(0 ${-40 * open})`}
        fill="none" stroke={GREY} strokeWidth={26} strokeLinecap="round" />
      <rect x={-120} y={-30} width={240} height={190} rx={26} fill={YELLOW} {...ink} />
      <circle cx={0} cy={50} r={22} fill={INK} />
      <path d="M -8,60 L -12,110 H 12 L 8,60 Z" fill={INK} />
    </g>
  );
};

export const Key: React.FC<PropDrawProps> = () => (
  <g transform="rotate(-20)">
    <path d="M -40,-18 H 160 V 18 H 140 V 52 H 110 V 18 H 90 V 44 H 64 V 18 H -40 Z" fill={YELLOW} {...ink} />
    <circle cx={-90} cy={0} r={70} fill={YELLOW} {...ink} />
    <circle cx={-100} cy={0} r={22} fill={CREAM} {...ink} />
  </g>
);

export const Server: React.FC<PropDrawProps> = ({ actT, frame }) => {
  const flash = actT >= 0 && actT < 24;
  return (
    <g>
      <Shadow d="M -150,-190 H 150 V 190 H -150 Z" />
      {[-190, -63, 64].map((y, i) => (
        <g key={y}>
          <rect x={-150} y={y} width={300} height={126} rx={16} fill={DARK} {...ink} />
          <rect x={-110} y={y + 50} width={140} height={24} rx={8} fill="#555" />
          <circle cx={80} cy={y + 62} r={13} fill={flash ? (Math.floor(frame / 3) % 2 ? RED : YELLOW) : i === 1 ? GREEN : "#7EE29A"} stroke={INK} strokeWidth={4} />
          <circle cx={115} cy={y + 62} r={13} fill={GREEN} stroke={INK} strokeWidth={4} />
        </g>
      ))}
    </g>
  );
};

export const Wifi: React.FC<PropDrawProps> = ({ actT, frame }) => {
  const on = actT >= 0;
  const lit = (i: number) => (on ? (Math.floor(frame / 5) % 4 > i ? 1 : 0.25) : 1);
  return (
    <g transform="translate(0 40)">
      <circle cx={0} cy={60} r={24} fill={INK} />
      {[1, 2, 3].map((i) => (
        <path key={i} d={`M ${-i * 52},${60 - i * 40} A ${i * 70},${i * 70} 0 0 1 ${i * 52},${60 - i * 40}`}
          fill="none" stroke={INK} strokeWidth={26} strokeLinecap="round" opacity={lit(i - 1)} />
      ))}
    </g>
  );
};

export const Bug: React.FC<PropDrawProps> = () => (
  <g>
    {[-1, 1].map((s) => (
      <g key={s} fill="none" stroke={INK} strokeWidth={10} strokeLinecap="round">
        <path d={`M ${s * 60},-20 L ${s * 130},-60`} />
        <path d={`M ${s * 70},20 L ${s * 136},20`} />
        <path d={`M ${s * 60},60 L ${s * 124},104`} />
        <path d={`M ${s * 20},-100 Q ${s * 40},-140 ${s * 70},-130`} />
      </g>
    ))}
    <ellipse cx={0} cy={20} rx={84} ry={104} fill={GREEN} {...ink} />
    <path d="M 0,-80 V 120" stroke={INK} strokeWidth={6} />
    <circle cx={0} cy={-90} r={50} fill={DARK} {...ink} />
    <circle cx={-20} cy={-96} r={12} fill={WHITE} />
    <circle cx={20} cy={-96} r={12} fill={WHITE} />
    {[[-40, 0], [40, 40], [-30, 70]].map(([x, y], i) => <circle key={i} cx={x} cy={y} r={14} fill="#1E6B3A" />)}
  </g>
);

export const Shield: React.FC<PropDrawProps> = ({ actT }) => {
  const flash = actT >= 0 && actT < 20 && Math.floor(actT / 4) % 2 === 0;
  return (
    <g>
      <path d="M 0,-160 L 130,-110 C 130,20 90,110 0,160 C -90,110 -130,20 -130,-110 Z" fill={flash ? WHITE : BLUE} {...ink} />
      <path d="M 0,-120 L 92,-84 C 92,10 64,80 0,118 Z" fill="#2E63B0" opacity={0.6} />
      <path d="M -50,0 L -12,40 L 60,-44" fill="none" stroke={WHITE} strokeWidth={22} strokeLinecap="round" strokeLinejoin="round" />
    </g>
  );
};

export const Cursor: React.FC<PropDrawProps> = ({ actT }) => {
  const press = actT >= 0 && actT < 8 ? 0.85 : 1;
  const ring = actT >= 0 ? actRamp(actT, 14) : 0;
  return (
    <g>
      {ring > 0 && ring < 1 && <circle cx={-56} cy={-96} r={20 + 60 * ring} fill="none" stroke={INK} strokeWidth={7} opacity={1 - ring} />}
      <g transform={`translate(-56 -96) scale(${press}) translate(56 96)`}>
        <path d="M -56,-96 L 64,24 L 10,28 L 40,92 L 10,104 L -18,40 L -56,76 Z" fill={WHITE} {...ink} />
      </g>
    </g>
  );
};

export const Clock: React.FC<PropDrawProps> = ({ actT, frame }) => {
  const ringing = actT >= 0 ? 1 : 0;
  const rattle = ringing ? Math.sin(frame * 2.1) * 5 : 0;
  return (
    <g transform="translate(0 30)">
      <Vibration hw={120} y={-60} on={ringing} />
      <g transform={`rotate(${rattle} 0 -40)`}>
        <path d="M -76,90 L -96,124 M 76,90 L 96,124" stroke={INK} strokeWidth={LINE_W} strokeLinecap="round" />
        <path d="M -90,-110 A 40,40 0 0 1 -30,-150 Z" fill={YELLOW} {...ink} />
        <path d="M 90,-110 A 40,40 0 0 0 30,-150 Z" fill={YELLOW} {...ink} />
        <circle cx={0} cy={-10} r={112} fill={RED} {...ink} />
        <circle cx={0} cy={-10} r={82} fill={CREAM} stroke={INK} strokeWidth={6} />
        <path d="M 0,-10 L 0,-62 M 0,-10 L 38,12" stroke={INK} strokeWidth={9} strokeLinecap="round" />
        <circle cx={0} cy={-10} r={8} fill={INK} />
      </g>
    </g>
  );
};
const LINE_W = 12;

export const Hourglass: React.FC<PropDrawProps> = ({ frame }) => {
  const t = (frame % 150) / 150;
  return (
    <g>
      <rect x={-110} y={-170} width={220} height={30} rx={10} fill={BROWN_DARK} {...ink} />
      <rect x={-110} y={140} width={220} height={30} rx={10} fill={BROWN_DARK} {...ink} />
      <path d="M -80,-140 H 80 C 80,-60 20,-20 20,0 C 20,20 80,60 80,140 H -80 C -80,60 -20,20 -20,0 C -20,-20 -80,-60 -80,-140 Z" fill={WHITE} fillOpacity={0.5} {...ink} />
      <path d={`M ${-60 + 40 * t},${-110 + 90 * t} H ${60 - 40 * t} L 6,-10 H -6 Z`} fill={YELLOW} />
      <path d={`M -64,130 H 64 C 50,${120 - 70 * t} 20,${110 - 80 * t} 0,${104 - 80 * t} C -20,${110 - 80 * t} -50,${120 - 70 * t} -64,130 Z`} fill={YELLOW} />
      <path d="M 0,-8 V 120" stroke={YELLOW} strokeWidth={5} />
    </g>
  );
};
const BROWN_DARK = "#9B6A43";

const Gear: React.FC<{ r: number; teeth: number; angle: number; fill: string }> = ({ r, teeth, angle, fill }) => {
  const pts: string[] = [];
  for (let i = 0; i < teeth * 4; i++) {
    const a = (i / (teeth * 4)) * Math.PI * 2;
    const rr = i % 4 < 2 ? r : r * 0.8;
    pts.push(`${(Math.cos(a) * rr).toFixed(1)},${(Math.sin(a) * rr).toFixed(1)}`);
  }
  return (
    <g transform={`rotate(${angle})`}>
      <polygon points={pts.join(" ")} fill={fill} {...ink} />
      <circle cx={0} cy={0} r={r * 0.32} fill={CREAM} {...ink} />
    </g>
  );
};

export const Gears: React.FC<PropDrawProps> = ({ actT, frame }) => {
  const speed = actT >= 0 ? 4 : 1.2;
  const a = frame * speed;
  return (
    <g>
      <g transform="translate(-60 20)"><Gear r={105} teeth={10} angle={a} fill={GREY} /></g>
      <g transform="translate(100 -60)"><Gear r={70} teeth={7} angle={-a * 1.5 + 12} fill="#F08A24" /></g>
    </g>
  );
};

export const Bulb: React.FC<PropDrawProps> = ({ actT }) => {
  const lit = actRamp(actT, 4);
  return (
    <g>
      {lit > 0 && [-60, -30, 0, 30, 60].map((a) => (
        <path key={a} transform={`rotate(${a}) translate(0 ${-150 - 10 * lit})`} d="M 0,0 L 0,-28" stroke={INK} strokeWidth={9} strokeLinecap="round" opacity={lit} />
      ))}
      <path d="M -50,60 C -100,10 -100,-110 0,-115 C 100,-110 100,10 50,60 L 44,100 H -44 Z" fill={lit > 0 ? YELLOW : "#F3F1E2"} {...ink} />
      <path d="M -20,90 L -20,40 Q 0,10 20,40 L 20,90" fill="none" stroke={INK} strokeWidth={5} />
      <rect x={-48} y={100} width={96} height={56} rx={10} fill={GREY} {...ink} />
      <path d="M -48,120 H 48 M -48,138 H 48" stroke={INK} strokeWidth={5} />
    </g>
  );
};

export const Cloud: React.FC<PropDrawProps> = ({ actT, frame }) => {
  const rain = actT >= 0;
  return (
    <g>
      {rain && [-120, -60, 0, 60, 120].map((x, i) => {
        const y = 40 + ((frame * 9 + i * 23) % 90);
        return <path key={x} d={`M ${x},${y} q -8,22 0,30`} stroke="#5AA9E6" strokeWidth={10} strokeLinecap="round" fill="none" />;
      })}
      <path d="M -150,40 C -210,40 -210,-40 -150,-50 C -150,-120 -60,-140 -30,-90 C 0,-150 110,-140 110,-60 C 190,-70 200,40 140,40 Z" fill="#B8C2CC" {...ink} />
    </g>
  );
};

export const Trophy: React.FC<PropDrawProps> = ({ actT, frame }) => (
  <g>
    {actT >= 0 && [0, 1, 2, 3].map((i) => {
      const a = i * 1.6 + frame / 12;
      return <path key={i} transform={`translate(${Math.cos(a) * 150} ${-60 + Math.sin(a) * 100}) scale(${0.7 + 0.3 * Math.sin(frame / 4 + i)})`}
        d="M 0,-24 Q 3,-3 24,0 Q 3,3 0,24 Q -3,3 -24,0 Q -3,-3 0,-24 Z" fill={WHITE} stroke={INK} strokeWidth={5} />;
    })}
    <path d="M -80,-130 C -150,-130 -150,-30 -70,-20 M 80,-130 C 150,-130 150,-30 70,-20" fill="none" stroke={INK} strokeWidth={30} strokeLinecap="round" />
    <path d="M -80,-130 C -150,-130 -150,-30 -70,-20 M 80,-130 C 150,-130 150,-30 70,-20" fill="none" stroke={YELLOW} strokeWidth={14} strokeLinecap="round" />
    <path d="M -95,-160 H 95 V -90 C 95,0 40,30 0,30 C -40,30 -95,0 -95,-90 Z" fill={YELLOW} {...ink} />
    <rect x={-22} y={30} width={44} height={60} fill="#D9A520" {...ink} />
    <rect x={-80} y={90} width={160} height={60} rx={8} fill={BROWN_DARK} {...ink} />
  </g>
);

export const Bomb: React.FC<PropDrawProps> = ({ frame }) => (
  <g transform="translate(0 30)">
    <path d="M 50,-100 Q 80,-150 120,-130" fill="none" stroke={BROWN_DARK} strokeWidth={10} strokeLinecap="round" />
    {[0, 1, 2].map((i) => {
      const a = frame * 0.9 + i * 2.1;
      return <path key={i} transform={`translate(${126 + Math.cos(a) * 18} ${-136 + Math.sin(a) * 18})`} d="M 0,-12 L 3,-3 L 12,0 L 3,3 L 0,12 L -3,3 L -12,0 L -3,-3 Z" fill={YELLOW} stroke={RED} strokeWidth={3} />;
    })}
    <rect x={20} y={-110} width={50} height={40} rx={8} fill={GREY} {...ink} transform="rotate(30 45 -90)" />
    <circle cx={0} cy={10} r={120} fill={DARK} {...ink} />
    <path d="M -70,-30 Q -60,-70 -20,-80" stroke={WHITE} strokeWidth={14} fill="none" strokeLinecap="round" opacity={0.7} />
  </g>
);

export const Magnifier: React.FC<PropDrawProps> = () => (
  <g transform="rotate(-30)">
    <path d="M 0,100 L 0,170" stroke={INK} strokeWidth={48} strokeLinecap="round" />
    <path d="M 0,104 L 0,166" stroke="#B5442B" strokeWidth={30} strokeLinecap="round" />
    <circle cx={0} cy={-20} r={110} fill="#CDEBFF" fillOpacity={0.5} stroke={INK} strokeWidth={16} />
    <circle cx={0} cy={-20} r={100} fill="none" stroke={GREY} strokeWidth={5} />
    <path d="M -64,-56 A 74,74 0 0 1 -24,-90" stroke={WHITE} strokeWidth={12} fill="none" strokeLinecap="round" />
  </g>
);
