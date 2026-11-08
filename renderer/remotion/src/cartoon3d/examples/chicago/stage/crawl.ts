// Crawlspace staging: diggers, a man setting a screw, the row of men at the bars, the foreman's whistle, the unison
// quarter turns (TURNS), the masons. Positions are local to the crawl set and offset by CRAWL here.
import { Stage, CamInfo, person, blob, lidAt, Who, q, hh } from "../../../kit/cast";
import { Expr, SideOpts, fxBlast, fxDirt } from "../../../kit/toon";
import { CRAWL, TURNS, TURN_LEN, WHISTLES, FPS, smooth, clamp01 } from "../story";
import { WORKER, FOREMAN, stand, pusher, fx } from "../scenes";
import { CRAWL_XS, CRAWL_ROWS } from "../sets/crawl";

const X = (x: number) => CRAWL[0] + x, Z = (z: number) => CRAWL[2] + z;
/** push pose for the turns: wind up just before, shove through the turn, ease back */
const turnPose = (f: number, k = 0) => {
  let pz = 0.25;
  for (const t0 of TURNS) {
    const d = f - t0 + (k % 3);
    if (d >= -6 && d < 0) pz = Math.max(pz, 0.25 + 0.15 * smooth((d + 6) / 6));
    else if (d >= 0 && d < TURN_LEN) pz = Math.max(pz, 0.4 + 0.6 * Math.sin((d / TURN_LEN) * Math.PI * 0.5));
    else if (d >= TURN_LEN && d < TURN_LEN + 10) pz = Math.max(pz, 1 - 0.75 * smooth((d - TURN_LEN) / 10));
  }
  return pz;
};
const whistleFx = (out: Stage, f: number, x: number, y: number, z: number) => {
  for (const w of WHISTLES) if (f >= w && f < w + 12) { const u = (f - w) / 12; fx(out, `blast${q(u, 30)}`, 400, 300, (p) => fxBlast(p, q(u, 30)), x + 0.45, y, z, 0.9, 0.68); }
};
/** the men of the front row, one at every screw from x0 to x1, standing to the screw's right facing it */
const row = (out: Stage, cam: CamInfo, t: number, f: number, x0: number, x1: number, rowZ = 0, seed = 700, expr?: (i: number) => Expr) => {
  CRAWL_XS.forEach((x, k) => {
    if (x < x0 || x > x1) return;
    const i = seed + k;
    pusher(out, cam, t, i, WORKER(i), X(x + 0.5), 0, Z(rowZ - 0.22), false, turnPose(f, k), expr ? expr(i) : k % 4 === 1 ? "pained" : "stern", [445, 575]);
  });
};
const foreman = (out: Stage, cam: CamInfo, t: number, f: number, x: number, z: number) => {
  const blowing = WHISTLES.some((w) => f >= w - 4 && f < w + 14);
  const raised = f >= 1722 || blowing;
  stand(out, cam, t, 760, FOREMAN, X(x), 0, Z(z), { prop: raised ? "whistle" : null, expr: blowing ? "whistle" : "stern", facing: -1 });
  whistleFx(out, f, X(x) + 0.05, 1.62, Z(z));
};

export const stageCrawl = (id: number, f: number, t: number, cam: CamInfo, out: Stage) => {
  switch (id) {
    case 19: { // crews dig under the foundations
      for (let k = 0; k < 3; k++) {
        const ph = ((t * 0.9 + hh(k, 2)) % 1), dig = ph < 0.5 ? ph * 2 : 1 - (ph - 0.5) * 2;
        stand(out, cam, t, 720 + k, WORKER(720 + k), X(-2.6 + k * 1.5), 0, Z(1.0 - (k % 2) * 1.4), { prop: ["shovel", q(dig, 20)], expr: k === 1 ? "pained" : "stern", facing: k % 2 ? 1 : -1 });
        if (ph > 0.5 && ph < 0.95) { const u = (ph - 0.5) / 0.45; fx(out, `dirt${q(u, 30)}`, 500, 400, (p) => fxDirt(p, q(u, 30)), X(-2.0 + k * 1.5), 0.85, Z(1.2 - (k % 2) * 1.4), 1.0, 0.8); }
      }
      break;
    }
    case 20: { // setting the screws: one man fits a screw, others carry them down the rows
      pusher(out, cam, t, 730, WORKER(730), X(6.0 + 0.62), 0, Z(0.32), false, 0.6 + 0.2 * Math.sin(t * 3), "stern", [445, 600]);
      row(out, cam, t, f, -6, 2, -2.4, 740, () => "neutral");
      break;
    }
    case 21: case 22: case 23: { // a man at every screw; the signal; every man turns his screw
      row(out, cam, t, f, -15, 12, 0, 700);
      row(out, cam, t, f, -15, 12, -2.4, 800);
      row(out, cam, t, f, -15, 12, -4.8, 900);
      foreman(out, cam, t, f, id === 23 ? 13.2 : 7.4, id === 23 ? 1.6 : -1.1);
      break;
    }
    case 24: break; // the beam rises a fraction of an inch: the rule alone
    case 25: { // masons build the new foundation underneath
      for (let k = 0; k < 2; k++) {
        const ph = (t * 0.8 + k * 0.5) % 1, tr = ph < 0.6 ? ph / 0.6 : 1 - (ph - 0.6) / 0.4;
        stand(out, cam, t, 780 + k, { ...WORKER(780 + k), jacket: "#e0d4bc", hat: "cap", cap: "#8a7a6a" }, X(k ? -4.7 : -5.6), 0, Z(k ? -5.2 : -5.95), { prop: ["trowel", q(tr, 20)], expr: k ? "smile_closed" : "stern", facing: k ? -1 : 1 });
      }
      stand(out, cam, t, 782, WORKER(782), X(-3.1), 0, Z(-4.9), { prop: "basket", expr: "neutral" }); // the hod carrier
      row(out, cam, t, f, -12, 4, -2.4, 800);
      break;
    }
    case 38: { // one quarter turn at a time: a single man, a single screw
      foreman(out, cam, t, f, 2.6, -1.6);
      const so: SideOpts = { mode: "push", pose: q(turnPose(f), 40), expr: "stern", blink: lidAt(t, 700), hand: [445, 575] };
      const who: Who = { i: 700, o: WORKER(700), okey: "w700" };
      out.places.push(person(cam, who, X(0.5), 0, Z(-0.22), { side: true, mirror: true }, {}, so));
      blob(out, X(0.5), 0, Z(-0.22));
      break;
    }
  }
  void CRAWL_ROWS; void clamp01; void FPS;
};
