// The dug-out space under a brick building while it is being lifted (seg 4, and the quarter-turn callback in seg 7):
// dirt floor, the building's floor joists and sill beams overhead (they rise a little at every unison turn), rows
// of iron jackscrews on timber blocks, each turned by a capstan bar at waist height, lanterns, the old foundation at
// the back and the masons' new courses growing under it, an inch rule with a pointer on the beam. Open daylight at
// the front (+z). Local frame, placed at story.CRAWL.
import * as THREE from "three";
import { Batch, boxGeo, lam } from "../../../kit/build";
import { fillHD, sideHD, glowTex, letter, boardsHD } from "../../../kit/chpaint";
import { ctex, beamHD } from "../../../kit/paint";
import { M, ub, iron, stemMat, JackGeo } from "../../../kit/blocks";
import { SetPiece, quadUp, V } from "../../../kit/set";
import { CRAWL, CRAWL_H, turnsAt, lin, SHOTS } from "../story";
import { NOINK } from "../../../post/ink";

export const CRAWL_ROWS = [0, -2.4, -4.8]; // z of the screw rows
export const CRAWL_XS = Array.from({ length: 26 }, (_, i) => -15 + i * 1.2);
export const BAR_Y = 0.92; // capstan bar height
/** the building's rise (m) by frame: a little per turn (exaggerated from the real fraction of an inch so it reads) */
export const crawlLift = (f: number) => 0.012 * turnsAt(f);
/** the masons' new foundation: courses laid by frame f (seg 4 end) */
export const coursesAt = (id: number, f: number) => (id === 25 ? Math.floor(lin([[1976, 6], [2060, 14]], f)) : id > 25 || id === 38 ? 16 : 5);

const inchTex = () => ctex("inchRule", 128, 1024, (g) => {
  g.fillStyle = "#efe6cf"; g.fillRect(0, 0, 128, 1024);
  const px = 1024 / 12; // 12 inches
  for (let i = 0; i <= 12 * 8; i++) {
    const y = 1024 - (i / 8) * px, big = i % 8 === 0, half = i % 4 === 0;
    g.fillStyle = "#2a1a1a"; g.fillRect(0, y - (big ? 2.5 : 1), big ? 64 : half ? 44 : 24, big ? 5 : 2);
    if (big && i > 0 && i < 96) { g.font = "bold 40px 'DejaVu Serif', serif"; g.textAlign = "center"; g.textBaseline = "middle"; g.fillStyle = "#2a1a1a"; g.fillText(String(i / 8), 98, y + 2); }
  }
  void letter;
});

export class Crawl implements SetPiece {
  root = new THREE.Group();
  private top = new THREE.Group(); // joists, sills, floorboards: rises with the building
  private stems: THREE.InstancedMesh; private heads: THREE.InstancedMesh; private bars: THREE.InstancedMesh;
  private courses: THREE.InstancedMesh;
  private glow: THREE.Sprite[] = [];
  private m4 = new THREE.Matrix4(); private q = new THREE.Quaternion(); private p = new THREE.Vector3(); private s = new THREE.Vector3();
  private spots: [number, number][] = [];

