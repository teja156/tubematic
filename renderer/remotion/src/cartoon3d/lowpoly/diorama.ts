// Low-Poly Skit diorama builders (TMDEV-250): the pieces a set is made of. A set is a few dozen primitives; these keep it
// to a few lines each. Everything is flat-shaded, unlit text and signs are canvas textures, units are metres.
import * as THREE from "three";

export const flat = (color: string) => new THREE.MeshLambertMaterial({ color, flatShading: true });

/** a box with its base at y (default sitting on the floor) */
export function box(parent: THREE.Object3D, w: number, h: number, d: number, color: string, x = 0, y = 0, z = 0) {
  const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), flat(color));
  m.position.set(x, y + h / 2, z);
  parent.add(m);
  return m;
}
/** a cylinder (6 sides: low poly) with its base at y */
export function cyl(parent: THREE.Object3D, r: number, h: number, color: string, x = 0, y = 0, z = 0, sides = 6) {
  const m = new THREE.Mesh(new THREE.CylinderGeometry(r, r, h, sides), flat(color));
  m.position.set(x, y + h / 2, z);
  parent.add(m);
  return m;
}

export type RoomOpts = { w?: number; d?: number; h?: number; wall?: string; wallSide?: string; floor?: string; trim?: string; rightWall?: boolean };
/** a room with its front wall off: floor slab, back wall, left wall (and the right if asked), a baseboard. Origin at the
 *  floor's centre, the open front toward +z. */
export function room(o: RoomOpts = {}) {
  const w = o.w ?? 3.6, d = o.d ?? 3, h = o.h ?? 2.4, g = new THREE.Group();
  box(g, w, 0.1, d, o.floor ?? "#503020", 0, -0.1, 0);
  box(g, w, h, 0.08, o.wall ?? "#d6ccb3", 0, 0, -d / 2);
  box(g, 0.08, h, d, o.wallSide ?? o.wall ?? "#e9dbc1", -w / 2, 0, 0);
  if (o.rightWall) box(g, 0.08, h, d, o.wallSide ?? o.wall ?? "#e9dbc1", w / 2, 0, 0);
  const trim = o.trim ?? "#8b7a5e";
  box(g, w, 0.09, 0.03, trim, 0, 0, -d / 2 + 0.05);
  box(g, 0.03, 0.09, d, trim, -w / 2 + 0.05, 0, 0);
  return { root: g, w, d, h };
}

/** text on a flat plane (a sign, a label, a clock): a canvas texture, unlit */
export function sign(parent: THREE.Object3D, text: string, w: number, h: number, o: { bg?: string; fg?: string; x?: number; y?: number; z?: number; font?: string; lines?: string[] } = {}) {
  const cv = document.createElement("canvas"); cv.width = 512; cv.height = Math.max(64, Math.round((512 * h) / w));
  const c = cv.getContext("2d")!;
  c.fillStyle = o.bg ?? "#f9e9ad"; c.fillRect(0, 0, cv.width, cv.height);
  c.fillStyle = o.fg ?? "#2a2a2a"; c.textAlign = "center"; c.textBaseline = "middle";
  const lines = o.lines ?? [text], px = Math.min(cv.height / (lines.length + 0.4), 512 / Math.max(4, Math.max(...lines.map((l) => l.length)) * 0.62));
  c.font = o.font ?? `800 ${px}px Montserrat, 'Arial Black', sans-serif`;
  lines.forEach((l, i) => c.fillText(l, 256, (cv.height * (i + 0.5)) / lines.length));
  const tex = new THREE.CanvasTexture(cv); tex.colorSpace = THREE.SRGBColorSpace;
  const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ map: tex }));
  m.position.set(o.x ?? 0, o.y ?? 1, o.z ?? 0);
  parent.add(m);
  return m;
}

/** a low-poly planet: a faceted ball whose triangles are sea or land by a seeded blob pattern */
export function globe(parent: THREE.Object3D, r = 1, o: { sea?: string; land?: string; seed?: number; detail?: number } = {}) {
  const geo = new THREE.IcosahedronGeometry(r, o.detail ?? 2);
  const pos = geo.getAttribute("position"), col: number[] = [];
  const sea = new THREE.Color(o.sea ?? "#2f6fb5"), land = new THREE.Color(o.land ?? "#4faa5b");
  const sd = o.seed ?? 3;
  const n = (x: number, y: number, z: number) => Math.sin(x * 3.1 + sd) * Math.sin(y * 2.7 + sd * 1.7) + Math.sin(z * 3.9 + sd * 0.6) * 0.8 + Math.sin((x + y + z) * 2.3);
  for (let i = 0; i < pos.count; i += 3) {
    const cx = (pos.getX(i) + pos.getX(i + 1) + pos.getX(i + 2)) / (3 * r), cy = (pos.getY(i) + pos.getY(i + 1) + pos.getY(i + 2)) / (3 * r), cz = (pos.getZ(i) + pos.getZ(i + 1) + pos.getZ(i + 2)) / (3 * r);
    const c = n(cx, cy, cz) > 0.5 ? land : sea;
    for (let k = 0; k < 3; k++) col.push(c.r, c.g, c.b);
  }
  geo.setAttribute("color", new THREE.Float32BufferAttribute(col, 3));
  const m = new THREE.Mesh(geo, new THREE.MeshLambertMaterial({ vertexColors: true, flatShading: true }));
  parent.add(m);
  return m;
}

/** stacked layers (soil, rock, magma, core): a cutaway block, thickest first at the top. Origin at the top's centre. */
export function strata(parent: THREE.Object3D, w: number, d: number, layers: { h: number; color: string }[]) {
  const g = new THREE.Group();
  let y = 0;
  for (const l of layers) { y -= l.h; box(g, w, l.h, d, l.color, 0, y, 0); }
  parent.add(g);
  return g;
}

/** a concentric cross-section of a ball, as stacked discs facing +z (outermost first). Origin at the centre. */
export function discs(parent: THREE.Object3D, rings: { r: number; color: string }[], thick = 0.06) {
  const g = new THREE.Group();
  rings.forEach((ring, i) => {
    const m = new THREE.Mesh(new THREE.CylinderGeometry(ring.r, ring.r, thick, 16), flat(ring.color));
    m.rotation.x = Math.PI / 2; m.position.z = i * thick; g.add(m);
  });
  parent.add(g);
  return g;
}
