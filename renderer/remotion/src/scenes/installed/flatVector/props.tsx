/*
 * Flat Vector Science's prop library: the creatures, bodies, worlds and scale
 * references a video can show, each a static flat two-tone drawing (./toon.tsx)
 * centred on (0, 0) inside its box ([width, height] in px at size 1). The
 * renderer rasterises each once and moves the bitmap: drift, bob and sway are
 * transforms, never a new drawing.
 *
 * `group` is for the skill's catalogue only. `light` marks a prop that glows
 * (the renderer adds its halo, a cheap cached sprite). Keep a new prop inside
 * its box: the bitmap is cut to it.
 */
import React from "react";
import { Eye, GlowDot, Toon, circleD, ellipseD, rrectD } from "./toon";

export type PropGroup = "sea" | "body" | "space" | "earth" | "scale";

export interface PropDef {
  box: [number, number];
  group: PropGroup;
  /** The colour of its halo, for a prop that gives light. */
  light?: string;
  draw: () => React.ReactNode;
}

const GREY = { base: "#484e4f", shade: "#2e3333", rim: "#677071" };
const GOLD = "#FACC12";

// ── sea ─────────────────────────────────────────────────────────────────────
const WHALE_BODY =
  "M 440 -40 C 440 -102 418 -122 356 -124 L 120 -128 C 40 -128 -40 -120 -100 -108 L -122 -128 L -150 -98 " +
  "C -230 -70 -320 -36 -384 -16 L -386 16 C -320 24 -240 46 -150 72 C -50 100 80 114 180 102 " +
  "C 262 94 330 82 382 64 C 424 50 440 22 440 -40 Z";
const FLUKE = "M -380 -16 C -410 -24 -442 -58 -464 -92 C -454 -46 -442 -14 -430 0 C -442 14 -454 46 -464 92 C -442 58 -410 24 -380 16 Z";

