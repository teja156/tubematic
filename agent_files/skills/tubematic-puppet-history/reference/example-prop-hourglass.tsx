// An hourglass, drawn for one video: a hand prop the library lacks, modelled on
// the library's props. Centred on (0, 0) inside a 110 x 170 box. Wooden caps and
// posts, pale glass, sand in the lower bulb, dark brown ink outlines at LW.
// {"id": "hourglass", "w": 110, "h": 170, "text": 0}
import React from "react";
import { INK, LW, PAPER, WOOD, inked } from "../../installed/puppetHistory/ink";

export default function Hourglass() {
  return (
    <g>
      <path d="M -34 -64 C -34 -20 -8 -14 -8 0 C -8 14 -34 20 -34 64 L 34 64 C 34 20 8 14 8 0 C 8 -14 34 -20 34 -64 Z" {...inked(PAPER, LW * 0.8)} />
      <path d="M -26 60 C -24 36 -10 30 0 22 C 10 30 24 36 26 60 Z" fill="#D8B66A" />
      <path d="M 0 2 L 0 22" stroke="#D8B66A" strokeWidth={4} />
      <rect x={-48} y={-80} width={96} height={18} rx={6} {...inked(WOOD)} />
      <rect x={-48} y={62} width={96} height={18} rx={6} {...inked(WOOD)} />
      <path d="M -42 -62 V 62 M 42 -62 V 62" stroke={INK} strokeWidth={LW} strokeLinecap="round" />
    </g>
  );
}
