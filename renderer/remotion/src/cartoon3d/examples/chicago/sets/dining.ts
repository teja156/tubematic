// The Tremont House dining room while the hotel is being raised (seg 6): striped wallpaper over dark wainscot, tall
// windows on the left with the key light, chandeliers, round tables in white cloth with china, the hero table with a
// teacup that trembles at every turn of the screws below. Local frame, placed at story.DINING.
import * as THREE from "three";
import { Batch, boxGeo, lam } from "../../../kit/build";
import { wallpaperHD, glowTex } from "../../../kit/chpaint";
import { planksHD } from "../../../kit/paint";
import { M, ub } from "../../../kit/blocks";
import { SetPiece, quadUp, V } from "../../../kit/set";
import { DINING, lin } from "../story";
import { NOINK } from "../../../post/ink";

export const TABLES: [number, number][] = [[0, 0], [-3.4, -2.6], [3.4, -2.4], [-3.6, 2.2], [3.8, 2.6], [0.2, -5.0], [-6.2, -0.4]];
export const CUP: [number, number, number] = [0.32, 0.79, 0.34]; // the teacup on the hero table (local)
/** the tremble: a small fast shake while the building rises (seg 6, shot 35), strongest around "reportedly" */
export const tremble = (f: number) => (f < 2909 ? 0.25 : lin([[2909, 0.5], [2925, 1], [2960, 1], [2976, 0.4]], f));

