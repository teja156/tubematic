/*
 * Hand props: things a puppet holds up in its raised hand, drawn once each
 * into a cached sprite, centred on (0, 0) inside their PROPS box
 * (./contract.ts) with about 6 units to spare. Same house look as the puppets:
 * INK outlines at LW, flat warm fills, no gradients, no filters.
 */
import React from "react";
import type { PropId } from "./contract";
import { BRASS, HAND, INK, LW, PAPER, RED, WOOD, WOOD_LIGHT, inked, type PropDrawProps } from "./ink";

const Scroll: React.FC<PropDrawProps> = ({ text }) => (
  <g>
    <rect x={-56} y={-62} width={112} height={124} {...inked(PAPER)} />
    <rect x={-68} y={-78} width={136} height={24} rx={12} {...inked("#D8C49A")} />
    <rect x={-68} y={54} width={136} height={24} rx={12} {...inked("#D8C49A")} />
    {text ? (
      <text x={0} y={8} textAnchor="middle" fontFamily={HAND} fontWeight={700} fontSize={Math.min(30, 96 / Math.max(1, text.length * 0.6))} fill={INK}>{text}</text>
    ) : (
      <path d="M -36 -24 H 36 M -36 0 H 30 M -36 24 H 36" stroke={INK} strokeWidth={LW * 0.6} strokeLinecap="round" />
    )}
  </g>
);

const thin = (c = INK) => ({ stroke: c, strokeWidth: LW * 0.6, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, fill: "none" });
const fit = (text: string, width: number, max: number) => Math.min(max, width / Math.max(1, text.length * 0.55));

const Letter: React.FC<PropDrawProps> = ({ text }) => (
  <g>
    <rect x={-62} y={-46} width={124} height={92} rx={6} {...inked(PAPER)} />
    <path d="M -62 -46 L 0 4 L 62 -46" {...thin()} />
    <circle cx={0} cy={4} r={12} {...inked(RED)} />
    {text ? (
      <text x={0} y={36} textAnchor="middle" fontFamily={HAND} fontWeight={700} fontSize={fit(text, 104, 22)} fill={INK}>{text}</text>
    ) : (
      <path d="M -34 26 H 34 M -26 38 H 26" {...thin()} />
    )}
  </g>
);

const CoinBag: React.FC<PropDrawProps> = () => (
  <g>
    <path d="M -16 -36 C -46 -20 -52 22 -42 44 C -32 58 32 58 42 44 C 52 22 46 -20 16 -36 Z" {...inked("#B89466")} />
    <path d="M -18 -40 L -26 -56 Q 0 -48 26 -56 L 18 -40 Z" {...inked("#B89466")} />
    <rect x={-20} y={-42} width={40} height={10} rx={5} {...inked(WOOD)} />
    <circle cx={0} cy={12} r={19} {...inked(BRASS)} />
    <circle cx={0} cy={12} r={10} {...thin()} />
  </g>
);

const Quill: React.FC<PropDrawProps> = () => (
  <g transform="rotate(18)">
    <path d="M 0 -74 C 26 -52 28 0 6 38 L 0 42 L -3 38 C -18 10 -20 -40 0 -74 Z" {...inked("#EFE6D4")} />
    <path d="M 0 -74 L 0 52" {...thin()} />
    <path d="M 0 -30 L 14 -42 M 0 -10 L 17 -24 M 0 10 L 14 -4 M 0 -30 L -12 -40 M 0 -8 L -14 -20" {...thin()} />
    <path d="M -5 50 L 0 74 L 5 50 Z" {...inked(INK)} />
  </g>
);

const Book: React.FC<PropDrawProps> = () => (
  <g>
    <rect x={-54} y={40} width={116} height={9} rx={3} {...inked(PAPER)} />
    <rect x={-58} y={-46} width={120} height={90} rx={6} {...inked("#7A3B2E")} />
    <rect x={-58} y={-46} width={18} height={90} rx={6} {...inked("#5F2C22")} />
    <rect x={-22} y={-26} width={64} height={18} rx={3} {...inked(BRASS)} />
    <path d="M -10 8 H 30 M -4 22 H 24" {...thin(BRASS)} />
  </g>
);

const Lantern: React.FC<PropDrawProps> = () => (
  <g>
    <path d="M -18 -52 C -18 -74 18 -74 18 -52" {...thin()} strokeWidth={LW} />
    <path d="M -22 -40 L -12 -54 H 12 L 22 -40 Z" {...inked("#5E5148")} />
    <rect x={-26} y={-40} width={52} height={80} {...inked("#F2D27A")} />
    <path d="M -9 -40 V 40 M 9 -40 V 40" {...thin()} />
    <path d="M 0 22 C -12 12 -4 0 0 -14 C 4 0 12 12 0 22 Z" {...inked("#E8883C", LW * 0.7)} />
    <rect x={-30} y={40} width={60} height={14} rx={3} {...inked("#5E5148")} />
  </g>
);

const Hammer: React.FC<PropDrawProps> = () => (
  <g>
    <rect x={-8} y={-34} width={16} height={106} rx={7} {...inked(WOOD)} />
    <rect x={-44} y={-68} width={88} height={36} rx={5} {...inked("#8C8A82")} />
    <path d="M -28 -68 V -32 M 28 -68 V -32" {...thin()} />
  </g>
);

