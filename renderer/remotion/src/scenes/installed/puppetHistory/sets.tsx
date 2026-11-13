/*
 * Sets: flat illustrated places the puppets stand in, full frame (1080 x 1920).
 * A set is flat colour bands from the top of the frame down (drawn as plain
 * page boxes, which cost nothing per frame), pieces of decor drawn once each
 * into a cached sprite, and the foreground band the puppets stand behind (from
 * GEOMETRY.frontY, 1600, to the bottom; it hides their waists).
 *
 * Rules every set keeps, because of what is measured on the CPU renderer and
 * what the rest of the frame holds:
 * - No full-frame picture: a bitmap's cost grows with its area, and one the
 *   size of the frame costs about 0.2 CPU-seconds on every frame. Big flat
 *   areas are bands; decor pieces are at most about 640 x 640 each and about
 *   0.7 megapixels together.
 * - The captions sit near y 270: nothing busy between y 180 and 360.
 * - Decor sits between y 380 and 1600. Puppets stand at x 230, 540 and 850
 *   with their heads around y 1180 to 1400, so decor there is background only.
 * - Generic places only: no real building, flag, emblem or sign of a real
 *   organisation; text on decor only if it is generic ("BANK", "1920").
 */
import React from "react";
import type { SpriteBox } from "../characterKit/sprite";
import type { SetId } from "./contract";
import { BRASS, CREAM, DADO, GRASS, HAND, INK, LW, PAPER, SKY, WOOD, WOOD_LIGHT, inked } from "./ink";

export type Decor = { id: string; x: number; y: number; box: SpriteBox; Draw: React.FC };
export type SetDrawing = {
  /** Flat bands, top to bottom: each from `top` to the next band's top (the last to frontY). */
  bands: { top: number; color: string }[];
  decor: Decor[];
  /** The foreground band's colour, and a line or two drawn along its top edge in the decor if needed. */
  front: string;
};

const Window: React.FC = () => (
  <g>
    <rect x={-150} y={-190} width={300} height={380} {...inked(PAPER)} />
    <rect x={-128} y={-168} width={256} height={336} {...inked(SKY, LW * 0.8)} />
    <path d="M 0 -168 V 168 M -128 0 H 128" stroke={INK} strokeWidth={LW * 0.8} />
    <rect x={-170} y={190} width={340} height={26} {...inked(WOOD_LIGHT)} />
  </g>
);

const Frame: React.FC = () => (
  <g>
    <rect x={-110} y={-80} width={220} height={160} {...inked(WOOD)} />
    <rect x={-88} y={-58} width={176} height={116} {...inked("#C9B98F", LW * 0.7)} />
    <path d="M -70 40 L -20 -20 L 10 20 L 40 -10 L 70 40 Z" {...inked("#8FA27A", LW * 0.6)} />
  </g>
);

const office: SetDrawing = {
  bands: [
    { top: 0, color: CREAM },
    { top: 1180, color: DADO },
  ],
  decor: [
    { id: "office-window", x: 300, y: 720, box: { left: -180, top: -200, width: 360, height: 430 }, Draw: Window },
    { id: "office-frame", x: 800, y: 640, box: { left: -120, top: -90, width: 240, height: 180 }, Draw: Frame },
  ],
  front: WOOD_LIGHT,
};


const L = LW * 0.7;
const BRICK = "#B07A5E";
const ROOF = "#9C5A4A";
const WHEAT = "#D8BC6A";
const HILL = "#93A56F";
const HILL2 = "#7F9A62";
const BOARD = "#4F6657";
const mk = (id: string, x: number, y: number, left: number, top: number, width: number, height: number, Draw: React.FC): Decor => ({ id, x, y, box: { left, top, width, height }, Draw });

/** A strip of rolling hills across the frame, local y 0 is the base. */
const Hills: React.FC<{ a?: string; b?: string }> = ({ a = HILL, b = HILL2 }) => (
  <g>
    <path d="M -540 20 L -540 -70 Q -380 -190 -210 -90 Q -60 -170 120 -70 Q 330 -200 540 -80 L 540 20 Z" {...inked(a)} />
    <path d="M -540 20 L -540 -10 Q -300 -90 -90 -20 Q 150 -80 540 -10 L 540 20 Z" {...inked(b, L)} />
  </g>
);
const HILLS_BOX = { left: -550, top: -210, width: 1100, height: 240 };

