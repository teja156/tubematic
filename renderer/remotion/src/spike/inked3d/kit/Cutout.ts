// Flat 2D character on a camera-facing plane, lit by the scene and casting a
// shadow of its own silhouette. States (pose + expression + blink) are canvas
// drawings uploaded once and swapped per frame.
import * as THREE from "three";
import { cutoutNormalMaterial } from "./InkPipeline";

export type DrawFn = (ctx: CanvasRenderingContext2D, w: number, h: number) => void;

export class Cutout {
  readonly mesh: THREE.Mesh;
  readonly width: number;
  readonly height: number;
  private states = new Map<string, { tex: THREE.Texture; normal: THREE.Material }>();
  private mat: THREE.MeshLambertMaterial;
  private depthMat: THREE.MeshDepthMaterial;
  current = "";

  // height in metres; the canvas is drawn at 1:2 (w:h)
  constructor(height: number, states: Record<string, DrawFn>, px = 1024) {
    this.height = height;
    this.width = height / 2;
    for (const [key, draw] of Object.entries(states)) {
      const c = document.createElement("canvas");
      c.width = px;
      c.height = px * 2;
      const ctx = c.getContext("2d");
      if (!ctx) throw new Error("no 2d context");
      ctx.scale(px / 512, px / 512);
      draw(ctx, 512, 1024);
      const tex = new THREE.CanvasTexture(c);
      tex.colorSpace = THREE.SRGBColorSpace;
      tex.anisotropy = 4;
      this.states.set(key, { tex, normal: cutoutNormalMaterial(tex) });
    }
    const first = this.states.values().next().value!;
    this.mat = new THREE.MeshLambertMaterial({
      map: first.tex,
      alphaTest: 0.5,
      side: THREE.DoubleSide,
      emissiveMap: first.tex,
      emissive: new THREE.Color(0.3, 0.3, 0.3),
    });
    this.depthMat = new THREE.MeshDepthMaterial({
      depthPacking: THREE.RGBADepthPacking,
      map: first.tex,
      alphaTest: 0.5,
      side: THREE.DoubleSide,
    });
    const geo = new THREE.PlaneGeometry(this.width, height);
    geo.translate(0, height / 2, 0); // origin at the feet
    this.mesh = new THREE.Mesh(geo, this.mat);
    this.mesh.castShadow = true;
    this.mesh.receiveShadow = false;
    this.mesh.customDepthMaterial = this.depthMat; // alpha-tested shadow: the shape, not the quad
    this.mesh.userData.normalMaterial = first.normal;
    this.current = Object.keys(states)[0];
  }

  setState(key: string) {
    if (key === this.current) return;
    const s = this.states.get(key);
    if (!s) throw new Error(`unknown cutout state ${key}`);
    this.mat.map = s.tex;
    this.mat.emissiveMap = s.tex;
    this.depthMat.map = s.tex;
    this.mesh.userData.normalMaterial = s.normal;
    this.current = key;
  }

  // ambient colour the flat art picks up regardless of the key light (keeps a
  // 2D character readable when the key is behind it)
  setTint(c: THREE.Color, amount: number) {
    this.mat.emissive.copy(c).multiplyScalar(amount);
  }

  // yaw-only billboard toward the camera (stays upright, so its shadow stays a
  // standing figure)
  face(cam: THREE.Camera, blend = 1, baseYaw = 0) {
    const p = this.mesh.position;
    const yaw = Math.atan2(cam.position.x - p.x, cam.position.z - p.z);
    this.mesh.rotation.set(0, baseYaw + (yaw - baseYaw) * blend, 0);
  }

  // canvas coordinates (512x1024 space) -> world, for attaching 3D props to hands
  canvasToWorld(x: number, y: number) {
    const local = new THREE.Vector3(((x - 256) / 512) * this.width, (1 - y / 1024) * this.height, 0.02);
    this.mesh.updateMatrixWorld(true);
    return local.applyMatrix4(this.mesh.matrixWorld);
  }
}
