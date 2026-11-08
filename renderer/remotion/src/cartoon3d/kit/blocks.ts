// Chicago's buildings and street things, built the skill's way (build.ts: merged batches per material, two-tone
// Lambert materials via lam(), painted textures, real 3D relief for every painted feature): brick commercial blocks
// with shopfronts, the lifting rig (timber cribbing + iron jackscrews), the wagon, plank walks, sewer pipes,
// temporary stairs, signs. Ours.
import * as THREE from "three";
import { Batch, boxGeo, lam, quad, V } from "./build";
import { twoTone } from "./shade";
import { frontHD, sideHD, Front, boardTex, boardsHD } from "./chpaint";
import { beamHD } from "./paint";

export const UB = new THREE.BoxGeometry(1, 1, 1);
/** unit box from (x0,y0,z0) to (x1,y1,z1) in the frame m */
export const ub = (b: Batch, mat: THREE.Material, m: THREE.Matrix4, x0: number, x1: number, y0: number, y1: number, z0: number, z1: number) =>
  b.add(UB, mat, m.clone().multiply(new THREE.Matrix4().compose(V((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), new THREE.Quaternion(), V(x1 - x0, y1 - y0, z1 - z0))));
export const M = {
  trim: () => lam("chTrim", () => ({ color: "#ece0c6" })),
  stone: () => lam("chStone", () => ({ color: "#cfc2a8" })),
  roof: () => lam("chRoof", () => ({ color: "#6e6460" })),
  iron: () => twoTone(new THREE.MeshPhongMaterial({ color: "#4f5666", specular: "#8a8a8a", shininess: 60 }), 0.15),
  timber: () => lam("chTimber", () => ({ map: beamHD() })),
  plank: () => lam("chBoards", () => ({ map: boardsHD() })),
  wood: (c: string) => lam("chWood" + c, () => ({ color: c })),
  col: (c: string) => lam("chCol" + c, () => ({ color: c })),
};
let IRON: THREE.Material | null = null;
export const iron = () => (IRON ??= M.iron());

export type BlockOpts = {
  key: string; w: number; d: number; front: Front;
  /** cornice style: brackets under a deep cornice, or a plain parapet */
  cornice?: "brackets" | "plain"; awning?: string | null; chimneys?: number; flag?: boolean;
};
/** total wall height of a block */
export const blockH = (f: Front) => f.groundH + (f.floors - 1) * f.floorH + 0.6;

/** one commercial block in its own local frame: front facade on z = 0 facing +z, x 0..w, back to z = -d, base y = 0 */
export const block = (b: Batch, o: BlockOpts) => {
  const f = o.front, w = o.w, d = o.d, h = blockH(f), m = new THREE.Matrix4();
  const front = lam("fr" + o.key, () => ({ map: frontHD(o.key, w, h, f) }));
  const side = lam("sd" + o.key + Math.round(h), () => ({ map: sideHD(o.key + Math.round(h), d, h, f.wall, true) }));
  b.add(quad(V(0, 0, 0), V(w, 0, 0), V(w, h, 0), V(0, h, 0)), front);
  b.add(quad(V(w, 0, -d), V(0, 0, -d), V(0, h, -d), V(w, h, -d)), side);
  b.add(quad(V(0, 0, -d), V(0, 0, 0), V(0, h, 0), V(0, h, -d)), side);
  b.add(quad(V(w, 0, 0), V(w, 0, -d), V(w, h, -d), V(w, h, 0)), side);
  b.add(quad(V(0, h, 0), V(w, h, 0), V(w, h, -d), V(0, h, -d)), M.roof());
  b.add(quad(V(0, 0, -d), V(w, 0, -d), V(w, 0, 0), V(0, 0, 0)), M.col("#2a2020")); // underside (seen when lifted)
  const tm = M.trim();
  // cornice: a deep moulded band with brackets, parapet behind
  ub(b, tm, m, -0.15, w + 0.15, h - 0.55, h - 0.25, 0, 0.42);
  ub(b, tm, m, -0.25, w + 0.25, h - 0.25, h + 0.06, -0.05, 0.6); // top proud of the roof plane (was coplanar with it)
  if (o.cornice !== "plain") for (let x = 0.4; x < w - 0.2; x += 1.2) ub(b, tm, m, x - 0.1, x + 0.1, h - 1.0, h - 0.55, 0, 0.32);
  ub(b, M.col("#8a5a44"), m, 0, w, h, h + 0.5, -0.4, -0.05); // parapet (brick)
  // string courses + sills + lintels as relief, matching frontHD's layout
  const nWin = Math.max(2, Math.floor(w / 2.3));
  for (let fl = 1; fl < f.floors; fl++) {
    const y = f.groundH + (fl - 1) * f.floorH;
    ub(b, tm, m, -0.05, w + 0.05, y - 0.12, y, 0, 0.1);
    for (let i = 0; i < nWin; i++) {
      const cx = ((i + 0.5) * w) / nWin, ww = Math.min(1.05, w / nWin - 0.9), sill = y + 0.75, wh = Math.min(2.1, f.floorH - 1.0);
      ub(b, tm, m, cx - ww / 2 - 0.1, cx + ww / 2 + 0.1, sill - 0.04, sill + 0.06, 0, 0.14);
      ub(b, tm, m, cx - ww / 2 - 0.16, cx + ww / 2 + 0.16, sill + wh + 0.06, sill + wh + 0.3, 0, 0.12);
    }
  }
  if (!f.hotel) {
    // shopfront: pilasters, a projecting sign board ledge, cornice over the shopfront, stall riser
    const fc = M.col(f.frame);
    for (const x of [0.05, w / 2 - 0.85, w / 2 + 0.85, w - 0.05]) ub(b, fc, m, x - 0.16, x + 0.16, 0, f.groundH - 0.05, 0, 0.18);
    ub(b, fc, m, -0.05, w + 0.05, f.groundH - 0.12, f.groundH + 0.02, 0, 0.32);
    ub(b, fc, m, 0.2, w - 0.2, 0, 0.6, 0, 0.08);
    if (o.awning) awning(b, o.awning, w, f.groundH - 0.85);
  } else {
    ub(b, tm, m, -0.05, w + 0.05, 0, 0.5, 0, 0.12);
    ub(b, tm, m, -0.05, w + 0.05, f.groundH - 0.1, f.groundH + 0.05, 0, 0.3);
  }
  for (let i = 0; i < (o.chimneys ?? 2); i++) {
    const cx = w * (0.25 + 0.5 * i), cz = -d * (0.4 + 0.2 * (i % 2));
    ub(b, M.col("#9a5a44"), m, cx - 0.35, cx + 0.35, h, h + 1.5, cz - 0.5, cz + 0.5);
    ub(b, M.col("#6b4a40"), m, cx - 0.42, cx + 0.42, h + 1.5, h + 1.7, cz - 0.57, cz + 0.57);
  }
  return h;
};
/** striped canvas awning sloping out over the shopfront */
const awning = (b: Batch, col: string, w: number, y: number) => {
  const tex = boardTex("awn" + col, 256, 64, col, [], {});
  const mat = lam("awn" + col, () => ({ map: stripes(col), side: THREE.DoubleSide }));
  void tex;
  b.add(quad(V(0.3, y - 0.9, 1.5), V(w - 0.3, y - 0.9, 1.5), V(w - 0.3, y, 0.05), V(0.3, y, 0.05), (w - 0.6) / 0.5, 1), mat);
  b.add(quad(V(0.3, y - 1.15, 1.5), V(w - 0.3, y - 1.15, 1.5), V(w - 0.3, y - 0.9, 1.5), V(0.3, y - 0.9, 1.5), (w - 0.6) / 0.5, 0.3), mat);
};
const stripes = (col: string) => {
  const cv = document.createElement("canvas"); cv.width = 64; cv.height = 16;
  const g = cv.getContext("2d")!; g.fillStyle = "#efe6d2"; g.fillRect(0, 0, 64, 16); g.fillStyle = col; g.fillRect(0, 0, 32, 16);
  const t = new THREE.CanvasTexture(cv); t.colorSpace = THREE.SRGBColorSpace; t.wrapS = t.wrapT = THREE.RepeatWrapping; return t;
};

/** a block placed on a street line: north row (faces +z) at z = zf, or south row (faces -z); x0 is the low-x corner */
export const placeM = (x0: number, w: number, zf: number, faceSouth: boolean, y = 0) =>
  faceSouth ? new THREE.Matrix4().makeRotationY(Math.PI).setPosition(x0 + w, y, zf) : new THREE.Matrix4().setPosition(x0, y, zf);

/** build a batch into its own group (for things that move: a lifted building, a crib) */
export const groupOf = (b: Batch, cast = true) => { const g = new THREE.Group(); b.build(g, cast); return g; };

// ---------------- the lifting rig: timber cribbing + iron jackscrews under a wall line ----------------
const CRIB_T = 0.24; // timber section
/** jackscrew: base housing, threaded stem, head with a bar through it (local: base at y = 0, height 1) */
export class JackGeo {
  static base = new THREE.CylinderGeometry(0.13, 0.19, 0.32, 14).translate(0, 0.16, 0);
  static stem = new THREE.CylinderGeometry(0.065, 0.065, 1, 12).translate(0, 0.5, 0);
  static head = new THREE.CylinderGeometry(0.11, 0.11, 0.12, 14).translate(0, 0.06, 0);
  static bar = new THREE.CylinderGeometry(0.022, 0.022, 1.1, 8).rotateZ(Math.PI / 2);
}
const ringTex = () => {
  const cv = document.createElement("canvas"); cv.width = 16; cv.height = 64;
  const g = cv.getContext("2d")!; g.fillStyle = "#4a4f5a"; g.fillRect(0, 0, 16, 64);
  for (let y = 0; y < 64; y += 8) { g.fillStyle = "#23262e"; g.fillRect(0, y, 16, 3); g.fillStyle = "#7a808c"; g.fillRect(0, y + 3, 16, 1); }
  const t = new THREE.CanvasTexture(cv); t.colorSpace = THREE.SRGBColorSpace; t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(1, 6); return t;
};
let STEM: THREE.Material | null = null;
export const stemMat = () => (STEM ??= twoTone(new THREE.MeshPhongMaterial({ color: "#ffffff", map: ringTex(), specular: "#777777", shininess: 50 }), 0.15));

/** instanced cribbing + screws along one or more wall lines; pose(lift) restacks them each frame */
export class Lifter {
  group = new THREE.Group();
  private cribA: THREE.InstancedMesh; private cribB: THREE.InstancedMesh;
  private base: THREE.InstancedMesh; private stem: THREE.InstancedMesh; private head: THREE.InstancedMesh; private bar: THREE.InstancedMesh;
  private m4 = new THREE.Matrix4(); private q = new THREE.Quaternion(); private p = new THREE.Vector3(); private s = new THREE.Vector3();
  /** spots: [x, z, yaw] per screw (world, building local already applied by the caller) */
  constructor(private spots: [number, number, number][], private maxLayers = 9) {
    const n = spots.length * maxLayers;
    const tm = M.timber();
    this.cribA = new THREE.InstancedMesh(UB, tm, n); this.cribB = new THREE.InstancedMesh(UB, tm, n);
    const ir = iron();
    this.base = new THREE.InstancedMesh(JackGeo.base, ir, spots.length);
    this.stem = new THREE.InstancedMesh(JackGeo.stem, stemMat(), spots.length);
    this.head = new THREE.InstancedMesh(JackGeo.head, ir, spots.length);
    this.bar = new THREE.InstancedMesh(JackGeo.bar, ir, spots.length);
    for (const im of [this.cribA, this.cribB, this.base, this.stem, this.head, this.bar]) { im.castShadow = true; im.receiveShadow = true; im.frustumCulled = false; this.group.add(im); }
  }
  /** lift = gap under the building (m); turn = bar angle (rad) */
  pose(lift: number, turn = 0) {
    const screwH = Math.min(lift, 0.55 + 0.25 * ((lift * 7) % 1)); // the screw makes up what the timbers do not
    const crib = Math.max(0, lift - screwH), layers = Math.min(this.maxLayers, Math.floor(crib / CRIB_T + 1e-6));
    const { m4, q, p, s } = this;
    let a = 0, bI = 0;
    this.spots.forEach(([x, z, yaw], i) => {
      for (let k = 0; k < layers; k++) {
        const along = k % 2 === 0;
        q.setFromAxisAngle(V(0, 1, 0), yaw + (along ? 0 : Math.PI / 2));
        m4.compose(p.set(x, (k + 0.5) * CRIB_T, z), q, s.set(1.1, CRIB_T * 0.96, CRIB_T));
        if (along) this.cribA.setMatrixAt(a++, m4); else this.cribB.setMatrixAt(bI++, m4);
      }
      const y0 = layers * CRIB_T, stemLen = Math.max(0.02, lift - y0 - 0.32 - 0.12);
      q.setFromAxisAngle(V(0, 1, 0), yaw);
      this.base.setMatrixAt(i, m4.compose(p.set(x, y0, z), q, s.set(1, 1, 1)));
      this.stem.setMatrixAt(i, m4.compose(p.set(x, y0 + 0.32, z), q, s.set(1, stemLen, 1)));
      q.setFromAxisAngle(V(0, 1, 0), yaw + turn);
      this.head.setMatrixAt(i, m4.compose(p.set(x, y0 + 0.32 + stemLen, z), q, s.set(1, 1, 1)));
      this.bar.setMatrixAt(i, m4.compose(p.set(x, y0 + 0.32 + stemLen + 0.06, z), q, s.set(1, 1, 1)));
    });
    this.cribA.count = a; this.cribB.count = bI;
    for (const im of [this.cribA, this.cribB, this.base, this.stem, this.head, this.bar]) im.instanceMatrix.needsUpdate = true;
    this.group.visible = lift > 0.05;
  }
}
/** screw spots along the front wall of a block (world coords) at spacing ds, inset from the facade line */
export const frontSpots = (x0: number, x1: number, zf: number, faceSouth: boolean, ds = 1.25, inset = 0.45): [number, number, number][] => {
  const out: [number, number, number][] = [];
  for (let x = x0 + 0.6; x <= x1 - 0.5; x += ds) out.push([x, zf + (faceSouth ? inset : -inset), 0]);
  return out;
};

// ---------------- street things ----------------
/** plank walk segment on posts: x0..x1 along x, z0..z1, top at y */
export const plankWalk = (b: Batch, x0: number, x1: number, z0: number, z1: number, y: number, posts = true) => {
  const pm = M.plank(), tm = M.timber(), m = new THREE.Matrix4();
  b.add(boxGeo(V(x0, y - 0.08, z0), V(x1, y, z1), 2.5), pm);
  if (posts) for (let x = x0 + 0.4; x < x1; x += 2.4) for (const z of [z0 + 0.15, z1 - 0.15]) ub(b, tm, m, x - 0.09, x + 0.09, -0.6, y - 0.08, z - 0.09, z + 0.09);
};
/** a long plank lying from a to b (the gentleman's crossing) */
export const plankAcross = (b: Batch, a: THREE.Vector3, c: THREE.Vector3, w = 0.45) => {
  const dir = c.clone().sub(a), len = dir.length(), mid = a.clone().add(c).multiplyScalar(0.5);
  const q = new THREE.Quaternion().setFromUnitVectors(V(0, 0, 1), dir.normalize());
  b.add(new THREE.BoxGeometry(w, 0.07, len), M.plank(), new THREE.Matrix4().compose(mid, q, V(1, 1, 1)));
};
/** spoked wagon wheel geometry pieces into a batch at centre c, axis along z (wheel plane xy), radius r */
export const wheel = (b: Batch, c: THREE.Vector3, r: number, yaw = 0) => {
  const m = new THREE.Matrix4().makeRotationY(yaw).setPosition(c);
  const rim = new THREE.TorusGeometry(r, 0.045, 8, 32);
  const wd = M.wood("#7a4f30"), ir = iron();
  b.add(rim, ir, m);
  b.add(new THREE.TorusGeometry(r - 0.05, 0.04, 8, 32), wd, m);
  for (let i = 0; i < 12; i++) { const a = (i / 12) * Math.PI * 2; b.add(new THREE.CylinderGeometry(0.022, 0.026, r - 0.08, 6).translate(0, (r - 0.08) / 2 + 0.06, 0).rotateZ(a), wd, m); }
  b.add(new THREE.CylinderGeometry(0.1, 0.1, 0.22, 12).rotateX(Math.PI / 2), wd, m);
};
/** farm wagon: bed, sideboards, four wheels; base y = 0 at the wheel bottoms, length along local x */
export const wagon = (b: Batch, x: number, y: number, z: number, yaw: number, load = true) => {
  const m = new THREE.Matrix4().makeRotationY(yaw).setPosition(x, y, z), wd = M.wood("#8a5a34"), dk = M.wood("#6a4428");
  ub(b, wd, m, -1.6, 1.6, 0.85, 0.97, -0.75, 0.75);
  for (const s of [-1, 1]) ub(b, dk, m, -1.6, 1.6, 0.97, 1.45, s * 0.75 - 0.05, s * 0.75 + 0.05);
  for (const s of [-1, 1]) ub(b, dk, m, s * 1.6 - 0.05, s * 1.6 + 0.05, 0.97, 1.4, -0.75, 0.75);
  ub(b, dk, m, 1.6, 3.2, 0.62, 0.7, -0.05, 0.05); // tongue
  if (load) { const sacks = M.col("#d8c49a"); for (let i = 0; i < 5; i++) b.add(new THREE.SphereGeometry(0.34, 12, 9).scale(1.2, 0.75, 1), sacks, m.clone().multiply(new THREE.Matrix4().makeTranslation(-1.1 + i * 0.55, 1.18, (i % 2 ? 0.25 : -0.22)))); }
  for (const [wx, r] of [[-1.15, 0.72], [1.05, 0.55]] as const) for (const s of [-1, 1]) {
    const c = V(wx, r, s * 0.92).applyMatrix4(m);
    wheel(b, c, r, yaw);
  }
};
/** big brick sewer pipe section along x, centre at (x, y, z), length L */
export const pipe = (b: Batch, x: number, y: number, z: number, L: number, r = 0.85) => {
  const m = new THREE.Matrix4().makeRotationZ(Math.PI / 2).setPosition(x, y, z);
  b.add(new THREE.CylinderGeometry(r, r, L, 28, 1, true), M.col("#9a5e4c"), m);
  b.add(new THREE.CylinderGeometry(r * 0.78, r * 0.78, L, 24, 1, true), M.col("#3a2420"), m);
  b.add(new THREE.RingGeometry(r * 0.78, r, 28).rotateY(Math.PI / 2), M.col("#a86a56"), new THREE.Matrix4().setPosition(x + L / 2, y, z));
  b.add(new THREE.RingGeometry(r * 0.78, r, 28).rotateY(-Math.PI / 2), M.col("#a86a56"), new THREE.Matrix4().setPosition(x - L / 2, y, z));
  for (const dx of [-L / 2 + 0.12, L / 2 - 0.12]) b.add(new THREE.CylinderGeometry(r + 0.05, r + 0.05, 0.22, 28, 1, true), M.col("#84503e"), new THREE.Matrix4().makeRotationZ(Math.PI / 2).setPosition(x + dx, y, z));
};
/** temporary wooden stairs rising along local +z from (x, y0, z0) up to y1, width w */
export const stairs = (b: Batch, x: number, y0: number, z0: number, y1: number, w = 1.2, dir = -1) => {
  const n = Math.max(2, Math.round((y1 - y0) / 0.2)), run = 0.28, m = new THREE.Matrix4(), pm = M.plank(), tm = M.timber();
  for (let i = 0; i < n; i++) {
    const yy = y0 + ((i + 1) * (y1 - y0)) / n, zz = z0 + dir * (n - 1 - i) * run;
    ub(b, pm, m, x - w / 2, x + w / 2, yy - 0.05, yy, Math.min(zz, zz + dir * run), Math.max(zz, zz + dir * run));
  }
  for (const s of [-1, 1]) {
    const a = V(x + s * (w / 2 + 0.04), y0, z0 + dir * n * run), c = V(x + s * (w / 2 + 0.04), y1, z0);
    const dirv = c.clone().sub(a), len = dirv.length();
    b.add(new THREE.BoxGeometry(0.06, 0.22, len), tm, new THREE.Matrix4().compose(a.clone().add(c).multiplyScalar(0.5), new THREE.Quaternion().setFromUnitVectors(V(0, 0, 1), dirv.normalize()), V(1, 1, 1)));
    // rickety handrail on two posts
    ub(b, tm, m, x + s * (w / 2 + 0.06) - 0.04, x + s * (w / 2 + 0.06) + 0.04, y0, y0 + 1.0, z0 + dir * n * run - 0.04, z0 + dir * n * run + 0.04);
    ub(b, tm, m, x + s * (w / 2 + 0.06) - 0.04, x + s * (w / 2 + 0.06) + 0.04, y1, y1 + 1.0, z0 - 0.04, z0 + 0.04);
    const ra = V(x + s * (w / 2 + 0.06), y0 + 0.95, z0 + dir * n * run), rc = V(x + s * (w / 2 + 0.06), y1 + 0.95, z0), rd = rc.clone().sub(ra);
    b.add(new THREE.BoxGeometry(0.05, 0.05, rd.length()), tm, new THREE.Matrix4().compose(ra.clone().add(rc).multiplyScalar(0.5), new THREE.Quaternion().setFromUnitVectors(V(0, 0, 1), rd.clone().normalize()), V(1, 1, 1)));
  }
};
/** a painted board on one or two posts (sign); unlit face (the skill's fix: side light turns signs grey-blue) */
export const signBoard = (root: THREE.Object3D, tex: THREE.Texture, x: number, y: number, z: number, w: number, h: number, yaw: number, posts: 0 | 1 | 2, postH = 0, tilt = 0) => {
  const g = new THREE.Group();
  const face = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ map: tex, color: 0xe2e2e2 }));
  face.position.z = 0.035;
  const back = new THREE.Mesh(new THREE.BoxGeometry(w + 0.06, h + 0.06, 0.06), M.timber());
  g.add(face, back);
  const tm = M.timber();
  if (posts === 1) { const p = new THREE.Mesh(new THREE.BoxGeometry(0.1, postH, 0.1), tm); p.position.set(0, -h / 2 - postH / 2 + 0.2, -0.06); g.add(p); }
  if (posts === 2) for (const s of [-1, 1]) { const p = new THREE.Mesh(new THREE.BoxGeometry(0.1, postH, 0.1), tm); p.position.set(s * (w / 2 - 0.1), -h / 2 - postH / 2 + 0.2, -0.06); g.add(p); }
  g.position.set(x, y, z); g.rotation.set(tilt, yaw, 0, "YXZ");
  g.traverse((o) => { o.castShadow = true; o.receiveShadow = true; });
  root.add(g);
  return g;
};
