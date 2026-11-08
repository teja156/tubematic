// River staging: the lamplighter on the north quay, strollers on the south quay, the rower drifting upstream.
import { Stage, CamInfo, q } from "../../../kit/cast";
import { RIVER, FPS } from "../story";
import { GENT, LADY, WORKER, stand, walk } from "../scenes";
import { LAMPS, lampPos, lampOn, boatAt, zc, HALF, QUAY } from "../sets/river";

const X = (x: number) => RIVER[0] + x, Z = (z: number) => RIVER[2] + z;
export const stageRiver = (id: number, f: number, t: number, cam: CamInfo, out: Stage) => {
  // the lamplighter: at the lamp the camera sees best, reaching up as it lights
  const k = id === 40 ? 6 : 8, [lx, ly, lz] = lampPos(LAMPS[k]);
  const reach = Math.abs(f - lampOn(k)) < 14;
  stand(out, cam, t, 900, { ...WORKER(3), jacket: "#3a4a6a", hat: "cap", cap: "#2e2a36", holds: "lantern", heldColor: "#ffd27a" }, X(lx + 0.6), ly, Z(lz + 0.4),
    { expr: reach ? "smile" : "neutral", wave: reach ? q(0.6, 10) : undefined, look: -1 });
  // strollers on the south quay, backlit
  for (let i = 0; i < 4; i++) {
    const x0 = -26 + i * 9, z0 = zc(x0) + HALF + 1.6;
    walk(out, cam, t, 910 + i, (i % 2 ? LADY : GENT)(i + 1), { x: X(x0), y: QUAY, z: Z(z0) }, { x: X(x0 + 5), y: QUAY, z: Z(zc(x0 + 5) + HALF + 1.6) }, 3382 / FPS - 1, 3614 / FPS, { expr: "smile_closed" });
  }
  // the rower, sitting in the drifting boat
  const [bx, by, bz] = boatAt(f);
  stand(out, cam, t, 920, { ...GENT(4), hat: "cap", cap: "#5a4030", coat: undefined }, X(bx), by - 0.15, Z(bz), { mode: "sit", expr: "smile_closed" }, 0.9);
};
