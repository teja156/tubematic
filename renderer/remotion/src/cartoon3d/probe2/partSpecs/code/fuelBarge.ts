// A wood flat at steamboat scale: an 18 x 6 m plank scow with raked ends, heaped with corded firewood (end grain
// showing), a little deckhouse aft and two lines reaching up its +z side to whatever it is lashed to. act.load = 1:
// split logs fly in a steady stream from the woodpiles across the +z gunwale (onto the boat alongside).
import * as THREE from "three";
import type { CodePart } from "./types";

type V3 = [number, number, number];
const C = (hex: string) => new THREE.Color(hex);
const lam = (hex: string, extra: THREE.MeshLambertMaterialParameters = {}) => new THREE.MeshLambertMaterial({ color: C(hex), ...extra });
const mk = (geo: THREE.BufferGeometry, mat: THREE.Material | THREE.Material[], at: V3, cast = true) => {
  const o = new THREE.Mesh(geo, mat);
  o.position.set(...at);
  o.castShadow = cast;
  o.receiveShadow = true;
  return o;
};

const endGrain = () => {
  const S = 256;
  const c = document.createElement("canvas");
  c.width = S;
  c.height = S;
  const ctx = c.getContext("2d") as CanvasRenderingContext2D;
  ctx.fillStyle = "#5e3a22";
  ctx.fillRect(0, 0, S, S);
  let s = 77;
  const rnd = () => ((s = (s * 16807) % 2147483647) / 2147483647);
  const r = 20;
  for (let row = 0; row < 7; row++) for (let col = 0; col < 7; col++) {
    const x = col * 37 + (row % 2) * 18 + 10 + rnd() * 4, y = row * 36 + 18 + rnd() * 4, rr = r * (0.8 + rnd() * 0.3);
    ctx.fillStyle = "#e0b277";
    ctx.beginPath();
    ctx.arc(x, y, rr, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = "rgba(150,95,50,0.8)";
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    ctx.arc(x, y, rr * 0.55, 0, Math.PI * 2);
    ctx.stroke();
  }
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.needsUpdate = true;
  return t;
};

/** concatenate already-placed geometries into one (one draw call, measured right) */
const merge = (geos: THREE.BufferGeometry[]) => {
  const parts = geos.map((g) => (g.index ? g.toNonIndexed() : g));
  const n = parts.reduce((s, g) => s + g.getAttribute("position").count, 0);
  const pos = new Float32Array(n * 3), nor = new Float32Array(n * 3), uv = new Float32Array(n * 2);
  let k = 0;
  for (const g of parts) {
    pos.set(g.getAttribute("position").array as Float32Array, k * 3);
    nor.set(g.getAttribute("normal").array as Float32Array, k * 3);
    uv.set(g.getAttribute("uv").array as Float32Array, k * 2);
    k += g.getAttribute("position").count;
  }
  const out = new THREE.BufferGeometry();
  out.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  out.setAttribute("normal", new THREE.BufferAttribute(nor, 3));
  out.setAttribute("uv", new THREE.BufferAttribute(uv, 2));
  return out;
};

const LOGS = 7;
const STACKS: [number, number][] = [[-5.4, -1.3], [-2.2, -1.3], [1.0, -1.3], [4.2, -1.3], [-3.8, 1.4], [-0.6, 1.4], [2.6, 1.4]];

export const FUEL_BARGE: CodePart = {
  blurb: "a wood flat: an 18 m plank scow with raked ends heaped with stacks of corded firewood, a small deckhouse aft; the fuel barge steamboats took alongside",
  acts: { load: "1 = split logs fly in a stream from the woodpiles over the +z side (onto a boat lashed alongside)" },
  build: () => {
    const g = new THREE.Group();
    const hull = lam("#7b5536");
    const plank = lam("#b98957");
    const bark = lam("#6e4628");
    const grain = new THREE.MeshLambertMaterial({ map: endGrain() });
    const endWood = lam("#dcae74");
    const white = lam("#ddd6c9");
    const roof = lam("#8e3b2e");
    const rope = lam("#c9b07a");
    // hull: side profile with raked ends, extruded across the beam
    const sh = new THREE.Shape();
    sh.moveTo(-9, 1.1);
    sh.lineTo(9, 1.1);
    sh.lineTo(7.6, 0);
    sh.lineTo(-7.6, 0);
    sh.lineTo(-9, 1.1);
    const hg = new THREE.ExtrudeGeometry(sh, { depth: 6, bevelEnabled: false }).translate(0, 0, -3);
    g.add(mk(hg, hull, [0, 0, 0]));
    g.add(mk(new THREE.BoxGeometry(18.1, 0.06, 6.05), plank, [0, 1.12, 0], false));
    // gunwale rub strakes
    for (const z of [-3.02, 3.02]) g.add(mk(new THREE.BoxGeometry(18.2, 0.22, 0.12), plank, [0, 0.95, z]));
    // cordwood stacks: split logs piled in a pyramid, bark sides and pale end grain (two merged geometries per stack)
    for (const [x, z] of STACKS) {
      const sides: THREE.BufferGeometry[] = [];
      const caps: THREE.BufferGeometry[] = [];
      const rows = [6, 5, 4, 3];
      rows.forEach((n, row) => {
        for (let k = 0; k < n; k++) {
          const zz = z + (k - (n - 1) / 2) * 0.36;
          const yy = 1.15 + 0.17 + row * 0.31;
          const r = 0.17 + ((k * 7 + row * 3) % 5) * 0.008;
          sides.push(new THREE.CylinderGeometry(r, r, 2.6, 8, 1, true).rotateZ(Math.PI / 2).translate(x, yy, zz));
          for (const e of [-1, 1]) caps.push(new THREE.CircleGeometry(r, 8).rotateY((e * Math.PI) / 2).translate(x + e * 1.3, yy, zz));
        }
      });
      g.add(mk(merge(sides), bark, [0, 0, 0]));
      g.add(mk(merge(caps), endWood, [0, 0, 0], false));
    }
    // deckhouse aft
    g.add(mk(new THREE.BoxGeometry(2.4, 2.0, 3.4), white, [-7.3, 1.15 + 1.0, 0]));
    const r = mk(new THREE.BoxGeometry(2.8, 0.14, 3.8), roof, [-7.3, 1.15 + 2.07, 0]);
    g.add(r);
    g.add(mk(new THREE.BoxGeometry(0.7, 1.3, 0.05), lam("#3a2a2e"), [-7.3, 1.15 + 0.75, 1.72], false));
    // lines up to the boat alongside (+z)
    for (const x of [-4.5, 6.5]) {
      const a = new THREE.Vector3(x, 1.2, 2.9), b = new THREE.Vector3(x + 0.6, 2.4, 4.2);
      const rr = mk(new THREE.CylinderGeometry(0.05, 0.05, a.distanceTo(b), 6), rope, [0, 0, 0], false);
      rr.position.copy(a).add(b).multiplyScalar(0.5);
      rr.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), b.clone().sub(a).normalize());
      g.add(rr);
      g.add(mk(new THREE.CylinderGeometry(0.12, 0.14, 0.4, 8), hull, [x, 1.35, 2.7]));
    }
    // flying logs (posed by animate; hidden unless loading)
    for (let i = 0; i < LOGS; i++) {
      const l = mk(new THREE.CylinderGeometry(0.16, 0.16, 1.3, 8), [bark, grain, grain], [0, 2.5, 0]);
      l.name = `log${i}`;
      l.visible = false;
      g.add(l);
    }
    return g;
  },
  animate: (g, s) => {
    const on = (s.act.load ?? 0) > 0;
    for (let i = 0; i < LOGS; i++) {
      const l = g.getObjectByName(`log${i}`);
      if (!l) continue;
      l.visible = on;
      if (!on) continue;
      const u = (((s.t * 0.9 + i / LOGS) % 1) + 1) % 1;
      const [sx] = STACKS[i % 4];
      const x = sx + 0.4 * Math.sin(i * 2.1);
      l.position.set(x, 3.0 + 3.2 * Math.sin(Math.PI * u) - 0.6 * u, 1.4 + u * 4.6);
      l.rotation.set(u * 4 + i, 0, Math.PI / 2 + u * 2);
    }
  },
  solid: true,
};