/* ---- farm ---- */
const Windmill: React.FC = () => (
  <g>
    <path d="M -75 200 L -48 -90 L 48 -90 L 75 200 Z" {...inked(PAPER)} />
    <path d="M -62 -90 L 0 -180 L 62 -90 Z" {...inked(ROOF)} />
    <path d="M -28 200 V 120 Q 0 90 28 120 V 200" {...inked(WOOD)} />
    <rect x={-18} y={-30} width={36} height={50} rx={6} {...inked(SKY, L)} />
    {[0, 90, 180, 270].map((r) => (
      <g key={r} transform={`translate(0 -100) rotate(${r + 22})`}>
        <path d="M 0 0 V -190" stroke={INK} strokeWidth={LW} />
        <rect x={6} y={-185} width={52} height={120} {...inked(CREAM, L)} />
      </g>
    ))}
    <circle cx={0} cy={-100} r={14} {...inked(WOOD)} />
  </g>
);
const Fence: React.FC = () => (
  <g>
    <rect x={-540} y={-34} width={1080} height={18} {...inked(WOOD_LIGHT, L)} />
    <rect x={-540} y={6} width={1080} height={18} {...inked(WOOD_LIGHT, L)} />
    {Array.from({ length: 9 }, (_, i) => (
      <rect key={i} x={-495 + i * 120} y={-58} width={30} height={102} rx={8} {...inked(WOOD, L)} />
    ))}
  </g>
);
const farm: SetDrawing = {
  bands: [
    { top: 0, color: SKY },
    { top: 1000, color: HILL },
    { top: 1330, color: WHEAT },
  ],
  decor: [
    mk("farm-hills", 540, 1000, HILLS_BOX.left, HILLS_BOX.top, HILLS_BOX.width, HILLS_BOX.height, () => <Hills />),
    mk("farm-windmill", 800, 800, -240, -300, 480, 530, Windmill),
    mk("farm-fence", 540, 1560, -550, -70, 1100, 130, Fence),
  ],
  front: GRASS,
};

/* ---- street ---- */
const House: React.FC<{ wall: string; door?: boolean }> = ({ wall, door = true }) => (
  <g>
    <rect x={-160} y={-500} width={320} height={500} {...inked(wall)} />
    <path d="M -185 -500 L 0 -610 L 185 -500 Z" {...inked(ROOF)} />
    {[-80, 80].map((x) => (
      <g key={x}>
        <rect x={x - 42} y={-420} width={84} height={110} {...inked(SKY, L)} />
        <path d={`M ${x} -420 V -310 M ${x - 42} -365 H ${x + 42}`} stroke={INK} strokeWidth={L} />
        <rect x={x - 42} y={-250} width={84} height={100} {...inked(SKY, L)} />
        <path d={`M ${x} -250 V -150`} stroke={INK} strokeWidth={L} />
      </g>
    ))}
    {door && <path d="M -36 0 V -90 Q 0 -125 36 -90 V 0" {...inked(WOOD)} />}
  </g>
);
const Lamp: React.FC = () => (
  <g>
    <rect x={-10} y={-420} width={20} height={430} {...inked(INK, L)} />
    <rect x={-34} y={-12} width={68} height={22} rx={6} {...inked(INK, L)} />
    <path d="M -34 -440 H 34 L 22 -500 H -22 Z" {...inked("#E8D08A", L)} />
    <path d="M -40 -440 L 0 -475 L 40 -440" {...inked(INK, L)} />
  </g>
);
const street: SetDrawing = {
  bands: [
    { top: 0, color: SKY },
    { top: 1300, color: "#B7A88C" },
  ],
  decor: [
    mk("street-houseA", 190, 1300, -170, -560, 340, 570, () => <g transform="scale(0.9)"><House wall="#D9C39A" /></g>),
    mk("street-houseB", 890, 1300, -170, -560, 340, 570, () => <g transform="scale(0.9)"><House wall="#C9B38E" door={false} /></g>),
    mk("street-houseC", 540, 1300, -140, -440, 280, 450, () => (
      <g transform="scale(0.72)">
        <House wall="#E0CFAA" />
      </g>
    )),
    mk("street-lamp", 540, 1300, -50, -515, 100, 530, Lamp),
  ],
  front: "#9C8E76",
};

