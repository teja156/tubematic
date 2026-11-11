/*
 * Props of rooms and houses: things that light, open and stand about.
 * Each is drawn with its base at the origin (see ./types.ts).
 */
import { Sh, circle, ellipse, poly, rect } from "../ink";
import { CREAM, GOLD, INK, STARGOLD, WOOD, WOOD_DARK } from "../palette";
import type { PropEntry } from "./types";

/** An oil lamp on a short stand. State 1: lit. */
const Lamp: PropEntry["draw"] = ({ state }) => (
  <g>
    {state === 1 && <path d={circle(0, -150, 64)} fill={STARGOLD} opacity={0.35} />}
    <Sh d={ellipse(0, -15, 62, 12)} fill={GOLD} pen="none" sw={3} />
    <Sh d={poly([[-14, -14], [14, -14], [10, -70], [-10, -70]])} fill={GOLD} penOp={0.25} sw={3} />
    <Sh d={ellipse(0, -96, 46, 32)} fill={GOLD} penOp={0.25} sw={3} />
    <Sh d={`M-24 -116 Q-34 -170 -16 -206 L16 -206 Q34 -170 24 -116Z`} fill={state === 1 ? "#F6E7B8" : CREAM} pen="none" sw={3} op={0.92} />
    {state === 1 && <path d={`M0 -128 q-12 -20 0 -44 q12 24 0 44z`} fill="#E9A23B" stroke={INK} strokeWidth={2} />}
    {state === 0 && <path d="M0 -128 v-14" stroke={INK} strokeWidth={4} strokeLinecap="round" />}
    <Sh d={rect(-20, -214, 40, 10)} fill={GOLD} pen="none" sw={2.5} />
  </g>
);

/** A panelled door in its frame. State 1: open, light spilling out. */
const Door: PropEntry["draw"] = ({ state }) => (
  <g>
    <Sh d={rect(-118, -473, 236, 470)} fill={WOOD_DARK} pen="l" penOp={0.15} sw={4} />
    {state === 0 ? (
      <g>
        <Sh d={rect(-98, -452, 196, 449)} fill={WOOD} pen="l" penOp={0.16} sw={3} />
        <path d={rect(-78, -430, 156, 170)} fill="none" stroke={INK} strokeWidth={2.5} opacity={0.6} />
        <path d={rect(-78, -230, 156, 200)} fill="none" stroke={INK} strokeWidth={2.5} opacity={0.6} />
        <path d={circle(66, -240, 9)} fill={GOLD} stroke={INK} strokeWidth={2} />
      </g>
    ) : (
      <g>
        <path d={rect(-98, -452, 196, 449)} fill="#FFF6D8" stroke={INK} strokeWidth={3} />
        <Sh d={poly([[-98, -452], [-150, -476], [-150, -3], [-98, -3]])} fill={WOOD} pen="l" penOp={0.16} sw={3} />
        <path d={circle(-140, -230, 7)} fill={GOLD} stroke={INK} strokeWidth={2} />
      </g>
    )}
    <Sh d={rect(-128, -484, 256, 18)} fill={WOOD} pen="none" sw={3} />
  </g>
);

export const ROOM_PROPS: Record<string, PropEntry> = {
  lamp: { label: "oil lamp", box: [140, 232], place: "floor", states: 2, acts: ["switch", "glow", "wobble"], draw: Lamp },
  door: { label: "door", box: [312, 500], place: "floor", states: 2, acts: ["switch"], portal: [0, -226], draw: Door },
};
