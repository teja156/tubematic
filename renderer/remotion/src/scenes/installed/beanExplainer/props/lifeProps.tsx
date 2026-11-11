/*
 * Money, health and the body: the everyday objects the style's topics lean on.
 * Each is centred on (0, 0) in its contract.ts box. Whole-prop acts (shake,
 * swing, spin, beat) are applied by the stage; the acts drawn here are the
 * ones that change the drawing itself (a chart growing, steam, sleep marks).
 */
import React from "react";
import {
  BROWN, CREAM, FitText, GREEN, GREY, INK, PINK, RED, Shadow, WHITE, YELLOW, actRamp, ink,
  type PropDrawProps,
} from "./common";

const Coin: React.FC<{ x: number; y: number }> = ({ x, y }) => (
  <g transform={`translate(${x} ${y})`}>
    <ellipse cx={0} cy={10} rx={70} ry={26} fill="#D9A520" {...ink} />
    <ellipse cx={0} cy={0} rx={70} ry={26} fill={YELLOW} {...ink} />
    <ellipse cx={0} cy={0} rx={40} ry={13} fill="none" stroke="#D9A520" strokeWidth={6} />
  </g>
);

export const Coins: React.FC<PropDrawProps> = () => (
  <g>
    {[60, 30, 0, -30].map((y) => <Coin key={y} x={-55} y={y + 20} />)}
    {[60, 30].map((y) => <Coin key={y} x={60} y={y + 20} />)}
    <g transform="translate(70 -60) rotate(-14)">
      <circle cx={0} cy={0} r={52} fill={YELLOW} {...ink} />
      <text x={0} y={22} textAnchor="middle" fontSize={64} fontWeight={700} fill="#B8860B">$</text>
    </g>
  </g>
);

export const Banknote: React.FC<PropDrawProps> = ({ text, round }) => (
  <g>
    <Shadow d="M -190,-95 H 190 V 95 H -190 Z" />
    <rect x={-190} y={-95} width={380} height={190} rx={10} fill="#9ED8A8" {...ink} />
    <rect x={-160} y={-66} width={320} height={132} rx={8} fill="none" stroke={GREEN} strokeWidth={6} />
    <ellipse cx={0} cy={0} rx={50} ry={60} fill="#C8EBCD" stroke={GREEN} strokeWidth={6} />
    <FitText text={text || "$"} x={-110} y={0} width={110} height={90} maxPx={64} maxLines={1} font={round} weight={700} fill="#1E6B3A" />
    <FitText text={text || "$"} x={110} y={0} width={110} height={90} maxPx={64} maxLines={1} font={round} weight={700} fill="#1E6B3A" />
  </g>
);

export const Wallet: React.FC<PropDrawProps> = () => (
  <g>
    <rect x={-120} y={-120} width={200} height={110} rx={10} fill="#9ED8A8" {...ink} transform="rotate(-8)" />
    <rect x={-160} y={-80} width={320} height={200} rx={24} fill={BROWN} {...ink} />
    <path d="M 40,-10 H 160 V 70 H 40 Q 10,70 10,30 Q 10,-10 40,-10 Z" fill="#B88456" {...ink} />
    <circle cx={50} cy={30} r={12} fill={YELLOW} stroke={INK} strokeWidth={5} />
  </g>
);

export const PiggyBank: React.FC<PropDrawProps> = () => (
  <g>
    <path d="M -110,90 L -110,130 M -50,100 L -50,135 M 50,100 L 50,135 M 110,90 L 110,130" stroke={INK} strokeWidth={36} strokeLinecap="round" />
    <path d="M -110,90 L -110,130 M -50,100 L -50,135 M 50,100 L 50,135 M 110,90 L 110,130" stroke={PINK} strokeWidth={20} strokeLinecap="round" />
    <ellipse cx={0} cy={10} rx={165} ry={115} fill={PINK} {...ink} />
    <path d="M -90,-80 L -60,-140 L -30,-94 Z" fill={PINK} {...ink} />
    <ellipse cx={150} cy={20} rx={30} ry={38} fill="#F7C2D0" {...ink} />
    <circle cx={142} cy={10} r={6} fill={INK} />
    <circle cx={156} cy={30} r={6} fill={INK} />
    <circle cx={86} cy={-30} r={9} fill={INK} />
    <rect x={-40} y={-100} width={80} height={14} rx={7} fill={INK} />
    <path d="M -165,0 Q -200,-20 -180,-44 Q -164,-60 -186,-70" fill="none" {...ink} />
  </g>
);

export const CreditCard: React.FC<PropDrawProps> = ({ text, round }) => (
  <g>
    <Shadow d="M -190,-120 H 190 V 120 H -190 Z" />
    <rect x={-190} y={-120} width={380} height={240} rx={22} fill="#3B7DD8" {...ink} />
    <rect x={-190} y={-70} width={380} height={44} fill={INK} />
    <rect x={-150} y={-10} width={60} height={46} rx={8} fill={YELLOW} stroke={INK} strokeWidth={5} />
    <FitText text={text || "1234 5678"} x={-150} y={76} width={300} height={44} maxPx={38} maxLines={1} font={round} weight={600} fill={WHITE} anchor="start" />
  </g>
);

