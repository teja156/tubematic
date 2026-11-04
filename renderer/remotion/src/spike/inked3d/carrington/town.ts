// The static set: a small inked frontier town street with a telegraph office,
// poles and sagging wires, a few neighbours, trees, rocks and far hills.
// Street runs along x; building fronts face +z; the sun sets toward -x.
import * as THREE from "three";
import { gable, mesh, pitchedRoof, rock, telegraphPole, tree, wire, worldBox } from "../kit/geometry";
import { makeRng, range } from "../kit/prng";
import * as T from "../kit/textures";

const lambert = (map?: THREE.Texture, color = 0xffffff, extra: THREE.MeshLambertMaterialParameters = {}) =>
  new THREE.MeshLambertMaterial({ map: map ?? null, color, ...extra });

export interface Town {
  root: THREE.Group;
  windowGlow: THREE.MeshLambertMaterial[]; // lit windows at night
  officeWireEnd: THREE.Vector3; // where the line enters the office wall
  poleTips: THREE.Vector3[][];
}

export const PORCH_H = 0.35;

export const buildTown = (): Town => {
  const root = new THREE.Group();
  const windowGlow: THREE.MeshLambertMaterial[] = [];

  // --- shared materials ---
  const boardwalk = lambert(T.planks({ seed: 11, planks: 6, hue: 28, sat: 0.62, light: 0.5 }));
  const cobble = lambert(T.cobbles(5));
  const dirtMat = lambert(T.dirt(7, 32, 0.55, 0.55));
  const stone = lambert(T.stoneBlocks(3));
  const poleWood = lambert(T.bark(21, 25, 0.42));
  const glass = lambert(undefined, 0x3fe0c0, { emissive: new THREE.Color(0x0a4a40) });
  const wireMat = lambert(undefined, 0x2a1d44);
  const trunk = lambert(T.bark(31, 20, 0.35));
  const leavesA = lambert(T.foliage(41, 120));
  const leavesB = lambert(T.foliage(42, 95));
  const rockMat = lambert(T.stoneBlocks(9), 0xd8c0ff);
  const roofRed = lambert(T.shingles(13, 4, 0.7, 0.45));
  const roofTeal = lambert(T.shingles(14, 185, 0.55, 0.4));
  const roofPlum = lambert(T.shingles(15, 290, 0.45, 0.42));

  // --- ground: dirt everywhere, cobbles in the street near the office ---
  const groundGeo = new THREE.PlaneGeometry(600, 600);
  groundGeo.rotateX(-Math.PI / 2);
  const uv = groundGeo.getAttribute("uv") as THREE.BufferAttribute;
  for (let i = 0; i < uv.count; i++) uv.setXY(i, uv.getX(i) * 150, uv.getY(i) * 150);
  const ground = mesh(groundGeo, dirtMat, [0, 0, 0], { cast: false });
  root.add(ground);
  const street = mesh(worldBox(70, 0.04, 8.4, 2.6), cobble, [-14, 0.02, 7.9], { cast: false });
  root.add(street);

  // --- boardwalk along the north side ---
  root.add(mesh(worldBox(46, PORCH_H, 2.6, 2.4), boardwalk, [-5, PORCH_H / 2, 1.3]));
  // porch posts and a step
  root.add(mesh(worldBox(46, 0.16, 0.5, 2.4), boardwalk, [-5, 0.08, 2.85]));

  // --- telegraph office (x 0 centre, front at z=0) ---
  const office = new THREE.Group();
  const officeWall = lambert(
    T.planks({ seed: 17, planks: 7, hue: 30, sat: 0.6, light: 0.45, clapboard: true, painted: { hue: 8, sat: 0.72, light: 0.5, wear: 0.4 } }),
  );
  const trim = lambert(T.planks({ seed: 18, planks: 3, hue: 40, sat: 0.4, light: 0.85 }), 0xfff1d6);
  const W = 6.6;
  const H = 3.7;
  const D = 6;
  office.add(mesh(worldBox(W, H, D, 2), officeWall, [0, H / 2 + PORCH_H, -D / 2]));
  office.add(mesh(worldBox(W + 0.3, 0.6, D + 0.3, 1.5), stone, [0, 0.3, -D / 2]));
  // gable end facing the street
  const gb = mesh(gable(W, 2.0, 0.2, 2), officeWall, [0, H + PORCH_H, -0.1]);
  office.add(gb);
  const roof = pitchedRoof(W, 2.0, D, roofRed, 0.35);
  roof.rotation.y = 0;
  roof.position.set(0, H + PORCH_H, -D / 2);
  office.add(roof);
  // corner trims
  for (const x of [-W / 2, W / 2]) office.add(mesh(worldBox(0.18, H, 0.18, 1), trim, [x, H / 2 + PORCH_H, 0.02]));
  // sign
  const signMat = lambert(T.signBoard("TELEGRAPH", "#1d2f8a", "#ffe08a"), 0xffffff);
  office.add(mesh(new THREE.BoxGeometry(4.2, 1.0, 0.12), [trim, trim, trim, trim, signMat, trim], [0, H + PORCH_H + 0.55, 0.12]));
  // open doorway at viewer's right: dark interior recess + swung door leaf
  const interior = lambert(undefined, 0x2a1f5c, { emissive: new THREE.Color(0x120a30) });
  office.add(mesh(new THREE.BoxGeometry(1.1, 2.3, 0.05), interior, [1.75, PORCH_H + 1.15, 0.01], { cast: false }));
  const doorMat = lambert(T.planks({ seed: 19, planks: 4, hue: 22, sat: 0.65, light: 0.42, vertical: true, painted: { hue: 200, sat: 0.6, light: 0.42, wear: 0.5 } }));
  const door = mesh(worldBox(1.05, 2.25, 0.08, 1.2), doorMat, [0, 0, 0]);
  const hinge = new THREE.Group();
  hinge.position.set(2.3, PORCH_H + 1.15, 0.05);
  door.position.set(-0.52, 0, 0);
  hinge.add(door);
  hinge.rotation.y = 1.9;
  office.add(hinge);
  for (const [x, w] of [[1.17, 0.14], [2.33, 0.14]] as const)
    office.add(mesh(worldBox(w, 2.5, 0.14, 1), trim, [x, PORCH_H + 1.25, 0.06]));
  office.add(mesh(worldBox(1.3, 0.16, 0.16, 1), trim, [1.75, PORCH_H + 2.4, 0.06]));
  // window behind the operator
  const winGlass = lambert(undefined, 0x1c2866, { emissive: new THREE.Color(0x04061a) });
  windowGlow.push(winGlass);
  office.add(mesh(new THREE.BoxGeometry(1.6, 1.1, 0.04), winGlass, [-0.6, PORCH_H + 1.85, 0.02], { cast: false }));
  for (const y of [1.28, 2.42]) office.add(mesh(worldBox(1.8, 0.12, 0.12, 1), trim, [-0.6, PORCH_H + y, 0.06]));
  for (const x of [-1.45, -0.6, 0.25]) office.add(mesh(worldBox(0.1, 1.2, 0.1, 1), trim, [x, PORCH_H + 1.85, 0.06]));
  // wall insulator bracket where the line comes in
  office.add(mesh(worldBox(0.9, 0.12, 0.4, 1), trim, [-2.6, PORCH_H + 3.2, 0.2]));
  office.add(mesh(new THREE.CylinderGeometry(0.05, 0.07, 0.16, 10), glass, [-2.6, PORCH_H + 3.34, 0.32]));
  const officeWireEnd = new THREE.Vector3(-2.6, PORCH_H + 3.42, 0.32);
  root.add(office);

  // --- neighbours ---
  const building = (
    x: number,
    w: number,
    h: number,
    d: number,
    wall: THREE.Material,
    roofMat: THREE.Material,
    opts: { falseFront?: number; z?: number; north?: boolean; windows?: number; lit?: number[]; seed: number },
  ) => {
    const g = new THREE.Group();
    const z = opts.z ?? -0.3;
    g.position.set(x, 0, z);
    if (opts.north) g.rotation.y = Math.PI;
    g.add(mesh(worldBox(w, h, d, 2), wall, [0, h / 2 + PORCH_H, -d / 2]));
    g.add(mesh(worldBox(w + 0.2, 0.5, d + 0.2, 1.5), stone, [0, 0.25, -d / 2]));
    const r = pitchedRoof(w, 1.4, d, roofMat, 0.3);
    r.position.set(0, h + PORCH_H, -d / 2);
    g.add(r);
    if (opts.falseFront) {
      g.add(mesh(worldBox(w + 0.2, opts.falseFront, 0.2, 2), wall, [0, h + PORCH_H + opts.falseFront / 2, 0.05]));
      g.add(mesh(worldBox(w + 0.5, 0.18, 0.4, 1), trim, [0, h + PORCH_H + opts.falseFront, 0.1]));
    } else {
      g.add(mesh(gable(w, 1.4, 0.2, 2), wall, [0, h + PORCH_H, -0.1]));
    }
    const n = opts.windows ?? 2;
    const rng = makeRng(opts.seed);
    for (let i = 0; i < n; i++) {
      for (const row of h > 5 ? [1.6, 4.3] : [1.7]) {
        const lit = (opts.lit?.includes(i) ?? false) && row < 3;
        const gm = lambert(undefined, lit ? 0xffb24a : 0x4060c8, { emissive: new THREE.Color(lit ? 0x2a1200 : 0x0c1240) });
        if (lit) windowGlow.push(gm);
        const wx = -w / 2 + ((i + 0.5) * w) / n + range(rng, -0.1, 0.1);
        g.add(mesh(new THREE.BoxGeometry(1.0, 1.25, 0.04), gm, [wx, PORCH_H + row, 0.02], { cast: false }));
        g.add(mesh(worldBox(1.2, 0.12, 0.12, 1), trim, [wx, PORCH_H + row - 0.68, 0.06]));
        g.add(mesh(worldBox(1.2, 0.12, 0.12, 1), trim, [wx, PORCH_H + row + 0.68, 0.06]));
      }
    }
    // South-side buildings (behind the camera most of the time) don't cast:
    // with a low key from the south they would put the whole street in shade
    // and swallow the characters' own shadows. A deliberate stylised cheat.
    if (opts.north) g.traverse((o) => (o.castShadow = false));
    root.add(g);
    return g;
  };

  const wallMat = (seed: number, hue: number, sat: number, light: number) =>
    lambert(T.planks({ seed, planks: 7, hue: 30, sat: 0.6, light: 0.45, clapboard: true, painted: { hue, sat, light, wear: 0.35 } }));

  building(-7.8, 6.2, 4.2, 7, wallMat(51, 48, 0.85, 0.58), roofTeal, { falseFront: 1.6, windows: 2, lit: [1], seed: 1 });
  building(-15.2, 7.2, 6.2, 8, wallMat(52, 190, 0.6, 0.48), roofPlum, { windows: 3, lit: [0, 2], seed: 2 });
  building(-22.5, 6.0, 3.8, 6, wallMat(53, 355, 0.7, 0.42), roofTeal, { falseFront: 1.2, windows: 2, seed: 3 });
  building(7.3, 6.0, 4.0, 6, wallMat(54, 140, 0.55, 0.5), roofRed, { falseFront: 1.4, windows: 2, lit: [0], seed: 4 });
  building(14.0, 6.0, 3.6, 6, wallMat(55, 30, 0.75, 0.55), roofPlum, { windows: 2, seed: 5 });
  // south side of the street, facing north
  building(-9, 7, 4.0, 6, wallMat(56, 265, 0.5, 0.5), roofRed, { north: true, z: 14.5, windows: 2, lit: [0], seed: 6 });
  building(-18, 6, 3.4, 6, wallMat(57, 75, 0.6, 0.55), roofTeal, { north: true, z: 14.5, falseFront: 1.2, windows: 2, seed: 7 });
  building(-27, 7, 4.4, 6, wallMat(58, 12, 0.7, 0.5), roofPlum, { north: true, z: 14.5, windows: 3, lit: [1], seed: 8 });

  // --- props on the boardwalk ---
  const crateMat = lambert(T.planks({ seed: 61, planks: 4, hue: 34, sat: 0.65, light: 0.55 }));
  const barrelMat = lambert(T.planks({ seed: 62, planks: 8, hue: 26, sat: 0.7, light: 0.45, vertical: true }));
  root.add(mesh(worldBox(0.8, 0.8, 0.8, 0.8), crateMat, [-5.6, PORCH_H + 0.4, 1.6]));
  root.add(mesh(worldBox(0.6, 0.6, 0.6, 0.8), crateMat, [-5.4, PORCH_H + 1.1, 1.5], { rot: [0, 0.4, 0] }));
  root.add(mesh(new THREE.CylinderGeometry(0.38, 0.42, 1.0, 14), barrelMat, [-4.6, PORCH_H + 0.5, 1.9]));
  root.add(mesh(new THREE.CylinderGeometry(0.38, 0.42, 1.0, 14), barrelMat, [4.3, PORCH_H + 0.5, 1.8]));
  // hitching rail
  for (const x of [-10.5, -8.5]) root.add(mesh(new THREE.CylinderGeometry(0.07, 0.08, 1.1, 10), poleWood, [x, 0.55, 3.4]));
  root.add(mesh(new THREE.CylinderGeometry(0.06, 0.06, 2.3, 10), poleWood, [-9.5, 1.05, 3.4], { rot: [0, 0, Math.PI / 2] }));

  // --- telegraph poles + wires toward the west ---
  const polesX = [-4.2, -15, -26, -37, -48, -59, -70, -81];
  const tips: THREE.Vector3[][] = [];
  for (const [i, x] of polesX.entries()) {
    const p = telegraphPole(new THREE.Vector3(x, 0, 3.3), 6.6 + (i % 2) * 0.25, poleWood, glass, (i % 3) * 0.04);
    root.add(p.group);
    tips.push(p.tips);
  }
  for (let i = 0; i < tips.length - 1; i++) {
    for (let k = 0; k < 4; k++) {
      root.add(mesh(wire(tips[i][k], tips[i + 1][k], 0.55 + 0.05 * k), wireMat, [0, 0, 0], { receive: false }));
    }
  }
  // drop from the first pole to the office wall, and down to the desk
  for (const k of [1, 2]) {
    root.add(mesh(wire(tips[0][k], officeWireEnd.clone().add(new THREE.Vector3(0, 0, (k - 1.5) * 0.1)), 0.35), wireMat, [0, 0, 0]));
  }

  // --- trees and rocks ---
  const rng = makeRng(77);
  const treeSpots: [number, number, number][] = [
    [-30, -4, 1.3],
    [-34, -9, 1.6],
    [-42, -3, 1.2],
    [-46, 16, 1.5],
    [-36, 18, 1.1],
    [5, -9, 1.5],
    [19, -2, 1.4],
    [-12, -12, 1.8],
    [-55, -6, 1.6],
    [-62, 14, 1.4],
    [-74, -2, 1.7],
  ];
  for (const [i, [x, z, s]] of treeSpots.entries()) root.add(tree(new THREE.Vector3(x, 0, z), s, trunk, i % 2 ? leavesA : leavesB, 100 + i));
  for (let i = 0; i < 16; i++) {
    const x = range(rng, -90, 25);
    const z = rng() < 0.5 ? range(rng, 4.5, 5.5) : range(rng, 12, 13);
    if (Math.abs(x) < 4) continue;
    root.add(rock(new THREE.Vector3(x, 0, z), range(rng, 0.25, 0.6), rockMat, 200 + i));
  }
  for (let i = 0; i < 10; i++) {
    root.add(rock(new THREE.Vector3(range(rng, -95, -40), 0, range(rng, -8, 20)), range(rng, 0.8, 2.2), rockMat, 300 + i));
  }

  // --- far hills / mesas (low detail, fogged) ---
  const hillMat = lambert(T.dirt(91, 15, 0.6, 0.5), 0xffb090);
  const mesaMat = lambert(T.stoneBlocks(92), 0xff8a66);
  const hills: [number, number, number, number][] = [
    [-170, -40, 40, 9],
    [-150, 60, 50, 11],
    [-120, -120, 70, 14],
    [40, -130, 80, 16],
    [-60, -160, 60, 12],
  ];
  for (const [x, z, r, h] of hills) {
    const m = mesh(new THREE.SphereGeometry(r, 20, 10), hillMat, [x, -r + h, z], { cast: false });
    root.add(m);
  }
  for (const [x, z, r, h] of [
    [-210, 10, 22, 26],
    [-190, -70, 16, 20],
    [-230, 70, 26, 22],
  ] as const) {
    root.add(mesh(new THREE.CylinderGeometry(r * 0.8, r, h, 9), mesaMat, [x, h / 2, z], { cast: false }));
  }

  return { root, windowGlow, officeWireEnd, poleTips: tips };
};