const Shovel: React.FC<PropDrawProps> = () => (
  <g>
    <rect x={-6} y={-76} width={12} height={90} rx={5} {...inked(WOOD)} />
    <rect x={-22} y={-90} width={44} height={14} rx={7} {...inked(WOOD_LIGHT)} />
    <path d="M -26 16 L 26 16 L 26 40 C 26 66 8 80 0 84 C -8 80 -26 66 -26 40 Z" {...inked("#8C8A82")} />
    <rect x={-9} y={4} width={18} height={14} rx={3} {...inked("#6E6C65")} />
    <path d="M 0 26 V 62" {...thin()} />
  </g>
);

const Flag: React.FC<PropDrawProps> = ({ text }) => (
  <g>
    <rect x={-57} y={-78} width={10} height={168} rx={5} {...inked(WOOD)} />
    <circle cx={-52} cy={-84} r={6} {...inked(BRASS)} />
    <path d="M -47 -76 C -10 -90 20 -62 66 -76 L 66 -4 C 20 -18 -10 -2 -47 -10 Z" {...inked("#C9534A")} />
    {text ? (
      <text x={10} y={-32} textAnchor="middle" fontFamily={HAND} fontWeight={700} fontSize={fit(text, 96, 28)} fill={PAPER}>{text}</text>
    ) : null}
  </g>
);

const Telescope: React.FC<PropDrawProps> = () => (
  <g>
    <rect x={-80} y={-8} width={30} height={16} rx={4} {...inked(BRASS)} />
    <rect x={-52} y={-11} width={50} height={22} rx={3} {...inked(WOOD)} />
    <rect x={-4} y={-14} width={56} height={28} rx={3} {...inked(BRASS)} />
    <path d="M 52 -14 L 76 -26 V 26 L 52 14 Z" {...inked(BRASS)} />
    <path d="M -2 -14 V 14 M 20 -14 V 14" {...thin()} />
    <path d="M -52 -11 V 11" {...thin()} />
  </g>
);

const Cup: React.FC<PropDrawProps> = () => (
  <g>
    <path d="M 22 -16 C 38 -18 38 22 22 22" fill="none" stroke={INK} strokeWidth={16} strokeLinecap="round" />
    <path d="M 22 -16 C 38 -18 38 22 22 22" fill="none" stroke="#C98F5E" strokeWidth={6} strokeLinecap="round" />
    <rect x={-34} y={-28} width={58} height={68} rx={6} {...inked("#C98F5E")} />
    <ellipse cx={-5} cy={-28} rx={29} ry={8} {...inked("#6B3E26")} />
    <path d="M -34 0 H 24" {...thin()} />
  </g>
);

const Bread: React.FC<PropDrawProps> = () => (
  <g>
    <path d="M -62 8 C -66 -26 -30 -34 0 -34 C 30 -34 66 -26 62 8 C 62 30 40 34 0 34 C -40 34 -62 30 -62 8 Z" {...inked("#C98F4E")} />
    <path d="M -36 -22 Q -28 -10 -38 2 M -8 -26 Q 0 -12 -10 0 M 20 -24 Q 28 -10 18 2" {...thin("#8A5A34")} />
  </g>
);

const Sword: React.FC<PropDrawProps> = () => (
  <g>
    <path d="M 0 -90 L 9 -70 V 28 H -9 V -70 Z" {...inked("#C9C6BB")} />
    <path d="M 0 -64 V 20" {...thin()} />
    <rect x={-20} y={28} width={40} height={10} rx={5} {...inked(BRASS)} />
    <rect x={-5} y={38} width={10} height={30} rx={3} {...inked(WOOD)} />
    <circle cx={0} cy={74} r={9} {...inked(BRASS)} />
  </g>
);

const Basket: React.FC<PropDrawProps> = () => (
  <g>
    <path d="M -48 -20 C -48 -62 48 -62 48 -20" fill="none" stroke={INK} strokeWidth={12} strokeLinecap="round" />
    <path d="M -48 -20 C -48 -62 48 -62 48 -20" fill="none" stroke={WOOD_LIGHT} strokeWidth={5} strokeLinecap="round" />
    <circle cx={-30} cy={-30} r={16} {...inked("#C9534A")} />
    <circle cx={4} cy={-34} r={16} {...inked("#8EA85A")} />
    <circle cx={36} cy={-28} r={15} {...inked("#E8B93C")} />
    <path d="M -56 -12 H 56 L 44 50 H -44 Z" {...inked("#B98A52")} />
    <path d="M -52 6 H 52 M -48 24 H 48 M -46 40 H 46 M -20 -12 V 50 M 20 -12 V 50" {...thin("#6B4526")} />
    <rect x={-62} y={-22} width={124} height={14} rx={7} {...inked(WOOD_LIGHT)} />
  </g>
);

export const PROP_DRAWINGS: Record<PropId, React.FC<PropDrawProps>> = {
  scroll: Scroll,
  letter: Letter,
  coin_bag: CoinBag,
  quill: Quill,
  book: Book,
  lantern: Lantern,
  hammer: Hammer,
  shovel: Shovel,
  flag: Flag,
  telescope: Telescope,
  cup: Cup,
  bread: Bread,
  sword: Sword,
  basket: Basket,
};