const sea: Record<string, PropDef> = {
  whale: {
    box: [960, 300], group: "sea",
    draw: () => (
      <g>
        <Toon d={FLUKE} base="#454b4c" shade="#2b3030" rim="#5d6667" shadeDy={46} />
        <Toon d={WHALE_BODY} base={GREY.base} shade={GREY.shade} rim={GREY.rim} rimDy={7}
          shadeD="M -420 2 C -240 30 -40 -2 160 -14 C 300 -22 400 -12 460 6 L 460 220 L -420 220 Z">
          {[0, 1, 2, 3].map((i) => <rect key={i} x={150 + i * 46} y={-70 + (i % 2) * 14} width={26} height={7} rx={3.5} fill="#3d4344" />)}
        </Toon>
        <Toon d="M 214 66 C 244 60 274 70 288 96 C 260 100 232 92 214 66 Z" base="#3c4243" shade="#2a2f2f" shadeDy={14} />
        <Eye x={330} y={18} r={8} />
      </g>
    ),
  },
  shark: {
    box: [700, 260], group: "sea",
    draw: () => (
      <g>
        <Toon d="M -300 0 L -340 -80 L -320 0 L -340 80 Z" base="#5b6b73" shade="#40505a" shadeDy={30} />
        <Toon d="M 320 10 C 300 -60 180 -96 0 -90 C -150 -84 -260 -40 -310 0 C -250 40 -140 70 10 70 C 170 70 290 50 320 10 Z"
          base="#6c7d86" shade="#d9e2e4" rim="#8a9aa2" shadeD="M -320 20 C -150 30 100 30 330 20 L 330 120 L -320 120 Z" />
        <Toon d="M -20 -86 L 30 -170 L 80 -88 Z" base="#5b6b73" shade="#40505a" shadeDx={22} />
        <Toon d="M 40 40 L -10 120 L 100 50 Z" base="#5b6b73" shade="#40505a" shadeDy={10} />
        <Eye x={230} y={-20} r={7} />
        {[0, 1, 2].map((i) => <rect key={i} x={140 - i * 20} y={-30} width={6} height={36} rx={3} fill="#40505a" />)}
      </g>
    ),
  },
  squid: {
    box: [420, 620], group: "sea",
    draw: () => (
      <g>
        {[-60, -30, 0, 30, 60].map((x, i) => (
          <path key={i} d={`M ${x * 0.6} 60 C ${x} 160 ${x * 1.4} 220 ${x * 1.6} 300`} stroke="#b9473f" strokeWidth={18} strokeLinecap="round" fill="none" />
        ))}
        <Toon d="M 0 -300 C 90 -200 110 -60 80 60 C 40 80 -40 80 -80 60 C -110 -60 -90 -200 0 -300 Z" base="#d8584e" shade="#a63c35" rim="#ef8a7f" shadeDx={40} />
        <Eye x={-30} y={20} r={14} />
        <Eye x={30} y={20} r={14} />
      </g>
    ),
  },
  jellyfish: {
    box: [320, 420], group: "sea", light: "#32BAEE",
    draw: () => (
      <g>
        {[-48, -16, 16, 48].map((tx, i) => (
          <path key={i} d={`M ${tx} 8 C ${tx + 16} 80 ${tx - 16} 140 ${tx + 10} 200`} stroke="#7DD3DC" strokeWidth={9} strokeLinecap="round" fill="none" opacity={0.7} />
        ))}
        <Toon d="M -92 8 C -92 -108 92 -108 92 8 C 60 24 -60 24 -92 8 Z" base="#4fc7ec" shade="#2c9cc9" rim="#a9eaf7" rimDy={10} shadeDy={60}
          glow={{ cx: 0, cy: -20, r: 92, color: "#F9FCFB", opacity: 0.55 }} />
      </g>
    ),
  },
  anglerfish: {
    box: [360, 300], group: "sea", light: GOLD,
    draw: () => (
      <g transform="translate(20 30)">
        <path d="M 66 0 L 110 -30 L 102 0 L 110 30 Z" fill="#262c2c" />
        <Toon d="M 70 0 C 70 -50 10 -70 -40 -60 C -70 -54 -86 -30 -88 -6 L -40 6 L -86 20 C -76 46 -40 60 0 58 C 40 56 70 40 70 0 Z"
          base="#3a4142" shade="#252b2b" rim="#58605f" rimDy={6} shadeDy={58} />
        {[-82, -70, -58, -47].map((tx, i) => <path key={i} d={`M ${tx} ${-4 + i * 2.3} l 5 12 l 5 -12 Z`} fill="#F9FCFB" />)}
        <path d="M -20 -60 Q -60 -132 -104 -98" stroke="#3a4142" strokeWidth={5} strokeLinecap="round" fill="none" />
        <GlowDot x={-104} y={-98} r={46} color={GOLD} core="#F9EF93" coreR={9} />
        <Eye x={-34} y={-26} r={9} />
      </g>
    ),
  },
  fish: {
    box: [140, 70], group: "sea",
    draw: () => (
      <g transform="scale(2)">
        <path d="M 22 0 L 40 -11 L 37 0 L 40 11 Z" fill="#5d98b0" />
        <ellipse cx={0} cy={0} rx={24} ry={10} fill="#9fd4e6" />
        <path d="M -24 0 A 24 10 0 0 0 24 0 Z" fill="#5d98b0" />
        <circle cx={-13} cy={-2} r={2.4} fill="#0c2a3a" />
      </g>
    ),
  },
  fish_school: {
    box: [420, 200], group: "sea",
    draw: () => (
      <g>
        {[[-150, -50], [-80, -70], [-10, -40], [60, -66], [130, -36], [-120, 20], [-40, 40], [40, 16], [110, 50], [170, 10]].map(([x, y], i) => (
          <g key={i} transform={`translate(${x} ${y}) scale(${0.9 + (i % 3) * 0.12})`}>
            <path d="M 22 0 L 40 -11 L 37 0 L 40 11 Z" fill="#5d98b0" />
            <ellipse cx={0} cy={0} rx={24} ry={10} fill="#9fd4e6" />
            <path d="M -24 0 A 24 10 0 0 0 24 0 Z" fill="#5d98b0" />
            <circle cx={-13} cy={-2} r={2.4} fill="#0c2a3a" />
          </g>
        ))}
      </g>
    ),
  },
  diver: {
    box: [520, 140], group: "sea", light: GOLD,
    draw: () => (
      <g transform="translate(-40 0)">
        <path d="M -64 -4 L -156 -12" stroke="#252a2b" strokeWidth={22} strokeLinecap="round" />
        <path d="M -160 -12 L -238 -35 C -250 -17 -250 7 -238 25 L -160 2 Z" fill="#c79d0b" />
        <path d="M -64 8 L -156 16" stroke="#343a3b" strokeWidth={22} strokeLinecap="round" />
        <Toon d="M -160 16 L -238 -7 C -250 11 -250 35 -238 53 L -160 30 Z" base={GOLD} shade="#d9a90a" rim="#fde27a" rimDy={4} shadeDy={14} />
        <Toon d={rrectD(-78, -50, 122, 28, 14)} base="#dfe6e6" shade="#aebbbc" rim="#ffffff" rimDy={4} shadeDy={16} />
        <Toon d={rrectD(-96, -26, 176, 52, 26)} base="#3c4344" shade="#2a2f30" rim="#59a7b8" rimDy={4} shadeDy={28} />
        <path d="M 40 8 L 124 26" stroke="#353b3c" strokeWidth={16} strokeLinecap="round" />
        <Toon d={circleD(92, -6, 28)} base="#3c4344" shade="#2a2f30" rim="#59a7b8" rimDy={4} shadeDy={30} />
        <rect x={96} y={-22} width={30} height={22} rx={9} fill="#7DD3DC" />
        <GlowDot x={156} y={26} r={44} color={GOLD} core="#F9EF93" coreR={8} />
      </g>
    ),
  },
  submarine: {
    box: [300, 180], group: "sea", light: GOLD,
    draw: () => (
      <g transform="scale(1.5)">
        <Toon d="M -60 -20 L -40 -58 L -20 -58 L -24 -20 Z" base="#d99a0a" shade="#b07c06" shadeDx={12} rimDy={0} />
        <Toon d="M -70 0 C -70 -34 -30 -38 10 -38 C 50 -38 72 -22 72 0 C 72 22 50 36 10 36 C -30 36 -70 34 -70 0 Z"
          base={GOLD} shade="#d99a0a" rim="#ffe27a" rimDy={5} shadeDy={40} />
        <circle cx={34} cy={-6} r={17} fill="#2c6f86" />
        <circle cx={34} cy={-6} r={13} fill="#7DD3DC" />
        <rect x={-84} y={-14} width={8} height={28} rx={4} fill="#5a6263" />
        <GlowDot x={66} y={18} r={30} color={GOLD} core="#F9EF93" coreR={6} />
      </g>
    ),
  },
  shipwreck: {
    box: [700, 420], group: "sea",
    draw: () => (
      <g transform="translate(0 60)">
        <path d="M 214 -54 L 238 -236" stroke="#5c4c47" strokeWidth={9} strokeLinecap="round" />
        <g transform="translate(-130 -128) rotate(-9)">
          <Toon d="M -28 -64 L 28 -64 L 30 30 L -30 30 Z" base="#a5582c" shade="#7d411f" rim="#c26f3c" shadeDx={20} rimDy={0} />
        </g>
        <Toon d="M -250 -100 L 130 -100 L 130 -40 L -250 -40 Z" base="#8a786a" shade="#6b5b50" rim="#a8927f" shadeDy={34}>
          {Array.from({ length: 11 }, (_, i) => <rect key={i} x={-232 + i * 34} y={-84} width={18} height={14} rx={4} fill="#3d3433" />)}
        </Toon>
        <Toon d="M -310 -30 L 250 -52 C 280 -54 300 -60 318 -66 C 302 -10 282 40 252 74 L -290 74 L -300 52 L -284 32 L -312 12 L -292 -8 Z"
          base="#3d3433" shade="#2a2322" rim="#64524b" rimDy={6} shadeDy={70}>
          <path d="M -320 46 L 320 46 L 320 90 L -320 90 Z" fill="#6e3826" />
          {Array.from({ length: 17 }, (_, i) => <circle key={i} cx={-276 + i * 32} cy={-6 + i * -0.9} r={5} fill="#1d1817" />)}
        </Toon>
      </g>
    ),
  },
  coral: {
    box: [300, 260], group: "sea",
    draw: () => (
      <g transform="translate(0 120)">
        {[[-80, 0, -110, -160], [0, 0, 10, -220], [80, 0, 120, -150], [-30, -80, -80, -170], [40, -90, 70, -200]].map(([x1, y1, x2, y2], i) => (
          <path key={i} d={`M ${x1} ${y1} Q ${(x1 + x2) / 2 + 30} ${(y1 + y2) / 2} ${x2} ${y2}`} stroke={i % 2 ? "#e0736a" : "#f29b6f"} strokeWidth={26} strokeLinecap="round" fill="none" />
        ))}
        <Toon d={ellipseD(0, 0, 130, 24)} base="#2a4a52" shade="#1d3a40" shadeDy={10} />
      </g>
    ),
  },
};

