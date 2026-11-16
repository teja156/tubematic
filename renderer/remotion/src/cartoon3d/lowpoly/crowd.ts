// Low-Poly Skit crowd (TMDEV-250): hundreds of the house figure as instanced meshes. The prototype figure is posed once
// per phase bucket per frame (a handful of poses, not one per person), and every member copies its bucket's part matrices
// under its own place, yaw and scale. A part is one InstancedMesh, so a whole crowd is about two dozen draw calls.
import * as THREE from "three";
import { buildFigure, HOUSE, type Outfit, type Role } from "./figure";
import { applyPose, type Pose } from "./poses";
import { faceGeometry } from "./faces";

export type CrowdMember = { x: number; y?: number; z: number; yaw?: number; scale?: number; outfit: Outfit; /** which phase bucket it dances in */ bucket?: number; smile?: boolean };
export type CrowdCycle = (f: number, bucket: number) => Pose;

const zero = new THREE.Matrix4().makeScale(0, 0, 0);
const INK = new THREE.MeshBasicMaterial({ color: "#1b1d33", side: THREE.DoubleSide });
const roleColor = (o: Outfit, r: Role) => (r === "stubble" ? "#6b4a30" : r === "hair" ? o.hair : r === "skin" ? o.skin : r === "shirt" ? o.shirt : r === "trousers" ? o.trousers : r === "boots" ? o.boots : o.sole);
const has = (o: Outfit, opt: string | undefined) =>
  !opt || (opt === "cap" ? o.hairStyle !== "bald" : opt === "tuft" ? o.hairStyle === "tuft" : opt === "bob" ? o.hairStyle === "bob" : !!o.stubble);

export class Crowd {
  readonly root = new THREE.Group();
  private proto = buildFigure(HOUSE, true);
  private parts: THREE.Mesh[] = [];
  private meshes: THREE.InstancedMesh[] = [];
  private faceMeshes: { mesh: THREE.InstancedMesh; ids: number[] }[] = [];
  private place: THREE.Matrix4[] = [];
  private hidden: boolean[][] = [];
  constructor(readonly members: CrowdMember[], private cycle: CrowdCycle, private buckets = 12) {
    this.proto.root.traverse((o) => { if ((o as THREE.Mesh).isMesh) this.parts.push(o as THREE.Mesh); });
    const n = members.length;
    this.parts.forEach((p, j) => {
      const im = new THREE.InstancedMesh(p.geometry, new THREE.MeshLambertMaterial({ color: "#ffffff", flatShading: true }), n);
      im.frustumCulled = false;
      members.forEach((m, i) => im.setColorAt(i, new THREE.Color(roleColor(m.outfit, p.userData.role as Role))));
      im.instanceColor!.needsUpdate = true;
      this.hidden[j] = members.map((m) => !has(m.outfit, p.userData.optional as string | undefined));
      this.meshes.push(im);
      this.root.add(im);
    });
    for (const [name, pick] of [["blank", (m: CrowdMember) => !m.smile], ["smile", (m: CrowdMember) => !!m.smile]] as const) {
      const ids = members.map((m, i) => (pick(m) ? i : -1)).filter((i) => i >= 0);
      if (!ids.length) continue;
      const mesh = new THREE.InstancedMesh(faceGeometry(name), INK, ids.length);
      mesh.frustumCulled = false;
      this.faceMeshes.push({ mesh, ids });
      this.root.add(mesh);
    }
    const q = new THREE.Quaternion(), pos = new THREE.Vector3(), s = new THREE.Vector3();
    this.place = members.map((m) => {
      q.setFromAxisAngle(new THREE.Vector3(0, 1, 0), m.yaw ?? 0);
      pos.set(m.x, m.y ?? 0, m.z);
      const k = m.scale ?? 1;
      return new THREE.Matrix4().compose(pos, q, s.set(k, k, k));
    });
    this.update(0);
  }
  /** pose the crowd at frame f */
  update(f: number) {
    const bm: THREE.Matrix4[][] = [];
    const head: THREE.Matrix4[] = [];
    for (let b = 0; b < this.buckets; b++) {
      applyPose(this.proto, this.cycle(f, b));
      this.proto.root.updateMatrixWorld(true);
      bm.push(this.parts.map((p) => p.matrixWorld.clone()));
      head.push(this.proto.headMount.matrixWorld.clone());
    }
    const out = new THREE.Matrix4();
    this.parts.forEach((_, j) => {
      const im = this.meshes[j];
      this.members.forEach((m, i) => {
        if (this.hidden[j][i]) im.setMatrixAt(i, zero);
        else im.setMatrixAt(i, out.multiplyMatrices(this.place[i], bm[(m.bucket ?? 0) % this.buckets][j]));
      });
      im.instanceMatrix.needsUpdate = true;
    });
    for (const { mesh, ids } of this.faceMeshes) {
      ids.forEach((id, k) => mesh.setMatrixAt(k, out.multiplyMatrices(this.place[id], head[(this.members[id].bucket ?? 0) % this.buckets])));
      mesh.instanceMatrix.needsUpdate = true;
    }
  }
  /** world position of member i's head after the last update (for a camera target) */
  headOf(i: number, target = new THREE.Vector3()) {
    const m = this.faceMeshes.find((fm) => fm.ids.includes(i));
    if (!m) return target;
    const mat = new THREE.Matrix4(); m.mesh.getMatrixAt(m.ids.indexOf(i), mat);
    return target.setFromMatrixPosition(mat);
  }
  /** a rectangular block of figures: rows back from z0, columns centred on x0, seeded outfits */
  static block(cols: number, rows: number, opts: { x0?: number; z0?: number; dx?: number; dz?: number; rise?: number; seed: number; outfit: (rnd: () => number) => Outfit; smileRate?: number; yaw?: number; buckets?: number }): CrowdMember[] {
    let s = opts.seed >>> 0;
    const rnd = () => { s = (s + 0x6d2b79f5) | 0; let t = Math.imul(s ^ (s >>> 15), 1 | s); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
    const out: CrowdMember[] = [];
    const dx = opts.dx ?? 0.3, dz = opts.dz ?? 0.35;
    for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
      out.push({
        x: (opts.x0 ?? 0) + (c - (cols - 1) / 2) * dx + (r % 2) * dx * 0.5, z: (opts.z0 ?? 0) - r * dz, y: r * (opts.rise ?? 0),
        yaw: (opts.yaw ?? 0) + (rnd() - 0.5) * 0.3, outfit: opts.outfit(rnd), bucket: Math.floor(rnd() * (opts.buckets ?? 12)), smile: rnd() < (opts.smileRate ?? 0.3),
      });
    }
    return out;
  }
}
