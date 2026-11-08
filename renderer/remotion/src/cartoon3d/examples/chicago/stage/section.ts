// Section staging: strollers on the finished street above the cut; nobody below, where the old street waits.
import { Stage, CamInfo, hh } from "../../../kit/cast";
import { SECTION, RAISE, FPS } from "../story";
import { GENT, LADY, walk, stand } from "../scenes";

const X = (x: number) => SECTION[0] + x, Z = (z: number) => SECTION[2] + z;
export const stageSection = (_id: number, _f: number, t: number, cam: CamInfo, out: Stage) => {
  const t0 = 3240 / FPS;
  for (let k = 0; k < 6; k++) {
    const z = [-1.4, -2.6, -4.0, -5.4, -7.0, -10.8][k], dir = k % 2 ? 1 : -1, x0 = (hh(k, 3) - 0.5) * 10;
    walk(out, cam, t, 650 + k, (k % 2 ? LADY : GENT)(k + 2), { x: X(x0 - dir * 3), y: RAISE + (k === 5 ? 0.12 : 0), z: Z(z) }, { x: X(x0 + dir * 3), y: RAISE + (k === 5 ? 0.12 : 0), z: Z(z) }, t0 - 1, t0 + 5, { expr: k % 2 ? "smile" : "smile_closed" });
  }
  stand(out, cam, t, 660, GENT(5), X(4.6), RAISE, Z(-2.0), { expr: "smile", look: -1 });
};
