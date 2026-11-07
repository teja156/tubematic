// Shared builder for the two 1870 Mississippi sidewheel packets (leeBoat.ts, natchezBoat.ts). NOT a part itself: the
// gate hashes each part's own file, so every change here bumps KIT_REV, which both part files print into their blurb
// source (a changed helper must re-open both verdicts).
//
// Full size for the frame: 38 m bow to stern (a real packet was ~85 m; 30-45 m reads at our distances), bow toward +x,
// the side faces +z, on y = 0 (the waterline). Flat cartoon paint (white cabins, one trim colour, black stacks), the
// look the reference boats have. Everything that moves is posed by animate() as a pure function of time and the act:
//   wheels turn (stop when moored/still), smoke puffs rise from the crowned chimneys and trail aft, the wake runs,
//   flags flutter; act.strip pulls the cabin doors and the fretwork valances off over the beat (they tumble over the
//   rail into the river), act.stripped keeps them gone, act.moored = d shows two lines to stakes d m off the -z side.
import * as THREE from "three";
import type { AnimState, CodePart } from "./types";

export const KIT_REV = 7;

export interface BoatLook {
  /** the painted name, on the texas board and round the paddle boxes */
  name: string;
  /** shorter form for the paddle-box arc */
  arc: string;
  trim: string;
  trimDark: string;
  blurb: string;
}

type V3 = [number, number, number];
const C = (hex: string) => new THREE.Color(hex);
const lam = (hex: string, extra: THREE.MeshLambertMaterialParameters = {}) => new THREE.MeshLambertMaterial({ color: C(hex), ...extra });

/** concatenate geometries (each already transformed) into one non-indexed geometry: one draw call, measured right */
const merge = (geos: THREE.BufferGeometry[]) => {
  const parts = geos.map((g) => (g.index ? g.toNonIndexed() : g));
  const n = parts.reduce((s, g) => s + g.getAttribute("position").count, 0);
  const pos = new Float32Array(n * 3), nor = new Float32Array(n * 3), uv = new Float32Array(n * 2);
  let k = 0;
  for (const g of parts) {
    const c = g.getAttribute("position").count;
    pos.set(g.getAttribute("position").array as Float32Array, k * 3);
    nor.set(g.getAttribute("normal").array as Float32Array, k * 3);
    const u = g.getAttribute("uv");
    if (u) uv.set(u.array as Float32Array, k * 2);
    k += c;
  }
  const out = new THREE.BufferGeometry();
  out.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  out.setAttribute("normal", new THREE.BufferAttribute(nor, 3));
  out.setAttribute("uv", new THREE.BufferAttribute(uv, 2));
  return out;
};
const boxGeo = (w: number, h: number, d: number, at: V3) => new THREE.BoxGeometry(w, h, d).translate(...at);

/** a painted detail (window, panel, doorway) sitting a few cm proud of a wall: no ink, so it reads as a tint, not a
 *  dashed coplanar line */
const tint = (o: THREE.Mesh) => {
  o.userData.noInk = true;
  return o;
};
const mk = (geo: THREE.BufferGeometry, mat: THREE.Material, at: V3 = [0, 0, 0], cast = true) => {
  const o = new THREE.Mesh(geo, mat);
  o.position.set(...at);
  o.castShadow = cast;
  o.receiveShadow = true;
  return o;
};

/** a flat outline in the deck plane (x, z), extruded upward from y0 by h */
const slab = (pts: [number, number][], y0: number, h: number) => {
  const s = new THREE.Shape(pts.map(([x, z]) => new THREE.Vector2(x, -z)));
  const g = new THREE.ExtrudeGeometry(s, { depth: h, bevelEnabled: false });
  g.rotateX(-Math.PI / 2);
  g.translate(0, y0, 0);
  return g;
};
const hullPts = (half: number, stern: number, shoulder: number, tip: number): [number, number][] => [
  [stern, -half], [shoulder, -half], [tip, 0], [shoulder, half], [stern, half],
];

const canvas = (w: number, h: number) => {
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  return { c, ctx: c.getContext("2d") as CanvasRenderingContext2D };
};
const tex = (c: HTMLCanvasElement) => {
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 8;
  t.needsUpdate = true;
  return t;
};

