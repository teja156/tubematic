// A telegraph key on a small desk: the first code part, and the worked example for the authoring agent.
// A code part is a builder (m = the kit materials, ctx = glows/lamps, seed) that returns a THREE.Group standing on
// y = 0 at the origin, facing +z, plus an optional animate() a beat drives through `act`.
import * as THREE from "three";
import type { CodePart } from "./types";

const box = (w: number, h: number, d: number, mat: THREE.Material, x: number, y: number, z: number) => {
  const o = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat);
  o.position.set(x, y, z);
  o.castShadow = true;
  o.receiveShadow = true;
  return o;
};

export const TELEGRAPH_KEY: CodePart = {
  blurb: "a brass morse key on a wooden base, with a sounder box beside it, on a small writing desk",
  acts: { tap: "0..1 how far the key lever is pressed (animate a beat with act.tap pulsing)", busy: "1 = the key taps by itself in a morse rhythm" },
  build: (m) => {
    const g = new THREE.Group();
    // desk: top and four legs
    g.add(box(1.1, 0.05, 0.6, m.darkWood, 0, 0.75, 0));
    for (const [x, z] of [[-0.5, -0.25], [0.5, -0.25], [-0.5, 0.25], [0.5, 0.25]]) g.add(box(0.06, 0.73, 0.06, m.darkWood, x, 0.365, z));
    // key base and lever, drawn big (a cartoon prop has to read at a glance): brass lever on a dark base
    g.add(box(0.44, 0.06, 0.26, m.darkWood, -0.18, 0.805, 0.08));
    g.add(box(0.12, 0.08, 0.12, m.brass, -0.34, 0.86, 0.08));
    const lever = new THREE.Group();
    lever.name = "lever";
    lever.position.set(-0.34, 0.91, 0.08);
    lever.add(box(0.42, 0.035, 0.06, m.brass, 0.21, 0, 0));
    const knob = new THREE.Mesh(new THREE.CylinderGeometry(0.065, 0.065, 0.05, 14), m.dark);
    knob.position.set(0.4, 0.035, 0);
    knob.castShadow = true;
    lever.add(knob);
    g.add(lever);
    // sounder: iron base, two brass coils, a brass armature bar on posts
    g.add(box(0.36, 0.05, 0.24, m.darkWood, 0.28, 0.8, -0.08));
    for (const z of [-0.14, -0.02]) {
      const coil = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 0.16, 12), m.brass);
      coil.position.set(0.22, 0.905, z);
      coil.castShadow = true;
      g.add(coil);
    }
    g.add(box(0.04, 0.22, 0.04, m.brass, 0.4, 0.935, -0.08));
    g.add(box(0.3, 0.035, 0.05, m.iron, 0.27, 1.03, -0.08));
    // a message pad and a wire running off the back edge of the desk
    g.add(box(0.2, 0.012, 0.26, m.canvas, -0.38, 0.783, -0.16));
    g.add(box(0.015, 0.73, 0.015, m.iron, 0.5, 0.41, -0.28));
    return g;
  },
  animate: (g, s) => {
    const lever = g.getObjectByName("lever");
    if (!lever) return;
    let tap = s.act.tap ?? 0;
    if (s.act.busy) {
      // a dot-dash-ish rhythm at about 6 presses a second, deterministic in time
      const u = (s.t * 6) % 1;
      const k = Math.floor(s.t * 6);
      const hold = (k * 7919) % 3 === 0 ? 0.6 : 0.3;
      tap = u < hold ? 1 : 0;
    }
    lever.rotation.z = -0.12 * tap;
  },
};
