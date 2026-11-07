// A landing clock: a double-faced round clock on an iron post (3.6 m). act.spin = 1 runs the hands through six hours
// over the beat (the minute hand six full turns, the hour hand from 4 to 10), for "loses six hours".
import * as THREE from "three";
import type { CodePart } from "./types";

type V3 = [number, number, number];
const lam = (hex: string) => new THREE.MeshLambertMaterial({ color: new THREE.Color(hex) });
const mk = (geo: THREE.BufferGeometry, mat: THREE.Material, at: V3, cast = true) => {
  const o = new THREE.Mesh(geo, mat);
  o.position.set(...at);
  o.castShadow = cast;
  o.receiveShadow = true;
  return o;
};

const dial = () => {
  const S = 512;
  const c = document.createElement("canvas");
  c.width = S;
  c.height = S;
  const ctx = c.getContext("2d") as CanvasRenderingContext2D;
  ctx.fillStyle = "#f3ead2";
  ctx.fillRect(0, 0, S, S);
  ctx.strokeStyle = "#2a2230";
  ctx.lineWidth = 10;
  ctx.beginPath();
  ctx.arc(S / 2, S / 2, S / 2 - 12, 0, Math.PI * 2);
  ctx.stroke();
  ctx.fillStyle = "#2a2230";
  ctx.font = "700 74px Georgia, 'Times New Roman', serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  for (let h = 1; h <= 12; h++) {
    const a = (h / 12) * Math.PI * 2 - Math.PI / 2;
    ctx.fillText(String(h), S / 2 + Math.cos(a) * 190, S / 2 + Math.sin(a) * 190 + 4);
  }
  for (let m = 0; m < 60; m++) {
    const a = (m / 60) * Math.PI * 2;
    const r0 = m % 5 ? 236 : 226;
    ctx.lineWidth = m % 5 ? 3 : 6;
    ctx.beginPath();
    ctx.moveTo(S / 2 + Math.cos(a) * r0, S / 2 + Math.sin(a) * r0);
    ctx.lineTo(S / 2 + Math.cos(a) * 244, S / 2 + Math.sin(a) * 244);
    ctx.stroke();
  }
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.needsUpdate = true;
  return t;
};

const Y = 3.1, R = 0.62;

export const SPIN_CLOCK: CodePart = {
  blurb: "a round double-faced landing clock with numerals on a navy-painted iron post with a stone foot, 3.7 m tall",
  acts: { spin: "1 = the hands race through six hours over the beat (minute hand six turns, hour hand 4 to 10)" },
  build: () => {
    const g = new THREE.Group();
    // painted navy iron, light enough to stay above L* 16 in sunset shade (round 3 verifier: the housing went pure black)
    const iron = lam("#3d4676");
    const gold = lam("#d4a33e");
    const stone = lam("#a59a8a");
    const face = new THREE.MeshLambertMaterial({ map: dial() });
    const hand = new THREE.MeshBasicMaterial({ color: new THREE.Color("#141018") });
    g.add(mk(new THREE.BoxGeometry(0.7, 0.4, 0.7), stone, [0, 0.2, 0]));
    const ph = Y - R - 0.3;
    g.add(mk(new THREE.CylinderGeometry(0.11, 0.16, ph, 10), iron, [0, 0.4 + ph / 2, 0]));
    const drum = mk(new THREE.CylinderGeometry(R + 0.08, R + 0.08, 0.34, 32), iron, [0, Y, 0]);
    drum.rotation.x = Math.PI / 2;
    g.add(drum);
    g.add(mk(new THREE.SphereGeometry(0.13, 10, 8), gold, [0, Y + R + 0.17, 0]));
    for (const s of [-1, 1]) {
      const f = mk(new THREE.CircleGeometry(R, 40), face, [0, Y, s * 0.175], false);
      if (s < 0) f.rotation.y = Math.PI;
      f.userData.noInk = true;
      g.add(f);
      for (const [name, len, w] of [["min", 0.52, 0.05], ["hr", 0.34, 0.08]] as [string, number, number][]) {
        const h = new THREE.Group();
        h.name = `${name}${s}`;
        h.position.set(0, Y, s * 0.19);
        const m = new THREE.Mesh(new THREE.PlaneGeometry(w, len).translate(0, len / 2 - 0.05, 0), hand);
        if (s < 0) m.rotation.y = Math.PI;
        m.position.z = name === "min" ? s * 0.01 : 0;
        m.userData.noInk = true;
        h.add(m);
        g.add(h);
      }
      g.add(mk(new THREE.CircleGeometry(0.05, 12), gold, [0, Y, s * 0.205], false));
    }
    pose(g, 0);
    return g;
  },
  animate: (g, s) => pose(g, s.act.spin ? s.beatT : 0),
  solid: true,
};

/** p = 0..1 of the six hours: 4:00 -> 10:00. Rotation about z, negative = clockwise seen from +z. */
function pose(g: THREE.Group, p: number) {
  const hours = 4 + 6 * p;
  for (const s of [-1, 1]) {
    const mn = g.getObjectByName(`min${s}`), hr = g.getObjectByName(`hr${s}`);
    const am = (hours % 1) * Math.PI * 2, ah = ((hours % 12) / 12) * Math.PI * 2;
    // seen from -z the dial is mirrored, so the hands turn the other way in part space
    if (mn) mn.rotation.z = -s * am;
    if (hr) hr.rotation.z = -s * ah;
  }
}
