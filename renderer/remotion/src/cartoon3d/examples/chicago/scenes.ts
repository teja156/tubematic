// Chicago's staging: who stands where, doing what, in every shot (the skill's cast.ts stage(), written per set).
// Reactions land 0-3 frames before their word (LEAD); every card is lit by the scene sun; standing cards get the
// skill's contact blob + sun tail.
import * as THREE from "three";
import { Stage, CamInfo, prepare, person, blob, lidAt, Who, hh, q, LEAD, viewOf } from "../../kit/cast";
import { Pen, Outfit, Expr, FrontOpts, SideOpts, Prop, SKINS, horseSide, fxMud, fxFlies, fxDirt, fxBlast, fxSteam, fxTremble, fxBurst, fxPuff } from "../../kit/toon";
import { SHOTS, FPS, RAISE, NZ, SZ, WALK, WALK_Y, HERO, ROW, TREMONT, WAGON, PLANK, liftAt, fillAt, turnsAt, TURNS, TURN_LEN, WHISTLES, smooth, lin, clamp01, CRAWL, DINING, SECTION, RIVER } from "./story";
import { stageCrawl } from "./stage/crawl";
import { stageDining } from "./stage/dining";
import { stageSection } from "./stage/section";
import { stageRiver } from "./stage/river";

// ---------------- the cast ----------------
const COATS = ["#3f6fb5", "#8c3b4a", "#5d7a3a", "#b5653f", "#2f5f6a", "#7b5ac9", "#6a4a3a", "#3a5a8a"];
export const GENT = (v = 0): Outfit => ({ jacket: ["#2f3550", "#4a3a3a", "#3a4a3a", "#5a4a6a"][v % 4], pants: "#3b3f52", boots: "#2a2026", hat: "tophat", coat: "tails",
  skin: SKINS[v % 4], moustache: v % 2 ? "#4a3426" : undefined });
export const LADY = (v = 0): Outfit => ({ jacket: COATS[(v + 2) % 8], pants: "#3b3f52", boots: "#4a3426", hat: "bonnet", dress: ["#d9a441", "#c25a7a", "#5a8fc2", "#7aa65a", "#c2809a"][v % 5], skin: SKINS[(v + 1) % 4] });
export const WORKER = (v = 0): Outfit => ({ jacket: ["#c9b48a", "#8a9ab0", "#b5653f", "#9aa070", "#d8c8a8"][v % 5], pants: ["#4a4a5a", "#5a4a3a", "#3a4a5a"][v % 3], boots: "#3a2a20",
  hat: v % 3 === 2 ? "hair" : "cap", cap: ["#4a4a4a", "#6a5040", "#3a4a5a"][v % 3], hair: "#4a3020", skin: SKINS[v % 4], moustache: v % 4 === 1 ? "#4a3426" : undefined });
