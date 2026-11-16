// Low-Poly Skit effects (TMDEV-250): the few things the reel adds to a hit. All are flat unlit shapes, all pure functions
// of the frame (set once with a start frame, then `update(f)`), so a still and a render agree.
import * as THREE from "three";

const clamp01 = (x: number) => Math.max(0, Math.min(1, x));

/** an impact burst: a yellow spiky star that pops in 2 frames, holds, then is gone. Faces the camera. */
export class Burst {
  readonly root = new THREE.Mesh(Burst.geo(), new THREE.MeshBasicMaterial({ color: "#ffd221", side: THREE.DoubleSide }));
  private t0 = -1e9;
  constructor(readonly size = 0.5, readonly hold = 4) { this.root.visible = false; }
  private static geo() {
    const sh = new THREE.Shape();
    const n = 9;
    for (let i = 0; i < n * 2; i++) { const r = i % 2 ? 0.45 : 1; const a = (i / (n * 2)) * Math.PI * 2; (i ? sh.lineTo : sh.moveTo).call(sh, Math.cos(a) * r, Math.sin(a) * r); }
    return new THREE.ShapeGeometry(sh);
  }
  at(frame: number, pos: THREE.Vector3 | [number, number, number]) { this.t0 = frame; this.root.position.set(...(Array.isArray(pos) ? pos : pos.toArray())); return this; }
  update(f: number, camera?: THREE.Camera) {
    const n = f - this.t0;
    this.root.visible = n >= 0 && n < 2 + this.hold;
    if (!this.root.visible) return;
    this.root.scale.setScalar(this.size * (n < 2 ? 0.45 + 0.55 * ((n + 1) / 2) : 1 + 0.04 * (n - 2)));
    if (camera) this.root.quaternion.copy(camera.quaternion);
    this.root.rotation.z += n * 0.15;
  }
}

/** debris chips thrown from a point and falling under gravity, gone after `life` frames */
export class Debris {
  readonly root = new THREE.Group();
  private chips: { m: THREE.Mesh; v: THREE.Vector3; spin: number }[] = [];
  private t0 = -1e9;
  private o = new THREE.Vector3();
  constructor(n = 14, seed = 5, readonly life = 22, color = "#f5f3ee") {
    let s = seed >>> 0;
    const rnd = () => { s = (s * 16807) % 2147483647; return s / 2147483647; };
    const geo = new THREE.BoxGeometry(0.035, 0.035, 0.012), mat = new THREE.MeshLambertMaterial({ color, flatShading: true });
    for (let i = 0; i < n; i++) {
      const m = new THREE.Mesh(geo, mat); m.visible = false; this.root.add(m);
      this.chips.push({ m, v: new THREE.Vector3((rnd() - 0.5) * 0.9, 0.35 + rnd() * 0.7, (rnd() - 0.2) * 0.8), spin: (rnd() - 0.5) * 0.8 });
    }
  }
  at(frame: number, pos: [number, number, number]) { this.t0 = frame; this.o.set(...pos); return this; }
  update(f: number) {
    const t = (f - this.t0) / 30;
    for (const c of this.chips) {
      c.m.visible = t >= 0 && f - this.t0 < this.life;
      if (!c.m.visible) continue;
      c.m.position.set(this.o.x + c.v.x * t, this.o.y + c.v.y * t - 4.9 * t * t, this.o.z + c.v.z * t);
      c.m.rotation.set(t * 9 * c.spin, t * 7 * c.spin, t * 11 * c.spin);
    }
  }
}

/** a comic word that scales up in 2 frames on the biggest hit (red, white outline) and holds */
export class ComicWord {
  readonly root: THREE.Mesh;
  private t0 = -1e9;
  constructor(text: string, readonly width = 1.4, readonly hold = 20, fill = "#e5262b") {
    const cv = document.createElement("canvas"); cv.width = 1024; cv.height = 384;
    const c = cv.getContext("2d")!;
    c.font = "900 230px Montserrat, 'Arial Black', Impact, sans-serif"; c.textAlign = "center"; c.textBaseline = "middle";
    c.lineJoin = "round"; c.lineWidth = 34; c.strokeStyle = "#ffffff"; c.strokeText(text, 512, 192);
    c.fillStyle = fill; c.fillText(text, 512, 192);
    const tex = new THREE.CanvasTexture(cv); tex.colorSpace = THREE.SRGBColorSpace;
    this.root = new THREE.Mesh(new THREE.PlaneGeometry(width, width * 0.375), new THREE.MeshBasicMaterial({ map: tex, transparent: true }));
    this.root.visible = false;
  }
  at(frame: number, pos: [number, number, number]) { this.t0 = frame; this.root.position.set(...pos); return this; }
  update(f: number, camera?: THREE.Camera) {
    const n = f - this.t0;
    this.root.visible = n >= 0 && n < this.hold;
    if (!this.root.visible) return;
    this.root.scale.setScalar(n < 2 ? 0.3 + 0.7 * ((n + 1) / 2) : 1 + 0.015 * (n - 2));
    if (camera) this.root.quaternion.copy(camera.quaternion);
    this.root.rotateZ(-0.12);
  }
}

/** a spotlight cone: additive, no depth write, so it glows over what it crosses */
export const lightCone = (height = 3, radius = 0.7, color = "#fff2c0", opacity = 0.16) => {
  const m = new THREE.Mesh(new THREE.ConeGeometry(radius, height, 14, 1, true), new THREE.MeshBasicMaterial({ color, transparent: true, opacity, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide }));
  m.geometry.translate(0, -height / 2, 0);
  return m;
};

/** 0 to 1 over `dur` frames from f0 (a helper for fading a prop in) */
export const ramp = (f: number, f0: number, dur: number) => clamp01((f - f0) / Math.max(1, dur));
