// The record, painted up at the St. Louis landing: a white bulletin board on two posts, ROBERT E. LEE in red, then
// 3 DAYS / 18 HOURS / 14 MINUTES and NEW ORLEANS TO ST. LOUIS. Faces +z. act.l2 / act.l3 = the beat fraction at which
// the 18 HOURS and 14 MINUTES lines are painted on (absent = already there), to land on the narrator's words.
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

const W = 3.4, H = 3.7, Y0 = 0.9;
const LINES: { text: string; y: number; px: number; col: string; h: number }[] = [
  { text: "ROBERT E. LEE", y: 0.88, px: 150, col: "#c63b2c", h: 0.55 },
  { text: "3 DAYS", y: 0.66, px: 190, col: "#1f1a26", h: 0.62 },
  { text: "18 HOURS", y: 0.45, px: 190, col: "#1f1a26", h: 0.62 },
  { text: "14 MINUTES", y: 0.24, px: 170, col: "#1f1a26", h: 0.62 },
  { text: "NEW ORLEANS TO ST. LOUIS", y: 0.08, px: 92, col: "#2f63b3", h: 0.32 },
];

const lineTex = (t: string, px: number, col: string, aspect: number) => {
  const cw = 1024, ch = Math.round(cw / aspect);
  const c = document.createElement("canvas");
  c.width = cw;
  c.height = ch;
  const ctx = c.getContext("2d") as CanvasRenderingContext2D;
  ctx.clearRect(0, 0, cw, ch);
  ctx.fillStyle = col;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  let size = px;
  ctx.font = `700 ${size}px Georgia, 'Times New Roman', serif`;
  while (ctx.measureText(t).width > cw * 0.94 && size > 20) {
    size -= 6;
    ctx.font = `700 ${size}px Georgia, 'Times New Roman', serif`;
  }
  ctx.fillText(t, cw / 2, ch / 2 + size * 0.05);
  const tx = new THREE.CanvasTexture(c);
  tx.colorSpace = THREE.SRGBColorSpace;
  tx.anisotropy = 8;
  tx.needsUpdate = true;
  return tx;
};

export const RECORD_BOARD: CodePart = {
  blurb: "a white painted bulletin board on two posts: ROBERT E. LEE, 3 DAYS, 18 HOURS, 14 MINUTES, NEW ORLEANS TO ST. LOUIS",
  acts: { l2: "beat fraction 0..1 at which '18 HOURS' appears", l3: "beat fraction 0..1 at which '14 MINUTES' appears" },
  build: () => {
    const g = new THREE.Group();
    const wood = lam("#6d4a30");
    // the painted face is UNLIT (LOOK-TARGETS readability trap: a sign face lit by a side or setting sun goes grey-blue
    // and loses its cream): it holds its albedo in every light, like the lettering on it
    const paint = new THREE.MeshBasicMaterial({ color: new THREE.Color("#f1e8d2") });
    const red = lam("#c63b2c");
    g.add(mk(new THREE.BoxGeometry(W + 0.24, H + 0.24, 0.1), red, [0, Y0 + H / 2, -0.02]));
    g.add(mk(new THREE.BoxGeometry(W, H, 0.12), paint, [0, Y0 + H / 2, 0]));
    for (const x of [-W / 2 + 0.3, W / 2 - 0.3]) g.add(mk(new THREE.BoxGeometry(0.18, Y0 + 0.3, 0.18), wood, [x, (Y0 + 0.3) / 2, -0.14]));
    // a little gable on top
    const roof = mk(new THREE.BoxGeometry(W + 0.6, 0.14, 0.5), wood, [0, Y0 + H + 0.2, 0.05]);
    g.add(roof);
    LINES.forEach((l, i) => {
      const map = lineTex(l.text, l.px, l.col, (W * 0.95) / l.h);
      const p = new THREE.Mesh(new THREE.PlaneGeometry(W * 0.95, l.h), new THREE.MeshBasicMaterial({ map, transparent: true, alphaTest: 0.3 }));
      p.name = `line${i}`;
      p.position.set(0, Y0 + H * l.y, 0.075);
      p.userData.noInk = true;
      g.add(p);
    });
    return g;
  },
  animate: (g, s) => {
    for (const [i, k] of [[2, "l2"], [3, "l3"]] as [number, string][]) {
      const o = g.getObjectByName(`line${i}`);
      if (o) o.visible = s.act[k] === undefined || s.beatT >= s.act[k];
    }
  },
  solid: true,
};
