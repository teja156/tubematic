// Small geometry helpers: boxes with world-scaled UVs (so textures keep a constant
// size on any box), gable prisms, catenary wires, poles, trees, rocks.
import * as THREE from "three";
import { makeRng, range } from "./prng";

// BoxGeometry whose UVs are in metres / texSize, so one texture tiles evenly.
export const worldBox = (w: number, h: number, d: number, texSize = 2) => {
  const g = new THREE.BoxGeometry(w, h, d);
  const uv = g.getAttribute("uv") as THREE.BufferAttribute;
  // face order: +x, -x, +y, -y, +z, -z (4 verts each)
  const spans: [number, number][] = [
    [d, h],
    [d, h],
    [w, d],
    [w, d],
    [w, h],
    [w, h],
  ];
  for (let f = 0; f < 6; f++) {
    for (let v = 0; v < 4; v++) {
      const i = f * 4 + v;
      uv.setXY(i, (uv.getX(i) * spans[f][0]) / texSize, (uv.getY(i) * spans[f][1]) / texSize);
    }
  }
  uv.needsUpdate = true;
  return g;
};

export const mesh = (
  g: THREE.BufferGeometry,
  m: THREE.Material | THREE.Material[],
  pos: [number, number, number],
  opts: { cast?: boolean; receive?: boolean; rot?: [number, number, number] } = {},
) => {
  const o = new THREE.Mesh(g, m);
  o.position.set(...pos);
  if (opts.rot) o.rotation.set(...opts.rot);
  o.castShadow = opts.cast ?? true;
  o.receiveShadow = opts.receive ?? true;
  return o;
};

// Triangular prism for a gable roof end / attic: width w along x, depth d along z.
export const gable = (w: number, h: number, d: number, texSize = 2) => {
  const shape = new THREE.Shape();
  shape.moveTo(-w / 2, 0);
  shape.lineTo(w / 2, 0);
  shape.lineTo(0, h);
  shape.closePath();
  const g = new THREE.ExtrudeGeometry(shape, { depth: d, bevelEnabled: false });
  g.translate(0, 0, -d / 2);
  const uv = g.getAttribute("uv") as THREE.BufferAttribute;
  for (let i = 0; i < uv.count; i++) uv.setXY(i, uv.getX(i) / texSize, uv.getY(i) / texSize);
  return g;
};

// A pitched roof made of two slabs meeting at a ridge along z.
export const pitchedRoof = (
  w: number,
  rise: number,
  d: number,
  mat: THREE.Material,
  overhang = 0.3,
) => {
  const grp = new THREE.Group();
  const half = w / 2 + overhang;
  const slope = Math.atan2(rise, w / 2);
  const len = Math.hypot(half, rise + overhang * Math.tan(slope));
  for (const s of [-1, 1]) {
    const slab = mesh(worldBox(len, 0.12, d + overhang * 2, 1.6), mat, [0, 0, 0]);
    slab.rotation.z = s * slope;
    slab.position.set((-s * len * Math.cos(slope)) / 2, rise - (len * Math.sin(slope)) / 2 + 0.06, 0);
    grp.add(slab);
  }
  return grp;
};

// Sagging wire between two points as a thin tube (parabolic approximation of a catenary).
export const wire = (a: THREE.Vector3, b: THREE.Vector3, sag: number, radius = 0.018, seg = 24) => {
  const pts: THREE.Vector3[] = [];
  for (let i = 0; i <= seg; i++) {
    const t = i / seg;
    const p = a.clone().lerp(b, t);
    p.y -= sag * 4 * t * (1 - t);
    pts.push(p);
  }
  return new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), seg, radius, 5, false);
};

export const tubeThrough = (pts: THREE.Vector3[], radius: number, seg = 32) =>
  new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), seg, radius, 6, false);

// Telegraph pole: trunk, crossarm, glass insulators. Returns the group and the
// world-space insulator tips (where wires attach).
export const telegraphPole = (
  pos: THREE.Vector3,
  height: number,
  woodMat: THREE.Material,
  glassMat: THREE.Material,
  yaw = 0,
) => {
  const g = new THREE.Group();
  g.position.copy(pos);
  g.rotation.y = yaw;
  const trunk = mesh(new THREE.CylinderGeometry(0.11, 0.16, height, 12), woodMat, [0, height / 2, 0]);
  g.add(trunk);
  const arm = mesh(worldBox(0.14, 0.14, 1.9, 1), woodMat, [0, height - 0.45, 0]);
  g.add(arm);
  const tips: THREE.Vector3[] = [];
  for (const z of [-0.8, -0.3, 0.3, 0.8]) {
    const ins = mesh(new THREE.CylinderGeometry(0.05, 0.07, 0.16, 10), glassMat, [0, height - 0.3, z]);
    g.add(ins);
  }
  g.updateMatrixWorld(true);
  for (const z of [-0.8, -0.3, 0.3, 0.8]) {
    tips.push(new THREE.Vector3(0, height - 0.22, z).applyMatrix4(g.matrixWorld));
  }
  return { group: g, tips };
};

export const tree = (
  pos: THREE.Vector3,
  scale: number,
  trunkMat: THREE.Material,
  leafMat: THREE.Material,
  seed: number,
) => {
  const rng = makeRng(seed);
  const g = new THREE.Group();
  g.position.copy(pos);
  const th = 2.2 * scale;
  g.add(mesh(new THREE.CylinderGeometry(0.12 * scale, 0.2 * scale, th, 12), trunkMat, [0, th / 2, 0]));
  for (let i = 0; i < 4; i++) {
    const r = range(rng, 0.9, 1.4) * scale;
    const blob = mesh(new THREE.IcosahedronGeometry(r, 1), leafMat, [
      range(rng, -0.6, 0.6) * scale,
      th + range(rng, 0.2, 1.3) * scale,
      range(rng, -0.6, 0.6) * scale,
    ]);
    blob.scale.y = 0.85;
    g.add(blob);
  }
  return g;
};

export const rock = (pos: THREE.Vector3, scale: number, mat: THREE.Material, seed: number) => {
  const rng = makeRng(seed);
  const geo = new THREE.DodecahedronGeometry(scale, 0);
  const p = geo.getAttribute("position") as THREE.BufferAttribute;
  const k = range(rng, 2, 6);
  // Duplicated (non-indexed) vertices must move together, so the jitter is a
  // function of the position, not of the vertex index.
  for (let i = 0; i < p.count; i++) {
    const x = p.getX(i);
    const z = p.getZ(i);
    const j = 1 + 0.15 * Math.sin(x * k + z * 3.1 + seed);
    p.setXYZ(i, x * j, p.getY(i) * 0.6, z * j);
  }
  geo.computeVertexNormals();
  const m = mesh(geo, mat, [pos.x, pos.y + scale * 0.3, pos.z]);
  m.rotation.y = rng() * 6;
  return m;
};
