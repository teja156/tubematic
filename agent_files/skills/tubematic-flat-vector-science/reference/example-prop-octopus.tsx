// A custom Flat Vector Science prop: an octopus, which the library does not have.
// Written to generated/<video_id>/prop-octopus.tsx with write_scene_file, and
// listed in the config's customProps as
//   {"id": "octopus", "src": "<video_id>/prop-octopus", "box": [360, 360]}
//
// Modelled on the library props (read them with read_scene_file, source
// "installed", "flatVector/props"): one still drawing centred on (0, 0) inside
// its box (x from -180 to 180, y from -180 to 180 here), flat two-tone shapes
// from Toon with a lighter rim and a darker shadow plane, no outlines, no text,
// no images, no filters or gradients of its own (GlowDot is the one glow).
// It never moves itself: the renderer drifts, bobs and pops it.
import { Eye, Toon, circleD } from "../../installed/flatVector/toon";

const BASE = "#c2557a";
const SHADE = "#963e5d";
const RIM = "#e98aac";

export default function Octopus() {
  return (
    <g>
      {[-120, -70, -25, 25, 70, 120].map((x, i) => (
        <path
          key={i}
          d={`M ${x * 0.5} 40 C ${x * 0.8} 100 ${x * 1.2} 120 ${x * 1.25} ${160 - (i % 2) * 20}`}
          stroke={i % 2 ? SHADE : BASE}
          strokeWidth={26}
          strokeLinecap="round"
          fill="none"
        />
      ))}
      <Toon d={circleD(0, -40, 110)} base={BASE} shade={SHADE} rim={RIM} rimDy={8} shadeDx={26} shadeDy={22}>
        <circle cx={-40} cy={-90} r={12} fill={SHADE} />
        <circle cx={30} cy={-110} r={8} fill={SHADE} />
      </Toon>
      <Eye x={-36} y={-20} r={14} />
      <Eye x={36} y={-20} r={14} />
    </g>
  );
}