/* ---- palace ---- */
const Column: React.FC = () => (
  <g>
    <rect x={-60} y={-410} width={120} height={46} rx={8} {...inked(PAPER)} />
    <rect x={-46} y={-364} width={92} height={730} {...inked("#E6DCC4")} />
    <path d="M -16 -364 V 366 M 16 -364 V 366" stroke={INK} strokeWidth={L} />
    <rect x={-64} y={366} width={128} height={44} rx={8} {...inked(PAPER)} />
  </g>
);
const ArchWindow: React.FC = () => (
  <g>
    <path d="M -110 220 V -60 Q -110 -200 0 -200 Q 110 -200 110 -60 V 220 Z" {...inked(PAPER)} />
    <path d="M -86 220 V -60 Q -86 -176 0 -176 Q 86 -176 86 -60 V 220 Z" {...inked(SKY, L)} />
    <path d="M 0 -176 V 220" stroke={INK} strokeWidth={L} />
    <path d="M -130 -170 Q -130 -120 -120 220 H -90 Q -100 -80 -100 -170 Z" {...inked("#9C4A44", L)} />
    <path d="M 130 -170 Q 130 -120 120 220 H 90 Q 100 -80 100 -170 Z" {...inked("#9C4A44", L)} />
  </g>
);
const Carpet: React.FC = () => (
  <g>
    <path d="M -150 -170 H 150 L 340 190 H -340 Z" {...inked("#A8453F")} />
    <path d="M -120 -140 H 120 L 290 170 H -290 Z" fill="none" stroke={BRASS} strokeWidth={L} />
  </g>
);
const palace: SetDrawing = {
  bands: [
    { top: 0, color: "#D9C7A0" },
    { top: 1250, color: "#CFC6B2" },
  ],
  decor: [
    mk("palace-colL", 85, 840, -70, -420, 140, 840, Column),
    mk("palace-colR", 995, 840, -70, -420, 140, 840, Column),
    mk("palace-window", 540, 800, -140, -210, 280, 440, ArchWindow),
    mk("palace-carpet", 540, 1430, -350, -180, 700, 380, Carpet),
  ],
  front: "#B9564B",
};

/* ---- castle ---- */
const Battlements: React.FC = () => (
  <g>
    <path d={"M -545 60 V -50 " + Array.from({ length: 9 }, (_, i) => `H ${-545 + i * 118 + 0} V -50 H ${-545 + i * 118 + 78} V -10 H ${-545 + i * 118 + 118} V -50`).join(" ") + " H 545 V 60 Z"} {...inked("#B3AA98")} />
  </g>
);
const Banner: React.FC = () => (
  <g>
    <rect x={-120} y={-30} width={240} height={14} rx={6} {...inked(WOOD)} />
    <path d="M -100 -16 V 300 L 0 240 L 100 300 V -16 Z" {...inked("#9C4A44")} />
    <path d="M -100 40 H 100 M -100 70 H 100" stroke={BRASS} strokeWidth={LW} />
  </g>
);
const Tower: React.FC = () => (
  <g>
    <rect x={-100} y={-300} width={200} height={600} {...inked("#A69D8B")} />
    <path d="M -115 -300 V -350 H -70 V -320 H -25 V -350 H 25 V -320 H 70 V -350 H 115 V -300 Z" {...inked("#A69D8B")} />
    <path d="M -14 -150 V -70 Q 0 -90 14 -70 V -150 Q 0 -170 -14 -150 Z" {...inked(INK, L)} />
  </g>
);
const castle: SetDrawing = {
  bands: [
    { top: 0, color: SKY },
    { top: 720, color: "#B3AA98" },
    { top: 1250, color: "#9E9684" },
  ],
  decor: [
    mk("castle-battle", 540, 700, -555, -60, 1110, 130, Battlements),
    mk("castle-tower", 930, 560, -125, -360, 250, 660, Tower),
    mk("castle-banner", 400, 760, -125, -40, 250, 360, Banner),
    mk("castle-slit", 700, 960, -30, -80, 60, 160, () => <path d="M -14 70 V -40 Q 0 -70 14 -40 V 70 Z" {...inked(INK, L)} />),
  ],
  front: "#8A8272",
};

