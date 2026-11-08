// Lake Street, 1858-1861, and the city around it down to the lake. One place in four states (story.ts era):
// 0 = mud street with plank walks, 1 = sewer pipes laid on the old street and buried under rising fill (the
// buildings left in pits), 2 = buildings lifted on timber cribbing and jackscrews, 3 = finished: paved, level.
// x runs east (the lake beyond x = 260), the river south at z ~ 150; old grade y = 0.
import * as THREE from "three";
import { Batch, boxGeo, lam, house, inTheWay } from "../../../kit/build";
import { grassHD } from "../../../kit/paint";
import { mudHD, fillHD, pavingHD, Front, boardTex, planTex, gaugeTex, sideHD, roadEdgeHD } from "../../../kit/chpaint";
import { block, blockH, placeM, groupOf, Lifter, frontSpots, plankWalk, plankAcross, wagon, pipe, stairs, signBoard, M, ub } from "../../../kit/blocks";
import { waterMat } from "../../../kit/water";
import { SetPiece, quadUp, V } from "../../../kit/set";
import { SHOTS, RAISE, NZ, SZ, WALK, WALK_Y, HERO, ROW, TREMONT, WAGON, PLANK, SIGN_AT, liftAt, fillAt, fillFrontAt, pipesAt, turnsAt } from "../story";

const BRICKS = ["#c4573c", "#cc6a46", "#b44c38", "#c87a46", "#d48c56", "#b0503a"]; // round 3: warm red, C* 45+
const STUCCO = ["#e2cfa8", "#d8b88a", "#e6d6b6"];
const FRAMES = ["#2f5a46", "#6a2f2f", "#3a4a6a", "#5a4a2a", "#2a2a2a", "#5f3a52"];
const SHOPS: [string, Front["goods"]][] = [
  ["DRY GOODS", "cloth"], ["HATS & CAPS", "hats"], ["DRUGS", "jars"], ["HARDWARE", "tools"], ["BOOKS", "books"], ["GROCER", "jars"],
  ["BOOTS & SHOES", "hats"], ["TEA & COFFEE", "jars"], ["SADDLERY", "tools"], ["CLOTHIER", "cloth"], ["JEWELLER", "jars"], ["STATIONER", "books"],
];
type Bld = { key: string; x0: number; w: number; south: boolean; front: Front; who: "hero" | "row" | "tremont" | "other" };
/** the two street rows: west to east, deterministic */
const ROWS = (): Bld[] => {
  const out: Bld[] = [];
  let k = 0;
  const mk = (x0: number, w: number, south: boolean, floors: number, who: Bld["who"] = "other", name?: string, goods?: Front["goods"]): Bld => {
    const i = k++, [nm, gd] = SHOPS[i % SHOPS.length], stucco = i % 5 === 3;
    return { key: `b${i}`, x0, w, south, who, front: {
      wall: stucco ? STUCCO[i % 3] : BRICKS[i % BRICKS.length], brick: !stucco, frame: FRAMES[i % FRAMES.length], board: i % 2 ? "#e9dcb8" : "#2a3a2e",
      ink: i % 2 ? "#5a2a20" : "#f0dca0", name: name ?? nm, goods: goods ?? gd, floors, groundH: 3.9, floorH: 3.2 } };
  };
  // north row: west others, the hero, a narrow one, the Lake Street row of five, east others
  for (let x = -61; x < HERO.x0 - 0.1;) { const w = Math.min(HERO.x0 - x, [8, 9, 7.5, 10][k % 4]); out.push(mk(x, w, false, 3 + (k % 2))); x += w; }
  out.push(mk(HERO.x0, HERO.x1 - HERO.x0, false, HERO.floors, "hero", "J. HOLLIS DRY GOODS", "cloth"));
  out.push(mk(HERO.x1, ROW.x0 - HERO.x1, false, 3));
  const rw = (ROW.x1 - ROW.x0) / ROW.n;
  const rowNames: [string, Front["goods"]][] = [["HATS & CAPS", "hats"], ["DRUGS", "jars"], ["DRY GOODS", "cloth"], ["HARDWARE", "tools"], ["BOOKS", "books"]];
  for (let i = 0; i < ROW.n; i++) out.push(mk(ROW.x0 + i * rw, rw, false, 4, "row", rowNames[i][0], rowNames[i][1]));
  out.push(mk(ROW.x1, 61 - ROW.x1, false, 3));
  // south row: others, then the Tremont House to the corner
  for (let x = -61; x < TREMONT.x0 - 0.1;) { const w = Math.min(TREMONT.x0 - x, [9, 8, 10, 7.5][k % 4]); out.push(mk(x, w, true, 3 + ((k + 1) % 2))); x += w; }
  return out;
};
const TREMONT_FRONT: Front = { wall: "#e2c896", brick: false, frame: "#3a2a2a", board: "#33406e", ink: "#f3e2b0", name: "TREMONT HOUSE", goods: "none",
  floors: 6, groundH: 4.6, floorH: 3.3, hotel: true };

