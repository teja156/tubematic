// The betting board on the New Orleans levee: a big slate chalkboard in a wooden frame on two legs, chalked with the
// odds on the two boats and the money down. Faces +z.
import * as THREE from "three";
import type { CodePart } from "./types";

type V3 = [number, number, number];
const lam = (hex: string, extra: THREE.MeshLambertMaterialParameters = {}) => new THREE.MeshLambertMaterial({ color: new THREE.Color(hex), ...extra });
const mk = (geo: THREE.BufferGeometry, mat: THREE.Material, at: V3, cast = true) => {
  const o = new THREE.Mesh(geo, mat);
  o.position.set(...at);
  o.castShadow = cast;
  o.receiveShadow = true;
  return o;
};

const W = 3.8, H = 2.7, Y0 = 1.0;

const slate = () => {
  const cw = 1024, ch = Math.round((cw * H) / W);
  const c = document.createElement("canvas");
  c.width = cw;
  c.height = ch;
  const ctx = c.getContext("2d") as CanvasRenderingContext2D;
  ctx.fillStyle = "#26372f";
  ctx.fillRect(0, 0, cw, ch);
  // one soft chalk haze, low frequency only (no tiled smudges on a big surface)
  const haze = ctx.createRadialGradient(cw * 0.4, ch * 0.4, 0, cw * 0.4, ch * 0.4, cw * 0.7);
  haze.addColorStop(0, "rgba(230,240,230,0.07)");
  haze.addColorStop(1, "rgba(230,240,230,0)");
  ctx.fillStyle = haze;
  ctx.fillRect(0, 0, cw, ch);
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  const line = (t: string, y: number, px: number, col: string) => {
    ctx.fillStyle = col;
    ctx.font = `700 ${px}px Georgia, 'Times New Roman', serif`;
    ctx.fillText(t, cw / 2, y);
  };
  line("WAGERS", ch * 0.15, 130, "#f6e27a");
  ctx.strokeStyle = "#f3f1e6";
  ctx.lineWidth = 6;
  ctx.beginPath();
  ctx.moveTo(cw * 0.2, ch * 0.27);
  ctx.lineTo(cw * 0.8, ch * 0.27);
  ctx.stroke();
  line("R. E. LEE    3 to 2", ch * 0.42, 92, "#ffffff");
  line("NATCHEZ    2 to 1", ch * 0.6, 92, "#ffffff");
  line("$1,000,000 BET!", ch * 0.82, 104, "#ffb1a4");
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 8;
  t.needsUpdate = true;
  return t;
};

export const BET_BOARD: CodePart = {
  blurb: "a big chalkboard on two wooden legs chalked WAGERS with the odds on the steamboats R. E. Lee and Natchez and $1,000,000 BET!",
  build: () => {
    const g = new THREE.Group();
    const wood = lam("#8a5a34");
    const face = new THREE.MeshLambertMaterial({ map: slate() });
    g.add(mk(new THREE.BoxGeometry(W + 0.3, H + 0.3, 0.12), wood, [0, Y0 + H / 2, 0]));
    const f = mk(new THREE.PlaneGeometry(W, H), face, [0, Y0 + H / 2, 0.065], false);
    f.userData.noInk = true;
    g.add(f);
    for (const x of [-W / 2 + 0.25, W / 2 - 0.25]) g.add(mk(new THREE.BoxGeometry(0.16, Y0 + 0.2, 0.16), wood, [x, (Y0 + 0.2) / 2, -0.12]));
    g.add(mk(new THREE.BoxGeometry(W * 0.8, 0.08, 0.3), wood, [0, Y0 - 0.05, 0.12]));
    return g;
  },
  solid: true,
};