const Chart: React.FC<PropDrawProps & { up: boolean }> = ({ actT, text, round, up }) => {
  const g = actT < 0 ? 1 : actRamp(actT, 18);
  const bars = up ? [0.3, 0.5, 0.7, 0.95] : [0.95, 0.7, 0.5, 0.3];
  const color = up ? GREEN : RED;
  return (
    <g>
      <rect x={-190} y={-160} width={380} height={320} rx={14} fill={WHITE} {...ink} />
      <FitText text={text} y={-118} width={330} height={50} maxPx={40} maxLines={1} font={round} weight={700} />
      {bars.map((h, i) => {
        const bh = 190 * h * g;
        return <rect key={i} x={-150 + i * 80} y={130 - bh} width={56} height={bh} fill={color} stroke={INK} strokeWidth={6} />;
      })}
      <path d="M -165,130 H 165" {...ink} />
      {g > 0.6 && (
        <g transform={`translate(${up ? 120 : -120} ${up ? -70 : -70}) scale(${(g - 0.6) / 0.4})`}>
          <path d={up ? "M -30,30 L 30,-30 M 30,-30 L 0,-30 M 30,-30 L 30,0" : "M 30,30 L -30,-30 M 30,30 L 0,30 M 30,30 L 30,0"}
            stroke={color} strokeWidth={12} strokeLinecap="round" fill="none" />
        </g>
      )}
    </g>
  );
};
export const ChartUp: React.FC<PropDrawProps> = (p) => <Chart {...p} up />;
export const ChartDown: React.FC<PropDrawProps> = (p) => <Chart {...p} up={false} />;

export const Brain: React.FC<PropDrawProps> = ({ actT, frame }) => {
  const spark = actT >= 0 ? 1 : 0;
  return (
    <g>
      <path
        d="M -20,-120 C -60,-150 -120,-130 -130,-90 C -175,-80 -180,-20 -150,10 C -180,50 -150,110 -100,110 C -80,140 -30,140 -10,115 L -10,-110 Z"
        fill="#F7B8C8" {...ink} />
      <path
        d="M 20,-120 C 60,-150 120,-130 130,-90 C 175,-80 180,-20 150,10 C 180,50 150,110 100,110 C 80,140 30,140 10,115 L 10,-110 Z"
        fill="#F7B8C8" {...ink} />
      <path d="M -110,-60 Q -70,-80 -60,-40 M -120,30 Q -80,10 -60,50 M -60,-10 Q -30,-30 -30,10 M 110,-60 Q 70,-80 60,-40 M 120,30 Q 80,10 60,50 M 60,-10 Q 30,-30 30,10"
        fill="none" stroke={INK} strokeWidth={6} strokeLinecap="round" />
      {spark > 0 && [0, 1, 2, 3, 4].map((i) => {
        const a = (i / 5) * Math.PI * 2 + frame / 20;
        const r = 170 + 10 * Math.sin(frame / 3 + i);
        return <path key={i} transform={`translate(${Math.cos(a) * r} ${Math.sin(a) * r * 0.8}) rotate(${(a * 180) / Math.PI + 90})`}
          d="M 0,-16 L 6,-2 L 0,0 L 4,16 L -6,-2 L 0,0 Z" fill={YELLOW} stroke={INK} strokeWidth={4} strokeLinejoin="round" />;
      })}
    </g>
  );
};

export const Heart: React.FC<PropDrawProps> = () => (
  <g>
    <path d="M 0,120 C -80,60 -150,10 -140,-60 C -130,-120 -60,-140 0,-80 C 60,-140 130,-120 140,-60 C 150,10 80,60 0,120 Z" fill={RED} {...ink} />
    <path d="M -96,-62 Q -90,-96 -56,-100" stroke={WHITE} strokeWidth={12} fill="none" strokeLinecap="round" opacity={0.8} />
  </g>
);

export const Stomach: React.FC<PropDrawProps> = () => (
  <g>
    <path d="M -40,-160 C -40,-120 -30,-100 -60,-70 C -130,-10 -120,110 -30,140 C 60,170 130,110 120,40 C 110,-20 40,-20 20,-60 C 10,-90 20,-130 20,-160 Z"
      fill="#F4A6A0" {...ink} />
    <path d="M -60,40 Q -20,60 10,30 M -40,90 Q 10,110 60,70" fill="none" stroke={INK} strokeWidth={6} strokeLinecap="round" />
  </g>
);

