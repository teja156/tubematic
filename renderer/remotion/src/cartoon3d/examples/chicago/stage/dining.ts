// Dining-room staging: guests keep eating while the hotel rises; the teacup trembles, a guest glances at it, shrugs
// and goes back to his newspaper (shot 35). Positions local to the dining set, offset by DINING here.
import { Stage, CamInfo, q, LEAD } from "../../../kit/cast";
import { Expr, Prop, fxSteam } from "../../../kit/toon";
import { DINING, FPS } from "../story";
import { GENT, LADY, stand, fx } from "../scenes";
import { TABLES, CUP, tremble } from "../sets/dining";

const X = (x: number) => DINING[0] + x, Z = (z: number) => DINING[2] + z;
const W = (t: number, word: number) => t >= word / FPS - LEAD;

export const stageDining = (id: number, f: number, t: number, cam: CamInfo, out: Stage) => {
  // every table but the hero's: two or three diners, eating (cups up and down, chatting)
  TABLES.forEach(([x, z], ti) => {
    if (ti === 0) return;
    for (let k = 0; k < 3; k++) {
      const a = (k / 4) * Math.PI * 2 + 0.4 + (ti % 2) * 0.8, i = 840 + ti * 4 + k;
      const sip = ((t * 0.35 + k * 0.33 + ti * 0.2) % 1) < 0.3;
      const o = (k + ti) % 2 ? LADY(i) : GENT(i);
      const expr: Expr = sip ? "smile_closed" : (["smile", "grin", "neutral", "laugh"] as Expr[])[(k + ti) % 4];
      const prop: Prop = sip ? "teacup" : null;
      stand(out, cam, t, i, { ...o, hat: o.hat === "tophat" ? "hair" : o.hat, hair: "#4a3020" }, X(x + Math.cos(a) * 1.05), 0, Z(z + Math.sin(a) * 1.05), { mode: "sit", expr, prop });
    }
  });
  // the hero table: the newspaper reader faces the lens, a lady across to his right
  // he glances at the rattling cup (calm), shrugs, and reads on: never alarmed
  const glance = id === 35 && W(t, 2914) && !W(t, 2932), shrug = id === 35 && W(t, 2932) && !W(t, 2958);
  // he "sits": a standing card sunk through the floor behind the table, so the paper is in his hands
  stand(out, cam, t, 830, { ...GENT(1), hat: "hair", hair: "#5a3b2a", holds: glance ? undefined : "paper", moustache: "#5a3b2a" }, X(-0.25), -0.48, Z(-0.7),
    { mode: "stand", expr: glance ? "neutral" : shrug ? "smile_closed" : "neutral", look: glance ? 1 : 0, headTilt: shrug ? 10 : 0 });
  stand(out, cam, t, 831, LADY(2), X(1.05), 0, Z(-0.35), { mode: "sit", expr: id === 33 ? "smile" : "smile_closed", prop: id === 33 && (t % 2) < 0.8 ? "teacup" : null });
  // steam from the cup; tea rings when it trembles
  const u = (t * 0.6) % 1;
  fx(out, `steam${q(u, 30)}`, 220, 400, (p) => fxSteam(p, q(u, 30)), X(CUP[0]), CUP[1] + 0.2, Z(CUP[2]), 0.11, 0.2, { soft: true });
  void tremble; void f;
};