/* ---- deck ---- */
const Mast: React.FC = () => (
  <g>
    <rect x={-18} y={-420} width={36} height={850} rx={8} {...inked(WOOD)} />
    <circle cx={0} cy={-430} r={22} {...inked(WOOD_LIGHT, L)} />
  </g>
);
const Sail: React.FC = () => (
  <g>
    <rect x={-240} y={-210} width={480} height={16} rx={8} {...inked(WOOD)} />
    <path d="M -226 -194 Q 0 -140 226 -194 L 210 170 Q 0 220 -210 170 Z" {...inked(PAPER)} />
    <path d="M -110 -175 Q -105 0 -100 190 M 110 -175 Q 105 0 100 190" stroke={INK} strokeWidth={L} fill="none" />
  </g>
);
const Rail: React.FC = () => (
  <g>
    <rect x={-540} y={-30} width={1080} height={22} rx={8} {...inked(WOOD_LIGHT)} />
    {Array.from({ length: 10 }, (_, i) => (
      <rect key={i} x={-505 + i * 114} y={-30} width={22} height={96} {...inked(WOOD, L)} />
    ))}
    <path d="M -540 24 Q -270 70 0 24 Q 270 70 540 24" fill="none" stroke={INK} strokeWidth={LW} />
  </g>
);
const deck: SetDrawing = {
  bands: [
    { top: 0, color: SKY },
    { top: 760, color: "#7FA3BA" },
    { top: 1250, color: "#B58A5C" },
  ],
  decor: [
    mk("deck-mast", 540, 850, -30, -450, 60, 890, Mast),
    mk("deck-sail", 540, 650, -250, -220, 500, 420, Sail),
    mk("deck-rail", 540, 1500, -550, -45, 1100, 125, Rail),
    mk("deck-boat", 170, 790, -70, -70, 140, 90, () => (
      <g>
        <path d="M -55 0 H 55 L 35 28 H -35 Z" {...inked(WOOD, L)} />
        <path d="M 0 0 V -50 L 30 -8 Z" {...inked(PAPER, L)} />
      </g>
    )),
  ],
  front: WOOD_LIGHT,
};

/* ---- market ---- */
const Stall: React.FC<{ a: string }> = ({ a }) => (
  <g>
    <rect x={-170} y={-130} width={16} height={430} {...inked(WOOD, L)} />
    <rect x={154} y={-130} width={16} height={430} {...inked(WOOD, L)} />
    <path d="M -190 -130 H 190 L 215 -50 H -215 Z" {...inked(a)} />
    {[-120, -40, 40, 120].map((x) => (
      <path key={x} d={`M ${x - 40} -130 L ${x - 52} -50 M ${x + 40} -130 L ${x + 52} -50`} stroke={INK} strokeWidth={L} />
    ))}
    <path d="M -215 -50 q 22 36 43 0 q 22 36 43 0 q 22 36 43 0 q 22 36 43 0 q 22 36 43 0 q 22 36 43 0 q 22 36 43 0 q 22 36 43 0 q 22 36 43 0 q 22 36 0 0" {...inked(a, L)} />
    <rect x={-190} y={150} width={380} height={150} {...inked(WOOD_LIGHT)} />
    <circle cx={-110} cy={134} r={20} {...inked("#C9553D", L)} />
    <circle cx={-66} cy={138} r={18} {...inked("#C9553D", L)} />
    <circle cx={30} cy={136} r={19} {...inked("#D9B04A", L)} />
    <circle cx={76} cy={138} r={18} {...inked("#D9B04A", L)} />
    <circle cx={128} cy={136} r={19} {...inked("#7A9A4A", L)} />
  </g>
);
const Crate: React.FC = () => (
  <g>
    <rect x={-70} y={-55} width={140} height={110} {...inked(WOOD_LIGHT)} />
    <path d="M -70 -18 H 70 M -70 18 H 70" stroke={INK} strokeWidth={L} />
  </g>
);
const market: SetDrawing = {
  bands: [
    { top: 0, color: SKY },
    { top: 800, color: "#CDB98E" },
    { top: 1250, color: "#B79F78" },
  ],
  decor: [
    mk("market-stallA", 200, 1000, -225, -140, 450, 460, () => <Stall a="#B5503F" />),
    mk("market-stallB", 880, 1000, -225, -140, 450, 460, () => <Stall a="#5F8C8C" />),
    mk("market-sign", 540, 620, -200, -50, 400, 100, () => (
      <g>
        <rect x={-190} y={-40} width={380} height={80} rx={14} {...inked(WOOD_LIGHT)} />
        <text x={0} y={16} textAnchor="middle" fontFamily={HAND} fontSize={56} fill={INK}>MARKET</text>
      </g>
    )),
    mk("market-crateA", 540, 1330, -80, -65, 160, 130, Crate),
    mk("market-crateB", 640, 1380, -80, -65, 160, 130, Crate),
  ],
  front: "#9C8660",
};