/** the painted paddle-box face: a sunburst fan, hub star, and the boat's name round the rim */
const paddleFace = (look: BoatLook) => {
  const S = 1024;
  const { c, ctx } = canvas(S, S);
  const cx = S / 2, cy = S / 2, R = S / 2 - 4;
  ctx.fillStyle = "#e6dfd2";
  ctx.fillRect(0, 0, S, S);
  // rays
  const n = 14;
  for (let i = 0; i < n; i++) {
    const a0 = Math.PI + (i / n) * Math.PI, a1 = Math.PI + ((i + 0.5) / n) * Math.PI;
    ctx.fillStyle = look.trim;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.arc(cx, cy, R * 0.74, a0, a1);
    ctx.closePath();
    ctx.fill();
  }
  // name band
  ctx.lineWidth = 6;
  ctx.strokeStyle = look.trimDark;
  ctx.fillStyle = "#efe6cf";
  ctx.beginPath();
  ctx.arc(cx, cy, R * 0.97, Math.PI, 2 * Math.PI);
  ctx.arc(cx, cy, R * 0.75, 2 * Math.PI, Math.PI, true);
  ctx.closePath();
  ctx.fill();
  ctx.stroke();
  ctx.fillStyle = look.trimDark;
  ctx.font = `700 ${Math.round(R * 0.15)}px Georgia, 'Times New Roman', serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  const chars = look.arc.split("");
  const span = Math.min(Math.PI * 0.8, chars.length * 0.13);
  chars.forEach((ch, i) => {
    const a = -Math.PI / 2 - span / 2 + (span * (i + 0.5)) / chars.length;
    ctx.save();
    ctx.translate(cx + Math.cos(a) * R * 0.86, cy + Math.sin(a) * R * 0.86);
    ctx.rotate(a + Math.PI / 2);
    ctx.fillText(ch, 0, 0);
    ctx.restore();
  });
  // hub with a gold star
  ctx.fillStyle = look.trimDark;
  ctx.beginPath();
  ctx.arc(cx, cy, R * 0.2, Math.PI, 2 * Math.PI);
  ctx.closePath();
  ctx.fill();
  ctx.fillStyle = "#e8b545";
  ctx.beginPath();
  for (let i = 0; i < 10; i++) {
    const a = -Math.PI / 2 + (i * Math.PI) / 5, r = (i % 2 ? 0.045 : 0.11) * R;
    const x = cx + Math.cos(a) * r, y = cy - R * 0.085 + Math.sin(a) * r;
    if (i) ctx.lineTo(x, y);
    else ctx.moveTo(x, y);
  }
  ctx.closePath();
  ctx.fill();
  // outer rim
  ctx.lineWidth = 14;
  ctx.strokeStyle = look.trim;
  ctx.beginPath();
  ctx.arc(cx, cy, R * 0.985, Math.PI, 2 * Math.PI);
  ctx.stroke();
  return tex(c);
};

/** the long name board on the texas cabin */
const nameBoard = (look: BoatLook) => {
  const W = 2048, H = 232;
  const { c, ctx } = canvas(W, H);
  ctx.fillStyle = "#f1e9d4";
  ctx.fillRect(0, 0, W, H);
  ctx.lineWidth = 16;
  ctx.strokeStyle = look.trim;
  ctx.strokeRect(8, 8, W - 16, H - 16);
  ctx.fillStyle = look.trimDark;
  ctx.font = "700 158px Georgia, 'Times New Roman', serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(look.name, W / 2, H / 2 + 8);
  return tex(c);
};

const flagTex = () => {
  const W = 256, H = 160;
  const { c, ctx } = canvas(W, H);
  for (let i = 0; i < 13; i++) {
    ctx.fillStyle = i % 2 ? "#f2ece0" : "#c63a2e";
    ctx.fillRect(0, (i * H) / 13, W, H / 13 + 1);
  }
  ctx.fillStyle = "#2c3f7a";
  ctx.fillRect(0, 0, W * 0.42, (H * 7) / 13);
  ctx.fillStyle = "#f2ece0";
  for (let i = 0; i < 12; i++) ctx.fillRect(10 + (i % 4) * 24, 10 + Math.floor(i / 4) * 24, 6, 6);
  return tex(c);
};

const foamTex = (seed: number) => {
  const W = 256, H = 512;
  const { c, ctx } = canvas(W, H);
  let s = seed;
  const rnd = () => ((s = (s * 16807) % 2147483647) / 2147483647);
  ctx.clearRect(0, 0, W, H);
  for (let i = 0; i < 90; i++) {
    const x = rnd() * W, y = rnd() * H, len = 30 + rnd() * 90;
    ctx.strokeStyle = `rgba(240,250,255,${0.5 + rnd() * 0.45})`;
    ctx.lineWidth = 3 + rnd() * 6;
    ctx.lineCap = "round";
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.lineTo(x + (rnd() - 0.5) * 10, y + len);
    ctx.stroke();
  }
  const t = tex(c);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  return t;
};

// ------------------------------------------------------------------ layout constants (part space)
const STERN = -18, BOW = 19;
const HULL_H = 1.25, RAIL_H = 0.25;
const DECK1 = HULL_H + RAIL_H; // main deck floor 1.5
const DECK2 = 5.0, SLAB = 0.3; // boiler deck
const CAB_TOP = DECK2 + SLAB + 2.8; // 8.1
const HUR = CAB_TOP + 0.3; // hurricane deck top 8.4
const WHEEL_X = -1, WHEEL_Y = 4.7, WHEEL_R = 4.4, WHEEL_Z0 = 5.4, WHEEL_Z1 = 7.5;
const HOUSE_R = 4.95;
const CHIM_X = 10.5, CHIM_Z = 2.4, CHIM_TOP = 23;
const CAB_Z = 3.6;
const PROM_Z = 7.0;
const inWheelZone = (x: number, pad = 0) => x > WHEEL_X - HOUSE_R - pad && x < WHEEL_X + HOUSE_R + pad;

const DOOR_XS = [-14.2, -12.4, -10.6, -8.8, 4.9, 6.7, 8.5];
const BAY_XS = (() => {
  const xs: number[] = [];
  for (let x = -16.5; x < 9.6; x += 2.6) xs.push(+x.toFixed(2));
  return xs;
})();

const PUFFS = 9;

const smokePose = (g: THREE.Group, t: number, quiet: boolean) => {
  for (const side of [-1, 1]) {
    for (let i = 0; i < PUFFS; i++) {
      const p = g.getObjectByName(`puff${side}_${i}`) as THREE.Mesh | undefined;
      if (!p) continue;
      const rate = quiet ? 0.12 : 0.32;
      const u = (((t * rate + i / PUFFS + (side > 0 ? 0.5 / PUFFS : 0)) % 1) + 1) % 1;
      const rise = quiet ? 6 : 8;
      const aft = quiet ? 2.5 : 15;
      p.position.set(CHIM_X - u * aft - u * u * (quiet ? 1 : 6), CHIM_TOP + 0.9 + u * rise - u * u * (quiet ? 0 : 2), side * CHIM_Z + side * u * 1.2);
      // opaque cartoon puffs: they swell as they rise, then shrink away (no see-through rings)
      const grow = (quiet ? 0.6 : 0.9) + u * (quiet ? 1.6 : 3.1);
      const s = grow * Math.min(1, (1 - u) / 0.3) * Math.min(1, u * 10 + 0.3);
      p.scale.set(s, s * 0.88, s);
    }
  }
};

export const makeSteamboat = (look: BoatLook): CodePart => {
  const build = (): THREE.Group => {
    const g = new THREE.Group();
    const white = lam("#ddd6c9");
    const whiteDS = lam("#ddd6c9", { side: THREE.DoubleSide });
    const deck = lam("#c79a62");
    const roof = lam("#bdb6aa");
    const trim = lam(look.trim);
    const trimDS = lam(look.trim, { side: THREE.DoubleSide });
    const oxblood = lam("#5c2b29");
    const chimney = lam("#262c51");
    const gold = lam("#d9a640");
    const glass = lam("#2f4c80");
    const doorMat = lam("#a8642e");
    const hole = lam("#2d2131");
    const iron = lam("#4a4f60");
    const bucket = lam("#6b4a33");
    const cotton = lam("#eee9dc");
    const cord = lam("#8a5a34");
    const fire = new THREE.MeshBasicMaterial({ color: C("#ff9b45") });
    const splashMat = new THREE.MeshLambertMaterial({ color: C("#f4fbff"), side: THREE.DoubleSide, transparent: true, opacity: 0.92, depthWrite: false });

    // ---- hull: oxblood waterline band, white topsides, trim rub rail
    g.add(mk(slab(hullPts(5, STERN, 11, BOW), 0, 0.42), oxblood));
    g.add(mk(slab(hullPts(5, STERN, 11, BOW), 0.42, HULL_H - 0.42), white));
    g.add(mk(slab(hullPts(5.15, STERN - 0.1, 11, BOW + 0.2), HULL_H, RAIL_H), trim));
    // main deck floor
    g.add(mk(slab(hullPts(4.95, STERN + 0.05, 11, BOW - 0.3), DECK1, 0.04), deck, [0, 0, 0], false));

    // ---- main deck: posts, boilers + firebox, engine house aft, cargo
    const posts: THREE.BufferGeometry[] = [];
    for (let x = -16.5; x <= 11.5; x += 2.6) for (const s of [-1, 1]) posts.push(boxGeo(0.2, DECK2 - DECK1, 0.2, [x, (DECK1 + DECK2) / 2, s * 4.8]));
    for (const x of [13.5, 15.5]) for (const s of [-1, 1]) posts.push(boxGeo(0.2, DECK2 - DECK1, 0.2, [x, (DECK1 + DECK2) / 2, s * (x > 14 ? 2.6 : 3.8)]));
    g.add(mk(merge(posts), white));
    for (const z of [-1.8, -0.6, 0.6, 1.8]) {
      const b = mk(new THREE.CylinderGeometry(0.55, 0.55, 10, 16), iron, [6, 2.3, z]);
      b.rotation.z = Math.PI / 2;
      g.add(b);
    }
    g.add(mk(new THREE.BoxGeometry(0.5, 2.2, 4.6), iron, [11.3, DECK1 + 1.1, 0]));
    for (const z of [-1.8, -0.6, 0.6, 1.8]) {
      const mouth = mk(new THREE.PlaneGeometry(0.6, 0.5), fire, [11.56, DECK1 + 0.6, z], false);
      mouth.rotation.y = Math.PI / 2;
      mouth.userData.noInk = true;
      g.add(mouth);
    }
    g.add(mk(new THREE.BoxGeometry(8, 2.6, 7), white, [-12.5, DECK1 + 1.3, 0]));
    for (const s of [-1, 1]) for (const x of [-15, -12.5, -10]) g.add(tint(mk(new THREE.BoxGeometry(1, 0.8, 0.05), glass, [x, DECK1 + 1.6, s * 3.53], false)));
    for (const [x, z, y] of [[14.2, -2.4, 0], [14.2, -1.2, 0], [14.2, 1.3, 0], [15.4, -1.8, 0], [14.2, -1.8, 1], [15.4, 1.6, 0]] as V3[])
      g.add(mk(new THREE.BoxGeometry(1.1, 0.95, 1.1), cotton, [x, DECK1 + 0.48 + y * 0.95, z]));
    g.add(mk(new THREE.BoxGeometry(4, 1.4, 2.2), cord, [-6.5, DECK1 + 0.7, 2.6]));
    g.add(mk(new THREE.BoxGeometry(4, 1.4, 2.2), cord, [-6.5, DECK1 + 0.7, -2.6]));

    // ---- boiler deck slab, cabin with doors, promenade posts, railings
    const deckOutline: [number, number][] = [[-17.6, -7.3], [10.2, -7.3], [15.6, -2.6], [15.6, 2.6], [10.2, 7.3], [-17.6, 7.3]];
    g.add(mk(slab(deckOutline, DECK2, SLAB), white));
    g.add(mk(slab(deckOutline.map(([x, z]) => [x * 1.003, z * 1.01] as [number, number]), DECK2 + SLAB - 0.04, 0.05), deck, [0, 0, 0], false));
    g.add(mk(new THREE.BoxGeometry(24, 2.8, CAB_Z * 2), white, [-3, DECK2 + SLAB + 1.4, 0]));
    // transom windows the length of the cabin
    for (const s of [-1, 1]) {
      for (let x = -14.2; x <= 8.6; x += 1.8) {
        if (inWheelZone(x, 0.4)) continue;
        g.add(tint(mk(new THREE.BoxGeometry(0.8, 0.35, 0.05), glass, [x, CAB_TOP - 0.35, s * (CAB_Z + 0.01)], false)));
      }
    }
    // doors (named, they come off) and the dark doorways behind them
    DOOR_XS.forEach((x, i) => {
      for (const s of [-1, 1]) {
        g.add(tint(mk(new THREE.BoxGeometry(0.98, 2.02, 0.04), hole, [x, DECK2 + SLAB + 1.01, s * (CAB_Z + 0.015)], false)));
        const d = new THREE.Group();
        d.name = `door${s}_${i}`;
        d.position.set(x, DECK2 + SLAB + 1.0, s * (CAB_Z + 0.06));
        d.add(mk(new THREE.BoxGeometry(0.92, 1.96, 0.08), doorMat));
        // two raised panels in trim so the door reads as a door at any distance
        d.add(tint(mk(new THREE.BoxGeometry(0.6, 0.6, 0.04), trim, [0, 0.45, s * 0.05], false)));
        d.add(tint(mk(new THREE.BoxGeometry(0.6, 0.6, 0.04), trim, [0, -0.4, s * 0.05], false)));
        d.add(mk(new THREE.SphereGeometry(0.06, 8, 6), gold, [0.3, 0, s * 0.07], false));
        g.add(d);
        // the splash where the door lands: a flat foam ring on the water and a fan of thin spray jets leaning out
        // (no ink; posed by animate())
        const sp = new THREE.Group();
        sp.position.set(x, 0.1, s * 9);
        sp.add(tint(mk(new THREE.RingGeometry(0.3, 1.3, 20).rotateX(-Math.PI / 2), splashMat, [0, 0.02, 0], false)));
        for (let k = 0; k < 9; k++) {
          const a = (k / 9) * Math.PI * 2 + 0.2;
          const h = 1.1 + 0.5 * ((k * 7) % 3) / 2;
          const jet = new THREE.ConeGeometry(0.16, h, 6).translate(0, h / 2, 0);
          jet.rotateZ(-0.45);
          jet.rotateY(-a);
          sp.add(tint(mk(jet, splashMat, [Math.cos(a) * 0.35, 0, Math.sin(a) * 0.35], false)));
        }
        sp.add(tint(mk(new THREE.ConeGeometry(0.22, 1.9, 7).translate(0, 0.95, 0), splashMat, [0, 0, 0], false)));
        sp.name = `splash${s}_${i}`;
        sp.userData.noInk = true;
        sp.visible = false;
        g.add(sp);
      }
    });
    // promenade posts and the boiler-deck railing
    const promPosts: THREE.BufferGeometry[] = [];
    const rails: THREE.BufferGeometry[] = [];
    const balus: THREE.BufferGeometry[] = [];
    for (const x of BAY_XS) for (const s of [-1, 1]) if (!inWheelZone(x, 0.3)) promPosts.push(boxGeo(0.18, CAB_TOP - DECK2 - SLAB, 0.18, [x, (DECK2 + SLAB + CAB_TOP) / 2, s * PROM_Z]));
    for (const s of [-1, 1]) {
      for (const [x0, x1] of [[-17.4, WHEEL_X - HOUSE_R], [WHEEL_X + HOUSE_R, 10.2]]) {
        rails.push(boxGeo(x1 - x0, 0.1, 0.12, [(x0 + x1) / 2, DECK2 + SLAB + 1.0, s * PROM_Z]));
        rails.push(boxGeo(x1 - x0, 0.06, 0.08, [(x0 + x1) / 2, DECK2 + SLAB + 0.12, s * PROM_Z]));
        for (let x = x0 + 0.15; x < x1; x += 0.32) balus.push(boxGeo(0.05, 0.9, 0.05, [x, DECK2 + SLAB + 0.55, s * PROM_Z]));
      }
    }
    // the bow end of the boiler deck
    rails.push(boxGeo(0.12, 0.1, 5.2, [15.5, DECK2 + SLAB + 1.0, 0]));
    for (let z = -2.5; z <= 2.5; z += 0.32) balus.push(boxGeo(0.05, 0.9, 0.05, [15.5, DECK2 + SLAB + 0.55, z]));
    for (const s of [-1, 1]) {
      const dx = 15.5 - 10.2, dz = PROM_Z - 2.6, len = Math.hypot(dx, dz);
      const r = boxGeo(len, 0.1, 0.12, [0, 0, 0]);
      r.rotateY(Math.atan2(s * dz, dx));
      r.translate((10.2 + 15.5) / 2, DECK2 + SLAB + 1.0, s * (PROM_Z + 2.6) / 2);
      rails.push(r);
    }
    g.add(mk(merge(promPosts), white));
    g.add(mk(merge(rails), trim));
    // the railing reads as one inked band (top and bottom rails); the balusters are painted between them, no ink
    g.add(tint(mk(merge(balus), white, [0, 0, 0], false)));
    // the fretwork valances between the promenade posts (named, they come off)
    const valShape = (w: number) => {
      const sh = new THREE.Shape();
      const top = 0.45, n = 4;
      sh.moveTo(-w / 2, top);
      sh.lineTo(w / 2, top);
      sh.lineTo(w / 2, 0);
      for (let k = n - 1; k >= 0; k--) {
        const x0 = -w / 2 + (k * w) / n, x1 = x0 + w / n;
        sh.absarc((x0 + x1) / 2, 0, (x1 - x0) / 2, 0, Math.PI, false);
      }
      sh.lineTo(-w / 2, top);
      return new THREE.ExtrudeGeometry(sh, { depth: 0.06, bevelEnabled: false }).translate(0, 0, -0.03);
    };
    const vg = valShape(2.3);
    BAY_XS.slice(0, -1).forEach((x, i) => {
      const xm = x + 1.3;
      if (inWheelZone(xm, 1.2)) return;
      for (const s of [-1, 1]) {
        const v = mk(vg, trimDS, [xm, CAB_TOP - 0.5, s * (PROM_Z + 0.02)]);
        v.name = `val${s}_${i}`;
        g.add(v);
      }
    });

    // ---- hurricane deck, texas, pilothouse
    const hurOutline: [number, number][] = [[-17.2, -7.25], [10.4, -7.25], [12.6, -4.5], [12.6, 4.5], [10.4, 7.25], [-17.2, 7.25]];
    g.add(mk(slab(hurOutline, CAB_TOP, 0.3), roof));
    // trim fascia round the hurricane deck edge
    const fascia: THREE.BufferGeometry[] = [];
    for (const s of [-1, 1]) fascia.push(boxGeo(27.6, 0.32, 0.06, [-3.4, CAB_TOP + 0.15, s * 7.28]));
    fascia.push(boxGeo(0.06, 0.32, 14.5, [-17.23, CAB_TOP + 0.15, 0]));
    g.add(mk(merge(fascia), trim, [0, 0, 0], false));
    const hrail: THREE.BufferGeometry[] = [];
    const hbal: THREE.BufferGeometry[] = [];
    for (const s of [-1, 1]) {
      hrail.push(boxGeo(27, 0.08, 0.08, [-3.6, HUR + 0.7, s * 7.1]));
      for (let x = -17; x < 10.3; x += 0.45) hbal.push(boxGeo(0.045, 0.7, 0.045, [x, HUR + 0.35, s * 7.1]));
    }
    g.add(mk(merge(hrail), white, [0, 0, 0], false));
    g.add(tint(mk(merge(hbal), white, [0, 0, 0], false)));
    // texas cabin + name boards
    g.add(mk(new THREE.BoxGeometry(12, 2.0, 5.2), white, [-1, HUR + 1.0, 0]));
    g.add(mk(new THREE.BoxGeometry(12.6, 0.18, 5.8), roof, [-1, HUR + 2.09, 0]));
    const nb = new THREE.MeshLambertMaterial({ map: nameBoard(look) });
    for (const s of [-1, 1]) {
      const p = mk(new THREE.PlaneGeometry(10.6, 1.2), nb, [-1, HUR + 1.0, s * 2.62], false);
      if (s < 0) p.rotation.y = Math.PI;
      g.add(p);
    }
    // pilothouse
    const PH = HUR + 2.18;
    g.add(mk(new THREE.BoxGeometry(3.2, 2.5, 3.2), white, [3.2, PH + 1.25, 0]));
    for (const s of [-1, 1]) {
      for (const k of [-1, 0, 1]) g.add(tint(mk(new THREE.BoxGeometry(0.8, 1.0, 0.05), glass, [3.2 + k * 0.95, PH + 1.55, s * 1.61], false)));
      for (const k of [-0.75, 0.75]) g.add(tint(mk(new THREE.BoxGeometry(0.05, 1.0, 0.9), glass, [3.2 + s * 1.61, PH + 1.55, k], false)));
    }
    const ph = mk(new THREE.ConeGeometry(2.75, 1.1, 4), trim, [3.2, PH + 3.05, 0]);
    ph.rotation.y = Math.PI / 4;
    g.add(ph);
    g.add(mk(new THREE.BoxGeometry(3.7, 0.16, 3.7), trim, [3.2, PH + 2.55, 0]));
    g.add(mk(new THREE.SphereGeometry(0.28, 12, 8), gold, [3.2, PH + 3.75, 0]));

    // ---- chimneys with crowns, brace and ornament
    for (const s of [-1, 1]) {
      const z = s * CHIM_Z;
      g.add(mk(new THREE.CylinderGeometry(0.8, 0.85, CHIM_TOP - DECK2, 18), chimney, [CHIM_X, (DECK2 + CHIM_TOP) / 2, z]));
      g.add(mk(new THREE.CylinderGeometry(1.25, 0.82, 1.3, 18, 1, true), chimney, [CHIM_X, CHIM_TOP + 0.4, z]));
      g.add(mk(new THREE.CylinderGeometry(0.86, 0.86, 0.5, 18), gold, [CHIM_X, CHIM_TOP - 1.2, z]));
      for (let k = 0; k < 10; k++) {
        const a = (k / 10) * Math.PI * 2;
        g.add(mk(new THREE.ConeGeometry(0.2, 0.7, 4), chimney, [CHIM_X + Math.cos(a) * 1.15, CHIM_TOP + 1.35, z + Math.sin(a) * 1.15]));
      }
    }
    const brace = mk(new THREE.CylinderGeometry(0.09, 0.09, CHIM_Z * 2, 8), gold, [CHIM_X, CHIM_TOP - 4, 0]);
    brace.rotation.x = Math.PI / 2;
    g.add(brace);
    g.add(mk(new THREE.SphereGeometry(0.42, 14, 10), gold, [CHIM_X, CHIM_TOP - 4.6, 0]));

    // ---- paddle wheels and their painted boxes
    const face = new THREE.MeshLambertMaterial({ map: paddleFace(look) });
    for (const s of [-1, 1]) {
      const zc = s * (WHEEL_Z0 + WHEEL_Z1) / 2;
      const wheel = new THREE.Group();
      wheel.name = `wheel${s}`;
      wheel.position.set(WHEEL_X, WHEEL_Y, zc);
      const hub = mk(new THREE.CylinderGeometry(0.5, 0.5, 2.4, 14), iron);
      hub.rotation.x = Math.PI / 2;
      wheel.add(hub);
      const spokes: THREE.BufferGeometry[] = [];
      const buckets: THREE.BufferGeometry[] = [];
      for (let k = 0; k < 16; k++) {
        const a = (k / 16) * Math.PI * 2;
        for (const dz of [-0.85, 0.85]) {
          const sp = new THREE.BoxGeometry(WHEEL_R - 0.3, 0.12, 0.1).translate((WHEEL_R - 0.3) / 2, 0, dz);
          sp.rotateZ(a);
          spokes.push(sp);
        }
        const b = new THREE.BoxGeometry(1.0, 0.2, 2.1).translate(WHEEL_R - 0.5, 0, 0);
        b.rotateZ(a);
        buckets.push(b);
      }
      wheel.add(mk(merge(spokes), trim));
      wheel.add(mk(merge(buckets), bucket));
      for (const dz of [-0.85, 0.85]) {
        const rim = mk(new THREE.TorusGeometry(WHEEL_R - 0.25, 0.09, 6, 40), trim, [0, 0, dz]);
        wheel.add(rim);
      }
      g.add(wheel);
      // housing: a half drum over the top, with painted faces both sides
      const shell = mk(new THREE.CylinderGeometry(HOUSE_R, HOUSE_R, WHEEL_Z1 - WHEEL_Z0 + 0.5, 40, 1, true, Math.PI / 2, Math.PI), whiteDS, [WHEEL_X, WHEEL_Y, zc]);
      shell.rotation.x = Math.PI / 2;
      g.add(shell);
      for (const side of [-1, 1]) {
        const half = (WHEEL_Z1 - WHEEL_Z0 + 0.5) / 2;
        const outer = side === s;
        const f = mk(new THREE.CircleGeometry(HOUSE_R, 40, 0, Math.PI), outer ? face : white, [WHEEL_X, WHEEL_Y, zc + side * half], false);
        if (side < 0) f.rotation.y = Math.PI;
        g.add(f);
      }
      // trim band along the housing's bottom edge
      g.add(mk(new THREE.BoxGeometry(HOUSE_R * 2 + 0.3, 0.3, WHEEL_Z1 - WHEEL_Z0 + 0.7), trim, [WHEEL_X, WHEEL_Y - 0.15, zc]));
      // spray at the wheel's foot
      for (let k = 0; k < 4; k++) {
        const sp = mk(new THREE.SphereGeometry(0.7, 10, 6), new THREE.MeshLambertMaterial({ color: C("#f2fbff"), transparent: true, opacity: 0.8, depthWrite: false }), [WHEEL_X - 2.6 + k * 1.2, 0.35, zc + s * 0.2], false);
        sp.name = `spray${s}_${k}`;
        sp.userData.noInk = true;
        sp.visible = false; // under way only (animate)
        g.add(sp);
      }
    }

    // ---- flags
    const fl = new THREE.MeshLambertMaterial({ map: flagTex(), side: THREE.DoubleSide });
    for (const [x, h, y0, w] of [[BOW - 1.2, 6, DECK2 + SLAB, 1.8], [STERN + 0.6, 6.5, CAB_TOP + 0.3, 2.4]]) {
      g.add(mk(new THREE.CylinderGeometry(0.07, 0.08, h, 6), gold, [x, y0 + h / 2, 0]));
      const fg = new THREE.Group();
      fg.name = x > 0 ? "flagBow" : "flagStern";
      fg.position.set(x, y0 + h - (w * 0.62) / 2 - 0.1, 0);
      const f = mk(new THREE.PlaneGeometry(w, w * 0.62, 6, 1).translate(-w / 2, 0, 0), fl, [0, 0, 0], false);
      fg.add(f);
      g.add(fg);
    }

    // ---- smoke (posed every frame; part of the boat so it follows it)
    for (const side of [-1, 1]) {
      for (let i = 0; i < PUFFS; i++) {
        const p = mk(new THREE.SphereGeometry(1, 16, 12), new THREE.MeshLambertMaterial({ color: C("#5f5a66"), transparent: true, opacity: 1, depthWrite: false }), [0, 0, 0], false);
        p.name = `puff${side}_${i}`;
        p.userData.noInk = true;
        g.add(p);
      }
    }

    // ---- wake: foam along the hull and a trail astern (flat, unlit, no ink)
    const foam = new THREE.MeshBasicMaterial({ map: foamTex(7), transparent: true, opacity: 0.85, depthWrite: false });
    const wake = new THREE.Group();
    wake.name = "wake";
    const trail = mk(new THREE.PlaneGeometry(26, 9), foam, [STERN - 12, 0.1, 0], false);
    trail.rotation.x = -Math.PI / 2;
    trail.userData.noInk = true;
    wake.add(trail);
    for (const s of [-1, 1]) {
      const side = mk(new THREE.PlaneGeometry(36, 1.6), foam, [-0.5, 0.1, s * 5.6], false);
      side.rotation.x = -Math.PI / 2;
      side.userData.noInk = true;
      wake.add(side);
    }
    wake.visible = false; // under way only (animate)
    g.add(wake);

    // ---- mooring lines (shown by act.moored)
    const moor = new THREE.Group();
    moor.name = "moor";
    moor.visible = false;
    g.add(moor);

    smokePose(g, 0, false);
    return g;
  };

  const moorLines = (g: THREE.Group, d: number) => {
    const moor = g.getObjectByName("moor") as THREE.Group;
    if (moor.userData.d === d) return;
    moor.clear();
    moor.userData.d = d;
    const rope = lam("#c9b07a");
    const stake = lam("#5a3d28");
    for (const [x, tx] of [[15.5, 19], [-16.5, -19.5]]) {
      const a = new THREE.Vector3(x, DECK1 + 0.2, -4.9);
      const b = new THREE.Vector3(tx, 0.9, -(5 + d));
      const mid = a.clone().lerp(b, 0.5).add(new THREE.Vector3(0, -0.5, 0));
      for (const [p, q] of [[a, mid], [mid, b]]) {
        const len = p.distanceTo(q);
        const r = mk(new THREE.CylinderGeometry(0.06, 0.06, len, 6), rope, [0, 0, 0], false);
        r.position.copy(p).add(q).multiplyScalar(0.5);
        r.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), q.clone().sub(p).normalize());
        moor.add(r);
      }
      moor.add(mk(new THREE.CylinderGeometry(0.16, 0.2, 1.2, 8), stake, [tx, 0.6, -(5 + d)]));
    }
  };

  const animate = (g: THREE.Group, s: AnimState) => {
    const moored = (s.act.moored ?? 0) > 0;
    const still = moored || (s.act.still ?? 0) > 0;
    // wheels: the foot of the wheel drives aft (-x)
    for (const side of [-1, 1]) {
      const w = g.getObjectByName(`wheel${side}`);
      if (w) w.rotation.z = still ? 0.2 : -s.t * 1.9;
      for (let k = 0; k < 4; k++) {
        const sp = g.getObjectByName(`spray${side}_${k}`);
        if (!sp) continue;
        sp.visible = !still;
        const u = ((s.t * 2.2 + k * 0.27) % 1 + 1) % 1;
        const sc = 0.5 + 0.8 * Math.sin(Math.PI * u);
        sp.scale.set(sc * 1.4, sc * 0.6, sc);
      }
    }
    const wake = g.getObjectByName("wake") as THREE.Group | undefined;
    if (wake) {
      wake.visible = !still;
      for (const m of wake.children) {
        const map = ((m as THREE.Mesh).material as THREE.MeshBasicMaterial).map;
        if (map) map.offset.y = (s.t * 0.35) % 1;
      }
    }
    smokePose(g, s.t, moored);
    for (const n of ["flagBow", "flagStern"]) {
      const f = g.getObjectByName(n);
      if (f) f.rotation.y = 0.18 * Math.sin(s.t * 5 + (n === "flagBow" ? 0 : 1.7));
    }
    const moor = g.getObjectByName("moor") as THREE.Group | undefined;
    if (moor) {
      moor.visible = moored;
      if (moored) moorLines(g, s.act.moored);
    }
    // stripping: doors first, then the valances, one after another over the beat; gone for good after
    const stripping = (s.act.strip ?? 0) > 0;
    const gone = (s.act.stripped ?? 0) > 0;
    const fly = (o: THREE.Object3D, home: V3, side: number, p: number, spin: number) => {
      if (p <= 0) {
        o.visible = true;
        o.position.set(...home);
        o.rotation.set(0, 0, 0);
        return;
      }
      o.visible = p < 1;
      const q = Math.min(1, p);
      o.position.set(home[0] + 0.8 * q, home[1] + 7 * q - (13.2 + home[1] - 6.3) * q * q, home[2] + side * 9 * q);
      o.rotation.set(side * q * Math.PI * spin, q * 0.9, side * q * 0.6);
    };
    DOOR_XS.forEach((x, i) => {
      for (const side of [-1, 1]) {
        const d = g.getObjectByName(`door${side}_${i}`);
        const sp = g.getObjectByName(`splash${side}_${i}`);
        if (!d) continue;
        const order = [3, 0, 5, 1, 6, 2, 4][i] ?? i;
        const st = 0.04 + (order / DOOR_XS.length) * 0.5 + (side > 0 ? 0.03 : 0);
        const p = gone ? 2 : stripping ? (s.beatT - st) / 0.26 : 0;
        fly(d, [x, DECK2 + SLAB + 1.0, side * (CAB_Z + 0.06)], side, p, 1.5);
        if (sp) {
          const u = (p - 1) / 0.35;
          sp.visible = !gone && stripping && u > 0 && u < 1;
          if (sp.visible) {
            sp.position.set(x + 0.8, 0.12, side * (CAB_Z + 9.06));
            const k = 0.5 + 1.0 * u;
            sp.scale.set(k, 1.1 * Math.sin(Math.PI * u) + 0.15, k);
          }
        }
      }
    });
    BAY_XS.forEach((x, i) => {
      for (const side of [-1, 1]) {
        const v = g.getObjectByName(`val${side}_${i}`);
        if (!v) continue;
        const st = 0.2 + ((i * 5) % 9) / 9 * 0.5 + (side > 0 ? 0.02 : 0);
        const p = gone ? 2 : stripping ? (s.beatT - st) / 0.24 : 0;
        fly(v, [x + 1.3, CAB_TOP - 0.5, side * (PROM_Z + 0.02)], side, p * 0.95, 2.2);
      }
    });
  };

  return {
    blurb: look.blurb,
    build: () => build(),
    animate,
    acts: {
      strip: "1 = the cabin doors and the fretwork valances come off one by one over the beat and tumble into the river",
      stripped: "1 = doors and valances already gone (dark doorways)",
      moored: "d > 0 = engines stopped, wheels still, two lines to stakes d m off the boat's -z side, lazy smoke",
      still: "1 = wheels stopped, no wake (drifting or landed)",
    },
    solid: true,
  };
};
