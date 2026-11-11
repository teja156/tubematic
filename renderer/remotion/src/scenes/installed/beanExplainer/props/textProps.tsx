/*
 * Props that carry the agent's words: a message on a phone, an address in a
 * browser bar, a note, a sign. The text slot is the only thing the agent sets;
 * the drawing is fixed. Each is centred on (0, 0) in its contract.ts box.
 */
import React from "react";
import {
  BLUE, CREAM, DARK, FitText, GREY, INK, PAPER, RED, Shadow, Vibration, WHITE, YELLOW, actRamp, ink,
  type PropDrawProps,
} from "./common";

export const Phone: React.FC<PropDrawProps> = ({ actT, text, round }) => {
  const buzz = actT >= 0 && actT < 24 ? 1 : 0;
  return (
    <g>
      <Vibration hw={120} y={-40} on={buzz} />
      <rect x={-120} y={-210} width={240} height={420} rx={36} fill={DARK} {...ink} />
      <rect x={-106} y={-196} width={212} height={392} rx={26} fill="#F6F8FF" />
      <rect x={-30} y={-186} width={60} height={14} rx={7} fill={DARK} />
      <text x={0} y={-128} textAnchor="middle" fontSize={40} fontWeight={600} fill={INK} style={{ fontFamily: round }}>9:41</text>
      {text && (
        <g>
          <rect x={-94} y={-96} width={188} height={170} rx={18} fill={WHITE} stroke={INK} strokeWidth={6} />
          <circle cx={-70} cy={-72} r={14} fill={RED} stroke={INK} strokeWidth={4} />
          <FitText text={text} y={4} width={164} height={110} maxPx={34} maxLines={3} font={round} weight={600} />
        </g>
      )}
      <rect x={-80} y={130} width={160} height={40} rx={20} fill={BLUE} stroke={INK} strokeWidth={5} />
    </g>
  );
};

export const Browser: React.FC<PropDrawProps> = ({ actT, text, round }) => {
  const flash = actT >= 0 && actT < 20 && Math.floor(actT / 4) % 2 === 0;
  return (
    <g>
      <rect x={-310} y={-57} width={620} height={130} rx={65} fill={INK} opacity={0.16} />
      <rect x={-310} y={-65} width={620} height={130} rx={65} fill={flash ? "#FFE1DE" : WHITE} {...ink} />
      <g transform="translate(-232 4)">
        <path d="M -14,-10 L -14,-22 A 14,14 0 0 1 14,-22 L 14,-10" fill="none" stroke={INK} strokeWidth={7} />
        <rect x={-22} y={-12} width={44} height={36} rx={8} fill={GREY} stroke={INK} strokeWidth={6} />
      </g>
      <FitText text={text} x={-180} y={0} width={450} height={80} maxPx={56} maxLines={1} font={round} weight={600} anchor="start" />
    </g>
  );
};

export const Laptop: React.FC<PropDrawProps> = ({ actT, text, round }) => {
  const flash = actT >= 0 && actT < 20 && Math.floor(actT / 4) % 2 === 0;
  return (
    <g>
      <rect x={-180} y={-160} width={360} height={250} rx={18} fill={DARK} {...ink} />
      <rect x={-162} y={-142} width={324} height={214} rx={8} fill={flash ? "#FFE1DE" : "#EAF4FF"} />
      <FitText text={text} y={-36} width={290} height={170} maxPx={44} maxLines={3} font={round} weight={600} />
      <path d="M -220,96 L 220,96 L 196,140 L -196,140 Z" fill={GREY} {...ink} />
      <rect x={-40} y={100} width={80} height={12} rx={6} fill={DARK} />
    </g>
  );
};

export const Sign: React.FC<PropDrawProps> = ({ text, hand }) => (
  <g>
    <rect x={-14} y={0} width={28} height={165} fill="#B07A4E" {...ink} />
    <Shadow d="M -190,-165 H 190 V 40 H -190 Z" />
    <rect x={-190} y={-165} width={380} height={205} rx={14} fill={YELLOW} {...ink} />
    <rect x={-172} y={-147} width={344} height={169} rx={8} fill="none" stroke={INK} strokeWidth={4} />
    <FitText text={text} y={-62} width={320} height={150} maxPx={64} maxLines={2} font={hand} weight={400} />
  </g>
);

export const Document: React.FC<PropDrawProps> = ({ actT, text, hand, round }) => {
  const stamp = actRamp(actT, 6);
  return (
    <g>
      <Shadow d="M -150,-195 H 100 L 150,-145 V 195 H -150 Z" />
      <path d="M -150,-195 H 100 L 150,-145 V 195 H -150 Z" fill={PAPER} {...ink} />
      <path d="M 100,-195 V -145 H 150" fill="none" {...ink} />
      <FitText text={text} y={-120} width={240} height={70} maxPx={46} maxLines={2} font={round} weight={700} />
      {[-40, 0, 40, 80, 120].map((y) => (
        <path key={y} d={`M -110,${y} H ${y === 120 ? 30 : 110}`} stroke={GREY} strokeWidth={8} strokeLinecap="round" />
      ))}
      {stamp > 0 && (
        <g transform={`translate(40 90) rotate(-14) scale(${1.6 - 0.6 * stamp})`} opacity={stamp}>
          <rect x={-86} y={-34} width={172} height={68} rx={10} fill="none" stroke={RED} strokeWidth={9} />
          <text x={0} y={16} textAnchor="middle" fontSize={44} fontWeight={700} fill={RED} style={{ fontFamily: hand }}>STAMPED</text>
        </g>
      )}
    </g>
  );
};