/* ---- factory ---- */
const FactoryWindow: React.FC<{ stack?: boolean }> = ({ stack }) => (
  <g>
    <rect x={-150} y={-200} width={300} height={400} {...inked("#8C8478")} />
    <rect x={-128} y={-178} width={256} height={356} {...inked(SKY, L)} />
    {stack && (
      <g>
        <path d="M 10 178 L 22 -60 H 62 L 74 178 Z" {...inked("#8A5A4A", L)} />
        <path d="M 18 -60 H 66" stroke={INK} strokeWidth={LW} />
        <path d="M 40 -75 Q 20 -110 50 -140 Q 60 -160 40 -178" fill="none" stroke="#E5E1D6" strokeWidth={14} strokeLinecap="round" />
      </g>
    )}
    <path d="M -128 -60 H 128 M -128 60 H 128 M 0 -178 V 178" stroke={INK} strokeWidth={L} />
  </g>
);
const Pipes: React.FC = () => (
  <g>
    <rect x={-540} y={-30} width={1080} height={56} rx={10} {...inked("#8C8478")} />
    {[-400, -120, 200, 440].map((x) => (
      <rect key={x} x={x - 14} y={-42} width={28} height={80} rx={6} {...inked("#6F685D", L)} />
    ))}
  </g>
);
const DownPipe: React.FC = () => (
  <g>
    <rect x={-26} y={-10} width={52} height={420} {...inked("#8C8478")} />
    <rect x={-42} y={394} width={84} height={30} rx={6} {...inked("#6F685D", L)} />
  </g>
);
const Gear: React.FC = () => {
  const teeth = Array.from({ length: 10 }, (_, i) => i * 36);
  return (
    <g>
      {teeth.map((r) => (
        <rect key={r} x={-16} y={-120} width={32} height={40} {...inked("#B0A58E", L)} transform={`rotate(${r})`} />
      ))}
      <circle r={96} {...inked("#B0A58E")} />
      <circle r={30} {...inked("#8C8478", L)} />
      {[0, 120, 240].map((r) => (
        <path key={r} d="M 0 -30 V -90" stroke={INK} strokeWidth={L} transform={`rotate(${r})`} />
      ))}
    </g>
  );
};
const factory: SetDrawing = {
  bands: [
    { top: 0, color: BRICK },
    { top: 1250, color: "#8C8478" },
  ],
  decor: [
    mk("factory-pipes", 540, 500, -550, -50, 1100, 100, Pipes),
    mk("factory-downpipe", 74, 526, -50, -30, 100, 480, DownPipe),
    mk("factory-winA", 230, 860, -160, -210, 320, 420, () => <FactoryWindow />),
    mk("factory-winB", 850, 860, -160, -210, 320, 420, () => <FactoryWindow stack />),
    mk("factory-gear", 540, 800, -130, -130, 260, 260, Gear),
  ],
  front: "#6F685D",
};

