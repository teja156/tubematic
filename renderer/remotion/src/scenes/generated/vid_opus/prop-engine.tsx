// A custom Storybook Atlas prop: Babbage's Analytical Engine, which the library
// does not have. Listed in customProps as
//   {"id": "engine", "src": "vid_opus/prop-engine", "box": [460, 420], "place": "floor",
//    "states": 2, "acts": ["cycle", "shake", "glow", "wobble"]}
//
// Drawn with its base at (0, 0), x from -230 to 230 and y from -420 to 0, ending
// 3 px inside the box. An iron frame on a wooden plinth: four columns of stacked
// brass figure wheels (the mill) geared together along the top, a big spoked
// drive wheel with a crank handle on the right, and a folded chain of punched
// cards feeding in from a brass prism on the left. State 1: the crank turned
// half round, the gears and wheels a notch on, the cards moved on one.
import { Sh, circle, poly, rect, rounded } from "../../installed/storybookAtlas/ink";
import { CREAM, GOLD, INK, WOOD, WOOD_DARK } from "../../installed/storybookAtlas/palette";

const IRON = "#4E4A47";
const STEEL = "#8E938F";
const COPPER = "#A8704A";

type Pt = [number, number];
const rad = (deg: number) => (deg * Math.PI) / 180;
const pt = (cx: number, cy: number, r: number, deg: number): Pt => [cx + r * Math.cos(rad(deg)), cy + r * Math.sin(rad(deg))];

/** A toothed wheel's outline. */
function gear(cx: number, cy: number, ro: number, ri: number, n: number, phase: number) {
  const step = 360 / n;
  const pts: Pt[] = [];
  for (let k = 0; k < n; k++) {
    const a = phase + k * step;
    pts.push(pt(cx, cy, ri, a - 0.3 * step), pt(cx, cy, ro, a - 0.16 * step), pt(cx, cy, ro, a + 0.16 * step), pt(cx, cy, ri, a + 0.3 * step));
  }
  return poly(pts);
}

const COLUMNS = [-112, -52, 8, 68];
const WHEELS = 6; // figure wheels per column
const WHEEL_Y0 = -100; // the lowest wheel's middle
const WHEEL_STEP = 40;

/** Holes punched in each card: positions along it, 0 to 4. */
const HOLES = [[0, 2, 3], [1, 4], [0, 1, 3], [2, 4], [0, 3, 4], [1, 2], [0, 4], [1, 3, 4], [2]];

export default function Engine({ state }: { state: number }) {
  const on = state === 1;
  const notch = on ? 12 : 0; // degrees the top gears turn
  const crank = on ? 120 : -60; // where the crank handle points
  const [hx, hy] = pt(162, -150, 42, crank);
  return (
    <g>
      {/* plinth and iron bed */}
      <Sh d={rect(-224, -40, 448, 37)} fill={WOOD_DARK} pen="l" penOp={0.15} sw={3} />
      <Sh d={rect(-170, -64, 392, 26)} fill={IRON} pen="l" penOp={0.15} sw={3} />

      {/* the frame: two iron posts and a top beam */}
      <Sh d={rect(-162, -392, 20, 330)} fill={IRON} pen="l" penOp={0.15} sw={3} />
      <Sh d={rect(200, -392, 20, 330)} fill={IRON} pen="l" penOp={0.15} sw={3} />
      <Sh d={rect(-170, -414, 392, 26)} fill={IRON} pen="l" penOp={0.15} sw={3} />

      {/* the mill: four columns of brass figure wheels on steel shafts */}
      {COLUMNS.map((cx, c) => (
        <g key={cx}>
          <Sh d={rect(cx - 5, -388, 10, 326)} fill={STEEL} pen="none" sw={2} />
          {Array.from({ length: WHEELS }, (_, k) => {
            const y = WHEEL_Y0 - k * WHEEL_STEP;
            const tick = (((k * 9 + c * 5 + (on ? 8 : 0)) % 36) - 18);
            return (
              <g key={k}>
                <Sh d={rounded(cx - 25, y - 12, 50, 24, 9)} fill={k % 2 === 0 ? GOLD : "#C4A464"} penOp={0.22} sw={2.5} />
                <path d={`M${cx + tick} ${y - 7}v14`} fill="none" stroke={INK} strokeWidth={3} strokeLinecap="round" opacity={0.7} />
              </g>
            );
          })}
        </g>
      ))}

      {/* gears along the top, meshing column to column */}
      {COLUMNS.map((cx, c) => (
        <g key={`g${cx}`}>
          <Sh d={gear(cx, -364, 29, 22, 10, (c % 2 === 0 ? notch : -notch) + c * 18)} fill={c % 2 === 0 ? GOLD : COPPER} penOp={0.2} sw={2.5} />
          <path d={circle(cx, -364, 6)} fill={INK} />
        </g>
      ))}

      {/* the big drive wheel and its crank */}
      <path d={`M68 -364 L162 -150`} fill="none" stroke={INK} strokeWidth={10} strokeLinecap="round" />
      <path d={`M68 -364 L162 -150`} fill="none" stroke={STEEL} strokeWidth={5} strokeLinecap="round" />
      <g fillRule="evenodd">
        <Sh
          d={
            gear(162, -150, 56, 47, 16, notch) +
            [0, 90, 180, 270].map((a) => {
              const [x, y] = pt(162, -150, 28, a + 45 + notch);
              return circle(x, y, 11);
            }).join("")
          }
          fill={GOLD}
          penOp={0.22}
          sw={3}
        />
      </g>
      <path d={`M162 -150 L${hx} ${hy}`} fill="none" stroke={INK} strokeWidth={13} strokeLinecap="round" />
      <path d={`M162 -150 L${hx} ${hy}`} fill="none" stroke={IRON} strokeWidth={8} strokeLinecap="round" />
      <Sh d={circle(hx, hy, 11)} fill={WOOD} penOp={0.2} sw={2.5} />
      <Sh d={circle(162, -150, 12)} fill={WOOD_DARK} pen="none" sw={2.5} />

      {/* the card reader: a brass prism and the folded chain of punched cards */}
      <Sh d={rect(-222, -392, 52, 44)} fill={GOLD} penOp={0.22} sw={3} />
      {[-210, -196, -182].map((x) => <path key={x} d={circle(x, -370, 4)} fill={INK} />)}
      {Array.from({ length: 9 }, (_, k) => {
        const y = -326 + k * 30;
        const tilt = k % 2 === 0 ? -9 : 9;
        const holes = HOLES[(k + (on ? 1 : 0)) % HOLES.length].map((p) => circle(-214 + p * 9, y + 9, 3)).join("");
        return (
          <g key={k} transform={`rotate(${tilt} -196 ${y + 9})`}>
            <Sh d={rect(-222, y, 52, 18)} fill={CREAM} penOp={0.12} sw={2.2} />
            <path d={holes} fill={INK} />
          </g>
        );
      })}
      <path d="M-170 -370 H-162" fill="none" stroke={INK} strokeWidth={6} />
    </g>
  );
}
