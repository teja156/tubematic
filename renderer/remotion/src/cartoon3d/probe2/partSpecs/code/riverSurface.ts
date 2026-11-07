// A 90 x 50 m reach of open river: a flat saturated blue sheet with sparse light crest marks (aspect ~5, each with a
// darker trough line under it) that drift downstream (-x) with the current. Chain several along x for a river.
// No bank, no rim, no ink (a water surface has no silhouette); it sits 6 cm above the ground so it wins over it.
import * as THREE from "three";
import type { CodePart } from "./types";

const TILE = 12; // metres per texture repeat

const waterTex = (seed: number) => {
  const S = 512;
  const c = document.createElement("canvas");
  c.width = S;
  c.height = S;
  const ctx = c.getContext("2d") as CanvasRenderingContext2D;
  let s = seed;
  const rnd = () => ((s = (s * 16807) % 2147483647) / 2147483647);
  ctx.fillStyle = "#1d6a94";
  ctx.fillRect(0, 0, S, S);
  // broad low-frequency swells, very soft
  for (let i = 0; i < 14; i++) {
    ctx.fillStyle = `rgba(${rnd() < 0.5 ? "30,120,170" : "10,80,130"},0.18)`;
    ctx.beginPath();
    ctx.ellipse(rnd() * S, rnd() * S, 80 + rnd() * 120, 18 + rnd() * 20, 0, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.lineCap = "round";
  for (let i = 0; i < 18; i++) {
    const x = rnd() * S, y = rnd() * S, len = 34 + rnd() * 50, th = 7 + rnd() * 5, tilt = (rnd() - 0.5) * 6;
    for (const dx of [0, -S, S]) for (const dy of [0, -S, S]) {
      ctx.strokeStyle = "rgba(20,74,112,0.7)";
      ctx.lineWidth = th * 0.8;
      ctx.beginPath();
      ctx.moveTo(x + dx, y + dy + th * 0.9);
      ctx.quadraticCurveTo(x + dx + len / 2, y + dy + th * 0.9 + tilt - 3, x + dx + len, y + dy + th * 0.9 + tilt);
      ctx.stroke();
      ctx.strokeStyle = "rgba(150,214,232,0.95)";
      ctx.lineWidth = th;
      ctx.beginPath();
      ctx.moveTo(x + dx, y + dy);
      ctx.quadraticCurveTo(x + dx + len / 2, y + dy + tilt - 4, x + dx + len, y + dy + tilt);
      ctx.stroke();
    }
  }
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.repeat.set(90 / TILE, 50 / TILE);
  t.anisotropy = 8;
  t.needsUpdate = true;
  return t;
};

export const RIVER_SURFACE: CodePart = {
  blurb: "a 90 x 50 m flat reach of river water, saturated blue with light ripple crests drifting downstream; no bank",
  build: (_m, _ctx, seed) => {
    const g = new THREE.Group();
    const mat = new THREE.MeshLambertMaterial({ map: waterTex(9001 + seed), polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 });
    const geo = new THREE.PlaneGeometry(90, 50);
    geo.rotateX(-Math.PI / 2);
    const o = new THREE.Mesh(geo, mat);
    o.name = "water";
    o.position.y = 0.06;
    o.receiveShadow = true;
    o.castShadow = false;
    o.userData.noInk = true;
    g.add(o);
    return g;
  },
  animate: (g, s) => {
    const w = g.getObjectByName("water") as THREE.Mesh | undefined;
    const map = (w?.material as THREE.MeshLambertMaterial | undefined)?.map;
    if (map) map.offset.set((s.t * 0.11) % 1, 0);
  },
  solid: false,
};
