// A trophy, drawn for one video: a prop the library lacks, modelled on the
// library's props. Centred on (0, 0) inside a 180 x 220 box. Flat yellow with
// gold halftone dots on its shaded side, heavy black ink outlines drawn last.
// {"id": "trophy", "w": 180, "h": 220, "text": 0}
import React from "react";
import { Dots, INK, WHITE, YEL } from "../../installed/comicPanels/ink";

const CUP = "M -56 -96 H 56 V -40 C 56 0, 30 22, 0 26 C -30 22, -56 0, -56 -40 Z";

export default function Trophy() {
  return (
    <g>
      <Dots id="trophy-gold" color="#d99a00" r={2.6} gap={10} />
      <clipPath id="trophy-clip"><path d={CUP} /></clipPath>
      <path d="M -56 -80 C -96 -80, -96 -20, -40 -10" fill="none" stroke={INK} strokeWidth={9} />
      <path d="M 56 -80 C 96 -80, 96 -20, 40 -10" fill="none" stroke={INK} strokeWidth={9} />
      <path d={CUP} fill={YEL} />
      <rect x={14} y={-100} width={46} height={130} fill="url(#trophy-gold)" clipPath="url(#trophy-clip)" />
      <rect x={-38} y={-86} width={12} height={60} rx={6} fill={WHITE} opacity={0.85} />
      <path d={CUP} fill="none" stroke={INK} strokeWidth={7} strokeLinejoin="round" />
      <path d="M -12 26 H 12 V 62 H -12 Z" fill={YEL} stroke={INK} strokeWidth={6} />
      <path d="M -54 62 H 54 V 100 H -54 Z" fill="#8a5cd0" stroke={INK} strokeWidth={7} strokeLinejoin="round" />
    </g>
  );
}