export const Pill: React.FC<PropDrawProps> = () => (
  <g transform="rotate(-20)">
    <path d="M 0,-60 H 70 A 60,60 0 0 1 70,60 H 0 Z" fill={WHITE} {...ink} />
    <path d="M 0,-60 H -70 A 60,60 0 0 0 -70,60 H 0 Z" fill={RED} {...ink} />
    <path d="M -86,-30 Q -70,-44 -40,-44" stroke={WHITE} strokeWidth={10} fill="none" strokeLinecap="round" opacity={0.8} />
  </g>
);

export const Coffee: React.FC<PropDrawProps> = ({ actT, frame }) => {
  const steam = actT >= 0 ? 1 : 0.4;
  return (
    <g>
      {[-40, 0, 40].map((x, i) => (
        <path key={x} d={`M ${x},-90 Q ${x + 20},-110 ${x},-130 Q ${x - 20},-150 ${x},-170`} fill="none" stroke={INK} strokeWidth={7} strokeLinecap="round"
          opacity={steam * (0.5 + 0.5 * Math.sin(frame / 6 + i))} transform={`translate(0 ${-((frame / 2 + i * 8) % 16)})`} />
      ))}
      <path d="M 90,-30 C 150,-30 150,60 80,70" fill="none" stroke={INK} strokeWidth={36} strokeLinecap="round" />
      <path d="M 90,-30 C 150,-30 150,60 80,70" fill="none" stroke={WHITE} strokeWidth={20} strokeLinecap="round" />
      <path d="M -110,-70 H 110 L 90,140 Q 88,160 68,160 H -68 Q -88,160 -90,140 Z" fill={WHITE} {...ink} />
      <ellipse cx={0} cy={-70} rx={110} ry={20} fill={BROWN} {...ink} />
      <rect x={-102} y={10} width={204} height={50} fill={RED} opacity={0.85} />
    </g>
  );
};

export const Water: React.FC<PropDrawProps> = ({ actT }) => {
  const level = actT < 0 ? 0.7 : 0.2 + 0.6 * actRamp(actT, 24);
  const top = 150 - 280 * level;
  return (
    <g>
      <path d={`M -80,${top} H 80 L 66,150 H -66 Z`} fill="#8FD0F2" />
      <path d="M -96,-150 H 96 L 72,160 H -72 Z" fill={WHITE} fillOpacity={0.35} {...ink} />
      <path d="M -60,-110 L -50,100" stroke={WHITE} strokeWidth={12} strokeLinecap="round" opacity={0.8} />
    </g>
  );
};

export const Bed: React.FC<PropDrawProps> = ({ actT, frame, round }) => {
  const z = actT >= 0;
  return (
    <g>
      <rect x={-240} y={-120} width={40} height={250} rx={10} fill={BROWN} {...ink} />
      <rect x={200} y={-40} width={40} height={170} rx={10} fill={BROWN} {...ink} />
      <rect x={-210} y={0} width={420} height={80} rx={14} fill={WHITE} {...ink} />
      <path d="M -60,-10 H 210 V 60 Q 70,90 -60,60 Z" fill="#7EA9E6" {...ink} />
      <ellipse cx={-130} cy={-10} rx={70} ry={34} fill={CREAM} {...ink} />
      {z && ["Z", "z", "z"].map((c, i) => {
        const t = ((frame + i * 14) % 42) / 42;
        return <text key={i} x={-110 + i * 46 + t * 30} y={-50 - i * 34 - t * 40} fontSize={76 - i * 12} fontWeight={700} fill={INK}
          opacity={Math.min(1, 1.6 * (1 - t))} style={{ fontFamily: round }}>{c}</text>;
      })}
    </g>
  );
};

export const Dumbbell: React.FC<PropDrawProps> = () => (
  <g>
    <rect x={-120} y={-14} width={240} height={28} rx={10} fill={GREY} {...ink} />
    {[-1, 1].map((s) => (
      <g key={s}>
        <rect x={s > 0 ? 110 : -170} y={-70} width={60} height={140} rx={14} fill={INK} />
        <rect x={s > 0 ? 160 : -200} y={-50} width={40} height={100} rx={12} fill={INK} />
      </g>
    ))}
  </g>
);

export const Apple: React.FC<PropDrawProps> = () => (
  <g>
    <path d="M 0,-80 C -20,-120 -60,-110 -60,-110" fill="none" {...ink} />
    <path d="M 6,-84 C 30,-130 80,-120 90,-110 C 70,-80 30,-74 6,-84 Z" fill={GREEN} {...ink} />
    <path d="M 0,-70 C -60,-110 -130,-80 -120,10 C -110,90 -50,130 0,110 C 50,130 110,90 120,10 C 130,-80 60,-110 0,-70 Z" fill={RED} {...ink} />
    <path d="M -80,-30 Q -86,-60 -60,-70" stroke={WHITE} strokeWidth={12} fill="none" strokeLinecap="round" opacity={0.8} />
  </g>
);

