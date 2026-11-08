// The buried street, as a diorama cut (seg 7, shot 39): the finished raised street with strollers on top, and below
// it, behind a cut face painted as earth strata, the old street level preserved in a vault: the old plank walk, mud,
// and the hero's old storefront doorway (J. HOLLIS DRY GOODS, the hook's shop) left at the bottom. The camera cranes
// down the cut face. Local frame, cut plane z = 0 (everything at z < 0), placed at story.SECTION.
import * as THREE from "three";
import { Batch, boxGeo, lam } from "../../../kit/build";
import { strataHD, pavingHD, mudHD, frontHD, sideHD, Front, glowTex } from "../../../kit/chpaint";
import { block, placeM, plankWalk, M, ub } from "../../../kit/blocks";
import { stoneHD } from "../../../kit/paint";
import { SetPiece, quadUp, V } from "../../../kit/set";
import { SECTION, RAISE } from "../story";
import { NOINK } from "../../../post/ink";

/** the vault under the street: x -3.6..3.6, z -9..0, old grade y = 0 up to the street's underside */
export const VAULT = { x0: -2.4, x1: 2.4, z0: -9.2, top: RAISE - 0.35 };
const OLD: Front = { wall: "#9a4a3a", brick: true, frame: "#2f4a3a", board: "#d8c49a", ink: "#5a2a20", name: "J. HOLLIS DRY GOODS", goods: "cloth", floors: 1, groundH: 3.9, floorH: 3.2 };

export class Section implements SetPiece {
  root = new THREE.Group();
  constructor() {
    const R = this.root, b = new Batch(), m = new THREE.Matrix4();
    R.position.set(...SECTION);
    const strata = lam("strata", () => ({ map: strataHD() }));
    const pave = lam("pavingHD", () => ({ map: pavingHD() })), mud = lam("mudHD", () => ({ map: mudHD() }));
    // the cut block: fill from y -1.6 (old mud below grade) to the street; front face at z = 0 with a hole for the vault
    const yb = -1.6, xa = -14, xb = 14;
    const face = (x0: number, x1: number, y0: number, y1: number) => {
      const g = new THREE.BufferGeometry(), ua = (x0 - xa) / 4, ub2 = (x1 - xa) / 4, va = (y0 - yb) / (RAISE - yb), vb = (y1 - yb) / (RAISE - yb);
      g.setAttribute("position", new THREE.Float32BufferAttribute([x0, y0, 0, x1, y0, 0, x1, y1, 0, x0, y0, 0, x1, y1, 0, x0, y1, 0], 3));
      g.setAttribute("normal", new THREE.Float32BufferAttribute(Array(6).fill([0, 0, 1]).flat(), 3));
      g.setAttribute("uv", new THREE.Float32BufferAttribute([ua, va, ub2, va, ub2, vb, ua, va, ub2, vb, ua, vb], 2));
      return g;
    };
    b.add(face(xa, VAULT.x0, yb, RAISE), strata);
    b.add(face(VAULT.x1, xb, yb, RAISE), strata);
    b.add(face(VAULT.x0, VAULT.x1, VAULT.top, RAISE), strata);
    b.add(face(VAULT.x0, VAULT.x1, yb, 0), strata);
    for (const x of [xa, xb]) b.add(boxGeo(V(x - 0.01, yb, -30), V(x + 0.01, RAISE, 0), 4), strata); // side cut faces
    // street on top (paving), sidewalk at the back, the raised row of shops behind
    b.add(quadUp(xa, xb, -9.5, 0, RAISE, 4), pave);
    b.add(boxGeo(V(xa, RAISE - 0.02, -13), V(xb, RAISE + 0.12, -9.5), 2), lam("flagstone", () => ({ map: sideHD("flagstone", 8, 8, "#b8ab98", false) })));
    for (const x of [-10, -2, 6]) { // gas lamps on the walk
      ub(b, M.col("#2e3038"), m, x - 0.06, x + 0.06, RAISE, RAISE + 3.2, -10.2, -10.08);
      ub(b, lam("lampGlass", () => ({ color: "#f3e6c0" })), m, x - 0.2, x + 0.2, RAISE + 3.2, RAISE + 3.65, -10.34, -9.94);
    }
    // the vault: its floor is the old street (mud), the old plank walk, earth walls, the street's joists overhead
    b.add(quadUp(VAULT.x0, VAULT.x1, VAULT.z0, 0, 0, 6), mud);
    plankWalk(b, VAULT.x0, VAULT.x1, VAULT.z0, VAULT.z0 + 2.4, 0.4, true);
    for (const x of [VAULT.x0, VAULT.x1]) b.add(boxGeo(V(x - 0.3, 0, VAULT.z0), V(x + 0.3, VAULT.top, 0), 2), lam("vaultStone", () => ({ map: stoneHD("vaultStoneHD", ["#b08a72", "#a8826a", "#b8927a"], "#7a5a48") })));
    for (let x = VAULT.x0; x <= VAULT.x1; x += 0.9) ub(b, M.timber(), m, x - 0.1, x + 0.1, VAULT.top - 0.25, VAULT.top, VAULT.z0, 0);
    b.add(quadUp(VAULT.x0, VAULT.x1, VAULT.z0, 0, VAULT.top - 0.25, 2).rotateX(Math.PI).translate(0, 2 * (VAULT.top - 0.25), VAULT.z0), M.plank());
    b.build(R, false);
    // the old storefront at the back of the vault (unlifted, one storey showing)
    const sf = new Batch();
    const front = lam("oldFront", () => ({ map: frontHD("oldHollis", 4.8, 4.6, OLD), color: "#d8d0c8" }));
    sf.add(new THREE.PlaneGeometry(4.8, VAULT.top).translate(0, VAULT.top / 2, 0), front);
    const sg = new THREE.Group(); sf.build(sg, false); sg.position.set(0, 0, VAULT.z0 + 0.02);
    // crop the painted front to the vault height: shift its texture so the ground floor shows
    (front.map as THREE.Texture).repeat.set(1, VAULT.top / 4.6); (front.map as THREE.Texture).needsUpdate = true;
    R.add(sg);
    // the raised row behind (two buildings), standing at the new grade
    for (const [x0, w, k] of [[-14, 9, "s1"], [-5, 10, "s2"], [5, 9, "s3"]] as const) {
      const bb = new Batch();
      block(bb, { key: "sec" + k, w, d: 14, front: { wall: ["#b5654a", "#a8553e", "#c08a5a"][x0 < 0 ? (x0 < -10 ? 0 : 1) : 2], brick: true, frame: "#2f5a46", board: "#e9dcb8", ink: "#5a2a20",
        name: ["HATS & CAPS", "J. HOLLIS DRY GOODS", "DRUGS"][x0 < -10 ? 0 : x0 < 0 ? 1 : 2], goods: "cloth", floors: 4, groundH: 3.9, floorH: 3.2 }, chimneys: 1 });
      const g = new THREE.Group(); bb.build(g); g.applyMatrix4(placeM(x0, w, -13, false, RAISE)); R.add(g);
    }
    // a lantern left in the vault by a modern visitor? no: a faint daylight glow from a sidewalk grate overhead
    const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex(), color: new THREE.Color(0.5, 0.45, 0.35), transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, fog: false }));
    sp.scale.setScalar(3); sp.position.set(-1.6, VAULT.top - 0.6, -6.5); sp.layers.set(NOINK); R.add(sp);
    // ground beyond the cut block (the sides and back), so the diorama stands on something
    const gb = new Batch(); gb.add(quadUp(-200, 200, -200, 200, -0.02, 8), mud); gb.build(R, false);
  }
  pose() {}
}