/* ---- camp ---- */
const Tent: React.FC<{ c: string }> = ({ c }) => (
  <g>
    <path d="M -200 0 L 0 -310 L 200 0 Z" {...inked(c)} />
    <path d="M 0 -310 L -62 0 H 62 Z" {...inked("#5A4636", L)} />
    <path d="M 0 -310 V -350" stroke={INK} strokeWidth={LW} />
    <path d="M -200 0 L -240 24 M 200 0 L 240 24" stroke={INK} strokeWidth={LW} />
  </g>
);
const camp: SetDrawing = {
  bands: [
    { top: 0, color: SKY },
    { top: 1000, color: HILL2 },
    { top: 1330, color: "#8FA06B" },
  ],
  decor: [
    mk("camp-hills", 540, 1010, HILLS_BOX.left, HILLS_BOX.top, HILLS_BOX.width, HILLS_BOX.height, () => <Hills a="#A5B280" b={HILL2} />),
    mk("camp-tentA", 190, 1330, -250, -360, 500, 400, () => <Tent c="#D8C9A0" />),
    mk("camp-tentB", 890, 1330, -250, -360, 500, 400, () => <Tent c="#C9B88C" />),
    mk("camp-pole", 540, 1100, -30, -310, 140, 520, () => (
      <g>
        <rect x={-6} y={-300} width={12} height={500} {...inked(WOOD, L)} />
        <path d="M 6 -296 H 90 L 66 -262 L 90 -228 H 6 Z" {...inked("#7C9A5E", L)} />
      </g>
    )),
    mk("camp-crate", 540, 1400, -80, -65, 160, 130, Crate),
  ],
  front: GRASS,
};

/* ---- lab ---- */
const Flask: React.FC<{ c: string; tall?: boolean }> = ({ c, tall }) => (
  <g>
    {tall ? (
      <g>
        <rect x={-16} y={-60} width={32} height={80} rx={6} {...inked("#E8E4D6", L)} />
        <rect x={-16} y={-10} width={32} height={30} {...inked(c, L)} />
      </g>
    ) : (
      <g>
        <path d="M -12 -50 H 12 V -20 L 34 20 H -34 L -12 -20 Z" {...inked("#E8E4D6", L)} />
        <path d="M -24 4 H 24 L 34 20 H -34 Z" {...inked(c, L)} />
      </g>
    )}
  </g>
);
const Shelves: React.FC = () => (
  <g>
    <rect x={-190} y={-190} width={380} height={380} {...inked(WOOD)} />
    <rect x={-170} y={-170} width={340} height={340} {...inked("#6B4528", L)} />
    {[-30, 120].map((y) => (
      <rect key={y} x={-176} y={y} width={352} height={16} {...inked(WOOD_LIGHT, L)} />
    ))}
    <g transform="translate(-100 -50)"><Flask c="#6FA06A" /></g>
    <g transform="translate(-20 -50)"><Flask c="#C9553D" tall /></g>
    <g transform="translate(70 -50)"><Flask c="#D9B04A" /></g>
    <g transform="translate(120 100)"><Flask c="#5F8CB0" tall /></g>
    <g transform="translate(-110 100)"><Flask c="#B07AA0" /></g>
    <g transform="translate(-30 100)"><Flask c="#6FA06A" tall /></g>
    <g transform="translate(-100 -150)"><Flask c="#D9B04A" tall /></g>
    <g transform="translate(40 -150)"><Flask c="#C9553D" /></g>
  </g>
);
const Chalkboard: React.FC<{ scribble?: boolean }> = ({ scribble = true }) => (
  <g>
    <rect x={-250} y={-150} width={500} height={300} rx={10} {...inked(WOOD)} />
    <rect x={-232} y={-132} width={464} height={264} {...inked(BOARD, L)} />
    {scribble && (
      <g fill="none" stroke="#E6E1D0" strokeWidth={6} strokeLinecap="round" strokeLinejoin="round">
        <path d="M -190 -70 q 30 -40 60 0 t 60 0 t 60 0" />
        <path d="M -190 -10 H 60 M -190 40 H 120" />
        <circle cx={150} cy={-50} r={34} />
        <path d="M 120 50 L 170 50 L 145 90 Z" />
      </g>
    )}
    <rect x={-200} y={150} width={400} height={14} rx={6} {...inked(WOOD_LIGHT, L)} />
  </g>
);
const lab: SetDrawing = {
  bands: [
    { top: 0, color: "#D6D0B0" },
    { top: 1250, color: "#9A7650" },
  ],
  decor: [
    mk("lab-shelfA", 160, 820, -160, -160, 320, 320, () => <g transform="scale(0.8)"><Shelves /></g>),
    mk("lab-shelfB", 920, 820, -160, -160, 320, 320, () => <g transform="scale(0.8)"><Shelves /></g>),
    mk("lab-board", 540, 700, -230, -140, 460, 300, () => <g transform="scale(0.88)"><Chalkboard /></g>),
  ],
  front: "#7A5A38",
};