// ── body ────────────────────────────────────────────────────────────────────
const body: Record<string, PropDef> = {
  cell: {
    box: [440, 440], group: "body",
    draw: () => (
      <g>
        <Toon d={circleD(0, 0, 200)} base="#e78fa6" shade="#c86d86" rim="#f6bccb" rimDy={10} shadeDx={30} shadeDy={30}>
          <ellipse cx={-80} cy={70} rx={40} ry={18} fill="#d67c95" />
          <ellipse cx={90} cy={-90} rx={34} ry={14} fill="#d67c95" />
        </Toon>
        <Toon d={circleD(20, -10, 74)} base="#8e4f9c" shade="#6e3a7c" rim="#b67ac4" shadeDx={14} shadeDy={14} />
        <circle cx={40} cy={-26} r={16} fill="#5a2a66" />
      </g>
    ),
  },
  red_blood_cell: {
    box: [300, 200], group: "body",
    draw: () => (
      <g>
        <Toon d={ellipseD(0, 0, 140, 90)} base="#d8343a" shade="#a92228" rim="#ef6f73" rimDy={8} shadeDy={30}>
          <ellipse cx={0} cy={-6} rx={70} ry={38} fill="#a92228" />
        </Toon>
      </g>
    ),
  },
  neuron: {
    box: [560, 320], group: "body", light: "#FACC12",
    draw: () => (
      <g>
        <path d="M -40 0 C -140 -40 -200 -100 -260 -130 M -40 0 C -160 10 -220 60 -250 120 M 30 -10 L 260 -20" stroke="#c9a9e8" strokeWidth={16} strokeLinecap="round" fill="none" />
        {[-150, -40, 70, 180].map((x, i) => <rect key={i} x={x} y={-30} width={60} height={22} rx={11} fill="#8f6fb8" transform={`rotate(${-2} ${x} -20)`} opacity={x > 0 ? 1 : 0} />)}
        <Toon d={circleD(-40, 0, 64)} base="#b48ee0" shade="#8f6fb8" rim="#d9c3f2" shadeDx={16} shadeDy={16} />
        <circle cx={-34} cy={-4} r={20} fill="#6e4f98" />
        <GlowDot x={262} y={-20} r={34} color={GOLD} core="#F9EF93" coreR={6} />
      </g>
    ),
  },
  virus: {
    box: [320, 320], group: "body",
    draw: () => (
      <g>
        {Array.from({ length: 12 }, (_, i) => {
          const a = (i / 12) * Math.PI * 2;
          return (
            <g key={i}>
              <line x1={Math.cos(a) * 100} y1={Math.sin(a) * 100} x2={Math.cos(a) * 140} y2={Math.sin(a) * 140} stroke="#7d9b3a" strokeWidth={12} strokeLinecap="round" />
              <circle cx={Math.cos(a) * 146} cy={Math.sin(a) * 146} r={12} fill="#d8343a" />
            </g>
          );
        })}
        <Toon d={circleD(0, 0, 108)} base="#9fbf4a" shade="#7d9b3a" rim="#c3dc79" shadeDx={22} shadeDy={22}>
          <circle cx={-30} cy={20} r={14} fill="#86a63f" />
          <circle cx={30} cy={-34} r={10} fill="#86a63f" />
        </Toon>
      </g>
    ),
  },
  bacterium: {
    box: [380, 180], group: "body",
    draw: () => (
      <g>
        {[-1, 1].map((s) => <path key={s} d={`M ${s * 150} 0 C ${s * 190} -20 ${s * 170} 40 ${s * 200} 30`} stroke="#5e9a6a" strokeWidth={6} fill="none" strokeLinecap="round" />)}
        <Toon d={rrectD(-150, -60, 300, 120, 60)} base="#7ec08c" shade="#5e9a6a" rim="#aee0b8" rimDy={8} shadeDy={36}>
          <circle cx={-50} cy={0} r={12} fill="#5e9a6a" />
          <circle cx={40} cy={-12} r={9} fill="#5e9a6a" />
        </Toon>
      </g>
    ),
  },
  dna: {
    box: [220, 520], group: "body",
    draw: () => (
      <g>
        {Array.from({ length: 11 }, (_, i) => {
          const y = -230 + i * 46;
          const x = Math.sin(i * 0.65) * 80;
          return <line key={i} x1={-x} y1={y} x2={x} y2={y} stroke={i % 2 ? "#FACC12" : "#32BAEE"} strokeWidth={10} strokeLinecap="round" />;
        })}
        {[1, -1].map((s) => (
          <path key={s} d={Array.from({ length: 23 }, (_, i) => `${i ? "L" : "M"} ${s * Math.sin(i * 0.325) * 84} ${-240 + i * 22}`).join(" ")}
            stroke={s > 0 ? "#e9e2f5" : "#b4a3d6"} strokeWidth={18} strokeLinecap="round" fill="none" />
        ))}
      </g>
    ),
  },
  heart: {
    box: [320, 320], group: "body",
    draw: () => (
      <g>
        <path d="M -30 -110 L -40 -150 M 20 -110 L 30 -160" stroke="#a92228" strokeWidth={26} strokeLinecap="round" />
        <Toon d="M 0 120 C -120 40 -150 -40 -110 -90 C -70 -130 -20 -110 0 -70 C 20 -110 70 -130 110 -90 C 150 -40 120 40 0 120 Z"
          base="#d8343a" shade="#a92228" rim="#ef6f73" rimDy={8} shadeDx={30} shadeDy={20} />
      </g>
    ),
  },
  lungs: {
    box: [380, 360], group: "body",
    draw: () => (
      <g>
        <path d="M 0 -160 L 0 -60 M 0 -60 L -50 -20 M 0 -60 L 50 -20" stroke="#d9c3c3" strokeWidth={22} strokeLinecap="round" fill="none" />
        {[-1, 1].map((s) => (
          <Toon key={s} d={`M ${s * 20} -80 C ${s * 120} -130 ${s * 170} -20 ${s * 160} 80 C ${s * 150} 150 ${s * 60} 160 ${s * 30} 120 C ${s * 20} 60 ${s * 20} -20 ${s * 20} -80 Z`}
            base="#e78fa6" shade="#c86d86" rim="#f6bccb" shadeDx={s * 24} shadeDy={20} />
        ))}
      </g>
    ),
  },
  brain: {
    box: [360, 300], group: "body",
    draw: () => (
      <g>
        <Toon d="M -150 20 C -170 -60 -110 -130 -30 -120 C 10 -150 90 -140 120 -90 C 170 -70 180 0 150 40 C 150 100 80 120 30 100 C -10 130 -80 120 -100 80 C -150 80 -160 50 -150 20 Z"
          base="#e7a0b6" shade="#c47b92" rim="#f6c6d4" rimDy={8} shadeDy={36}>
          {["M -100 -40 C -60 -60 -40 -20 -10 -50", "M 20 -80 C 40 -40 90 -60 110 -20", "M -110 40 C -60 20 -40 70 0 40", "M 30 20 C 60 60 100 30 130 50", "M 0 -110 L 0 100"].map((d, i) => (
            <path key={i} d={d} stroke="#c47b92" strokeWidth={10} strokeLinecap="round" fill="none" />
          ))}
        </Toon>
        <path d="M 60 100 C 70 130 60 150 40 170" stroke="#c47b92" strokeWidth={30} strokeLinecap="round" fill="none" />
      </g>
    ),
  },
  eye: {
    box: [340, 220], group: "body",
    draw: () => (
      <g>
        <Toon d="M -160 0 C -80 -100 80 -100 160 0 C 80 100 -80 100 -160 0 Z" base="#F2F0EA" shade="#cfcac0" rim="#ffffff" shadeDy={30} />
        <circle cx={0} cy={0} r={62} fill="#3c8fb8" />
        <circle cx={0} cy={0} r={30} fill="#101418" />
        <circle cx={14} cy={-16} r={10} fill="#F9FCFB" />
      </g>
    ),
  },
  mitochondrion: {
    box: [360, 200], group: "body",
    draw: () => (
      <g>
        <Toon d={ellipseD(0, 0, 160, 80)} base="#f2a35a" shade="#c97c38" rim="#f9c48d" rimDy={8} shadeDy={30}>
          <path d="M -120 0 C -100 -50 -80 50 -60 0 C -40 -50 -20 50 0 0 C 20 -50 40 50 60 0 C 80 -50 100 50 120 0" stroke="#c97c38" strokeWidth={12} fill="none" strokeLinecap="round" />
        </Toon>
      </g>
    ),
  },
};

