// The Chicago River at dusk (seg 8): the river bending between stone quays, warehouses and shops along both banks with
// warm windows, gas lamps on the north quay that light one by one as the lamplighter passes, a small rowboat drifting
// against where the current used to run. Golden light, sun low ahead. Local frame, placed at story.RIVER.
import * as THREE from "three";
import { Batch, boxGeo, lam } from "../../../kit/build";
import { sideHD, glowTex, Front } from "../../../kit/chpaint";
import { stoneHD, ctex } from "../../../kit/paint";
import { block, M, ub } from "../../../kit/blocks";
import { waterMat } from "../../../kit/water";
import { SetPiece, quadUp } from "../../../kit/set";
import { RIVER, lin } from "../story";
import { NOINK } from "../../../post/ink";

export const zc = (x: number) => 10 * Math.sin(x / 45);
export const HALF = 14, QUAY = 1.0, WATER = -0.8;
/** gas lamps along the north quay: x positions; each lights at its frame */
export const LAMPS = Array.from({ length: 16 }, (_, k) => -36 + k * 6);
export const lampOn = (k: number) => 3392 + k * 9; // the lamplighter's pace
export const lampPos = (x: number): [number, number, number] => [x, QUAY, zc(x) - HALF - 1.0];
/** the boat: drifting slowly upstream (-x) on the river's centreline */
export const boatAt = (f: number): [number, number, number] => { const x = lin([[3382, 9], [3614, -1]], f); return [x, WATER + 0.3, zc(x) + 3]; };
const BRICKS = ["#9a4a3a", "#a8553e", "#b07448", "#8f4a3c", "#b5654a"];

const winTex = () => ctex("duskWindows", 256, 256, (g) => {
  g.clearRect(0, 0, 256, 256);
  for (let y = 20; y < 256; y += 64) for (let x = 16; x < 256; x += 60) if ((x * 7 + y * 3) % 5 < 2) { g.fillStyle = "rgba(255,200,120,1)"; g.fillRect(x, y, 26, 40); }
});