export const Note: React.FC<PropDrawProps> = ({ text, hand }) => (
  <g transform="rotate(-3)">
    <Shadow d="M -135,-135 H 135 V 135 H -135 Z" />
    <rect x={-135} y={-135} width={270} height={270} fill="#FFF07A" {...ink} />
    <rect x={-50} y={-150} width={100} height={34} fill="#FFFFFF" opacity={0.7} transform="rotate(4)" />
    <FitText text={text} y={6} width={220} height={210} maxPx={48} maxLines={4} font={hand} weight={400} />
  </g>
);

export const Speech: React.FC<PropDrawProps> = ({ text, round }) => (
  <g>
    <path d="M -200,-125 H 200 Q 220,-125 220,-105 V 55 Q 220,75 200,75 H -60 L -130,125 L -110,75 H -200 Q -220,75 -220,55 V -105 Q -220,-125 -200,-125 Z" fill={WHITE} {...ink} />
    <FitText text={text} y={-25} width={390} height={170} maxPx={50} maxLines={3} font={round} weight={600} />
  </g>
);

export const Thought: React.FC<PropDrawProps> = ({ text, hand }) => (
  <g>
    <path
      d="M -150,-60 C -230,-60 -230,40 -160,46 C -170,96 -90,110 -60,80 C -30,120 50,118 70,80 C 120,110 200,80 180,30 C 236,10 230,-80 160,-86 C 160,-140 80,-150 50,-112 C 20,-150 -60,-150 -80,-104 C -130,-120 -170,-90 -150,-60 Z"
      fill={WHITE} {...ink} />
    <circle cx={-150} cy={106} r={20} fill={WHITE} {...ink} />
    <circle cx={-186} cy={134} r={11} fill={WHITE} stroke={INK} strokeWidth={6} />
    <FitText text={text} y={-14} width={330} height={150} maxPx={48} maxLines={3} font={hand} weight={400} />
  </g>
);

export const PriceTag: React.FC<PropDrawProps> = ({ text, round }) => (
  <g>
    <path d="M -160,-55 L -100,-95 H 160 V 95 H -100 L -160,55 Z" fill={CREAM} {...ink} />
    <circle cx={-108} cy={0} r={14} fill="#F9D648" stroke={INK} strokeWidth={6} />
    <FitText text={text} x={30} y={0} width={230} height={120} maxPx={84} maxLines={1} font={round} weight={700} />
  </g>
);

export const Calendar: React.FC<PropDrawProps> = ({ actT, text, round }) => {
  const flip = actT >= 0 && actT < 12 ? Math.cos((actT / 12) * Math.PI) : 1;
  return (
    <g>
      <Shadow d="M -150,-130 H 150 V 160 H -150 Z" />
      <rect x={-150} y={-130} width={300} height={290} rx={16} fill={WHITE} {...ink} />
      <path d="M -150,-60 V -114 Q -150,-130 -134,-130 H 134 Q 150,-130 150,-114 V -60 Z" fill={RED} {...ink} />
      <rect x={-90} y={-160} width={18} height={56} rx={9} fill={GREY} stroke={INK} strokeWidth={6} />
      <rect x={72} y={-160} width={18} height={56} rx={9} fill={GREY} stroke={INK} strokeWidth={6} />
      <g transform={`translate(0 50) scale(1 ${Math.max(0.05, Math.abs(flip))})`}>
        <FitText text={text} y={0} width={230} height={170} maxPx={110} maxLines={1} font={round} weight={700} />
      </g>
    </g>
  );
};

export const Envelope: React.FC<PropDrawProps> = ({ text, round }) => (
  <g>
    <Shadow d="M -170,-120 H 170 V 120 H -170 Z" />
    <rect x={-170} y={-120} width={340} height={240} rx={12} fill={WHITE} {...ink} />
    <path d="M -164,-112 L 0,20 L 164,-112" fill="none" {...ink} />
    {text && (
      <g>
        <rect x={-140} y={46} width={280} height={56} rx={10} fill={CREAM} stroke={INK} strokeWidth={5} />
        <FitText text={text} y={74} width={260} height={46} maxPx={34} maxLines={1} font={round} weight={600} />
      </g>
    )}
    <circle cx={128} cy={-80} r={16} fill={RED} stroke={INK} strokeWidth={5} />
  </g>
);