// ── space ───────────────────────────────────────────────────────────────────
const planet = (base: string, shade: string, rim: string, r: number, extra?: React.ReactNode): PropDef["draw"] => () => (
  <Toon d={circleD(0, 0, r)} base={base} shade={shade} rim={rim} rimDy={r * 0.06} shadeDx={r * 0.28} shadeDy={r * 0.18}>
    {extra}
  </Toon>
);

const space: Record<string, PropDef> = {
  sun: {
    box: [440, 440], group: "space", light: GOLD,
    draw: () => (
      <g>
        <GlowDot x={0} y={0} r={215} color={GOLD} />
        <Toon d={circleD(0, 0, 130)} base={GOLD} shade="#e8a50c" rim="#F9EF93" rimDy={10} shadeDx={30} shadeDy={30} />
      </g>
    ),
  },
  star: {
    box: [200, 200], group: "space", light: "#F9EF93",
    draw: () => (
      <g>
        <GlowDot x={0} y={0} r={96} color="#F9EF93" />
        <path d="M 0 -60 L 14 -14 L 60 0 L 14 14 L 0 60 L -14 14 L -60 0 L -14 -14 Z" fill="#fffbe0" />
      </g>
    ),
  },
  earth: {
    box: [400, 400], group: "space",
    draw: planet("#3c8fd8", "#2a6aa8", "#7cc0f0", 190, (
      <g fill="#6fbf5a">
        <path d="M -120 -80 C -60 -120 0 -90 -20 -40 C -40 0 -100 -10 -130 -30 Z" />
        <path d="M 40 10 C 100 -10 140 40 110 90 C 80 130 30 110 40 60 Z" />
        <path d="M -90 60 C -60 50 -40 90 -70 120 C -100 110 -110 80 -90 60 Z" />
      </g>
    )),
  },
  moon: { box: [260, 260], group: "space", draw: planet("#c9c9c2", "#9a9a92", "#e8e8e2", 120, (
    <g fill="#a8a8a0"><circle cx={-40} cy={-30} r={22} /><circle cx={30} cy={40} r={16} /><circle cx={50} cy={-50} r={10} /></g>
  )) },
  mars: { box: [300, 300], group: "space", draw: planet("#d4673e", "#a64a28", "#f09a72", 140, (
    <g fill="#b85634"><ellipse cx={-30} cy={-20} rx={50} ry={16} /><ellipse cx={40} cy={50} rx={36} ry={10} /></g>
  )) },
  jupiter: { box: [460, 460], group: "space", draw: planet("#d9b38c", "#b08a66", "#f0d6b8", 220, (
    <g>{[-120, -60, 0, 60, 120].map((y, i) => <rect key={i} x={-240} y={y - 14} width={480} height={22} fill={i % 2 ? "#c19470" : "#e6c8a6"} />)}
      <ellipse cx={60} cy={70} rx={40} ry={22} fill="#c0563a" /></g>
  )) },
  saturn: {
    box: [560, 300], group: "space",
    draw: () => (
      <g>
        <ellipse cx={0} cy={0} rx={260} ry={60} fill="none" stroke="#c9b27e" strokeWidth={26} />
        <Toon d={circleD(0, 0, 120)} base="#e3c98c" shade="#b89a5c" rim="#f4e2b6" shadeDx={34} shadeDy={22} />
        <path d="M -250 6 A 260 60 0 0 0 250 6" fill="none" stroke="#dcc590" strokeWidth={26} />
      </g>
    ),
  },
  black_hole: {
    box: [480, 480], group: "space", light: "#f29b4a",
    draw: () => (
      <g>
        <GlowDot x={0} y={0} r={236} color="#f29b4a" />
        <ellipse cx={0} cy={0} rx={220} ry={56} fill="none" stroke="#f9c48d" strokeWidth={22} />
        <circle cx={0} cy={0} r={108} fill="#05080a" />
        <path d="M -216 -8 A 220 56 0 0 0 216 -8" fill="none" stroke="#fde3c2" strokeWidth={22} />
      </g>
    ),
  },
  galaxy: {
    box: [520, 400], group: "space", light: "#b48ee0",
    draw: () => (
      <g transform="scale(1 0.7)">
        <GlowDot x={0} y={0} r={250} color="#b48ee0" />
        {[0, 1].map((k) => (
          <path key={k} transform={`rotate(${k * 180})`}
            d={Array.from({ length: 40 }, (_, i) => { const a = i * 0.16; const r = 18 + i * 5.5; return `${i ? "L" : "M"} ${Math.cos(a) * r} ${Math.sin(a) * r}`; }).join(" ")}
            stroke="#d9c3f2" strokeWidth={26} strokeLinecap="round" fill="none" opacity={0.85} />
        ))}
        <circle cx={0} cy={0} r={36} fill="#fffbe0" />
      </g>
    ),
  },
  comet: {
    box: [460, 180], group: "space", light: "#7DD3DC",
    draw: () => (
      <g>
        <path d="M 120 0 L -220 -50 L -200 0 L -220 50 Z" fill="#7DD3DC" opacity={0.45} />
        <path d="M 120 0 L -160 -24 L -150 0 L -160 24 Z" fill="#c9f2f6" opacity={0.7} />
        <Toon d={circleD(140, 0, 44)} base="#9aa6a8" shade="#6e7a7c" rim="#c4d0d2" shadeDx={10} shadeDy={10} />
      </g>
    ),
  },
  rocket: {
    box: [220, 520], group: "space", light: "#f29b4a",
    draw: () => (
      <g>
        <GlowDot x={0} y={220} r={70} color="#f29b4a" core="#fde3c2" coreR={20} />
        <Toon d="M -60 140 L -110 200 L -60 180 Z" base="#d8343a" shade="#a92228" shadeDy={10} />
        <Toon d="M 60 140 L 110 200 L 60 180 Z" base="#d8343a" shade="#a92228" shadeDy={10} />
        <Toon d="M 0 -240 C 70 -170 70 60 60 190 L -60 190 C -70 60 -70 -170 0 -240 Z" base="#e8ecee" shade="#b9c2c6" rim="#ffffff" shadeDx={30} />
        <Toon d={circleD(0, -60, 34)} base="#3c8fb8" shade="#2a6a8a" rim="#7cc0e0" shadeDx={8} shadeDy={8} />
        <path d="M 0 -240 C 30 -210 46 -180 54 -150 L -54 -150 C -46 -180 -30 -210 0 -240 Z" fill="#d8343a" />
      </g>
    ),
  },
  astronaut: {
    box: [260, 380], group: "space",
    draw: () => (
      <g>
        <Toon d={rrectD(-80, -40, 160, 170, 50)} base="#e8ecee" shade="#b9c2c6" rim="#ffffff" shadeDx={26} />
        {[-1, 1].map((s) => <path key={s} d={`M ${s * 70} -10 L ${s * 110} 70`} stroke="#d9dee0" strokeWidth={40} strokeLinecap="round" />)}
        {[-1, 1].map((s) => <path key={`l${s}`} d={`M ${s * 36} 120 L ${s * 44} 180`} stroke="#d9dee0" strokeWidth={44} strokeLinecap="round" />)}
        <Toon d={circleD(0, -110, 80)} base="#e8ecee" shade="#b9c2c6" rim="#ffffff" shadeDx={20} shadeDy={20} />
        <Toon d={rrectD(-56, -150, 112, 76, 34)} base="#2c4a6a" shade="#1c3048" rim="#5a8ab0" shadeDx={10} shadeDy={10}>
          <rect x={-30} y={-140} width={26} height={12} rx={6} fill="#9fd4e6" />
        </Toon>
        <rect x={-30} y={10} width={60} height={34} rx={8} fill="#b9c2c6" />
      </g>
    ),
  },
  satellite: {
    box: [440, 200], group: "space",
    draw: () => (
      <g>
        {[-1, 1].map((s) => (
          <g key={s}>
            <rect x={s > 0 ? 60 : -200} y={-40} width={140} height={80} rx={6} fill="#2c4a8a" />
            {[0, 1, 2].map((k) => <rect key={k} x={(s > 0 ? 60 : -200) + 8 + k * 44} y={-32} width={36} height={64} fill="#3c6ac0" />)}
          </g>
        ))}
        <Toon d={rrectD(-50, -50, 100, 100, 12)} base={GOLD} shade="#d99a0a" rim="#ffe27a" shadeDx={20} shadeDy={14} />
        <path d="M 0 -50 L 0 -90" stroke="#b9c2c6" strokeWidth={8} />
        <circle cx={0} cy={-94} r={10} fill="#e8ecee" />
      </g>
    ),
  },
};