export class Street implements SetPiece {
  root = new THREE.Group();
  private groups: Record<Bld["who"], THREE.Group[]> = { hero: [], row: [], tremont: [], other: [] };
  private lifters: { who: "hero" | "row" | "tremont"; l: Lifter }[] = [];
  private only0 = new THREE.Group(); private only1 = new THREE.Group(); private from3 = new THREE.Group(); private pits = new THREE.Group();
  private roadTop: THREE.Mesh; private roadSideN: THREE.Mesh; private roadSideS: THREE.Mesh;
  private walk3: THREE.Group = new THREE.Group();
  private roadEnd: THREE.Mesh;
  private pipes: THREE.Group[] = [];
  private gauge: THREE.Group; private rowStairs = new THREE.Group(); private tremontStairs = new THREE.Group();
  private tripod = new THREE.Group(); private hang: THREE.Group; private mound: THREE.Mesh;
  private mats: { mud: THREE.Material; fill: THREE.Material; pave: THREE.Material };

  constructor() {
    const R = this.root;
    for (const g of [this.only0, this.only1, this.from3, this.pits, this.walk3, this.rowStairs, this.tremontStairs, this.tripod]) R.add(g);
    this.mats = {
      mud: lam("mudHD", () => ({ map: mudHD() })),
      fill: lam("fillHD", () => ({ map: fillHD() })),
      pave: lam("pavingHD", () => ({ map: pavingHD() })),
    };
    // ---- ground: the street's mud, the city's dirt, prairie to the west, the lake to the east ----
    const b = new Batch();
    b.add(quadUp(-400, 260, -400, 400, -0.02, 8), this.mats.mud);
    b.add(quadUp(-1100, -400, -1100, 1100, -0.05, 12), lam("grassHD", () => ({ map: grassHD() })));
    b.add(quadUp(-400, 260, -1100, -400, -0.05, 12), lam("grassHD", () => ({ map: grassHD() })));
    b.add(quadUp(-400, 260, 400, 1100, -0.05, 12), lam("grassHD", () => ({ map: grassHD() })));
    b.add(quadUp(260, 275, -1100, 1100, -0.06, 4), lam("sand", () => ({ color: "#cdb48a" }))); // starts where the mud ends: no overlap
    b.build(R, false);
    const lake = new THREE.Mesh(quadUp(272, 2600, -2600, 2600, -0.35, 1), waterMat("#5f7f9a", 0.45, 0.0));
    lake.receiveShadow = true; R.add(lake);
    const river = new THREE.Mesh(quadUp(-1100, 273, 140, 170, -0.4, 1), waterMat("#6a6050", 0.3, 0.2));
    river.receiveShadow = true; R.add(river);

    // ---- the two street rows ----
    const rows = ROWS();
    for (const bd of rows) {
      const bb = new Batch(), zf = bd.south ? SZ : NZ;
      block(bb, { key: bd.key, w: bd.w, d: 20, front: bd.front, awning: bd.who === "other" && (bd.key.endsWith("3") || bd.key.endsWith("7")) ? "#b8553a" : bd.key.endsWith("5") ? "#3f6f5a" : null, chimneys: 2 });
      const g = new THREE.Group(); bb.build(g); g.matrixAutoUpdate = true;
      const pm = placeM(bd.x0, bd.w, zf, bd.south);
      const inner = new THREE.Group(); inner.applyMatrix4(pm); inner.add(...g.children);
      const outer = new THREE.Group(); outer.add(inner); R.add(outer);
      this.groups[bd.who].push(outer);
    }
    // the Tremont House: six storeys, grand front, a flag on the roof
    {
      const bb = new Batch(), w = TREMONT.x1 - TREMONT.x0;
      const h = block(bb, { key: "tremont", w, d: 34, front: TREMONT_FRONT, cornice: "brackets", chimneys: 3 });
      const inner = new THREE.Group(); bb.build(inner); inner.applyMatrix4(placeM(TREMONT.x0, w, SZ, true));
      const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.08, 6, 8).translate(0, 3, 0), M.wood("#6e4b33"));
      pole.position.set(w / 2, h, -6); inner.add(pole);
      const flag = new THREE.Mesh(new THREE.PlaneGeometry(2.4, 1.4), lam("usFlag", () => ({ map: usFlag(), side: THREE.DoubleSide })));
      flag.position.set(w / 2 + 1.25, h + 5.2, -6); inner.add(flag);
      const outer = new THREE.Group(); outer.add(inner); R.add(outer);
      this.groups.tremont.push(outer);
    }
    // ---- lifting rigs under the hero, the row and the Tremont (front wall lines) ----
    this.lifters.push({ who: "hero", l: new Lifter(frontSpots(HERO.x0, HERO.x1, NZ, false, 1.0)) });
    this.lifters.push({ who: "row", l: new Lifter(frontSpots(ROW.x0, ROW.x1, NZ, false, 1.15)) });
    this.lifters.push({ who: "tremont", l: new Lifter(frontSpots(TREMONT.x0, TREMONT.x1, SZ, true, 1.2)) });
    // second line one metre further in (reads as rows of screws going back under the building)
    this.lifters.push({ who: "row", l: new Lifter(frontSpots(ROW.x0, ROW.x1, NZ - 1.4, false, 1.15)) });
    this.lifters.push({ who: "hero", l: new Lifter(frontSpots(HERO.x0, HERO.x1, NZ - 1.4, false, 1.0)) });
    for (const { l } of this.lifters) R.add(l.group);

    // ---- plank walks at the old level (all eras: they are the pit floors later) ----
    const pw = new Batch();
    // the walk is taken up in front of the hero (its lift shows) and the Tremont (it sits in a pit)
    plankWalk(pw, -61, HERO.x0 - 0.3, NZ, NZ + WALK, WALK_Y);
    plankWalk(pw, HERO.x1 + 0.3, 61, NZ, NZ + WALK, WALK_Y);
    plankWalk(pw, -61, TREMONT.x0 - 0.3, SZ - WALK, SZ, WALK_Y);
    pw.build(this.pits);
    const pw2 = new Batch(); plankWalk(pw2, TREMONT.x0, 61, SZ - WALK, SZ, WALK_Y); pw2.build(this.only0);
    // era 3 sidewalks: stone flags at the new grade over the pits
    const w3 = new Batch(), flagM = lam("flagstone", () => ({ map: sideHD("flagstone", 8, 8, "#b8ab98", false) }));
    w3.add(boxGeo(V(-61, 0, NZ), V(61, RAISE, NZ + WALK + 0.5), 2), flagM);
    w3.add(boxGeo(V(-61, 0, SZ - WALK - 0.5), V(61, RAISE, SZ), 2), flagM);
    for (let x = -58; x < 61; x += 9) for (const z of [NZ + WALK + 0.2, SZ - WALK - 0.2]) { // gas lamp posts
      ub(w3, iron2(), new THREE.Matrix4(), x - 0.06, x + 0.06, RAISE, RAISE + 3.2, z - 0.06, z + 0.06);
      ub(w3, lam("lampGlass", () => ({ color: "#f3e6c0" })), new THREE.Matrix4(), x - 0.2, x + 0.2, RAISE + 3.2, RAISE + 3.65, z - 0.2, z + 0.2);
    }
    w3.build(this.walk3);
    // ---- the road: one top quad at the fill height, retaining faces along both curbs ----
    this.roadTop = new THREE.Mesh(quadUp(-140, 140, NZ + WALK + 0.5, SZ - WALK - 0.5, 0, 8), this.mats.fill);
    this.roadTop.receiveShadow = true; R.add(this.roadTop);
    const sideM = lam("roadEdge", () => ({ map: roadEdgeHD() }));
    const sideGeo = (z: number, dir: number) => {
      const g = new THREE.PlaneGeometry(280, 1, 1, 1); g.translate(0, 0.5, 0); if (dir < 0) g.rotateY(Math.PI); g.translate(0, 0, z);
      const uv = g.attributes.uv as THREE.BufferAttribute; for (let i = 0; i < uv.count; i++) uv.setX(i, uv.getX(i) * 70);
      g.translate(0, -0.0, 0);
      return g;
    };
    this.roadSideN = new THREE.Mesh(sideGeo(NZ + WALK + 0.5, -1), sideM); this.roadSideS = new THREE.Mesh(sideGeo(SZ - WALK - 0.5, 1), sideM);
    for (const s of [this.roadSideN, this.roadSideS]) { s.receiveShadow = true; s.castShadow = true; R.add(s); }
    // the fill's end face where it stops (shot 15): layers of new fill on the old mud road
    this.roadEnd = new THREE.Mesh(new THREE.PlaneGeometry(SZ - NZ - 2 * WALK - 1, 1).translate(0, 0.5, 0).rotateY(Math.PI / 2), sideM);
    this.roadEnd.position.z = 0; this.roadEnd.castShadow = true; this.roadEnd.receiveShadow = true; R.add(this.roadEnd);

    // ---- era 0: mud street dressing ----
    const e0 = new Batch();
    wagon(e0, WAGON[0], -0.42, WAGON[2], 0.15);
    plankAcross(e0, V(PLANK.x, WALK_Y - 0.06, PLANK.z0 + 0.2), V(PLANK.x + 0.1, 0.05, PLANK.z1));
    plankAcross(e0, V(-24, WALK_Y - 0.06, -8.8), V(-23.6, 0.04, -6.0), 0.35);
    e0.build(this.only0);
    for (const [x, z, w, d] of [[-14.5, -1.6, 4.2, 2.6], [-11, 3.5, 2.6, 1.6], [6, 4.2, 3.2, 2.0], [-26, 2.0, 3.0, 1.8], [18, -2.8, 2.6, 1.6]] as const) {
      const pd = new THREE.Mesh(new THREE.CircleGeometry(1, 28).rotateX(-Math.PI / 2).scale(w / 2, 1, d / 2), waterMat("#7a6a58", 0.25, 0.0));
      pd.position.set(x, 0.02, z); pd.receiveShadow = true; this.only0.add(pd);
    }
    // the gutter along the north walk: brown standing water
    const gut = new THREE.Mesh(quadUp(-61, 61, NZ + WALK, NZ + WALK + 0.9, 0.015, 4), waterMat("#5a4a2a", 0.6, 0.05));
    gut.receiveShadow = true; this.only0.add(gut);
    signBoard(this.only0, boardTex("nobottom", 512, 300, "#d8c49a", [["NO BOTTOM", 1.2, "#3a2418"], ["HERE", 1, "#a02a20"]], { rough: true }), SIGN_AT[0], 1.25, SIGN_AT[2], 1.3, 0.76, -0.35, 1, 1.4, 0.12);
    // the Board of Health notice on a wall (seg 2): pasted bill
    signBoard(this.only0, boardTex("cholera", 600, 800, "#efe6cc",
      [["NOTICE", 0.8, "#2a2a2a"], ["CHOLERA", 1.4, "#a02a20"], ["BOARD OF HEALTH", 0.5, "#2a2a2a"], ["BOIL ALL WATER", 0.5, "#2a2a2a"]], { border: "#2a2a2a" }),
      -32.4, WALK_Y + 1.75, NZ + 2.55, 0.9, 1.2, 0.3, 1, 1.9);
    // the officials' table with the engineer's section drawing (seg 2 "a strange choice")
    const tb = new Batch(), tm = M.wood("#7a4f30");
    ub(tb, tm, new THREE.Matrix4(), 16.6, 18.6, 0.98 + WALK_Y, 1.04 + WALK_Y, 9.9, 11.0);
    for (const [x, z] of [[16.7, 10.0], [18.5, 10.0], [16.7, 10.9], [18.5, 10.9]]) ub(tb, tm, new THREE.Matrix4(), x - 0.04, x + 0.04, WALK_Y, WALK_Y + 0.98, z - 0.04, z + 0.04);
    tb.build(this.only0);
    const plan = new THREE.Mesh(new THREE.PlaneGeometry(1.5, 1.07), new THREE.MeshBasicMaterial({ map: planTex(), color: 0xe8e8e8 }));
    plan.position.set(17.6, 1.06 + WALK_Y + 0.12, 10.45); plan.rotation.set(-1.3, Math.PI, 0, "YXZ"); this.only0.add(plan);

    // ---- era 1: sewer pipes along the middle of the street, a lifting tripod, dirt heaps ----
    for (let i = 0; i < 12; i++) {
      const g = new THREE.Group(), pb = new Batch();
      pipe(pb, -24 + i * 4.05, 0.85, 0, 4.0); pb.build(g); this.pipes.push(g); R.add(g);
    }
    const tp = new Batch(), apex = V(14.5, 4.6, 0);
    for (const [x, z] of [[12.8, -1.6], [16.2, -1.6], [14.5, 2.2]]) {
      const a = V(x, 0, z), d = apex.clone().sub(a);
      tp.add(new THREE.CylinderGeometry(0.07, 0.09, d.length(), 8), M.timber(), new THREE.Matrix4().compose(a.clone().add(apex).multiplyScalar(0.5), new THREE.Quaternion().setFromUnitVectors(V(0, 1, 0), d.normalize()), V(1, 1, 1)));
    }
    tp.build(this.tripod);
    const hb = new Batch(); pipe(hb, 0, 0, 0, 4.0); this.hang = groupOf(hb); this.tripod.add(this.hang);
    const rope = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, 1, 6).translate(0, 0.5, 0), M.col("#c8b080")); rope.name = "rope"; this.tripod.add(rope);
    // the burial mound heaped over the pipes (shot 13): a fill half-cylinder along the pipe line, growing
    this.mound = new THREE.Mesh(new THREE.SphereGeometry(1, 40, 12, 0, Math.PI * 2, 0, Math.PI / 2), lam("moundFill", () => ({ map: fillHD(), color: "#9a7a62" })));
    this.mound.rotation.set(0, 0, 0); this.mound.castShadow = true; this.mound.receiveShadow = true; R.add(this.mound);
    const heaps = new Batch();
    for (const [x, z, r] of [[-20, 6.5, 1.6], [-8, -6.5, 1.3], [8, 6.6, 1.8], [24, -6.4, 1.4], [-30, -6.2, 1.5]] as const)
      heaps.add(new THREE.SphereGeometry(r, 18, 10, 0, Math.PI * 2, 0, Math.PI / 2).scale(1.4, 0.7, 1), this.mats.fill, new THREE.Matrix4().makeTranslation(x, 0, z));
    heaps.build(this.only1);

    // ---- era 2: the Lake Street gauge, the tally board, the row's stairs and OPEN sign, the Tremont's steps ----
    this.gauge = new THREE.Group();
    const GH = 6 * 0.3048; // six feet
    const gp = new THREE.Mesh(new THREE.BoxGeometry(0.22, GH, 0.08), new THREE.MeshBasicMaterial({ map: gaugeTex(), color: 0xe6e6e6 }));
    gp.position.set(0, GH / 2, 0); this.gauge.add(gp);
    const gpost = new THREE.Mesh(new THREE.BoxGeometry(0.12, GH + 0.4, 0.12), M.timber()); gpost.position.set(0.18, (GH + 0.4) / 2, -0.05); this.gauge.add(gpost);
    this.gauge.position.set(16.9 - 1.05, WALK_Y, NZ + 0.35); R.add(this.gauge);
    // the pointer fixed to the building's sill (moves with the row): a red arrow at the gauge
    const ptr = new THREE.Mesh(new THREE.ConeGeometry(0.09, 0.3, 3).rotateZ(Math.PI / 2), M.col("#c0352e"));
    ptr.position.set(16.9 - 0.75, WALK_Y, NZ + 0.32); ptr.name = "ptr"; this.groups.row[0]?.add(ptr);
    const sb = new Batch(), rw = (ROW.x1 - ROW.x0) / ROW.n;
    for (const i of [2, 3]) stairs(sb, ROW.x0 + (i + 0.5) * rw, WALK_Y, NZ + 0.2, 1.42 + 0.05, 1.3, 1);
    sb.build(this.rowStairs);
    const open = boardTex("open", 400, 160, "#2a3a2e", [["OPEN", 1, "#f0dca0"]], { border: "#d7b25a" });
    for (const i of [2, 3]) signBoard(this.groups.row[i] ?? R, open, ROW.x0 + (i + 0.5) * rw + 0.95, 1.45, NZ + 0.12, 0.9, 0.36, 0, 0);
    const ts = new Batch(); stairs(ts, (TREMONT.x0 + TREMONT.x1) / 2, 1.15, SZ - WALK - 0.4, RAISE, 1.8, 1); ts.build(this.tremontStairs);
    signBoard(R, boardTex("lakest", 600, 160, "#efe6cc", [["LAKE ST.", 1, "#2a2a2a"]], { border: "#2a2a2a" }), 62.6, 3.2, NZ + WALK + 0.3, 1.5, 0.4, -Math.PI / 2, 1, 3.2);

    // ---- the city around: blocks of plainer buildings, houses toward the prairie, spires, the lake shore ----
    this.city();
  }

  /** the rest of 1850s Chicago for the aerials: low 2-4 storey blocks on a grid, frame houses further out */
  private city() {
    const b = new Batch();
    const facs = [0, 1, 2, 3, 4, 5].map((i) => lam("cityFac" + i, () => ({ map: sideHD("city" + i, 24, 14, BRICKS[i], true) })));
    const roof = M.roof();
    let n = 0;
    for (let bx = -380; bx < 250; bx += 82) for (let bz = -330; bz < 330; bz += 76) {
      if (bz > -40 && bz < 40 && bx > -150 && bx < 150) continue; // Lake Street's own blocks
      if (bz > 100 && bz < 190) continue; // the river
      for (let i = 0; i < 6; i++) {
        n++;
        const x0 = bx + 4 + (i % 3) * 20, z0 = bz + 4 + Math.floor(i / 3) * 30, w = 16 + ((n * 7) % 5), d = 22, h = 7 + ((n * 13) % 4) * 3;
        const far = Math.hypot(x0, z0);
        if (bx < -250 && (n % 3)) { if (!inTheWay(x0, x0 + 10, 0, 9, z0, z0 + 10)) house(b, x0 + 5, z0 + 6, (n % 4) * (Math.PI / 2), 9, 7, 5.6, n % 8, 0); continue; }
        if (inTheWay(x0, x0 + w, 0, h, z0, z0 + d)) continue;
        const fm = facs[n % 6];
        b.add(boxGeo(V(x0, 0, z0), V(x0 + w, h, z0 + d), far > 200 ? 24 : 12, false, false), fm); // no top face: the roof quad is the only surface up there
        b.add(quadUp(x0, x0 + w, z0, z0 + d, h, 8), roof);
        if (n % 17 === 0) { // a church spire
          b.add(boxGeo(V(x0 + w / 2 - 2, 0, z0 + 2), V(x0 + w / 2 + 2, h + 10, z0 + 6), 4), facs[(n + 2) % 6]);
          b.add(new THREE.ConeGeometry(2.6, 12, 4).rotateY(Math.PI / 4), lam("spire", () => ({ color: "#5a5f6a" })), new THREE.Matrix4().makeTranslation(x0 + w / 2, h + 16, z0 + 4));
        }
      }
    }
    // piers into the lake and a few masts
    for (const z of [-180, -60, 60, 220]) b.add(boxGeo(V(260, -0.2, z - 3), V(330, 0.6, z + 3), 4), M.plank());
    b.build(this.root);
  }

  pose(id: number, f: number) {
    const s = SHOTS[id - 1], era = s.era;
    for (const who of ["hero", "row", "tremont", "other"] as const) {
      const lift = liftAt(who, id, f);
      for (const g of this.groups[who]) g.position.y = lift;
    }
    const turn = turnsAt(f) * (Math.PI / 2) + f * 0.0; // street rigs: bars static between turns
    for (const { who, l } of this.lifters) l.pose(era >= 3 ? 0 : liftAt(who, id, f), turn);
    const fill = fillAt(id, f);
    this.roadTop.position.y = Math.max(0, fill);
    this.roadTop.visible = fill > 0.01;
    this.roadTop.material = era >= 3 ? this.mats.pave : this.mats.fill;
    const xf = fillFrontAt(id, f), sx = (xf + 140) / 280;
    this.roadTop.scale.x = sx; this.roadTop.position.x = -140 * (1 - sx);
    for (const sd of [this.roadSideN, this.roadSideS]) { sd.visible = fill > 0.01; sd.scale.y = Math.max(0.01, fill); sd.scale.x = sx; sd.position.x = -140 * (1 - sx); }
    this.roadEnd.visible = xf < 139 && fill > 0.01; this.roadEnd.position.x = xf; this.roadEnd.scale.y = Math.max(0.01, fill);
    this.only0.visible = era === 0;
    this.only1.visible = era === 1;
    this.walk3.visible = era >= 3;
    this.pits.visible = era < 3;
    const np = era >= 1 && era < 3 ? pipesAt(id, f) : 0;
    this.pipes.forEach((g, i) => { g.visible = i < Math.floor(np) && id <= 13; });
    // the tripod lowers the next pipe into its place during shot 12
    this.tripod.visible = id === 12 || id === 13;
    if (this.tripod.visible) {
      const k = np % 1, y = 0.85 + 3.0 * (1 - k);
      this.hang.position.set(14.5, y, 0);
      const rope = this.tripod.getObjectByName("rope")!;
      rope.position.set(14.5, y + 0.85, 0); rope.scale.y = Math.max(0.05, 4.6 - (y + 0.85));
    }
    // the mound grows over the pipes through shot 13: from a scatter to half buried
    this.mound.visible = id === 13;
    if (this.mound.visible) { const k = lin2(f, 1022, 1067); this.mound.scale.set(22, 1.1 + 0.6 * k, 1.6 + 0.3 * k); this.mound.position.set(-2, 0, 0); }
    this.gauge.visible = id === 28;
    this.rowStairs.visible = id === 29 || id === 30;
    this.tremontStairs.visible = id === 34;
  }
}
let IR2: THREE.Material | null = null;
const iron2 = () => (IR2 ??= lam("lampIron", () => ({ color: "#2e3038" })));
const usFlag = () => {
  const cv = document.createElement("canvas"); cv.width = 380; cv.height = 200;
  const g = cv.getContext("2d")!;
  for (let i = 0; i < 13; i++) { g.fillStyle = i % 2 ? "#f2ece0" : "#b8332e"; g.fillRect(0, (i * 200) / 13, 380, 200 / 13 + 1); }
  g.fillStyle = "#2a3a6a"; g.fillRect(0, 0, 160, 108);
  g.fillStyle = "#f2ece0"; for (let y = 12; y < 104; y += 18) for (let x = 12; x < 156; x += 22) { g.beginPath(); g.arc(x + (y % 36 ? 11 : 0), y, 3.5, 0, 7); g.fill(); }
  const t = new THREE.CanvasTexture(cv); t.colorSpace = THREE.SRGBColorSpace; return t;
};
export const STREET_H = blockH;

const lin2 = (f: number, a: number, b: number) => Math.max(0, Math.min(1, (f - a) / (b - a)));