  constructor() {
    const R = this.root, b = new Batch();
    R.position.set(...CRAWL);
    const dirt = lam("crawlDirt", () => ({ map: fillHD(), color: "#9a8a78" }));
    b.add(quadUp(-17, 17, -8, 9, 0, 6), dirt);
    b.add(quadUp(-60, 60, 9, 60, 0, 8), dirt); // the yard outside the open front
    // old foundation (stone rubble) at the back and both ends; the open front shows daylight
    const stone = lam("crawlStone", () => ({ map: sideHD("crawlStone", 12, 3, "#8a7a6a", false), color: "#b8a894" }));
    b.add(boxGeo(V(-17, 0, -8.4), V(17, CRAWL_H + 0.6, -7.6), 3), stone);
    for (const x of [-17.4, 16.6]) b.add(boxGeo(V(x, 0, -8.4), V(x + 0.8, CRAWL_H + 0.6, 6), 3), stone);
    b.build(R, true);
    // cribbing blocks under every screw
    const cb = new Batch(), tm = M.timber(), m = new THREE.Matrix4();
    for (const z of CRAWL_ROWS) for (const x of CRAWL_XS) {
      this.spots.push([x, z]);
      ub(cb, tm, m, x - 0.5, x + 0.5, 0, 0.14, z - 0.16, z + 0.16);
      ub(cb, tm, m, x - 0.16, x + 0.16, 0.14, 0.28, z - 0.5, z + 0.5);
    }
    // dirt heaps, a barrow plank, spare timbers
    for (const [x, z, r] of [[-12, 3.5, 1.1], [9, 4.2, 0.9], [-4, -6.6, 0.8]] as const) cb.add(new THREE.SphereGeometry(r, 16, 9, 0, Math.PI * 2, 0, Math.PI / 2).scale(1.5, 0.6, 1), dirt, new THREE.Matrix4().makeTranslation(x, 0, z));
    for (let i = 0; i < 4; i++) ub(cb, tm, m, 3 + i * 0.05, 6.5 + i * 0.05, 0.12 * i, 0.12 * i + 0.12, 3.4 + i * 0.3, 3.62 + i * 0.3);
    cb.build(R, true);
    // screws: base housings (static), stems + capstan heads + bars (instanced, posed per frame)
    const n = this.spots.length, ir = iron();
    const base = new THREE.InstancedMesh(JackGeo.base, ir, n);
    this.spots.forEach(([x, z], i) => base.setMatrixAt(i, this.m4.compose(this.p.set(x, 0.28, z), this.q.identity(), this.s.set(1.1, 1.6, 1.1))));
    this.stems = new THREE.InstancedMesh(JackGeo.stem, stemMat(), n);
    this.heads = new THREE.InstancedMesh(new THREE.CylinderGeometry(0.13, 0.13, 0.16, 16).translate(0, 0.08, 0), ir, n);
    this.bars = new THREE.InstancedMesh(new THREE.CylinderGeometry(0.024, 0.024, 1.3, 8).rotateZ(Math.PI / 2), ir, n);
    for (const im of [base, this.stems, this.heads, this.bars]) { im.castShadow = true; im.receiveShadow = true; im.frustumCulled = false; R.add(im); }
    // overhead: sill beams along x above each row, joists across, floorboards (no shadow: the key comes in under them)
    const top = new Batch();
    const beamM = lam("crawlBeam", () => ({ map: beamHD() }));
    for (const z of CRAWL_ROWS) top.add(boxGeo(V(-17, CRAWL_H - 0.36, z - 0.2), V(17, CRAWL_H, z + 0.2), 1.5), beamM);
    for (let x = -16.6; x < 17; x += 1.3) top.add(boxGeo(V(x - 0.1, CRAWL_H, -8), V(x + 0.1, CRAWL_H + 0.28, 6), 1.5), beamM);
    const tg = new THREE.Group(); top.build(tg, true); this.top.add(tg);
    const fb = new Batch(); fb.add(quadUp(-17, 17, -8, 6, CRAWL_H + 0.3, 3).rotateX(Math.PI).translate(0, 2 * (CRAWL_H + 0.3), -2), lam("crawlBoards2", () => ({ map: boardsHD(), color: "#c8b8a4" })));
    const fg = new THREE.Group(); fb.build(fg, false); this.top.add(fg);
    // the front sill outside line: the building's brick wall above the opening (seen in the wide shots)
    const wb = new Batch(); wb.add(boxGeo(V(-17, CRAWL_H + 0.3, 5.6), V(17, CRAWL_H + 4, 6.2), 3), lam("crawlWall", () => ({ map: sideHD("crawlWall", 34, 4, "#a8553e", false) })));
    const wg = new THREE.Group(); wb.build(wg, false); this.top.add(wg);
    // the inch rule on a post at screw (0, 0) and its pointer on the beam
    const rule = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.3048, 0.03), new THREE.MeshBasicMaterial({ map: inchTex(), color: 0xe6e6e6 }));
    rule.position.set(0.55, CRAWL_H - 0.36 - 0.16, 0.24); R.add(rule);
    const post = new THREE.Mesh(new THREE.BoxGeometry(0.08, CRAWL_H - 0.4, 0.08), M.timber()); post.position.set(0.64, (CRAWL_H - 0.4) / 2, 0.21); R.add(post);
    const ptr = new THREE.Mesh(new THREE.ConeGeometry(0.03, 0.12, 3).rotateZ(Math.PI / 2), M.col("#c0352e")); ptr.position.set(0.44, CRAWL_H - 0.36 - 0.16 - 0.12, 0.25); this.top.add(ptr);
    R.add(this.top);
    // lanterns hanging from the joists: warm HDR glass (blooms), a soft glow sprite
    const glass = new THREE.MeshBasicMaterial({ color: new THREE.Color(3.2, 2.2, 1.1) });
    for (const [x, z] of [[-11, 1.2], [-5, -1.2], [1.5, 1.3], [7.5, -1.2], [13, 1.2], [-8, -3.6], [4, -3.6], [10, -6]]) {
      const lg = new THREE.Group();
      const cage = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.14, 0.3, 8), M.col("#2e3038")); cage.scale.set(1.05, 1, 1.05);
      const gl = new THREE.Mesh(new THREE.CylinderGeometry(0.1, 0.12, 0.26, 8), glass);
      const wire = new THREE.Mesh(new THREE.CylinderGeometry(0.01, 0.01, 0.5, 4), M.col("#2e3038")); wire.position.y = 0.4;
      lg.add(cage, gl, wire); lg.position.set(x, CRAWL_H - 0.75, z); this.top.add(lg);
      const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex(), color: new THREE.Color(0.7, 0.52, 0.32), transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, fog: false }));
      sp.scale.setScalar(0.9); sp.position.set(x, CRAWL_H - 0.75, z); sp.layers.set(NOINK); this.top.add(sp); this.glow.push(sp);
    }
    // the masons' new foundation: brick courses under the back sill (instanced bricks, count grows)
    const brickM = lam("crawlBrick", () => ({ color: "#b05a42" }));
    this.courses = new THREE.InstancedMesh(new THREE.BoxGeometry(0.22, 0.075, 0.1), brickM, 30 * 16);
    this.courses.castShadow = true; this.courses.receiveShadow = true; this.courses.frustumCulled = false; R.add(this.courses);
    void SHOTS;
  }

  pose(id: number, f: number) {
    const lift = crawlLift(f), turn = turnsAt(f) * (Math.PI / 2);
    this.top.position.y = lift;
    const { m4, q, p, s } = this;
    this.spots.forEach(([x, z], i) => {
      const stemLen = CRAWL_H - 0.36 + lift - (BAR_Y + 0.08);
      q.setFromAxisAngle(V(0, 1, 0), turn + (i % 3) * 0.02);
      this.heads.setMatrixAt(i, m4.compose(p.set(x, BAR_Y - 0.08, z), q, s.set(1, 1, 1)));
      this.bars.setMatrixAt(i, m4.compose(p.set(x, BAR_Y, z), q, s.set(1, 1, 1)));
      this.stems.setMatrixAt(i, m4.compose(p.set(x, BAR_Y + 0.08, z), q, s.set(1, stemLen, 1)));
    });
    for (const im of [this.heads, this.bars, this.stems]) im.instanceMatrix.needsUpdate = true;
    // brick courses: 6 m of new foundation under the back sill (x -8.6..-2.6), z -4.8 row line
    const n = coursesAt(id, f);
    let k = 0;
    for (let c = 0; c < n; c++) for (let j = 0; j < 27; j++) {
      const x = -8.6 + j * 0.23 + (c % 2 ? 0.115 : 0);
      if (x > -2.6) continue;
      this.courses.setMatrixAt(k++, m4.compose(p.set(x, 0.04 + c * 0.08, -6.6), q.identity(), s.set(1, 1, 1)));
    }
    this.courses.count = k; this.courses.instanceMatrix.needsUpdate = true;
  }
}
export const CRAWL_GLOW = glowTex;
