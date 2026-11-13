// A ticket, drawn for one video: a prop the library lacks, modelled on the
// library's props. Centred on (0, 0) inside a 200 x 120 box, its label in the
// middle. Hatched cream paper with notched ends and a dashed tear line drawn as
// short ink strokes.
// {"id": "ticket", "w": 200, "h": 120, "text": 10}
import React from "react";
import { CREAM_TONE, Hatches, INK, Inked, MONO, inkLine, polyPath } from "../../installed/processCast/ink";

export default function Ticket({ text }: { text: string }) {
  const body = polyPath([[-92, -50], [92, -50], [92, -14], [78, 0], [92, 14], [92, 50], [-92, 50], [-92, 14], [-78, 0], [-92, -14]], 611, 2);
  const size = Math.min(30, 150 / Math.max(text.length * 0.62, 1));
  return (
    <g>
      <Hatches tones={{ cream: CREAM_TONE }} />
      <Inked d={body} k="cream" tone={CREAM_TONE} />
      {[-36, -12, 12, 36].map((y) => (
        <path key={y} d={inkLine([52, y - 8], [52, y + 6], 620 + y, 0.8, 2)} stroke={INK} strokeWidth={3} fill="none" />
      ))}
      <text x={-14} y={size * 0.36} textAnchor="middle" fontFamily={MONO} fontWeight={700} fontSize={size} fill={INK}>{text}</text>
    </g>
  );
}