// ── earth ───────────────────────────────────────────────────────────────────
const earth: Record<string, PropDef> = {
  mountain: {
    box: [560, 360], group: "earth",
    draw: () => (
      <g transform="translate(0 170)">
        <Toon d="M -270 0 L -60 -330 L 100 -120 L 160 -200 L 270 0 Z" base="#5a6f7a" shade="#3e505a" rim="#7d93a0"
          shadeD="M -60 -330 L 30 0 L 270 0 L 160 -200 L 100 -120 Z" />
        <path d="M -60 -330 L -112 -248 L -86 -256 L -60 -230 L -34 -262 L -10 -252 Z" fill="#F2F0EA" />
      </g>
    ),
  },
  volcano: {
    box: [560, 420], group: "earth", light: "#f29b4a",
    draw: () => (
      <g transform="translate(0 200)">
        <GlowDot x={0} y={-300} r={110} color="#f29b4a" />
        <Toon d="M -270 0 L -60 -280 L 60 -280 L 270 0 Z" base="#5d4a42" shade="#3f312b" rim="#7a6358" shadeD="M 0 -280 L 60 -280 L 270 0 L 40 0 Z" />
        <path d="M -60 -280 C -30 -250 0 -300 30 -260 C 40 -250 50 -270 60 -280 Z" fill="#f29b4a" />
        <path d="M -10 -280 C -20 -220 10 -180 -10 -120" stroke="#f29b4a" strokeWidth={20} strokeLinecap="round" fill="none" />
      </g>
    ),
  },
  cloud: {
    box: [400, 220], group: "earth",
    draw: () => (
      <Toon d="M -170 60 C -200 60 -200 0 -160 -4 C -170 -60 -100 -90 -60 -50 C -40 -110 60 -110 70 -40 C 120 -70 190 -30 160 30 C 190 40 180 80 150 80 L -150 80 C -170 80 -180 70 -170 60 Z"
        base="#e6eef2" shade="#b8c6ce" rim="#ffffff" shadeD="M -200 40 C -100 60 100 60 200 40 L 200 100 L -200 100 Z" />
    ),
  },
  raindrop: {
    box: [160, 240], group: "earth",
    draw: () => (
      <Toon d="M 0 -110 C 30 -60 70 -10 70 40 C 70 85 38 110 0 110 C -38 110 -70 85 -70 40 C -70 -10 -30 -60 0 -110 Z"
        base="#4fa8e0" shade="#2f80b8" rim="#a9dcf7" rimDy={8} shadeDx={22} shadeDy={10} />
    ),
  },
  lightning: {
    box: [200, 380], group: "earth", light: GOLD,
    draw: () => (
      <g>
        <GlowDot x={0} y={0} r={100} color={GOLD} />
        <path d="M 30 -180 L -60 20 L 0 20 L -30 180 L 70 -30 L 10 -30 L 50 -180 Z" fill={GOLD} />
      </g>
    ),
  },
  iceberg: {
    box: [440, 480], group: "earth",
    draw: () => (
      <g>
        <Toon d="M -110 -40 L -60 -200 L 20 -150 L 90 -220 L 140 -40 Z" base="#e8f6fb" shade="#b8dcea" rim="#ffffff"
          shadeD="M 20 -150 L 90 -220 L 140 -40 L 60 -40 Z" />
        <Toon d="M -200 -40 L 210 -40 L 160 120 L 40 220 L -120 160 Z" base="#7cc0e0" shade="#4f9ac0" rim="#a9dcf7" shadeDx={40} shadeDy={30} />
        <rect x={-220} y={-44} width={440} height={6} fill="#e8f6fb" opacity={0.7} />
      </g>
    ),
  },
  tree: {
    box: [300, 420], group: "earth",
    draw: () => (
      <g transform="translate(0 200)">
        <rect x={-18} y={-150} width={36} height={150} rx={10} fill="#7a5238" />
        <Toon d="M 0 -400 C 90 -380 140 -300 120 -220 C 160 -180 130 -120 70 -130 C 40 -100 -40 -100 -70 -130 C -130 -120 -160 -180 -120 -220 C -140 -300 -90 -380 0 -400 Z"
          base="#5fae5a" shade="#3f8a3e" rim="#8ccf7c" shadeDx={30} shadeDy={20} />
      </g>
    ),
  },
  rock: {
    box: [300, 180], group: "earth",
    draw: () => (
      <Toon d="M -140 70 L -120 -10 L -40 -70 L 60 -60 L 130 0 L 140 70 Z" base="#6a6f72" shade="#4a4f52" rim="#8a9094"
        shadeD="M 60 -60 L 130 0 L 140 70 L 30 70 Z">
        {[[-60, 20], [20, 30], [70, -10]].map(([x, y], i) => <circle key={i} cx={x} cy={y} r={7} fill="#5a5f62" />)}
      </Toon>
    ),
  },
};

