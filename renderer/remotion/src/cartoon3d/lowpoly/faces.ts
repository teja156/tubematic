// Low-Poly Skit faces (TMDEV-250): flat dark shapes on the front of the head, swapped on a frame, never animated. A
// mouth never follows the speech. Each face is a Group of thin shapes mounted on Figure.headMount.
import * as THREE from "three";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import { FACE_Z } from "./figure";

export const FACE_NAMES = ["neutral", "smile", "smug", "shock", "shout", "worry", "grin", "blank"] as const;
export type FaceName = (typeof FACE_NAMES)[number];

const INK = new THREE.MeshBasicMaterial({ color: "#1b1d33", side: THREE.DoubleSide });
const WHITE = new THREE.MeshBasicMaterial({ color: "#ffffff", side: THREE.DoubleSide });
const Z = FACE_Z + 0.001;

const disc = (r: number, x: number, y: number, mat = INK, sx = 1) => {
  const m = new THREE.Mesh(new THREE.CircleGeometry(r, 10), mat);
  m.position.set(x, y, Z); m.scale.x = sx;
  return m;
};
const bar = (w: number, h: number, x: number, y: number, rot = 0) => {
  const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), INK);
  m.position.set(x, y, Z); m.rotation.z = rot;
  return m;
};
/** a smile (up) or frown (down) arc as a thin torus section */
const arc = (r: number, y: number, up: boolean, span = Math.PI * 0.8) => {
  const m = new THREE.Mesh(new THREE.TorusGeometry(r, 0.0065, 4, 10, span), INK);
  m.rotation.z = up ? Math.PI + (Math.PI - span) / 2 : (Math.PI - span) / 2;
  m.position.set(0, y + (up ? r * 0.55 : -r * 0.55), Z);
  return m;
};

const BUILD: Record<FaceName, () => THREE.Object3D[]> = {
  neutral: () => [disc(0.0155, -0.042, 0.01), disc(0.0155, 0.042, 0.01), bar(0.05, 0.008, 0, -0.05)],
  smile: () => [disc(0.0155, -0.042, 0.01), disc(0.0155, 0.042, 0.01), arc(0.04, -0.045, true)],
  smug: () => [bar(0.034, 0.011, -0.042, 0.008), bar(0.034, 0.011, 0.042, 0.008), bar(0.03, 0.008, -0.04, 0.035, -0.18), bar(0.03, 0.008, 0.04, 0.035, 0.18), bar(0.04, 0.008, 0.012, -0.05, 0.12)],
  shock: () => [disc(0.02, -0.042, 0.016), disc(0.02, 0.042, 0.016), disc(0.011, -0.042, 0.016, WHITE), disc(0.011, 0.042, 0.016, WHITE), disc(0.021, 0, -0.052, INK, 0.85)],
  shout: () => [bar(0.034, 0.009, -0.042, 0.03, -0.35), bar(0.034, 0.009, 0.042, 0.03, 0.35), disc(0.014, -0.042, 0.004), disc(0.014, 0.042, 0.004), disc(0.03, 0, -0.054, INK, 1.1)],
  worry: () => [disc(0.0155, -0.042, 0.008), disc(0.0155, 0.042, 0.008), bar(0.03, 0.008, -0.042, 0.036, 0.3), bar(0.03, 0.008, 0.042, 0.036, -0.3), arc(0.026, -0.052, false, Math.PI * 0.7)],
  grin: () => [disc(0.0155, -0.042, 0.015), disc(0.0155, 0.042, 0.015), arc(0.05, -0.035, true, Math.PI * 0.9)],
  blank: () => [disc(0.01, -0.04, 0.008), disc(0.01, 0.04, 0.008)],
};

const cache = new Map<FaceName, THREE.Group>();
/** the shared face group for a name: mount it with `setFace` */
export const faceGroup = (name: FaceName): THREE.Group => {
  let g = cache.get(name);
  if (!g) { g = new THREE.Group(); for (const o of BUILD[name]()) g.add(o); cache.set(name, g); }
  return g;
};

/** a figure shows one face at a time: swap on the frame, no tween */
export const setFace = (headMount: THREE.Group, name: FaceName) => {
  const prev = headMount.getObjectByName("face");
  if (prev) headMount.remove(prev);
  const g = faceGroup(name).clone();
  g.name = "face";
  headMount.add(g);
};

/** a face as one merged geometry (for a crowd, which draws one face mesh for every figure that shows it) */
export const faceGeometry = (name: FaceName): THREE.BufferGeometry => {
  const g = faceGroup(name);
  g.updateMatrixWorld(true);
  const parts: THREE.BufferGeometry[] = [];
  g.traverse((o) => {
    if (!(o as THREE.Mesh).isMesh) return;
    const m = o as THREE.Mesh;
    const geo = m.geometry.clone().applyMatrix4(m.matrixWorld);
    parts.push(geo.index ? geo.toNonIndexed() : geo);
  });
  return mergeGeometries(parts.map((p) => { p.deleteAttribute("uv"); return p; }), false)!;
};