export const FOREMAN: Outfit = { jacket: "#5a4a3a", pants: "#3b3f52", boots: "#2a2026", hat: "cap", cap: "#2e2a36", moustache: "#3a2a20", build: "stout", skin: SKINS[1] };
export const SHOPKEEP: Outfit = { jacket: "#efe8d8", pants: "#3b3f52", boots: "#2a2026", hat: "hair", hair: "#5a3b2a", belt: "#8a5a34", moustache: "#5a3b2a", skin: SKINS[0] };
export const PULLMAN: Outfit = { jacket: "#22283a", pants: "#2e3040", boots: "#1d1b22", hat: "tophat", coat: "tails", beard: "#4a3020", skin: SKINS[0], buttons: "#c9a24e" };
export const DRIVER: Outfit = { jacket: "#6a4a3a", pants: "#4a4a5a", boots: "#3a2a20", hat: "cap", cap: "#5a4030", moustache: "#4a3020", skin: SKINS[3] };
const okeyOf = (o: Outfit) => JSON.stringify(o).length + "_" + (o.jacket + (o.dress ?? "") + (o.hat ?? "")).replace(/#/g, "");

type Spot = { x: number; y: number; z: number };
/** someone standing still (front view), optional prop/wave/expression changes at word times */
export const stand = (out: Stage, cam: CamInfo, t: number, i: number, o: Outfit, x: number, y: number, z: number, opts: Partial<FrontOpts> = {}, scale = 1) => {
  const who: Who = { i, o, okey: okeyOf(o) };
  out.places.push(person(cam, who, x, y, z, { side: false, mirror: false }, { mode: "stand", blink: lidAt(t, i), ...opts }, {}, scale));
  blob(out, x, y, z, scale);
};
/** someone walking from a to b over [t0, t1] (s), front or side view picked from the camera like the bridge's column */
export const walk = (out: Stage, cam: CamInfo, t: number, i: number, o: Outfit, a: Spot, b: Spot, t0: number, t1: number, opts: { expr?: Expr; prop?: Prop; scale?: number; pace?: number } = {}) => {
  const u = clamp01((t - t0) / (t1 - t0)), x = a.x + (b.x - a.x) * u, y = a.y + (b.y - a.y) * u, z = a.z + (b.z - a.z) * u;
  const dx = b.x - a.x, dz = b.z - a.z, L = Math.hypot(dx, dz) || 1, moving = t > t0 && t < t1;
  const speed = L / Math.max(0.1, t1 - t0), cad = (opts.pace ?? 1) * speed / 1.4; // 0.7 m per step
  const phase = moving ? q((((t - t0) * cad + hh(i, 5)) % 1 + 1) % 1, 120) : 0;
  const view = viewOf(cam, x, z, dx / L, dz / L);
  const who: Who = { i, o, okey: okeyOf(o) };
  const fo: FrontOpts = { mode: moving ? "stroll" : "stand", phase, expr: opts.expr ?? "neutral", prop: opts.prop ?? null, blink: lidAt(t, i) };
  const so: SideOpts = { mode: moving ? "march" : "stand", phase, expr: opts.expr ?? "neutral", stomp: 0.5, stride: 0.875 * view.fs, blink: lidAt(t, i) };
  out.places.push(person(cam, who, x, y, z, view, fo, so, opts.scale ?? 1));
  blob(out, x, y, z, opts.scale ?? 1);
};
/** a worker at a screw or a bar, side view, pushing (pose 0..1) */
export const pusher = (out: Stage, cam: CamInfo, t: number, i: number, o: Outfit, x: number, y: number, z: number, faceRight: boolean, pose: number, expr: Expr = "stern", hand: [number, number] = [455, 640]) => {
  const who: Who = { i, o, okey: okeyOf(o) };
  const so: SideOpts = { mode: "push", pose: q(pose, 40), expr, blink: lidAt(t, i), hand };
  const p = person(cam, who, x, y, z, { side: true, mirror: !faceRight }, {}, so);
  out.places.push(p);
  blob(out, x, y, z);
};
export const fx = (out: Stage, key: string, cw: number, ch: number, draw: (p: Pen) => void, x: number, y: number, z: number, w: number, h: number, extra: Partial<Stage["fx"][number]> = {}) =>
  out.fx.push({ key, cw, ch, draw, x, y, z, w, h, ...extra });
/** the horse: a side-view card, hooves at y */
export const horse = (out: Stage, cam: CamInfo, t: number, x: number, y: number, z: number, strain: number, step: number, mirror = false) => {
  const s = q(strain, 10), st = q(step, 12), bl = lidAt(t, 501) > 0.5 ? 1 : 0;
  const right = cam.right, facingRight = (right.x >= 0) !== mirror;
  out.places.push({ key: `horse|${s}|${st}|${bl}`, x, y, z, mirror: !facingRight, draw: (p) => horseSide(p, { strain: s, step: st, blink: bl }), size: [1000, 700, 1], geo: HORSE_GEO });
};
const HORSE_GEO = (() => { const g = new THREE.PlaneGeometry(2.6, 1.82); g.translate(0, 1.82 / 2 - (20 / 700) * 1.82, 0); return g; })();
/** a loop phase for crowd idles */
const loop = (t: number, i: number, per = 1.4) => (((t / per + hh(i, 7)) % 1) + 1) % 1;

// ---------------- the street ----------------
const W = (t: number, word: number) => t >= word / FPS - LEAD; // at/after a word (frame number)

/** the gentleman on the plank (seg 1): walks the plank, steps off at "step" (f 98) and sinks */
const GENT_STEP = 98;
const gentleman = (out: Stage, cam: CamInfo, f: number, t: number) => {
  const zA = -8.2, zB = PLANK.z1 - 0.15;
  if (f < GENT_STEP) {
    const u = clamp01(f / GENT_STEP), z = zA + (zB - zA) * u, y = WALK_Y - 0.03 + (0.09 - WALK_Y) * clamp01((z - PLANK.z0) / (PLANK.z1 - PLANK.z0));
    // a careful balancing step: a stroll on the spot, moving forward along the plank
    const who: Who = { i: 1, o: GENT(0), okey: "gent0" };
    out.places.push(person(cam, who, PLANK.x, y, z, { side: false, mirror: false }, { mode: "stroll", phase: q((t * 0.9) % 1, 120), expr: f > 70 ? "nervous" : "neutral", blink: lidAt(t, 1), wave: q(0.4 * Math.sin(t * 3), 30) }, {}));
    blob(out, PLANK.x, y, z);
    return;
  }
  const k = smooth((f - GENT_STEP) / 10), y = 0.06 - 0.5 * k, z = zB + 0.45 * k;
  stand(out, cam, t, 1, GENT(0), PLANK.x + 0.05, y, z, { expr: f < GENT_STEP + 3 ? "nervous" : "shock", tilt: -4 * k });
  if (f >= GENT_STEP && f < GENT_STEP + 16) { const u = (f - GENT_STEP) / 16; fx(out, `mud${q(u, 30)}`, 500, 500, (p) => fxMud(p, q(u, 30)), PLANK.x + 0.05, 0.25, z + 0.2, 1.2, 1.2); }
};
/** the stuck wagon: horse straining, the driver flicking the reins */
const wagonTeam = (out: Stage, cam: CamInfo, t: number, f: number, strain = 0.8) => {
  horse(out, cam, t, WAGON[0] + 4.1, -0.45, WAGON[2], strain + 0.1 * Math.sin(t * 3), loop(t, 3, 1.2) * 0.4);
  // mud thrown up by the hooves and the stuck wheel, every 0.8 s
  { const u = loop(t, 11, 0.8); if (u < 0.45) { const k = u / 0.45; fx(out, `mudh${q(k, 30)}`, 500, 500, (p) => fxMud(p, q(k, 30)), WAGON[0] + 5.0, 0.1, WAGON[2] + 0.4, 1.0, 1.0); } }
  const flick = Math.sin(t * 5) > 0.6;
  stand(out, cam, t, 2, DRIVER, WAGON[0] + 0.9, 0.5, WAGON[2] + 0.1, { mode: "sit", expr: "stern", wave: flick ? 1 : undefined } as Partial<FrontOpts>);
  if ((f % 50) < 12) { const u = (f % 50) / 12; fx(out, `mudw${q(u, 30)}`, 500, 500, (p) => fxMud(p, q(u, 30)), WAGON[0] + 1.1, 0.15, WAGON[2] + 1.0, 1.0, 1.0); }
};
/** townsfolk on the old walks: some standing, some strolling (a deterministic crowd), y = walk level */
const walkers = (out: Stage, cam: CamInfo, t: number, x0: number, x1: number, south: boolean, y: number, n: number, seed: number, expr: (i: number) => Expr = () => "neutral", prop: (i: number) => Prop = () => null) => {
  const z = south ? SZ - WALK / 2 : NZ + WALK / 2;
  for (let k = 0; k < n; k++) {
    const i = seed + k, xa = x0 + (x1 - x0) * hh(i, 1), dir = hh(i, 2) < 0.5 ? -1 : 1, o = (k % 3 === 1 ? LADY : GENT)(i);
    if (hh(i, 3) < 0.4) stand(out, cam, t, i, o, xa, y, z + (hh(i, 4) - 0.5) * 1.2, { expr: expr(i), prop: prop(i) });
    else walk(out, cam, t, i, o, { x: xa - dir * 6, y, z: z + (hh(i, 4) - 0.5) }, { x: xa + dir * 6, y, z: z + (hh(i, 4) - 0.5) }, -2 + hh(i, 6) * 3, 10 + hh(i, 6) * 3, { expr: expr(i), prop: prop(i) });
  }
};
/** a row of men at the screws along a building's front, on the walk or pit floor (y), facing the wall */
const screwCrew = (out: Stage, cam: CamInfo, t: number, f: number, x0: number, x1: number, zWall: number, south: boolean, y: number, every = 2.4, seed = 300, idle = false) => {
  const z = zWall + (south ? -0.55 : 0.55);
  let k = 0;
  for (let x = x0 + 0.9; x < x1 - 0.5; x += every, k++) {
    const i = seed + k, turn = idle ? 0.25 + 0.15 * Math.sin(t * 2 + i) : 0.5 + 0.5 * Math.sin(((f - 3 * (k % 2)) / 24) * Math.PI);
    pusher(out, cam, t, i, WORKER(i), x, y, z, cam.pos.x < x === !south ? true : true, turn, k % 3 ? "stern" : "pained");
  }
};

const street = (id: number, f: number, t: number, cam: CamInfo, out: Stage) => {
  const heroL = liftAt("hero", id, f), rowL = liftAt("row", id, f), trL = liftAt("tremont", id, f), fill = fillAt(id, f);
  switch (id) {
    case 1: case 2: {
      gentleman(out, cam, f, t);
      wagonTeam(out, cam, t, f, 0.9);
      walkers(out, cam, t, -30, 30, false, WALK_Y, 7, 20);
      walkers(out, cam, t, -30, 20, true, WALK_Y, 6, 40);
      if (id === 2) stand(out, cam, t, 60, SHOPKEEP, 0, heroL, NZ + 0.1, { expr: "neutral" });
      break;
    }
    case 3: { // the fix: men set iron jackscrews in a trench under the hero's front wall
      for (let k = 0; k < 2; k++) pusher(out, cam, t, 70 + k, WORKER(70 + k), -3.4 + k * 1.6, 0, NZ + 0.7, true, 0.35 + 0.3 * Math.sin(t * 3 + k), "stern", [440, 790]);
      break;
    }
    case 4: { // up into the air: the crew at the bars, the street gapes
      for (let k = 0; k < 5; k++) pusher(out, cam, t, 70 + k, WORKER(70 + k), -4.0 + k * 2.0, 0, NZ + 0.95, true, 0.5 + 0.5 * Math.sin((f / 20 + k * 0.3) * Math.PI), "stern", [450, 700]);
      const wow: Expr = W(t, 300) ? "shock" : "neutral";
      walkers(out, cam, t, -24, -7, false, WALK_Y, 5, 90, () => wow);
      walkers(out, cam, t, 7, 24, false, WALK_Y, 5, 110, () => wow);
      walkers(out, cam, t, -12, 12, true, WALK_Y, 6, 130, (i) => (i % 2 ? wow : "laugh"));
      stand(out, cam, t, 60, SHOPKEEP, 0, heroL, NZ + 0.1, { expr: "smile", wave: W(t, 320) ? q(Math.sin(t * 9), 30) : undefined });
      break;
    }
    case 5: { // people still inside: the shopkeeper sweeps his raised doorstep, a customer comes out with a parcel
      stand(out, cam, t, 60, SHOPKEEP, -0.25, heroL, NZ + 0.15, { expr: W(t, 394) ? "smile" : "neutral", wave: W(t, 408) ? q(Math.sin(t * 8), 30) : undefined });
      stand(out, cam, t, 61, LADY(3), 0.85, heroL, NZ + 0.25, { expr: "smile_closed", prop: "basket" });
      break;
    }
    case 7: { // standing water: a lady at the brink of the puddle, a man bailing his doorway
      stand(out, cam, t, 150, LADY(1), -16.8, 0.02, -2.9, { expr: "nervous", look: 1 });
      stand(out, cam, t, 151, GENT(2), -12.6, 0.02, -3.4, { expr: "stern", look: -1 });
      const u = loop(t, 4, 1.6);
      fx(out, `ring${q(u, 30)}`, 300, 300, (p) => fxTremble(p, q(u, 30)), -14.2, 0.04, -1.0, 0.9, 0.9, { flat: true, soft: true });
      break;
    }
    case 8: { wagonTeam(out, cam, t, f, 1.0); walkers(out, cam, t, -24, 4, true, WALK_Y, 4, 160); break; }
    case 9: { // the gutter: flies, a lady with a cloth to her nose, a gent holding his breath
      walk(out, cam, t, 170, LADY(4), { x: -27, y: WALK_Y, z: NZ + 1.4 }, { x: -20, y: WALK_Y, z: NZ + 1.4 }, 727 / FPS - 1, 778 / FPS + 1, { expr: "pained", prop: "cloth" });
      stand(out, cam, t, 171, GENT(3), -25.6, WALK_Y, NZ + 0.8, { expr: "pained", prop: "cloth" });
      for (const x of [-24.4, -22.6]) { const u = loop(t, x, 2.2); fx(out, `flies${q(u, 40)}`, 300, 260, (p) => fxFlies(p, q(u, 40)), x, 0.55, NZ + WALK + 0.45, 0.8, 0.7); }
      break;
    }
    case 10: { // the notice; people pass with cloths to their faces
      walk(out, cam, t, 180, GENT(1), { x: -36, y: WALK_Y, z: NZ + 1.6 }, { x: -28, y: WALK_Y, z: NZ + 1.6 }, 778 / FPS - 0.5, 845 / FPS + 0.5, { expr: "nervous", prop: "cloth" });
      stand(out, cam, t, 181, LADY(0), -31.2, WALK_Y, NZ + 1.0, { expr: "nervous", prop: "cloth", look: -1 });
      stand(out, cam, t, 182, LADY(3), -33.8, WALK_Y, NZ + 1.2, { expr: "pained", prop: "cloth" });
      break;
    }
    case 11: { // the officials over the engineer's drawing; the engineer points at "strange choice"
      stand(out, cam, t, 190, GENT(0), 16.5, WALK_Y, 11.0, { expr: W(t, 877) ? "nervous" : "stern", look: 1 });
      stand(out, cam, t, 191, { ...GENT(3), moustache: "#ddd" }, 18.8, WALK_Y, 11.2, { expr: W(t, 877) ? "shock" : "neutral", look: -1 });
      stand(out, cam, t, 192, { ...GENT(2), coat: undefined, jacket: "#7a6a4a" }, 17.7, WALK_Y, 11.55, { expr: "grin", prop: W(t, 864) ? "point" : null, facing: -1 });
      break;
    }
    case 12: { // pipes laid on the old street: men guide the hanging pipe, others roll the next
      for (let k = 0; k < 3; k++) pusher(out, cam, t, 200 + k, WORKER(200 + k), 13.0 + k * 1.4, 0, 1.7, false, 0.6 + 0.3 * Math.sin(t * 2.5 + k), "stern", [450, 520]);
      for (let k = 0; k < 4; k++) pusher(out, cam, t, 210 + k, WORKER(210 + k), -20 + k * 7.5, 0, k % 2 ? 1.4 : -1.4, k % 2 === 0, 0.4 + 0.3 * Math.sin(t * 2 + k), "stern", [455, 700]);
      walkers(out, cam, t, -30, 10, false, WALK_Y, 5, 220, (i) => (i % 2 ? "nervous" : "neutral"));
      break;
    }
    case 13: { // shovels bury them: dirt lands on the pipes from both sides
      for (let k = 0; k < 4; k++) {
        const ph = ((t / 1.1 + k * 0.27) % 1 + 1) % 1, dig = ph < 0.5 ? ph * 2 : 1 - (ph - 0.5) * 2, side = k % 2 ? 1 : -1;
        stand(out, cam, t, 230 + k, WORKER(230 + k), -1.2 + (k >> 1) * 2.6, Math.max(0, fill - 0.05), side * 2.1, { prop: ["shovel", q(dig, 20)], expr: "stern", facing: side > 0 ? -1 : 1 });
        if (ph > 0.3) { const u = (ph - 0.3) / 0.7; fx(out, `dirt${q(u, 30)}`, 500, 400, (p) => fxDirt(p, q(u, 30)), -1.2 + (k >> 1) * 2.6, 1.5, side * (1.5 - 1.2 * u), 2.0, 1.6, { rot: side > 0 ? 0 : Math.PI }); }
      }
      break;
    }
    case 14: { // the street climbs: a navvy on the new level, a townsman still on the old walk below
      stand(out, cam, t, 240, WORKER(240), -13.4, fill, -6.8, { prop: ["shovel", 0.2], expr: "grin" });
      stand(out, cam, t, 241, GENT(1), -15.2, WALK_Y, NZ + 1.2, { expr: W(t, 1105) ? "shock" : "neutral", look: 1 });
      stand(out, cam, t, 242, WORKER(241), -11.6, fill, -5.6, { prop: ["shovel", q(loop(t, 9, 1.1), 20)], expr: "stern" });
      break;
    }
    case 15: { // the new road on top of the old: navvies and a townsman on the new surface, the old mud below the edge
      const xf = -16 + 10 * clamp01((f - 1146) / 89);
      for (let k = 0; k < 3; k++) stand(out, cam, t, 250 + k, WORKER(250 + k), xf - 1.0 - k * 1.6, fill, -3.5 + k * 3.2, { prop: ["shovel", q(loop(t, k, 1.2), 20)], expr: k === 1 ? "grin" : "stern" });
      stand(out, cam, t, 255, GENT(1), xf + 3.2, 0.02, 1.5, { expr: "shock", look: -1 });
      stand(out, cam, t, 256, LADY(2), xf + 4.4, 0.02, -2.0, { expr: "nervous", look: -1 });
      break;
    }
    case 16: { // on the new road, looking down at the sunken block
      for (let k = 0; k < 5; k++) walk(out, cam, t, 260 + k, (k % 2 ? LADY : GENT)(k + 4), { x: -22 + k * 6, y: RAISE, z: -3 + k * 1.3 }, { x: -16 + k * 6, y: RAISE, z: -3 + k * 1.3 }, 1235 / FPS, 1337 / FPS);
      walkers(out, cam, t, -16, 8, false, WALK_Y, 8, 270, () => "nervous");
      break;
    }
    case 17: { // the pit: a customer on the road edge peers down; the shopkeeper looks up from his door
      const so: SideOpts = { mode: "stand", expr: "shock", blink: lidAt(t, 280) };
      out.places.push(person(cam, { i: 280, o: GENT(2), okey: "pitgent" }, 0.9, RAISE, NZ + WALK + 0.62, { side: true, mirror: true }, {}, so));
      blob(out, 0.9, RAISE, NZ + WALK + 0.62);
      stand(out, cam, t, 60, SHOPKEEP, 0.0, 0.0, NZ + 0.35, { expr: W(t, 1373) ? "nervous" : "neutral", look: 0, wave: W(t, 1380) ? q(Math.sin(t * 7), 30) : undefined });
      break;
    }
    case 18: { // the contractor on the road edge; below, the crew jacks the hero up out of its pit
      stand(out, cam, t, 290, { ...GENT(0), jacket: "#3a2a4a" }, 2.6, RAISE, NZ + WALK + 0.9, { expr: "grin", prop: W(t, 1439) ? "point" : null, facing: -1 });
      for (let k = 0; k < 4; k++) pusher(out, cam, t, 300 + k, WORKER(300 + k), -3.6 + k * 1.9, 0, NZ + 0.75, true, 0.5 + 0.5 * Math.sin((f / 18 + k * 0.4) * Math.PI), "stern", [450, 700]);
      break;
    }
    case 26: case 27: { // Lake Street: men all along the row at the screws; onlookers
      screwCrew(out, cam, t, f, ROW.x0, ROW.x1, NZ, false, WALK_Y, id === 27 ? 1.15 : 2.3, 400);
      if (id === 26) { walkers(out, cam, t, 20, 60, true, WALK_Y, 7, 430, (i) => (i % 3 ? "smile" : "shock")); stand(out, cam, t, 440, FOREMAN, 50.5, WALK_Y, NZ + 1.8, { prop: "whistle", expr: "stern" }); }
      break;
    }
    case 28: { // the gauge: the foreman reads off the inches
      stand(out, cam, t, 440, FOREMAN, 14.6, WALK_Y, NZ + 1.7, { expr: W(t, 2364) ? "grin" : "stern", look: 1 });
      screwCrew(out, cam, t, f, ROW.x0 + 2.4, ROW.x0 + 8, NZ, false, WALK_Y, 2.3, 450);
      break;
    }
    case 29: case 30: { // open for business: clerk at the door, customers up the stairs with baskets
      const rw = (ROW.x1 - ROW.x0) / ROW.n, dx = ROW.x0 + 2.5 * rw;
      stand(out, cam, t, 460, SHOPKEEP, dx + 0.2, rowL, NZ + 0.15, { expr: "smile", wave: id === 29 && W(t, 2443) ? q(Math.sin(t * 8), 30) : undefined });
      const climb = (i: number, o: Outfit, t0: number) => {
        const u = clamp01((t - t0) / 2.6), z = NZ + 1.7 - 1.45 * u, y = WALK_Y + (rowL + 0.05 - WALK_Y) * smooth((u - 0.1) / 0.85);
        walk(out, cam, t, i, o, { x: dx, y, z }, { x: dx, y, z }, -1, -0.5, { prop: "basket", expr: "smile_closed" });
      };
      climb(461, LADY(2), id === 29 ? 2420 / FPS - 2.5 : 2482 / FPS - 0.3);
      climb(462, LADY(4), id === 29 ? 2420 / FPS + 3 : 2482 / FPS + 1.2);
      if (id === 30) stand(out, cam, t, 463, GENT(2), dx + 1.9, WALK_Y, NZ + 2.0, { prop: "basket", expr: "smile" });
      screwCrew(out, cam, t, f, ROW.x0 + 3 * rw, ROW.x1, NZ, false, WALK_Y, 2.3, 470, true);
      break;
    }
    case 31: { // George Pullman on the road above the Tremont's pit, directing
      stand(out, cam, t, 500, PULLMAN, 43.2, RAISE, SZ - WALK - 0.9, { expr: W(t, 2662) ? "grin" : "smile_closed", prop: W(t, 2662) ? "point" : null, facing: 1 });
      stand(out, cam, t, 501, FOREMAN, 41.6, RAISE, SZ - WALK - 1.2, { prop: "whistle", expr: "stern" });
      screwCrew(out, cam, t, f, TREMONT.x0 + 8, TREMONT.x0 + 22, SZ, true, 0, 2.2, 510);
      break;
    }
    case 32: { screwCrew(out, cam, t, f, TREMONT.x0, TREMONT.x1, SZ, true, 0, 1.6, 520); walkers(out, cam, t, 50, 72, false, WALK_Y, 4, 560); break; }
    case 34: { // checking out: a guest with his valise climbs the steps to the road, the porter waves him off
      const sx = (TREMONT.x0 + TREMONT.x1) / 2, u = clamp01((t - 2846 / FPS) / 2.0);
      const z = SZ - WALK - 0.4 + 2.0 * (1 - u), y = 1.15 + (RAISE - 1.15) * smooth(u);
      walk(out, cam, t, 570, GENT(3), { x: sx, y, z }, { x: sx, y, z }, -1, -0.5, { prop: "valise", expr: "smile_closed" });
      stand(out, cam, t, 571, { ...SHOPKEEP, jacket: "#7a2a2a", hat: "cap", cap: "#7a2a2a" }, sx + 1.6, trL, SZ - 0.3, { expr: "smile", wave: q(Math.sin(t * 8), 30) });
      screwCrew(out, cam, t, f, sx - 8, sx - 2, SZ, true, 0, 2.0, 580);
      break;
    }
    case 36: { // the finished street: dry, paved, people strolling
      for (let k = 0; k < 9; k++) {
        const z = [-6, -3, 1, 3.5, 0, -8, -4.5, -1.5, 2.5][k], x0 = -8 + hh(k, 1) * 14, dir = k % 2 ? 1 : -1;
        walk(out, cam, t, 600 + k, (k % 3 === 1 ? LADY : GENT)(k), { x: x0, y: RAISE, z }, { x: x0 + dir * 8, y: RAISE, z }, 2976 / FPS - 1, 3034 / FPS + 1, { expr: k % 2 ? "smile" : "smile_closed" });
      }
      break;
    }
  }
};

/** everything with a face in shot `id` at frame f */
export const stage = (id: number, f: number, cam: CamInfo): Stage => {
  const out: Stage = { places: [], fx: [] };
  const s = SHOTS[id - 1], t = f / FPS;
  prepare(s.light, cam);
  if (s.set === "street") street(id, f, t, cam, out);
  else if (s.set === "crawl") stageCrawl(id, f, t, cam, out);
  else if (s.set === "dining") stageDining(id, f, t, cam, out);
  else if (s.set === "section") stageSection(id, f, t, cam, out);
  else if (s.set === "river") stageRiver(id, f, t, cam, out);
  return out;
};
export { turnsAt, TURNS, TURN_LEN, WHISTLES, fxBlast, fxSteam, fxTremble, fxBurst, fxPuff, lin, CRAWL, DINING, SECTION, RIVER, HERO };