/* ---- classroom ---- */
const MapBlob: React.FC = () => (
  <g>
    <rect x={-110} y={-90} width={220} height={180} {...inked(PAPER)} />
    <path d="M -70 20 Q -90 -40 -40 -50 Q -10 -70 20 -40 Q 70 -50 60 0 Q 80 40 20 50 Q -20 70 -70 20 Z" {...inked("#9CB07A", L)} />
    <path d="M -110 -90 V 90 M 110 -90 V 90" stroke={INK} strokeWidth={LW} />
  </g>
);
const Clock: React.FC = () => (
  <g>
    <circle r={68} {...inked(PAPER)} />
    {Array.from({ length: 12 }, (_, i) => (
      <path key={i} d="M 0 -56 V -46" stroke={INK} strokeWidth={4} transform={`rotate(${i * 30})`} />
    ))}
    <path d="M 0 0 V -38 M 0 0 L 28 12" stroke={INK} strokeWidth={LW} fill="none" />
    <circle r={6} fill={INK} />
  </g>
);
const classroom: SetDrawing = {
  bands: [
    { top: 0, color: "#D8CDA6" },
    { top: 1100, color: DADO },
    { top: 1280, color: "#B08A5E" },
  ],
  decor: [
    mk("classroom-board", 540, 800, -260, -160, 520, 340, () => <Chalkboard scribble={false} />),
    mk("classroom-map", 160, 700, -120, -100, 240, 200, MapBlob),
    mk("classroom-clock", 920, 600, -80, -80, 160, 160, Clock),
  ],
  front: "#8A5A34",
};

/* ---- field ---- */
const Tree: React.FC = () => (
  <g>
    <path d="M -22 220 L -14 -20 H 14 L 22 220 Z" {...inked(WOOD)} />
    <circle cx={0} cy={-110} r={110} {...inked("#6F9250")} />
    <circle cx={-80} cy={-60} r={70} {...inked("#6F9250")} />
    <circle cx={80} cy={-60} r={70} {...inked("#6F9250")} />
    <circle cx={0} cy={-110} r={104} fill="#6F9250" />
  </g>
);
// a low hedge of bushes on the near grass (a road drawn flat read as a mountain)
const Bushes: React.FC = () => (
  <g>
    {[[-150, 20, 70], [-60, -6, 84], [40, 14, 72], [130, 0, 80]].map(([x, y, r], k) => (
      <circle key={k} cx={x} cy={y} r={r} {...inked(k % 2 ? "#6F9250" : "#7E9F5C")} />
    ))}
    <rect x={-236} y={30} width={472} height={70} fill="#A3B47A" />
  </g>
);
const field: SetDrawing = {
  bands: [
    { top: 0, color: SKY },
    { top: 900, color: HILL },
    { top: 1200, color: "#A3B47A" },
  ],
  decor: [
    mk("field-hills", 540, 920, HILLS_BOX.left, HILLS_BOX.top, HILLS_BOX.width, HILLS_BOX.height, () => <Hills a={HILL2} b={HILL} />),
    mk("field-tree", 880, 1000, -210, -240, 420, 480, Tree),
    mk("field-bushes", 250, 1240, -240, -100, 480, 200, Bushes),
  ],
  front: GRASS,
};

export const SET_DRAWINGS: Record<SetId, SetDrawing> = {
  farm, street, office, palace, castle, deck, market, factory, camp, lab, classroom, field,
};

/** A whole set as one SVG (the sheets draw it this way; the scene draws bands as boxes and decor as sprites). */
export const SetSvg: React.FC<{ set: SetId }> = ({ set }) => {
  const s = SET_DRAWINGS[set];
  if (!s) return null;
  return (
    <g>
      {s.bands.map((b, i) => (
        <rect key={i} x={0} y={b.top} width={1080} height={(s.bands[i + 1]?.top ?? 1600) - b.top} fill={b.color} />
      ))}
      {s.decor.map((d) => (
        <g key={d.id} transform={`translate(${d.x} ${d.y})`}>
          <d.Draw />
        </g>
      ))}
      <rect x={0} y={1600} width={1080} height={320} fill={s.front} />
      <path d="M 0 1600 H 1080" stroke={INK} strokeWidth={LW} />
    </g>
  );
};