// ── scale references ────────────────────────────────────────────────────────
const scale: Record<string, PropDef> = {
  bus: {
    box: [440, 200], group: "scale",
    draw: () => (
      <g>
        <Toon d={rrectD(-200, -80, 400, 140, 22)} base={GOLD} shade="#d99a0a" rim="#ffe27a" shadeD="M -210 30 L 210 30 L 210 80 L -210 80 Z">
          {[-160, -90, -20, 50].map((x, i) => <rect key={i} x={x} y={-60} width={56} height={46} rx={6} fill="#2c4a5a" />)}
          <rect x={130} y={-60} width={54} height={96} rx={6} fill="#2c4a5a" />
        </Toon>
        {[-120, 120].map((x) => <g key={x}><circle cx={x} cy={64} r={30} fill="#1d2224" /><circle cx={x} cy={64} r={12} fill="#7a8284" /></g>)}
      </g>
    ),
  },
  person: {
    box: [120, 340], group: "scale",
    draw: () => (
      <g>
        <path d="M -18 70 L -20 150 M 18 70 L 20 150" stroke="#2c4a6a" strokeWidth={28} strokeLinecap="round" />
        <Toon d={rrectD(-44, -60, 88, 140, 36)} base="#d8343a" shade="#a92228" rim="#ef6f73" shadeDx={18} />
        <Toon d={circleD(0, -110, 40)} base="#f2c09a" shade="#d89c74" rim="#fbdcc0" shadeDx={12} shadeDy={8} />
        <circle cx={-12} cy={-112} r={4} fill="#1d2224" />
        <circle cx={12} cy={-112} r={4} fill="#1d2224" />
        <circle cx={-22} cy={-98} r={6} fill="#ef8a7f" opacity={0.6} />
        <circle cx={22} cy={-98} r={6} fill="#ef8a7f" opacity={0.6} />
      </g>
    ),
  },
  skyscraper: {
    box: [200, 560], group: "scale",
    draw: () => (
      <g>
        <path d="M 0 -280 L 0 -240" stroke="#b9c2c6" strokeWidth={8} />
        <Toon d="M -80 -240 L 80 -240 L 80 280 L -80 280 Z" base="#5a7a96" shade="#3e5a72" rim="#86a6c0" shadeD="M 10 -240 L 80 -240 L 80 280 L 10 280 Z">
          {Array.from({ length: 16 }, (_, r) => [0, 1, 2].map((c) => (
            <rect key={`${r}-${c}`} x={-62 + c * 44} y={-220 + r * 30} width={30} height={16} fill={(r * 3 + c) % 7 ? "#9fd4e6" : "#F9EF93"} opacity={0.8} />
          )))}
        </Toon>
      </g>
    ),
  },
  plane: {
    box: [520, 200], group: "scale",
    draw: () => (
      <g>
        <Toon d="M -240 -10 L -270 -80 L -220 -80 L -170 -14 Z" base="#c9d2d6" shade="#9aa6aa" shadeDy={10} />
        <Toon d="M -40 0 L -120 90 L -60 90 L 60 4 Z" base="#c9d2d6" shade="#9aa6aa" shadeDy={10} />
        <Toon d="M 250 0 C 250 -24 220 -34 180 -34 L -230 -24 C -260 -20 -260 20 -230 24 L 180 34 C 220 34 250 24 250 0 Z" base="#e8ecee" shade="#b9c2c6" rim="#ffffff"
          shadeD="M -260 6 L 260 6 L 260 40 L -260 40 Z">
          {Array.from({ length: 12 }, (_, i) => <circle key={i} cx={-170 + i * 30} cy={-8} r={6} fill="#2c4a5a" />)}
        </Toon>
      </g>
    ),
  },
  car: {
    box: [360, 170], group: "scale",
    draw: () => (
      <g>
        <Toon d="M -170 40 L -160 -10 L -90 -20 L -50 -70 L 70 -70 L 120 -20 L 170 -10 L 170 40 Z" base="#d8343a" shade="#a92228" rim="#ef6f73"
          shadeD="M -180 20 L 180 20 L 180 50 L -180 50 Z">
          <path d="M -40 -60 L 10 -60 L 10 -22 L -70 -22 Z" fill="#2c4a5a" />
          <path d="M 24 -60 L 64 -60 L 100 -22 L 24 -22 Z" fill="#2c4a5a" />
        </Toon>
        {[-100, 100].map((x) => <g key={x}><circle cx={x} cy={44} r={30} fill="#1d2224" /><circle cx={x} cy={44} r={12} fill="#7a8284" /></g>)}
      </g>
    ),
  },
};

export const PROPS: Record<string, PropDef> = { ...sea, ...body, ...space, ...earth, ...scale };
export const PROP_NAMES = Object.keys(PROPS);