export class Dining implements SetPiece {
  root = new THREE.Group();
  private cup = new THREE.Group();
  constructor() {
    const R = this.root, b = new Batch(), m = new THREE.Matrix4();
    R.position.set(...DINING);
    const H = 4.8;
    b.add(quadUp(-8, 8, -7, 8, 0, 2.5), lam("diningFloor", () => ({ map: planksHD(), color: "#b08a68" })));
    const paper = lam("wallpaper", () => ({ map: wallpaperHD() }));
    const wains = M.wood("#5a3424"), trim = M.trim();
    // back wall (z = -7), right wall (x = 8), left wall with windows (x = -8)
    b.add(boxGeo(V(-8, 1.1, -7.3), V(8, H, -7), 1), paper);
    b.add(boxGeo(V(-8, 0, -7.3), V(8, 1.1, -6.95), 2), wains);
    b.add(boxGeo(V(8, 1.1, -7), V(8.3, H, 8), 1), paper);
    b.add(boxGeo(V(7.95, 0, -7), V(8.3, 1.1, 8), 2), wains);
    for (const [z0, z1] of [[-7, -5.6], [-3.6, -2.2], [-0.2, 1.2], [3.2, 4.6], [6.6, 8]]) {
      b.add(boxGeo(V(-8.3, 1.1, z0), V(-8, H, z1), 1), paper);
      b.add(boxGeo(V(-8.3, 0, z0), V(-7.95, 1.1, z1), 2), wains);
    }
    for (const zc of [-4.6, -1.2, 2.2, 5.6]) { // tall windows: sill, frame, bright glass, red curtains
      ub(b, wains, m, -8.3, -7.95, 0, 0.9, zc - 1, zc + 1);
      ub(b, wains, m, -8.3, -7.95, 4.2, H, zc - 1, zc + 1);
      for (const s of [-1, 1]) ub(b, lam("curtain", () => ({ color: "#8c2f2f" })), m, -7.95, -7.75, 0.2, 4.4, zc + s * 0.9 - 0.25, zc + s * 0.9 + 0.25);
      ub(b, lam("valance", () => ({ color: "#7a2828" })), m, -7.95, -7.7, 4.0, 4.5, zc - 1.2, zc + 1.2);
    }
    b.add(boxGeo(V(-8, H, -7), V(8, H + 0.3, 8), 2), trim); // ceiling
    for (const z of [-7, 8]) ub(b, trim, m, -8, 8, H - 0.3, H, z - 0.12, z + 0.12);
    // tables, cloths, chairs, china
    const cloth = lam("cloth", () => ({ color: "#f4efe4" })), china = lam("china", () => ({ color: "#fbf7ee" })), chair = M.wood("#6a3a26");
    for (const [x, z] of TABLES) {
      b.add(new THREE.CylinderGeometry(0.78, 0.86, 0.76, 28), cloth, new THREE.Matrix4().makeTranslation(x, 0.38, z));
      b.add(new THREE.CylinderGeometry(0.8, 0.8, 0.03, 28), cloth, new THREE.Matrix4().makeTranslation(x, 0.775, z));
      for (let k = 0; k < 4; k++) {
        const a = (k / 4) * Math.PI * 2 + 0.4, px = x + Math.cos(a) * 0.5, pz = z + Math.sin(a) * 0.5;
        b.add(new THREE.CylinderGeometry(0.13, 0.11, 0.02, 20), china, new THREE.Matrix4().makeTranslation(px, 0.8, pz));
        const cx = x + Math.cos(a) * 1.15, cz = z + Math.sin(a) * 1.15, rot = new THREE.Matrix4().makeRotationY(-a + Math.PI / 2).setPosition(cx, 0, cz);
        ub(b, chair, rot, -0.22, 0.22, 0.44, 0.5, -0.22, 0.22);
        ub(b, chair, rot, -0.22, 0.22, 0.5, 1.05, 0.18, 0.24);
        for (const [lx, lz] of [[-0.18, -0.18], [0.18, -0.18], [-0.18, 0.18], [0.18, 0.18]]) ub(b, chair, rot, lx - 0.025, lx + 0.025, 0, 0.44, lz - 0.025, lz + 0.025);
      }
      if (x === 0 && z === 0) continue; // the hero table keeps its cloth clear for the cup
      b.add(new THREE.CylinderGeometry(0.05, 0.07, 0.22, 12), lam("vase", () => ({ color: "#3a6a9a" })), new THREE.Matrix4().makeTranslation(x, 0.9, z));
      b.add(new THREE.SphereGeometry(0.1, 12, 8), lam("flowers", () => ({ color: "#d0453a" })), new THREE.Matrix4().makeTranslation(x, 1.06, z));
    }
    // a sideboard and a painting on the back wall
    ub(b, wains, m, -3, 3, 0, 1.0, -6.95, -6.4);
    ub(b, lam("frameGold", () => ({ color: "#c9a24e" })), m, -1.6, 1.6, 2.2, 3.9, -6.98, -6.92);
    ub(b, lam("painting", () => ({ color: "#4a6a5a" })), m, -1.45, 1.45, 2.35, 3.75, -6.93, -6.9);
    b.build(R, true);
    // window light: bright glass panes (unlit, HDR) and chandeliers (HDR candles + glow)
    const pane = new THREE.MeshBasicMaterial({ color: new THREE.Color(1.6, 1.5, 1.3) });
    for (const zc of [-4.6, -1.2, 2.2, 5.6]) { const g = new THREE.Mesh(new THREE.PlaneGeometry(2, 3.3), pane); g.position.set(-8.1, 2.55, zc); g.rotation.y = Math.PI / 2; R.add(g); }
    const brass = lam("brass", () => ({ color: "#c9a24e" })), flame = new THREE.MeshBasicMaterial({ color: new THREE.Color(3.4, 2.4, 1.2) });
    for (const [x, z] of [[0, -1], [-4, 2.5], [4, -3]]) {
      const ch = new THREE.Group();
      ch.add(new THREE.Mesh(new THREE.TorusGeometry(0.55, 0.035, 8, 24).rotateX(Math.PI / 2), brass));
      const rod = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, 1.0, 6), brass); rod.position.y = 0.5; ch.add(rod);
      for (let k = 0; k < 6; k++) { const a = (k / 6) * Math.PI * 2, c = new THREE.Mesh(new THREE.SphereGeometry(0.05, 8, 6), flame); c.position.set(Math.cos(a) * 0.55, 0.08, Math.sin(a) * 0.55); ch.add(c); }
      const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex(), color: new THREE.Color(0.9, 0.7, 0.45), transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, fog: false }));
      sp.scale.setScalar(2.2); sp.layers.set(NOINK); ch.add(sp);
      ch.position.set(x, H - 1.3, z); R.add(ch);
    }
    // the teacup and saucer on the hero table (its own group: it trembles)
    const cupG = new THREE.CylinderGeometry(0.055, 0.04, 0.07, 20, 1, true), saucer = new THREE.CylinderGeometry(0.1, 0.07, 0.015, 24);
    const cup = new THREE.Mesh(cupG, lam("cupChina", () => ({ color: "#fbf7ee", side: THREE.DoubleSide }))); cup.position.y = 0.045;
    const tea = new THREE.Mesh(new THREE.CircleGeometry(0.05, 20).rotateX(-Math.PI / 2), lam("tea", () => ({ color: "#9a5a2a" }))); tea.position.y = 0.072; tea.name = "tea";
    const sc = new THREE.Mesh(saucer, lam("cupChina", () => ({ color: "#fbf7ee", side: THREE.DoubleSide })));
    const handle = new THREE.Mesh(new THREE.TorusGeometry(0.022, 0.006, 6, 12, Math.PI * 1.3), lam("cupChina", () => ({ color: "#fbf7ee" }))); handle.position.set(0.06, 0.045, 0); handle.rotation.z = -Math.PI / 2;
    this.cup.add(cup, tea, sc, handle);
    for (const o of this.cup.children) { o.castShadow = true; o.receiveShadow = true; }
    this.cup.position.set(...CUP); R.add(this.cup);
  }
  pose(_id: number, f: number) {
    const k = tremble(f), j = f % 2 ? 1 : -1;
    this.cup.position.set(CUP[0] + 0.0025 * k * j, CUP[1], CUP[2] + 0.0015 * k * Math.sin(f * 1.7));
    this.cup.rotation.z = 0.02 * k * j;
  }
}