export class River implements SetPiece {
  root = new THREE.Group();
  private lamps: { glass: THREE.MeshBasicMaterial; glow: THREE.Sprite; k: number }[] = [];
  private boat = new THREE.Group(); private oars: THREE.Mesh[] = [];
  constructor() {
    const R = this.root, b = new Batch(), m = new THREE.Matrix4();
    R.position.set(...RIVER);
    const water = new THREE.Mesh(quadUp(-600, 600, -600, 600, WATER, 1), waterMat("#000000", 0, 0.5));
    water.receiveShadow = true; R.add(water);
    // banks: strips following the curve, quay walls facing the water
    const quayM = lam("quayStone", () => ({ map: stoneHD("quayHD", ["#b8a894", "#ad9d88", "#c2b3a0", "#a39380"], "#857663") }));
    const land = lam("quayTop", () => ({ map: stoneHD("quayTopHD", ["#a89a88", "#9e907e", "#b2a492"], "#7d705f") }));
    const step = 3;
    for (let x = -300; x < 300; x += step) {
      for (const s of [-1, 1]) {
        const e0 = zc(x) + s * HALF, e1 = zc(x + step) + s * HALF, far = s * 260;
        const top = new THREE.BufferGeometry(), za = Math.min(e0, far), zb = Math.max(e0, far), za1 = Math.min(e1, far), zb1 = Math.max(e1, far);
        top.setAttribute("position", new THREE.Float32BufferAttribute([x, QUAY, za, x + step, QUAY, za1, x + step, QUAY, zb1, x, QUAY, za, x + step, QUAY, zb1, x, QUAY, zb], 3));
        top.setAttribute("normal", new THREE.Float32BufferAttribute(Array(6).fill([0, 1, 0]).flat(), 3));
        top.setAttribute("uv", new THREE.Float32BufferAttribute([x / 4, za / 4, (x + step) / 4, za1 / 4, (x + step) / 4, zb1 / 4, x / 4, za / 4, (x + step) / 4, zb1 / 4, x / 4, zb / 4], 2));
        // winding: make it face up
        const pos = top.attributes.position as THREE.BufferAttribute;
        { for (const [i, j] of [[1, 2], [4, 5]]) { const a = [pos.getX(i), pos.getY(i), pos.getZ(i)]; pos.setXYZ(i, pos.getX(j), pos.getY(j), pos.getZ(j)); pos.setXYZ(j, a[0], a[1], a[2]); } }
        b.add(top, land);
        const wall = new THREE.BufferGeometry(), y0 = WATER - 0.5, y1 = QUAY;
        const pts = s < 0 ? [x, y0, e0, x + step, y0, e1, x + step, y1, e1, x, y0, e0, x + step, y1, e1, x, y1, e0] : [x + step, y0, e1, x, y0, e0, x, y1, e0, x + step, y0, e1, x, y1, e0, x + step, y1, e1];
        wall.setAttribute("position", new THREE.Float32BufferAttribute(pts, 3));
        wall.computeVertexNormals();
        wall.setAttribute("uv", new THREE.Float32BufferAttribute([0, 0, step / 3, 0, step / 3, 0.6, 0, 0, step / 3, 0.6, 0, 0.6], 2));
        b.add(wall, quayM);
      }
    }
    // mooring posts and a plank landing on the south quay near the boat
    for (let x = -30; x < 60; x += 9) ub(b, M.timber(), m, x - 0.1, x + 0.1, QUAY, QUAY + 0.6, zc(x) + HALF - 0.4, zc(x) + HALF - 0.2);
    b.build(R, true);
    // buildings along both banks, facing the water, set back behind the quay walk
    let n = 0;
    for (const s of [-1, 1]) for (let x = -160; x < 220; x += 0) {
      const w = 8 + ((n * 5) % 4) * 2, floors = 3 + (n % 3), f: Front = { wall: BRICKS[n % 5], brick: true, frame: "#3a3a3a", board: "#2a3a2e", ink: "#f0dca0",
        name: ["WAREHOUSE", "SHIP CHANDLER", "GRAIN", "LUMBER", "HOTEL", "SALOON"][n % 6], goods: "none", floors, groundH: 3.8, floorH: 3.1 };
      const bb = new Batch();
      block(bb, { key: "rv" + (n % 12), w, d: 14, front: f, chimneys: 1 });
      const g = new THREE.Group(); bb.build(g);
      const zf = (zc(x) + zc(x + w)) / 2 + s * (HALF + 6), yaw = s < 0 ? 0 : Math.PI, mm = new THREE.Matrix4().makeRotationY(yaw).setPosition(s < 0 ? x : x + w, QUAY, zf);
      g.applyMatrix4(mm); R.add(g);
      // lit windows: an emissive overlay just in front of the facade
      const win = new THREE.Mesh(new THREE.PlaneGeometry(w, floors * 3.1), new THREE.MeshBasicMaterial({ map: winTex(), color: new THREE.Color(2.2, 1.6, 0.9), transparent: true, depthWrite: false }));
      win.position.set(w / 2, 3.8 + (floors - 1) * 1.55, 0.05); win.layers.set(NOINK); g.add(win);
      x += w + 2 + (n % 3) * 3; n++;
    }
    // gas lamps on the north quay
    for (let k = 0; k < LAMPS.length; k++) {
      const [x, y, z] = lampPos(LAMPS[k]);
      const post = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.09, 3.2, 8).translate(0, 1.6, 0), lam("lampIron", () => ({ color: "#2e3038" })));
      post.position.set(x, y, z); post.castShadow = true;
      const glass = new THREE.MeshBasicMaterial({ color: new THREE.Color(0.35, 0.33, 0.3) });
      const head = new THREE.Mesh(new THREE.CylinderGeometry(0.2, 0.13, 0.45, 6), glass); head.position.set(x, y + 3.45, z);
      const cap = new THREE.Mesh(new THREE.ConeGeometry(0.26, 0.22, 6), lam("lampIron", () => ({ color: "#2e3038" }))); cap.position.set(x, y + 3.78, z);
      const glow = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex(), color: new THREE.Color(1.5, 1.0, 0.55), transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, fog: false }));
      glow.position.set(x, y + 3.45, z); glow.scale.setScalar(2.8); glow.layers.set(NOINK);
      R.add(post, head, cap, glow);
      this.lamps.push({ glass, glow, k });
    }
    // the rowboat: a half-ellipsoid hull with a rim, two oars
    const hull = new THREE.Mesh(new THREE.SphereGeometry(1, 24, 12, 0, Math.PI * 2, Math.PI / 2, Math.PI / 2).scale(1.9, 0.55, 0.7), M.wood("#8a4a2a"));
    const inside = new THREE.Mesh(new THREE.CircleGeometry(1, 24).rotateX(-Math.PI / 2).scale(1.82, 1, 0.64), M.wood("#c08a5a")); inside.position.y = -0.08;
    const rim = new THREE.Mesh(new THREE.TorusGeometry(1, 0.05, 6, 32).rotateX(Math.PI / 2).scale(1.9, 1, 0.7), M.wood("#5a3424"));
    this.boat.add(hull, inside, rim);
    for (const s of [-1, 1]) { const o = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 2.6, 6).rotateX(Math.PI / 2), M.wood("#c8a070")); o.position.set(0, 0.25, s * 1.0); this.boat.add(o); this.oars.push(o); }
    this.boat.traverse((o) => { o.castShadow = true; o.receiveShadow = true; });
    R.add(this.boat);
    void boxGeo; void sideHD;
  }
  pose(_id: number, f: number) {
    for (const L of this.lamps) {
      const on = Math.min(1, Math.max(0, (f - lampOn(L.k)) / 6));
      L.glass.color.setRGB(0.35 + 3.0 * on, 0.33 + 2.1 * on, 0.3 + 1.0 * on);
      L.glow.visible = on > 0.02; (L.glow.material as THREE.SpriteMaterial).opacity = on;
    }
    const [x, y, z] = boatAt(f);
    this.boat.position.set(x, y + 0.03 * Math.sin(f / 13), z);
    this.boat.rotation.set(0.02 * Math.sin(f / 17), 0.15, 0.015 * Math.sin(f / 11));
    const a = 0.4 * Math.sin(f / 22);
    this.oars.forEach((o, i) => { o.rotation.set(0, a * (i ? 1 : -1), 0.25); });
  }
}
