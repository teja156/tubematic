// A river fog bank, drawn the cartoon way: long low rolls of puffy white cloud lying on the water in four rows (two in
// front of whatever sits at its centre, two behind, the back ones taller), flat white with the two-tone shade giving
// them lavender undersides, no outline (cartoon clouds carry none). The back rows stand tall enough to wall off the
// far bank. Rolls drift and breathe. Place it hidden, show it in the fog beat; it is not solid.
import * as THREE from "three";
import type { CodePart } from "./types";

/** one roll: overlapping flattened lumps along x, merged into one geometry */
const roll = (len: number, h: number, seed: number) => {
  let s = seed;
  const rnd = () => ((s = (s * 16807) % 2147483647) / 2147483647);
  const geos: THREE.BufferGeometry[] = [];
  for (let x = -len / 2; x < len / 2; ) {
    const r = h * (0.55 + rnd() * 0.5);
    const g = new THREE.SphereGeometry(r, 16, 10, 0, Math.PI * 2, 0, Math.PI / 2); // a dome: nothing below the water
    g.scale(1.25, 0.8 + rnd() * 0.35, 0.8);
    g.translate(x + r, 0, (rnd() - 0.5) * h * 0.6);
    geos.push(g.toNonIndexed());
    x += r * (1.1 + rnd() * 0.5);
  }
  const n = geos.reduce((a, g) => a + g.getAttribute("position").count, 0);
  const pos = new Float32Array(n * 3), nor = new Float32Array(n * 3);
  let k = 0;
  for (const g of geos) {
    pos.set(g.getAttribute("position").array as Float32Array, k * 3);
    nor.set(g.getAttribute("normal").array as Float32Array, k * 3);
    k += g.getAttribute("position").count;
  }
  const out = new THREE.BufferGeometry();
  out.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  out.setAttribute("normal", new THREE.BufferAttribute(nor, 3));
  return out;
};

const ROWS: { z: number; len: number; h: number; x: number }[] = [
  { z: -10, len: 46, h: 1.9, x: -4 },
  { z: -6.6, len: 34, h: 1.5, x: 9 },
  { z: 9, len: 60, h: 3.4, x: 0 },
  { z: 15, len: 64, h: 5.6, x: 2 },
  { z: 21, len: 68, h: 7.6, x: -2 },
];

export const FOG_BANK: CodePart = {
  blurb: "a river fog bank in cartoon style: long low rolls of puffy white cloud lying in rows over 70 m of water, the back rows tall as a wall",
  build: () => {
    const g = new THREE.Group();
    const cloud = new THREE.MeshLambertMaterial({ color: new THREE.Color("#eceef3") });
    ROWS.forEach((r, i) => {
      const o = new THREE.Mesh(roll(r.len, r.h, 300 + i * 17), cloud);
      o.name = `roll${i}`;
      o.position.set(r.x, 0.05, r.z);
      o.castShadow = false;
      o.receiveShadow = false;
      o.userData.noInk = true;
      g.add(o);
    });
    return g;
  },
  animate: (g, s) => {
    ROWS.forEach((r, i) => {
      const o = g.getObjectByName(`roll${i}`);
      if (!o) return;
      o.position.x = r.x + Math.sin(s.t * 0.25 + i * 1.7) * 1.5 - s.t * 0.25;
      o.scale.y = 1 + 0.06 * Math.sin(s.t * 0.8 + i);
    });
  },
  solid: false,
};
