// A custom Storybook Atlas prop: a moth, which the library does not have.
// Written to generated/<video_id>/prop-moth.tsx with write_scene_file, and
// listed in the config's customProps as
//   {"id": "moth", "src": "<video_id>/prop-moth", "box": [300, 220], "place": "wall",
//    "states": 1, "acts": ["wobble", "glow"]}
//
// Modelled on the library props (read them with read_scene_file, source
// "installed", e.g. "storybookAtlas/props/things"): drawn with its base at
// (0, 0), x from -150 to 150 and y from -220 to 0, ending 3 px inside the box;
// flat fills from the palette, an ink outline and pencil hatching with Sh, no
// filters, gradients, patterns of its own, text or images. `state` picks the
// drawing; this moth has one.
import { Sh, ellipse } from "../../installed/storybookAtlas/ink";
import { INK, IVORY } from "../../installed/storybookAtlas/palette";

const WING = "#8C7559";
const WING_LOW = "#A08A6C";
const BODY = "#4E3D2E";

export default function Moth({ state }: { state: number }) {
  void state;
  return (
    <g transform="translate(0 -110)">
      {[-1, 1].map((k) => (
        <g key={k} transform={`scale(${k} 1)`}>
          <g transform="rotate(-22 70 -30)">
            <Sh d={ellipse(70, -30, 72, 44)} fill={WING} penOp={0.28} sw={3} />
          </g>
          <g transform="rotate(26 52 34)">
            <Sh d={ellipse(52, 34, 48, 32)} fill={WING_LOW} penOp={0.28} sw={3} />
          </g>
          <circle cx={84} cy={-38} r={15} fill="none" stroke={IVORY} strokeWidth={4} opacity={0.75} />
          <circle cx={84} cy={-38} r={6} fill={INK} />
          <path d="M8 -52 Q24 -92 44 -100" fill="none" stroke={INK} strokeWidth={4} strokeLinecap="round" />
        </g>
      ))}
      <Sh d={ellipse(0, 4, 12, 56)} fill={BODY} penOp={0.25} sw={3} />
    </g>
  );
}
