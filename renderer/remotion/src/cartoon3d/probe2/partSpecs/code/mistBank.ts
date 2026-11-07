// River fog, second design (fogBank.ts failed the gate twice: soft unoutlined puffs read as a different kit).
// Chunky cartoon fog: three rows of big flattened lumps in flat pale lavender-white, low-poly and INKED like every
// other kit part, so each lump gets a bold outline and the rows read as one banked mass: a low roll in front, a
// middle roll, and a tall back wall that hides whatever is behind it. Rolls drift and breathe. Not solid.
import * as THREE from "three";
import type { CodePart } from "./types";

const roll = (len: number, h: number, depth: number, seed: number) => {
  let s = seed;
  const rnd = () => ((s = (s * 16807) % 2147483647) / 2147483647);
  const geos: THREE.BufferGeometry[] = [];
  // two staggered courses: a row of big lumps and smaller ones riding on top of it
  for (const [course, k] of [[0, 1], [1, 0.62]] as [number, number][]) {
    for (let x = -len / 2 + (course ? h * 0.8 : 0); x < len / 2 - h * 0.5; ) {
      const r = h * k * (0.75 + rnd() * 0.35);
      const g = new THREE.SphereGeometry(r, 9, 6, 0, Math.PI * 2, 0, Math.PI / 2);
      g.scale(1.35, 0.85, depth / (2 * r));
      g.translate(x + r, course ? h * 0.55 : 0, (rnd() - 0.5) * depth * 0.3 - course * depth * 0.15);
      geos.push(g.toNonIndexed());
      x += r * (course ? 2.3 : 1.7);
    }
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

const ROWS: { z: number; len: number; h: number; d: number; x: number }[] = [
  { z: -10, len: 44, h: 2.4, d: 3.5, x: -3 },
  { z: 9, len: 58, h: 4.2, d: 5, x: 2 },
  { z: 17, len: 66, h: 8, d: 7, x: 0 },
];

export const MIST_BANK: CodePart = {
  blurb: "a cartoon river fog bank: three long banked rolls of big flat pale-white lumps, low in front and a tall wall at the back, over 66 m of water",
  build: () => {
    const g = new THREE.Group();
    const mist = new THREE.MeshLambertMaterial({ color: new THREE.Color("#e6e7ef") });
    ROWS.forEach((r, i) => {
      const o = new THREE.Mesh(roll(r.len, r.h, r.d, 410 + i * 23), mist);
      o.name = `roll${i}`;
      o.position.set(r.x, 0.05, r.z);
      o.castShadow = false;
      o.receiveShadow = true;
      g.add(o);
    });
    return g;
  },
  animate: (g, s) => {
    ROWS.forEach((r, i) => {
      const o = g.getObjectByName(`roll${i}`);
      if (!o) return;
      o.position.x = r.x + Math.sin(s.t * 0.25 + i * 1.7) * 1.2 - s.t * 0.2;
      o.scale.y = 1 + 0.05 * Math.sin(s.t * 0.8 + i);
    });
  },
  solid: false,
};
