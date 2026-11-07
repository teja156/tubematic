// PROBE 2 parts pool — the DOM half: materials, textures and meshes for every
// PartKind and for styled buildings. Pure facts (footprints, catalog, style
// resolution, facade layout, extents) live in partsSpec.ts.
//
// Conventions:
// - every part is built at the origin on y = 0, facing +z, local +x to its right
// - materials come from makePartMaterials(), built ONCE per world and shared
// - lamps: a THREE.PointLight with intensity 0 and castShadow false, registered
//   in ctx.lamps (the scene drives intensity from Lamp.peak); glowing surfaces
//   get their own material registered in ctx.glows (the scene drives emissive)
// - smoke: the returned group carries `userData.smoke: THREE.Vector3[]` in the
//   group's LOCAL frame. The caller applies the group's world matrix
//   (`g.updateMatrixWorld(); p.clone().applyMatrix4(g.matrixWorld)`) after it
//   has positioned the group. ctx.smokeLocal is kept for API compatibility and
//   is never written.
// - flat decals, glows and flames carry userData.noInk; every solid gets ink
import * as THREE from "three";
import { gable, mesh, pitchedRoof, rock, tubeThrough, wire, worldBox } from "../kit/geometry";
import { cutoutNormalMaterial } from "../kit/InkPipeline";
import { figureTex, plateTex } from "./cardDraw";
import { compilePart } from "./partCompile";
import type { PartSpec } from "./partGrammar";
import { PART_SPECS } from "./partSpecs";
import { makeRng, range, type Rng } from "../kit/prng";
import * as T from "../kit/textures";
import type { Glow, Lamp } from "./worldBuild";
import { signDims, type BuildingPiece, type Hsl } from "./worldKit";
import { chimneyPlace, facadeLayout, PART_DIMS, partSpecOf, resolveStyle, roofRise, type BuildingStyle, type PartKind, type PropName } from "./partsSpec";
import { CODE_PARTS } from "./partSpecs/code/index";
import { registerCodeBuilder } from "./partSpecs/code/measure";

export interface PartCtx {
  glows: Glow[];
  lamps: Lamp[];
  /** unused — smoke points travel on group.userData.smoke (see header) */
  smokeLocal: THREE.Vector3[];
  /** the kit's water surface (kit/Water.ts): a w x d sheet, lit and fogged by the scene, for a code part that
   *  carries water (a pond, a mill race); whole rivers go in WorldSpec.water instead */
  water?: (w: number, d: number, o?: { flow?: [number, number]; marks?: number }) => THREE.Mesh;
}

type V3 = [number, number, number];

// ------------------------------------------------------------------ colour

const css = (h: number, s: number, l: number, a = 1) =>
  `hsla(${h.toFixed(1)},${(Math.max(0, Math.min(1, s)) * 100).toFixed(1)}%,${(Math.max(0, Math.min(1, l)) * 100).toFixed(1)}%,${a})`;
const col = (h: number, s: number, l: number) => new THREE.Color().setHSL(((h % 360) + 360) % 360 / 360, s, l, THREE.SRGBColorSpace);
const lam = (map?: THREE.Texture | null, color: THREE.ColorRepresentation = 0xffffff, extra: THREE.MeshLambertMaterialParameters = {}) =>
  new THREE.MeshLambertMaterial({ map: map ?? null, color, ...extra });
const flat = (h: number, s: number, l: number, extra: THREE.MeshLambertMaterialParameters = {}) => lam(null, col(h, s, l), extra);

// ---------------------------------------------------------------- textures
// All hand-painted on canvases, seeded, muted. kit/textures covers planks,
// shingles, dirt, bark and signs; these are the extra surfaces the pool needs.

const strawTex = (seed: number, hue = 42, sat = 0.32, light = 0.6, ends = false) => {
  const S = 256;
  const { c, ctx } = T.makeCanvas(S, S);
  const rng = makeRng(seed);
  ctx.fillStyle = css(hue - 4, sat, light - 0.14);
  ctx.fillRect(0, 0, S, S);
  ctx.lineCap = "round";
  for (let i = 0; i < (ends ? 1400 : 1100); i++) {
    const x = rng() * S;
    const y = rng() * S;
    const l = light + range(rng, -0.16, 0.12);
    ctx.strokeStyle = css(hue + range(rng, -6, 6), sat + range(rng, -0.08, 0.06), l, range(rng, 0.55, 0.95));
    ctx.lineWidth = range(rng, 1, 2.4);
    ctx.beginPath();
    if (ends) {
      ctx.arc(x, y, range(rng, 0.8, 2.2), 0, Math.PI * 2);
      ctx.stroke();
    } else {
      const a = range(rng, -0.35, 0.35);
      const len = range(rng, 8, 26);
      ctx.moveTo(x, y);
      ctx.lineTo(x + Math.cos(a) * len, y + Math.sin(a) * len);
      ctx.stroke();
    }
  }
  return T.toTexture(c);
};

const ringsTex = (seed: number, hue = 34, sat = 0.34, light = 0.64) => {
  const S = 256;
  const { c, ctx } = T.makeCanvas(S, S);
  const rng = makeRng(seed);
  // the face fills the square so polygonal caps never sample a border; bark
  // shows as a thin dark rim right at the edge
  ctx.fillStyle = css(hue, sat, light);
  ctx.fillRect(0, 0, S, S);
  ctx.strokeStyle = css(hue - 8, 0.35, 0.3);
  ctx.lineWidth = S * 0.05;
  ctx.beginPath();
  ctx.arc(S / 2, S / 2, S * 0.475, 0, Math.PI * 2);
  ctx.stroke();
  for (let r = 6; r < S * 0.45; r += range(rng, 5, 11)) {
    ctx.strokeStyle = css(hue - 4, sat, light - range(rng, 0.1, 0.2), 0.6);
    ctx.lineWidth = range(rng, 1, 2.2);
    ctx.beginPath();
    for (let k = 0; k <= 24; k++) {
      const a = (k / 24) * Math.PI * 2;
      const rr = r * (1 + 0.04 * Math.sin(a * 3 + r));
      const px = S / 2 + Math.cos(a) * rr;
      const py = S / 2 + Math.sin(a) * rr;
      if (k === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    }
    ctx.stroke();
  }
  // a check crack
  ctx.strokeStyle = css(hue - 10, 0.4, 0.25, 0.8);
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(S / 2, S / 2);
  ctx.lineTo(S / 2 + S * 0.42, S / 2 + range(rng, -20, 20));
  ctx.stroke();
  return T.toTexture(c, false);
};

const fieldstoneTex = (seed: number, hue = 30, sat = 0.1, light = 0.6) => {
  const S = 512;
  const { c, ctx } = T.makeCanvas(S, S);
  const rng = makeRng(seed);
  ctx.fillStyle = css(hue + 230, 0.18, 0.24);
  ctx.fillRect(0, 0, S, S);
  let y = 0;
  while (y < S) {
    const rh = range(rng, 46, 78);
    let x = -range(rng, 0, 60);
    while (x < S) {
      const w = range(rng, 60, 120);
      const l = light + range(rng, -0.08, 0.07);
      const hh = hue + range(rng, -14, 14);
      for (const dx of [0, S, -S]) {
        ctx.fillStyle = css(hh, sat + range(rng, -0.03, 0.05), l);
        ctx.beginPath();
        ctx.roundRect(x + dx + 4, y + 4, w - 8, Math.min(rh, S - y) - 8, range(rng, 10, 22));
        ctx.fill();
        ctx.fillStyle = css(hh, sat, l + 0.08, 0.5);
        ctx.beginPath();
        ctx.ellipse(x + dx + w * 0.4, y + rh * 0.35, w * 0.25, rh * 0.15, 0, 0, Math.PI * 2);
        ctx.fill();
      }
      x += w;
    }
    y += rh;
  }
  return T.toTexture(c);
};

const brickTex = (seed: number, hue = 12, sat = 0.38, light = 0.42) => {
  const S = 512;
  const { c, ctx } = T.makeCanvas(S, S);
  const rng = makeRng(seed);
  ctx.fillStyle = css(35, 0.12, 0.7);
  ctx.fillRect(0, 0, S, S);
  const rows = 16;
  const rh = S / rows;
  const bw = S / 4;
  for (let r = 0; r < rows; r++) {
    const off = r % 2 ? bw / 2 : 0;
    for (let k = -1; k <= 4; k++) {
      const x = k * bw + off;
      const l = light + range(rng, -0.07, 0.06) - (rng() < 0.12 ? 0.1 : 0);
      ctx.fillStyle = css(hue + range(rng, -5, 5), sat + range(rng, -0.06, 0.06), l);
      ctx.fillRect(x + 3, r * rh + 3, bw - 6, rh - 6);
      ctx.fillStyle = css(hue, sat, l + 0.07, 0.4);
      ctx.fillRect(x + 5, r * rh + 4, bw - 14, 4);
    }
  }
  return T.toTexture(c);
};

const adobeTex = (seed: number, hue = 26, sat = 0.32, light = 0.66) => {
  const S = 512;
  const { c, ctx } = T.makeCanvas(S, S);
  const rng = makeRng(seed);
  ctx.fillStyle = css(hue, sat, light);
  ctx.fillRect(0, 0, S, S);
  for (let i = 0; i < 160; i++) {
    ctx.fillStyle = css(hue + range(rng, -6, 6), sat, light + range(rng, -0.07, 0.05), range(rng, 0.15, 0.35));
    ctx.beginPath();
    ctx.ellipse(rng() * S, rng() * S, range(rng, 14, 60), range(rng, 8, 30), rng() * 3, 0, Math.PI * 2);
    ctx.fill();
  }
  // patches where the plaster fell away and the mud bricks show
  for (let p = 0; p < 3; p++) {
    const px = rng() * (S - 120);
    const py = rng() * (S - 80);
    ctx.fillStyle = css(hue - 2, sat * 0.8, light - 0.08);
    ctx.beginPath();
    ctx.ellipse(px + 60, py + 40, 64, 36, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = css(hue - 4, sat * 0.8, light - 0.2, 0.6);
    ctx.lineWidth = 2;
    for (let ry = py + 14; ry < py + 72; ry += 18) {
      ctx.beginPath();
      ctx.moveTo(px + 12, ry);
      ctx.lineTo(px + 108, ry);
      ctx.stroke();
    }
  }
  for (let k = 0; k < 5; k++) {
    ctx.strokeStyle = css(hue - 8, sat, light - 0.3, 0.6);
    ctx.lineWidth = 1.5;
    let x = rng() * S;
    let y = rng() * S;
    ctx.beginPath();
    ctx.moveTo(x, y);
    for (let s = 0; s < 6; s++) {
      x += range(rng, -14, 14);
      y += range(rng, 6, 18);
      ctx.lineTo(x, y);
    }
    ctx.stroke();
  }
  return T.toTexture(c);
};

const clothTex = (seed: number, hue: number, sat: number, light: number, stripe?: Hsl, stripes = 0, band = 0.5) => {
  const S = 256;
  const { c, ctx } = T.makeCanvas(S, S);
  const rng = makeRng(seed);
  ctx.fillStyle = css(hue, sat, light);
  ctx.fillRect(0, 0, S, S);
  if (stripe && stripes > 0) {
    const pitch = S / stripes;
    ctx.fillStyle = css(stripe.hue, stripe.sat, stripe.light);
    for (let i = 0; i < stripes; i++) ctx.fillRect(i * pitch, 0, pitch * band, S);
  }
  for (let i = 0; i < 260; i++) {
    ctx.strokeStyle = css(hue, sat, light + range(rng, -0.1, 0.08), 0.18);
    ctx.lineWidth = 1;
    const y = rng() * S;
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(S, y + range(rng, -2, 2));
    ctx.stroke();
  }
  for (let i = 0; i < 30; i++) {
    ctx.fillStyle = css(hue, sat * 0.6, light - 0.12, 0.12);
    ctx.beginPath();
    ctx.ellipse(rng() * S, rng() * S, range(rng, 10, 40), range(rng, 4, 14), rng() * 3, 0, Math.PI * 2);
    ctx.fill();
  }
  return T.toTexture(c);
};

const tinTex = (seed: number, hue = 220, sat = 0.06, light = 0.6) => {
  const S = 256;
  const { c, ctx } = T.makeCanvas(S, S);
  const rng = makeRng(seed);
  const n = 16;
  for (let i = 0; i < n; i++) {
    const g = ctx.createLinearGradient((i * S) / n, 0, ((i + 1) * S) / n, 0);
    g.addColorStop(0, css(hue, sat, light - 0.16));
    g.addColorStop(0.5, css(hue, sat, light + 0.08));
    g.addColorStop(1, css(hue, sat, light - 0.16));
    ctx.fillStyle = g;
    ctx.fillRect((i * S) / n, 0, S / n + 1, S);
  }
  for (let i = 0; i < 14; i++) {
    const x = rng() * S;
    const g = ctx.createLinearGradient(0, 0, 0, S);
    g.addColorStop(0, "hsla(20,50%,35%,0.0)");
    g.addColorStop(1, "hsla(20,50%,35%,0.5)");
    ctx.fillStyle = g;
    ctx.fillRect(x, range(rng, 0, S * 0.6), range(rng, 3, 9), S);
  }
  return T.toTexture(c);
};

const posterTex = (seed: number) => {
  const W = 192;
  const H = 256;
  const { c, ctx } = T.makeCanvas(W, H);
  const rng = makeRng(seed);
  ctx.fillStyle = css(range(rng, 36, 48), range(rng, 0.25, 0.4), range(rng, 0.78, 0.86));
  ctx.fillRect(0, 0, W, H);
  ctx.fillStyle = css(range(rng, 0, 360) < 180 ? 8 : 220, 0.3, 0.3);
  ctx.fillRect(14, 16, W - 28, 34);
  ctx.strokeStyle = "hsla(260,30%,18%,0.75)";
  ctx.lineCap = "round";
  for (let y = 70; y < H - 20; y += range(rng, 14, 22)) {
    ctx.lineWidth = range(rng, 2, 4);
    ctx.beginPath();
    let x = 18;
    ctx.moveTo(x, y);
    const end = W - range(rng, 18, 60);
    while (x < end) {
      x += range(rng, 8, 16);
      ctx.lineTo(x, y + range(rng, -2, 2));
    }
    ctx.stroke();
  }
  if (rng() < 0.5) {
    ctx.strokeStyle = "hsla(260,30%,18%,0.7)";
    ctx.lineWidth = 3;
    ctx.strokeRect(50, 120, W - 100, 70);
  }
  return T.toTexture(c, false);
};

/** a painted board with illegible hand lettering, for arrows and labels */
const letteredTex = (seed: number, bg: Hsl, fg: Hsl) => {
  const W = 512;
  const H = 128;
  const { c, ctx } = T.makeCanvas(W, H);
  const rng = makeRng(seed);
  ctx.fillStyle = css(bg.hue, bg.sat, bg.light);
  ctx.fillRect(0, 0, W, H);
  for (let i = 0; i < 40; i++) {
    ctx.strokeStyle = css(bg.hue, bg.sat, bg.light + range(rng, -0.08, 0.06), 0.3);
    ctx.lineWidth = range(rng, 1, 3);
    const y = rng() * H;
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(W, y + range(rng, -3, 3));
    ctx.stroke();
  }
  ctx.strokeStyle = css(fg.hue, fg.sat, fg.light);
  ctx.lineWidth = 9;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  let x = 70;
  const y = H / 2;
  while (x < W - 70) {
    ctx.beginPath();
    ctx.moveTo(x, y + range(rng, -22, 22));
    for (let k = 0; k < 3; k++) ctx.lineTo(x + range(rng, 4, 22), y + range(rng, -26, 26));
    ctx.stroke();
    x += range(rng, 26, 40);
    if (rng() < 0.15) x += 26;
  }
  return T.toTexture(c, false);
};

const clockTex = () => {
  const S = 256;
  const { c, ctx } = T.makeCanvas(S, S);
  ctx.fillStyle = css(44, 0.35, 0.88);
  ctx.fillRect(0, 0, S, S);
  ctx.strokeStyle = "hsl(260,35%,16%)";
  ctx.lineWidth = 8;
  ctx.beginPath();
  ctx.arc(S / 2, S / 2, S * 0.44, 0, Math.PI * 2);
  ctx.stroke();
  for (let i = 0; i < 12; i++) {
    const a = (i / 12) * Math.PI * 2;
    ctx.lineWidth = i % 3 === 0 ? 9 : 5;
    ctx.beginPath();
    ctx.moveTo(S / 2 + Math.cos(a) * S * 0.33, S / 2 + Math.sin(a) * S * 0.33);
    ctx.lineTo(S / 2 + Math.cos(a) * S * 0.4, S / 2 + Math.sin(a) * S * 0.4);
    ctx.stroke();
  }
  ctx.lineCap = "round";
  ctx.lineWidth = 9;
  ctx.beginPath();
  ctx.moveTo(S / 2, S / 2);
  ctx.lineTo(S / 2 + S * 0.16, S / 2 - S * 0.12);
  ctx.stroke();
  ctx.lineWidth = 6;
  ctx.beginPath();
  ctx.moveTo(S / 2, S / 2);
  ctx.lineTo(S / 2 - S * 0.04, S / 2 - S * 0.33);
  ctx.stroke();
  return T.toTexture(c, false);
};

const leafTex = (seed: number, hue: number, sat: number, light: number) => {
  const S = 256;
  const { c, ctx } = T.makeCanvas(S, S);
  const rng = makeRng(seed);
  ctx.fillStyle = css(hue, sat, light);
  ctx.fillRect(0, 0, S, S);
  for (let i = 0; i < 160; i++) {
    ctx.fillStyle = css(hue + range(rng, -10, 12), sat + range(rng, -0.06, 0.06), light + range(rng, -0.1, 0.1), 0.55);
    ctx.beginPath();
    ctx.ellipse(rng() * S, rng() * S, range(rng, 5, 15), range(rng, 3, 8), rng() * 3, 0, Math.PI * 2);
    ctx.fill();
  }
  return T.toTexture(c);
};

/** stripes: vertical (vary along u) or horizontal (vary along v) */
const ribTex = (hue: number, sat: number, light: number, ribs: number, vertical: boolean) => {
  const S = 256;
  const { c, ctx } = T.makeCanvas(S, S);
  for (let i = 0; i < ribs; i++) {
    const a = (i * S) / ribs;
    const b = ((i + 1) * S) / ribs;
    const g = vertical ? ctx.createLinearGradient(a, 0, b, 0) : ctx.createLinearGradient(0, a, 0, b);
    g.addColorStop(0, css(hue, sat, light - 0.12));
    g.addColorStop(0.5, css(hue, sat, light + 0.06));
    g.addColorStop(1, css(hue, sat, light - 0.12));
    ctx.fillStyle = g;
    if (vertical) ctx.fillRect(a, 0, b - a + 1, S);
    else ctx.fillRect(0, a, S, b - a + 1);
  }
  return T.toTexture(c);
};

const lumpsTex = (seed: number, hue: number, sat: number, light: number) => {
  const S = 256;
  const { c, ctx } = T.makeCanvas(S, S);
  const rng = makeRng(seed);
  ctx.fillStyle = css(hue, sat, light - 0.1);
  ctx.fillRect(0, 0, S, S);
  for (let i = 0; i < 420; i++) {
    ctx.fillStyle = css(hue + range(rng, -10, 10), sat, light + range(rng, -0.1, 0.14));
    ctx.beginPath();
    ctx.ellipse(rng() * S, rng() * S, range(rng, 3, 10), range(rng, 2, 7), rng() * 3, 0, Math.PI * 2);
    ctx.fill();
  }
  return T.toTexture(c);
};

const waterTex = (seed: number, bold = false) => {
  const S = 512;
  const { c, ctx } = T.makeCanvas(S, S);
  const rng = makeRng(seed);
  ctx.fillStyle = css(196, 0.2, 0.42);
  ctx.fillRect(0, 0, S, S);
  for (let i = 0; i < (bold ? 130 : 70); i++) {
    ctx.strokeStyle = css(190, 0.2, range(rng, 0.52, 0.64) + (bold ? 0.1 : 0), bold ? 0.7 : 0.45);
    ctx.lineWidth = bold ? range(rng, 3, 6) : range(rng, 1.5, 3);
    const x = rng() * S;
    const y = rng() * S;
    const len = bold ? range(rng, 40, 120) : range(rng, 20, 70);
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.quadraticCurveTo(x + len / 2, y - 3, x + len, y);
    ctx.stroke();
  }
  return T.toTexture(c);
};

const birchTex = (seed: number) => {
  const S = 256;
  const { c, ctx } = T.makeCanvas(S, S);
  const rng = makeRng(seed);
  ctx.fillStyle = css(40, 0.3, 0.8);
  ctx.fillRect(0, 0, S, S);
  for (let i = 0; i < 46; i++) {
    ctx.fillStyle = css(30, 0.25, 0.25, range(rng, 0.5, 0.85));
    ctx.fillRect(rng() * S, rng() * S, range(rng, 8, 30), range(rng, 2, 4));
  }
  return T.toTexture(c);
};

// ---------------------------------------------------------------- materials

export const makePartMaterials = () => {
  const P = (seed: number, planks: number, hue: number, sat: number, light: number, more: Partial<T.PlankOpts> = {}) =>
    lam(T.planks({ seed, planks, hue, sat, light, ...more }));
  const posters = [posterTex(611), posterTex(612), posterTex(613), posterTex(614)].map((t) => lam(t));
  const sides = { side: THREE.DoubleSide } as const;
  return {
    // woods
    crate: P(301, 4, 34, 0.36, 0.58),
    lightWood: P(304, 5, 36, 0.32, 0.64),
    midWood: P(309, 5, 30, 0.34, 0.47),
    darkWood: P(303, 5, 24, 0.32, 0.32),
    tieWood: P(348, 4, 26, 0.26, 0.4),
    greyWood: P(310, 6, 34, 0.1, 0.56),
    greyWoodV: P(311, 6, 34, 0.1, 0.54, { vertical: true }),
    freshWood: P(312, 5, 38, 0.38, 0.7),
    barrel: P(302, 9, 26, 0.4, 0.44, { vertical: true }),
    barrelDS: lam(T.planks({ seed: 302, planks: 9, hue: 26, sat: 0.4, light: 0.44, vertical: true }), 0xffffff, sides),
    redPaint: P(313, 6, 6, 0.34, 0.4, { painted: { hue: 6, sat: 0.38, light: 0.42, wear: 0.35 } }),
    redPaintV: P(314, 6, 6, 0.34, 0.4, { vertical: true, painted: { hue: 6, sat: 0.38, light: 0.42, wear: 0.35 } }),
    creamPaint: P(315, 6, 36, 0.3, 0.55, { painted: { hue: 42, sat: 0.28, light: 0.82, wear: 0.4 } }),
    greenPaint: P(316, 6, 30, 0.3, 0.45, { painted: { hue: 150, sat: 0.18, light: 0.38, wear: 0.3 } }),
    bluePaint: P(317, 6, 30, 0.3, 0.45, { painted: { hue: 210, sat: 0.2, light: 0.42, wear: 0.3 } }),
    bark: lam(T.bark(305, 24, 0.36)),
    barkGrey: lam(lumpsTex(318, 34, 0.07, 0.52)),
    rings: lam(ringsTex(319, 30, 0.32, 0.55)),
    ringsFresh: lam(ringsTex(320, 38, 0.38, 0.72)),
    // metals
    iron: flat(258, 0.22, 0.2),
    steel: flat(240, 0.1, 0.42),
    tinSheet: flat(215, 0.08, 0.62),
    rust: flat(18, 0.38, 0.36),
    brass: flat(42, 0.42, 0.52),
    // fibres and cloth
    burlap: lam(T.dirt(306, 36, 0.3, 0.58)),
    canvas: lam(clothTex(321, 42, 0.22, 0.8), 0xffffff, sides),
    mailCanvas: lam(clothTex(322, 40, 0.14, 0.74, { hue: 215, sat: 0.22, light: 0.42 }, 2, 0.12)),
    straw: lam(strawTex(307)),
    strawEnd: lam(strawTex(308, 40, 0.3, 0.56, true)),
    twine: flat(30, 0.28, 0.32),
    rope: flat(38, 0.26, 0.62),
    leather: flat(22, 0.4, 0.3),
    leatherLight: flat(28, 0.38, 0.42),
    blanket: lam(clothTex(323, 8, 0.32, 0.44, { hue: 40, sat: 0.3, light: 0.78 }, 4), 0xffffff, sides),
    flag: lam(clothTex(324, 6, 0.36, 0.44, { hue: 40, sat: 0.3, light: 0.82 }, 3), 0xffffff, sides),
    flagCanton: flat(220, 0.25, 0.32, sides),
    clothes: [
      lam(clothTex(325, 42, 0.18, 0.86), 0xffffff, sides),
      lam(clothTex(326, 212, 0.2, 0.5), 0xffffff, sides),
      lam(clothTex(327, 8, 0.3, 0.5), 0xffffff, sides),
      lam(clothTex(328, 34, 0.22, 0.7, { hue: 6, sat: 0.3, light: 0.48 }, 6), 0xffffff, sides),
    ],
    shirt: lam(clothTex(329, 205, 0.18, 0.46, { hue: 30, sat: 0.2, light: 0.36 }, 5)),
    denim: flat(220, 0.2, 0.34),
    // earth and stone
    stone: lam(fieldstoneTex(330, 30, 0.08, 0.6)),
    stoneDark: lam(fieldstoneTex(331, 25, 0.08, 0.46)),
    stoneRough: lam(T.dirt(349, 26, 0.07, 0.44)),
    rockMat: lam(T.dirt(332, 30, 0.08, 0.56)),
    hill: lam(T.dirt(351, 28, 0.1, 0.5), 0xffffff, { flatShading: true }),
    gravel: lam(lumpsTex(333, 30, 0.1, 0.5)),
    sandstone: lam(T.dirt(350, 36, 0.14, 0.64)),
    coal: lam(lumpsTex(334, 250, 0.12, 0.16)),
    ore: lam(lumpsTex(335, 22, 0.25, 0.4)),
    soil: lam(T.dirt(336, 24, 0.3, 0.28)),
    mud: lam(T.dirt(337, 28, 0.3, 0.36), 0xffffff, { polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1 }),
    water: lam(waterTex(338), 0xffffff, { polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 }),
    waterTop: flat(196, 0.18, 0.4),
    river: lam(waterTex(345, true), 0xffffff, { polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 }),
    // plants
    leaf: lam(leafTex(339, 96, 0.2, 0.37)),
    leafDark: lam(leafTex(340, 132, 0.2, 0.29)),
    leafDry: lam(leafTex(341, 62, 0.2, 0.44)),
    reed: flat(72, 0.2, 0.42),
    cattail: flat(22, 0.4, 0.28),
    cactus: lam(ribTex(104, 0.17, 0.42, 14, true)),
    cactusH: lam(ribTex(104, 0.17, 0.42, 6, false)),
    lily: flat(100, 0.2, 0.36, { polygonOffset: true, polygonOffsetFactor: -3, polygonOffsetUnits: -3 }),
    blooms: [flat(4, 0.42, 0.58), flat(40, 0.48, 0.62), flat(44, 0.3, 0.86), flat(285, 0.18, 0.64)],
    birch: lam(birchTex(342)),
    // printed
    posters,
    clock: lam(clockTex()),
    arrow: lam(letteredTex(343, { hue: 40, sat: 0.3, light: 0.8 }, { hue: 260, sat: 0.3, light: 0.2 })),
    arrowDark: lam(letteredTex(344, { hue: 24, sat: 0.32, light: 0.32 }, { hue: 44, sat: 0.4, light: 0.82 })),
    // shared misc
    dark: new THREE.MeshBasicMaterial({ color: col(262, 0.4, 0.07) }),
    darkHole: new THREE.MeshBasicMaterial({ color: col(262, 0.4, 0.05), polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 }),
    personRef: flat(250, 0.08, 0.5),
    // rolling stock
    engineBlack: flat(255, 0.14, 0.17),
    engineRed: flat(2, 0.55, 0.42),
    coachPaint: P(352, 6, 30, 0.3, 0.45, { painted: { hue: 44, sat: 0.5, light: 0.52, wear: 0.2 } }),
    coachRoof: flat(250, 0.1, 0.3),
    // building trim/doors are made per building (they take the piece's colours)
  };
};
export type PartMaterials = ReturnType<typeof makePartMaterials>;

// ------------------------------------------------------------------ helpers

const add = (g: THREE.Object3D, geo: THREE.BufferGeometry, mat: THREE.Material | THREE.Material[], pos: V3, rot?: V3, cast = true) => {
  const o = mesh(geo, mat, pos, { rot, cast });
  g.add(o);
  return o;
};
const box = (g: THREE.Object3D, w: number, h: number, d: number, mat: THREE.Material | THREE.Material[], pos: V3, rot?: V3, tex = 1) =>
  add(g, worldBox(w, h, d, tex), mat, pos, rot);
const cyl = (g: THREE.Object3D, rt: number, rb: number, h: number, mat: THREE.Material | THREE.Material[], pos: V3, rot?: V3, seg = 10) =>
  add(g, new THREE.CylinderGeometry(rt, rb, h, seg), mat, pos, rot);

const UP = new THREE.Vector3(0, 1, 0);
/** a cylinder from a to b */
const rod = (g: THREE.Object3D, a: V3, b: V3, r: number, mat: THREE.Material | THREE.Material[], seg = 6, r2 = r) => {
  const va = new THREE.Vector3(...a);
  const vb = new THREE.Vector3(...b);
  const len = va.distanceTo(vb);
  const o = mesh(new THREE.CylinderGeometry(r2, r, len, seg), mat, [0, 0, 0]);
  o.position.copy(va).add(vb).multiplyScalar(0.5);
  o.quaternion.setFromUnitVectors(UP, vb.clone().sub(va).normalize());
  g.add(o);
  return o;
};
/** a log with bark round its side and growth rings on its ends */
const log = (g: THREE.Object3D, m: PartMaterials, r: number, len: number, pos: V3, axis: "x" | "z" | "y", seg = 10, spin = 0) => {
  const rot: V3 = axis === "x" ? [spin, 0, Math.PI / 2] : axis === "z" ? [Math.PI / 2, spin, 0] : [0, spin, 0];
  return add(g, new THREE.CylinderGeometry(r, r, len, seg), [m.bark, m.rings, m.rings], pos, rot);
};
const scaleUv = <G extends THREE.BufferGeometry>(geo: G, su: number, sv: number) => {
  const uv = geo.getAttribute("uv") as THREE.BufferAttribute;
  for (let i = 0; i < uv.count; i++) uv.setXY(i, uv.getX(i) * su, uv.getY(i) * sv);
  return geo;
};
const lathe = (pts: [number, number][], seg = 16) => new THREE.LatheGeometry(pts.map(([r, y]) => new THREE.Vector2(r, y)), seg);
const decal = (o: THREE.Object3D) => {
  o.userData.noInk = true;
  o.castShadow = false;
  return o;
};
const glowMat = (ctx: PartCtx, base: THREE.ColorRepresentation, emit: THREE.Color, peak: number) => {
  const mat = lam(null, base, { emissive: new THREE.Color(0x000000) });
  ctx.glows.push({ mat, color: emit, peak });
  return mat;
};
const lampLight = (g: THREE.Object3D, ctx: PartCtx, color: THREE.ColorRepresentation, pos: V3, peak: number, flicker: boolean, dist = 10) => {
  const light = new THREE.PointLight(color, 0, dist, 2);
  light.castShadow = false;
  light.position.set(...pos);
  ctx.lamps.push({ light, peak, flicker });
  g.add(light);
};

/** spoked wheel in the xy plane (axle along z) */
const wheel = (g: THREE.Object3D, m: PartMaterials, r: number, pos: V3, spokes = 10, rim: THREE.Material = m.midWood) => {
  const w = new THREE.Group();
  w.position.set(...pos);
  add(w, new THREE.TorusGeometry(r - 0.03, 0.04, 6, 24), rim, [0, 0, 0]);
  add(w, new THREE.TorusGeometry(r, 0.022, 4, 24), m.iron, [0, 0, 0]);
  cyl(w, r * 0.16, r * 0.16, 0.16, m.darkWood, [0, 0, 0], [Math.PI / 2, 0, 0], 10);
  for (let i = 0; i < spokes; i++) {
    const a = (i / spokes) * Math.PI * 2;
    rod(w, [Math.cos(a) * r * 0.14, Math.sin(a) * r * 0.14, 0], [Math.cos(a) * (r - 0.05), Math.sin(a) * (r - 0.05), 0], Math.max(0.014, r * 0.035), m.midWood, 5);
  }
  g.add(w);
  return w;
};

const barrelGeo = (r = 0.3, h = 0.88, bulge = 0.04) => {
  const pts: [number, number][] = [];
  for (let i = 0; i <= 8; i++) {
    const y = (i / 8) * h;
    pts.push([r - bulge + bulge * Math.sin((Math.PI * y) / h), y]);
  }
  return lathe(pts, 16);
};
const barrelAt = (g: THREE.Object3D, m: PartMaterials, pos: V3, rot: V3 = [0, 0, 0], open = false, s = 1) => {
  const b = new THREE.Group();
  b.position.set(...pos);
  b.rotation.set(...rot);
  b.scale.setScalar(s);
  const r = 0.3;
  const h = 0.88;
  add(b, barrelGeo(r, h), open ? m.barrelDS : m.barrel, [0, 0, 0]);
  if (!open) add(b, new THREE.CircleGeometry(r - 0.03, 16), m.darkWood, [0, h - 0.015, 0], [-Math.PI / 2, 0, 0]);
  add(b, new THREE.CircleGeometry(r - 0.03, 16), m.darkWood, [0, 0.005, 0], [Math.PI / 2, 0, 0]);
  for (const t of [0.12, 0.3, 0.7, 0.88]) {
    const y = t * h;
    const rr = r - 0.04 + 0.04 * Math.sin(Math.PI * t) + 0.008;
    cyl(b, rr, rr, 0.04, m.iron, [0, y, 0], undefined, 16);
  }
  g.add(b);
  return b;
};

const crateAt = (g: THREE.Object3D, m: PartMaterials, s: number, pos: V3, yaw = 0) => {
  const c = new THREE.Group();
  c.position.set(...pos);
  c.rotation.y = yaw;
  const t = 0.07 * (s / 0.8);
  box(c, s - 0.02, s - 0.02, s - 0.02, m.crate, [0, s / 2, 0]);
  for (const x of [-1, 1]) for (const z of [-1, 1]) box(c, t, s, t, m.midWood, [(x * (s - t)) / 2, s / 2, (z * (s - t)) / 2]);
  for (const y of [t / 2, s - t / 2]) {
    for (const z of [-1, 1]) box(c, s, t, t, m.midWood, [0, y, (z * (s - t)) / 2]);
    for (const x of [-1, 1]) box(c, t, t, s, m.midWood, [(x * (s - t)) / 2, y, 0]);
  }
  const span = s - 2 * t;
  box(c, t * 0.9, span * 1.38, 0.025, m.midWood, [0, s / 2, s / 2 - 0.005], [0, 0, Math.PI / 4]);
  box(c, 0.025, span * 1.38, t * 0.9, m.midWood, [s / 2 - 0.005, s / 2, 0], [-Math.PI / 4, 0, 0]);
  g.add(c);
  return c;
};

const sackAt = (g: THREE.Object3D, mat: THREE.Material, tie: THREE.Material, pos: V3, rot: V3, scale: V3) => {
  const s = new THREE.Group();
  s.position.set(...pos);
  s.rotation.set(...rot);
  const body = add(s, new THREE.SphereGeometry(0.32, 10, 8), mat, [0, 0, 0]);
  body.scale.set(...scale);
  cyl(s, 0.06, 0.1, 0.12, mat, [0, scale[1] * 0.32 + 0.02, 0], undefined, 7);
  cyl(s, 0.065, 0.065, 0.03, tie, [0, scale[1] * 0.32 + 0.05, 0], undefined, 7);
  add(s, new THREE.ConeGeometry(0.08, 0.1, 6), mat, [0, scale[1] * 0.32 + 0.12, 0], [Math.PI, 0, 0]);
  g.add(s);
};

const rails = (g: THREE.Object3D, m: PartMaterials, len: number, gauge: number, axis: "x" | "z", ties: number, y0 = 0, tieLen = gauge + 0.9) => {
  const along = (a: number, s: number): V3 => (axis === "x" ? [a, 0, s] : [s, 0, a]);
  for (let i = 0; i < ties; i++) {
    const a = -len / 2 + (len / ties) * (i + 0.5);
    const p = along(a, 0);
    box(g, axis === "x" ? 0.2 : tieLen, 0.1, axis === "x" ? tieLen : 0.2, m.tieWood, [p[0], y0 + 0.05, p[2]]);
  }
  for (const s of [-gauge / 2, gauge / 2]) {
    const p = along(0, s);
    const w = axis === "x" ? len : 0.07;
    const d = axis === "x" ? 0.07 : len;
    box(g, w, 0.06, d, m.steel, [p[0], y0 + 0.17, p[2]]);
    box(g, axis === "x" ? len : 0.13, 0.025, axis === "x" ? 0.13 : len, m.iron, [p[0], y0 + 0.11, p[2]]);
  }
};

const rockAt = (g: THREE.Object3D, mat: THREE.Material, pos: V3, s: number, seed: number) => {
  const r = rock(new THREE.Vector3(...pos), s, mat, seed);
  g.add(r);
  return r;
};

/** a flat blob outline in the xz plane, for ponds and mud */
const blobGeo = (rng: Rng, rx: number, rz: number, n = 18) => {
  const shape = new THREE.Shape();
  const radii = Array.from({ length: n }, () => range(rng, 0.82, 1.08));
  for (let i = 0; i <= n; i++) {
    const a = (i / n) * Math.PI * 2;
    const r = (radii[i % n] + radii[(i + 1) % n] + radii[(i + n - 1) % n]) / 3;
    const x = Math.cos(a) * rx * r;
    const y = Math.sin(a) * rz * r;
    if (i === 0) shape.moveTo(x, y);
    else shape.lineTo(x, y);
  }
  const geo = new THREE.ShapeGeometry(shape, 2);
  geo.rotateX(-Math.PI / 2);
  const uv = geo.getAttribute("uv") as THREE.BufferAttribute;
  for (let i = 0; i < uv.count; i++) uv.setXY(i, uv.getX(i) / 3, uv.getY(i) / 3);
  return geo;
};

/** a thin double-sided flat panel cut from a 2D outline (clothes, flags, flaps) */
const shapeGeo = (pts: [number, number][]) => {
  const s = new THREE.Shape();
  pts.forEach(([x, y], i) => (i === 0 ? s.moveTo(x, y) : s.lineTo(x, y)));
  const geo = new THREE.ShapeGeometry(s);
  const bb = new THREE.Box3().setFromBufferAttribute(geo.getAttribute("position") as THREE.BufferAttribute);
  const uv = geo.getAttribute("uv") as THREE.BufferAttribute;
  const p = geo.getAttribute("position") as THREE.BufferAttribute;
  for (let i = 0; i < uv.count; i++) {
    uv.setXY(i, (p.getX(i) - bb.min.x) / Math.max(0.01, bb.max.x - bb.min.x), (p.getY(i) - bb.min.y) / Math.max(0.01, bb.max.y - bb.min.y));
  }
  return geo;
};

/** a hull: the bottom half of a sphere, stretched and pinched to a point */
const hullGeo = (len: number, depth: number, beam: number, bowPinch: number, sternPinch: number, sheer: number, inner = 1) => {
  const geo = new THREE.SphereGeometry(1, 24, 10, 0, Math.PI * 2, Math.PI / 2, Math.PI / 2);
  const p = geo.getAttribute("position") as THREE.BufferAttribute;
  for (let i = 0; i < p.count; i++) {
    const x = p.getX(i);
    const t = Math.abs(x);
    const pinch = x > 0 ? bowPinch : sternPinch;
    const z = p.getZ(i) * beam * inner * (1 - pinch * t * t);
    const y = p.getY(i) * depth * inner + sheer * t ** 4;
    p.setXYZ(i, x * (len / 2) * inner, y, z);
  }
  geo.computeVertexNormals();
  return geo;
};


/** a fire: a glowing ember bed and a few leaning flame tongues (no ink) */
const fire = (g: THREE.Object3D, ctx: PartCtx, rng: Rng, r: number) => {
  const ember = glowMat(ctx, col(14, 0.45, 0.28), new THREE.Color(1.0, 0.42, 0.12), 2.6);
  decal(cyl(g, r, r * 1.1, 0.06, ember, [0, 0.09, 0], undefined, 9));
  const flame = glowMat(ctx, col(30, 0.62, 0.58), new THREE.Color(1.0, 0.5, 0.14), 1.3);
  const core = glowMat(ctx, col(44, 0.7, 0.72), new THREE.Color(1.0, 0.72, 0.34), 1.1);
  for (let i = 0; i < 5; i++) {
    const a = (i / 5) * Math.PI * 2 + range(rng, -0.3, 0.3);
    const h = range(rng, 0.28, 0.5) * (r / 0.28);
    const d = range(rng, 0.03, 0.1) * (r / 0.28);
    decal(add(g, new THREE.ConeGeometry(range(rng, 0.06, 0.09) * (r / 0.28), h, 5), i === 0 ? core : flame, [Math.cos(a) * d, 0.1 + h / 2, Math.sin(a) * d], [range(rng, -0.25, 0.25), rng() * 3, range(rng, -0.25, 0.25)]));
  }
};

// ------------------------------------------------- rolling stock and people

/** railTrack facts every vehicle needs: the rail tops and where the rails run */
const RAIL_TOP = 0.26;
const RAIL_Z = 1.435 / 2;

/** a locomotive wheel in the xy plane: iron tread ring with an inside flange,
 *  red spoked centre, optional crank pin on the outside face. `out` is the
 *  side of the vehicle it is on (+-1), so the flange goes inside */
const locoWheel = (g: THREE.Object3D, m: PartMaterials, r: number, pos: V3, out: number, spokes: number, crank?: number) => {
  const w = new THREE.Group();
  w.position.set(...pos);
  add(w, new THREE.CylinderGeometry(r, r, 0.12, 24, 1, true), m.iron, [0, 0, 0], [Math.PI / 2, 0, 0]);
  add(w, new THREE.TorusGeometry(r + 0.02, 0.035, 6, 24), m.iron, [0, 0, -out * 0.07]);
  add(w, new THREE.TorusGeometry(r - 0.08, 0.05, 6, 24), m.engineRed, [0, 0, 0]);
  cyl(w, r * 0.22, r * 0.22, 0.16, m.engineRed, [0, 0, 0], [Math.PI / 2, 0, 0], 12);
  for (let i = 0; i < spokes; i++) {
    const a = (i / spokes) * Math.PI * 2;
    rod(w, [Math.cos(a) * r * 0.18, Math.sin(a) * r * 0.18, 0], [Math.cos(a) * (r - 0.1), Math.sin(a) * (r - 0.1), 0], Math.max(0.028, r * 0.05), m.engineRed, 5);
  }
  if (crank !== undefined) cyl(w, 0.06, 0.06, 0.18, m.steel, [Math.cos(crank) * r * 0.55, Math.sin(crank) * r * 0.55, out * 0.1], [Math.PI / 2, 0, 0], 8);
  g.add(w);
  return w;
};

/** a two-axle truck (bogie) centred at x, wheels on the rails */
const truckAt = (g: THREE.Object3D, m: PartMaterials, x: number, r = 0.4, spread = 0.9) => {
  const y = RAIL_TOP + r;
  for (const dx of [-spread / 2, spread / 2]) {
    for (const s of [-1, 1]) locoWheel(g, m, r, [x + dx, y, s * RAIL_Z], s, 8);
    rod(g, [x + dx, y, -RAIL_Z], [x + dx, y, RAIL_Z], 0.05, m.iron, 8);
  }
  box(g, spread + 0.6, 0.16, 1.2, m.engineBlack, [x, y + 0.2, 0]);
  for (const s of [-1, 1]) box(g, spread + 0.7, 0.16, 0.08, m.darkWood, [x, y, s * 0.87]);
};

/** a flat two-sided figure h metres tall standing at pos, face toward +z;
 *  alpha-tested in colour, shadow and ink passes like the main characters */
const figureAt = (g: THREE.Object3D, seed: number, h: number, pos: V3, yaw = 0) => {
  const tex = figureTex(seed);
  const mat = new THREE.MeshLambertMaterial({
    map: tex,
    alphaTest: 0.5,
    side: THREE.DoubleSide,
    emissiveMap: tex,
    emissive: new THREE.Color(0.22, 0.22, 0.22),
  });
  const geo = new THREE.PlaneGeometry(h / 2, h);
  geo.translate(0, h / 2, 0);
  const o = new THREE.Mesh(geo, mat);
  o.position.set(...pos);
  o.rotation.y = yaw;
  o.castShadow = true;
  o.receiveShadow = false;
  o.customDepthMaterial = new THREE.MeshDepthMaterial({ depthPacking: THREE.RGBADepthPacking, map: tex, alphaTest: 0.5, side: THREE.DoubleSide });
  o.userData.normalMaterial = cutoutNormalMaterial(tex);
  g.add(o);
  return o;
};

// ------------------------------------------------------------------- props

/** Each part at the origin, facing +z, standing on y = 0. Kinds written in the
 *  part grammar (partSpecs/) are compiled from their spec. */
export const makePart = (kind: PropName, seed: number, m: PartMaterials, ctx: PartCtx, custom?: Record<string, PartSpec>): THREE.Group => {
  const spec = (PART_SPECS as Partial<Record<string, PartSpec>>)[kind] ?? partSpecOf(kind, custom);
  if (spec) return compilePart(spec, seed, m, ctx);
  const code = CODE_PARTS[kind];
  if (code) {
    const g = code.build(m, ctx, seed);
    g.userData.codePart = kind;
    if (code.smoke?.length) {
      g.userData.smoke = code.smoke.map((s) => new THREE.Vector3(...s.at));
      g.userData.smokeKinds = code.smoke.map((s) => s.kind);
    }
    return g;
  }
  if (!(kind in PART_DIMS)) throw new Error(`unknown part "${kind}"`);
  return makeHandPart(kind as PartKind, seed, m, ctx);
};
// the measuring side (partsSpec.ts partDims, the gate, headless QA) builds code parts through here. Registered at
// load for the browser; Node entries call ensureCodeBuilder() explicitly, since the package's sideEffects list lets
// the bundler drop a bare `import "./parts"`.
let measureMats: PartMaterials | null = null;
export const ensureCodeBuilder = () =>
  registerCodeBuilder((name, seed) => {
    measureMats ??= makePartMaterials();
    return makePart(name, seed, measureMats, { glows: [], lamps: [], smokeLocal: [] });
  });
ensureCodeBuilder();

/** The hand-built parts. Still holds the originals of the PART_SPECS kinds,
 *  for the grammar comparison gallery, until they are deleted. */
export const makeHandPart = (kind: PartKind, seed: number, m: PartMaterials, ctx: PartCtx): THREE.Group => {
  const g = new THREE.Group();
  const rng = makeRng(seed * 7919 + kind.length * 131);
  const smoke: THREE.Vector3[] = [];
  switch (kind) {
    // ---------------------------------------------------- the original twelve
    case "crate":
      crateAt(g, m, 0.8, [0, 0, 0]);
      break;
    case "barrel":
      barrelAt(g, m, [0, 0, 0]);
      break;
    case "cart": {
      const x0 = -0.2;
      box(g, 1.6, 0.1, 1.1, m.midWood, [x0, 0.72, 0]);
      for (const z of [-0.53, 0.53]) box(g, 1.6, 0.3, 0.05, m.midWood, [x0, 0.92, z]);
      for (const x of [x0 - 0.78, x0 + 0.78]) box(g, 0.05, 0.3, 1.1, m.midWood, [x, 0.92, 0]);
      for (const x of [-0.5, 0.5]) {
        rod(g, [x + x0, 0.38, -0.66], [x + x0, 0.38, 0.66], 0.03, m.iron);
        for (const z of [-0.62, 0.62]) wheel(g, m, 0.38, [x + x0, 0.38, z], 8);
      }
      for (const z of [-0.3, 0.3]) rod(g, [0.55, 0.72, z], [1.1, 0.55, z * 0.7], 0.035, m.lightWood);
      rod(g, [1.08, 0.56, -0.22], [1.08, 0.56, 0.22], 0.03, m.lightWood);
      break;
    }
    case "trough":
      for (const x of [-0.8, 0.8]) box(g, 0.08, 0.36, 0.72, m.darkWood, [x, 0.18, 0]);
      box(g, 1.72, 0.32, 0.56, m.midWood, [0, 0.3, 0]);
      for (const z of [-0.27, 0.27]) box(g, 1.8, 0.06, 0.06, m.darkWood, [0, 0.47, z]);
      for (const x of [-0.87, 0.87]) box(g, 0.06, 0.06, 0.6, m.darkWood, [x, 0.47, 0]);
      add(g, new THREE.PlaneGeometry(1.66, 0.48), m.waterTop, [0, 0.455, 0], [-Math.PI / 2, 0, 0], false);
      break;
    case "lamp": {
      cyl(g, 0.11, 0.14, 0.28, m.iron, [0, 0.14, 0], undefined, 8);
      cyl(g, 0.045, 0.06, 2.3, m.iron, [0, 1.42, 0], undefined, 8);
      cyl(g, 0.08, 0.06, 0.06, m.iron, [0, 2.55, 0], undefined, 8);
      const head = glowMat(ctx, 0xf2dcae, new THREE.Color(1.0, 0.72, 0.32), 2.2);
      box(g, 0.24, 0.32, 0.24, head, [0, 2.74, 0]).castShadow = false;
      for (const x of [-0.13, 0.13]) for (const z of [-0.13, 0.13]) box(g, 0.03, 0.36, 0.03, m.iron, [x, 2.74, z]);
      box(g, 0.3, 0.04, 0.3, m.iron, [0, 2.58, 0]);
      add(g, new THREE.ConeGeometry(0.22, 0.18, 4), m.iron, [0, 3.0, 0], [0, Math.PI / 4, 0]);
      add(g, new THREE.SphereGeometry(0.04, 6, 4), m.iron, [0, 3.1, 0]);
      lampLight(g, ctx, 0xffb060, [0, 2.7, 0], 9, false);
      break;
    }
    case "sacks":
      sackAt(g, m.burlap, m.twine, [-0.24, 0.2, -0.14], [0.1, range(rng, 0, 3), -0.08], [1, 0.62, 0.85]);
      sackAt(g, m.burlap, m.twine, [0.24, 0.2, -0.1], [-0.06, range(rng, 0, 3), 0.1], [1, 0.6, 0.85]);
      sackAt(g, m.burlap, m.twine, [0, 0.19, 0.22], [0, range(rng, 0, 3), 0], [1.05, 0.58, 0.8]);
      break;
    case "hitchRail":
      for (const x of [-1.15, 1.15]) {
        cyl(g, 0.07, 0.08, 1.06, m.darkWood, [x, 0.53, 0], undefined, 8);
        cyl(g, 0.09, 0.07, 0.06, m.darkWood, [x, 1.08, 0], undefined, 8);
      }
      box(g, 2.5, 0.09, 0.09, m.midWood, [0, 0.98, 0]);
      for (const x of [-0.5, 0.4]) add(g, new THREE.TorusGeometry(0.07, 0.012, 4, 12), m.iron, [x, 0.88, 0.05]);
      break;
    case "woodpile": {
      for (const x of [-0.76, 0.76]) cyl(g, 0.04, 0.05, 0.95, m.darkWood, [x, 0.47, 0], undefined, 6);
      const piece = new THREE.CylinderGeometry(0.085, 0.085, 0.9, 5);
      for (let layer = 0; layer < 5; layer++) {
        const n = layer < 4 ? 9 : 6;
        for (let i = 0; i < n; i++) {
          const x = (i - (n - 1) / 2) * 0.165 + range(rng, -0.01, 0.01);
          const o = add(g, piece, [m.bark, m.rings, m.rings], [x, 0.085 + layer * 0.155, range(rng, -0.04, 0.04)], [Math.PI / 2, range(rng, 0, 6), 0]);
          o.rotation.order = "XZY";
        }
      }
      break;
    }
    case "stump":
      add(g, new THREE.CylinderGeometry(0.32, 0.38, 0.45, 12), [m.bark, m.rings, m.bark], [0, 0.225, 0]);
      for (let i = 0; i < 5; i++) {
        const a = (i / 5) * Math.PI * 2 + range(rng, -0.3, 0.3);
        rod(g, [Math.cos(a) * 0.28, 0.16, Math.sin(a) * 0.28], [Math.cos(a) * 0.46, 0.0, Math.sin(a) * 0.46], 0.03, m.bark, 5, 0.08);
      }
      break;
    case "bench":
      box(g, 1.6, 0.06, 0.4, m.lightWood, [0, 0.45, 0.02]);
      for (const x of [-0.68, 0.68]) {
        for (const z of [-0.14, 0.16]) box(g, 0.06, 0.42, 0.06, m.darkWood, [x, 0.21, z]);
        box(g, 0.06, 0.06, 0.4, m.darkWood, [x, 0.66, 0.02]);
        box(g, 0.06, 0.24, 0.06, m.darkWood, [x, 0.57, 0.16]);
        box(g, 0.06, 0.5, 0.06, m.darkWood, [x, 0.7, -0.17], [-0.12, 0, 0]);
      }
      for (const y of [0.66, 0.84]) box(g, 1.5, 0.1, 0.03, m.lightWood, [0, y, -0.19 - (y - 0.6) * 0.12], [-0.12, 0, 0]);
      break;
    case "haybale": {
      const mats = [m.strawEnd, m.strawEnd, m.straw, m.straw, m.straw, m.straw];
      box(g, 1.1, 0.55, 0.6, mats, [0, 0.275, 0], undefined, 0.8);
      for (const x of [-0.28, 0.28]) box(g, 0.035, 0.565, 0.615, m.twine, [x, 0.275, 0]);
      break;
    }
    case "firepit": {
      for (let i = 0; i < 9; i++) {
        const a = (i / 9) * Math.PI * 2;
        rockAt(g, m.stoneRough, [Math.cos(a) * 0.56, 0, Math.sin(a) * 0.56], range(rng, 0.14, 0.19), seed + i);
      }
      for (const yaw of [0.5, -0.6, 1.6]) log(g, m, 0.065, 0.85, [0, 0.1, 0], "x", 7, 0).rotation.y = yaw;
      fire(g, ctx, rng, 0.3);
      lampLight(g, ctx, 0xff8a3a, [0, 0.8, 0], 16, true, 14);
      smoke.push(new THREE.Vector3(0, 0.75, 0));
      break;
    }

    // ------------------------------------------------------------ railway
    case "railTrack":
      box(g, 4.0, 0.08, 2.7, m.gravel, [0, 0.04, 0], undefined, 0.8);
      rails(g, m, 4.0, 1.435, "x", 7, 0.06, 2.4);
      break;
    case "bufferStop":
      rails(g, m, 1.3, 1.435, "z", 2, 0, 2.0);
      for (const x of [-0.72, 0.72]) {
        box(g, 0.24, 1.05, 0.24, m.darkWood, [x, 0.6, -0.05]);
        rod(g, [x, 1.0, -0.12], [x, 0.12, -0.62], 0.07, m.darkWood, 5);
        cyl(g, 0.12, 0.14, 0.3, m.iron, [x, 0.95, 0.3], [Math.PI / 2, 0, 0], 10);
        cyl(g, 0.2, 0.2, 0.05, m.iron, [x, 0.95, 0.46], [Math.PI / 2, 0, 0], 14);
      }
      box(g, 2.0, 0.34, 0.3, m.redPaint, [0, 0.95, 0.03]);
      box(g, 0.5, 0.06, 0.31, m.creamPaint, [0, 0.95, 0.04]);
      break;
    case "handcar": {
      for (const x of [-0.55, 0.55]) {
        rod(g, [x, 0.25, -0.62], [x, 0.25, 0.62], 0.025, m.iron);
        for (const z of [-0.62, 0.62]) wheel(g, m, 0.24, [x, 0.25, z], 6, m.iron);
      }
      box(g, 1.6, 0.1, 1.1, m.midWood, [0, 0.5, 0]);
      for (const z of [-0.5, 0.5]) box(g, 1.6, 0.08, 0.08, m.darkWood, [0, 0.42, z]);
      rod(g, [-0.25, 0.55, 0], [0, 1.2, 0], 0.04, m.iron);
      rod(g, [0.25, 0.55, 0], [0, 1.2, 0], 0.04, m.iron);
      const beam = new THREE.Group();
      beam.position.set(0, 1.25, 0);
      beam.rotation.z = 0.16;
      box(beam, 1.6, 0.07, 0.07, m.darkWood, [0, 0, 0]);
      for (const x of [-0.78, 0.78]) rod(beam, [x, 0, -0.45], [x, 0, 0.45], 0.03, m.lightWood);
      g.add(beam);
      break;
    }
    case "railSignal": {
      cyl(g, 0.09, 0.12, 5.0, m.creamPaint, [0, 2.5, 0], undefined, 8);
      add(g, new THREE.ConeGeometry(0.12, 0.25, 8), m.iron, [0, 5.12, 0]);
      for (const x of [0.18, 0.4]) rod(g, [x, 0, 0.05], [x, 4.2, 0.05], 0.018, m.iron, 4);
      for (let y = 0.3; y < 4.2; y += 0.32) rod(g, [0.18, y, 0.05], [0.4, y, 0.05], 0.012, m.iron, 4);
      const arm = new THREE.Group();
      arm.position.set(0.1, 4.55, 0.13);
      arm.rotation.z = 0.5;
      box(arm, 1.1, 0.18, 0.04, m.redPaint, [0.55, 0, 0]);
      box(arm, 0.08, 0.19, 0.045, m.creamPaint, [0.85, 0, 0]);
      g.add(arm);
      cyl(g, 0.07, 0.07, 0.06, m.iron, [0.1, 4.55, 0.13], [Math.PI / 2, 0, 0]);
      box(g, 0.24, 0.26, 0.2, m.iron, [-0.22, 4.3, 0.06]);
      const glass = glowMat(ctx, 0xb04040, new THREE.Color(1.0, 0.18, 0.12), 2.6);
      cyl(g, 0.07, 0.07, 0.04, glass, [-0.22, 4.3, 0.17], [Math.PI / 2, 0, 0], 12).castShadow = false;
      lampLight(g, ctx, 0xff4030, [-0.22, 4.3, 0.35], 3, false, 6);
      break;
    }
    case "waterTower": {
      const legs: V3[] = [[1.3, 0, 1.3], [-1.3, 0, 1.3], [-1.3, 0, -1.3], [1.3, 0, -1.3]];
      const tops = legs.map(([x, , z]) => [x * 0.8, 4.0, z * 0.8] as V3);
      legs.forEach((p, i) => rod(g, p, tops[i], 0.1, m.darkWood, 6));
      for (let i = 0; i < 4; i++) {
        const a = legs[i];
        const b = legs[(i + 1) % 4];
        const at = (p: V3, q: V3, t: number): V3 => [p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t, p[2] + (q[2] - p[2]) * t];
        const la = (t: number) => at(a, tops[i], t);
        const lb = (t: number) => at(b, tops[(i + 1) % 4], t);
        rod(g, la(0.15), lb(0.55), 0.045, m.darkWood, 5);
        rod(g, lb(0.15), la(0.55), 0.045, m.darkWood, 5);
        rod(g, la(0.6), lb(0.6), 0.05, m.darkWood, 5);
      }
      cyl(g, 1.7, 1.7, 0.14, m.darkWood, [0, 4.07, 0], undefined, 16);
      const tank = scaleUv(new THREE.CylinderGeometry(1.5, 1.5, 2.2, 18, 1, true), 3, 1.1);
      add(g, tank, m.barrel, [0, 5.24, 0]);
      for (const y of [4.45, 5.24, 6.05]) cyl(g, 1.52, 1.52, 0.06, m.iron, [0, y, 0], undefined, 18);
      add(g, new THREE.ConeGeometry(1.72, 0.95, 18), m.greyWood, [0, 6.8, 0]);
      add(g, new THREE.SphereGeometry(0.09, 6, 4), m.iron, [0, 7.3, 0]);
      rod(g, [0, 4.7, 1.5], [0, 5.9, 2.05], 0.11, m.iron, 8);
      cyl(g, 0.15, 0.15, 0.12, m.iron, [0, 4.7, 1.45], [Math.PI / 2, 0, 0], 8);
      rod(g, [0, 5.9, 2.05], [0, 3.6, 2.05], 0.01, m.rope, 4);
      for (const x of [-0.22, 0.22]) rod(g, [x, 0, 1.35], [x, 4.05, 1.12], 0.025, m.lightWood, 4);
      for (let y = 0.35; y < 4; y += 0.38) rod(g, [-0.22, y, 1.35 - y * 0.057], [0.22, y, 1.35 - y * 0.057], 0.015, m.lightWood, 4);
      break;
    }
    case "stationClock": {
      cyl(g, 0.14, 0.17, 0.2, m.iron, [0, 0.1, 0], undefined, 10);
      cyl(g, 0.055, 0.07, 2.6, m.iron, [0, 1.4, 0], undefined, 8);
      for (const s of [-1, 1]) rod(g, [0, 2.55, 0], [s * 0.2, 2.75, 0], 0.025, m.iron, 4);
      cyl(g, 0.3, 0.3, 0.14, m.greenPaint, [0, 2.98, 0], [Math.PI / 2, 0, 0], 22);
      for (const s of [-1, 1]) {
        const face = add(g, new THREE.CircleGeometry(0.255, 22), m.clock, [0, 2.98, s * 0.072], s < 0 ? [0, Math.PI, 0] : undefined, false);
        face.receiveShadow = true;
      }
      add(g, new THREE.SphereGeometry(0.06, 6, 4), m.brass, [0, 3.3, 0]);
      break;
    }
    case "luggage": {
      const trunk = new THREE.Group();
      trunk.position.set(-0.15, 0, -0.05);
      box(trunk, 0.9, 0.5, 0.56, m.greenPaint, [0, 0.25, 0]);
      for (const x of [-0.25, 0.25]) box(trunk, 0.05, 0.52, 0.58, m.leather, [x, 0.25, 0]);
      for (const x of [-0.44, 0.44]) for (const y of [0.03, 0.47]) box(trunk, 0.04, 0.06, 0.58, m.brass, [x, y, 0]);
      g.add(trunk);
      box(g, 0.66, 0.16, 0.42, m.leatherLight, [-0.12, 0.58, -0.04], [0, 0.12, 0]);
      add(g, new THREE.TorusGeometry(0.06, 0.012, 4, 10, Math.PI), m.leather, [-0.12, 0.66, 0.18], [0, 0.12, 0]);
      box(g, 0.16, 0.48, 0.6, m.leather, [0.52, 0.24, 0.05], [0, -0.1, 0.04]);
      cyl(g, 0.16, 0.16, 0.2, m.creamPaint, [-0.08, 0.76, -0.05], undefined, 14);
      break;
    }
    case "coalBin": {
      box(g, 1.4, 0.8, 0.06, m.greyWood, [0, 0.4, -0.47]);
      for (const x of [-0.67, 0.67]) box(g, 0.06, 0.8, 1.0, m.greyWood, [x, 0.4, 0]);
      box(g, 1.4, 0.3, 0.06, m.greyWood, [0, 0.15, 0.47]);
      const heap = add(g, new THREE.DodecahedronGeometry(0.62, 0), m.coal, [0, 0.25, -0.05]);
      heap.scale.set(1.0, 0.75, 0.72);
      for (let i = 0; i < 6; i++) rockAt(g, m.coal, [range(rng, -0.5, 0.5), 0.0, range(rng, 0.2, 0.55)], range(rng, 0.06, 0.1), seed + i);
      rod(g, [0.3, 0.6, -0.1], [0.45, 1.2, 0.15], 0.02, m.lightWood, 5);
      box(g, 0.2, 0.26, 0.02, m.iron, [0.26, 0.5, -0.18], [0.4, 0.2, 0]);
      break;
    }

    // ----------------------------------------------------- post and telegraph
    case "mailbox": {
      box(g, 0.1, 1.05, 0.1, m.greyWood, [0, 0.52, 0]);
      box(g, 0.2, 0.04, 0.42, m.greyWood, [0, 1.06, 0.02]);
      box(g, 0.2, 0.12, 0.46, m.bluePaint, [0, 1.14, 0.02]);
      add(g, new THREE.CylinderGeometry(0.1, 0.1, 0.46, 12, 1, false, 0, Math.PI), m.steel, [0, 1.2, 0.02], [Math.PI / 2, Math.PI / 2, 0]);
      rod(g, [0.11, 1.12, -0.12], [0.11, 1.34, -0.12], 0.012, m.iron, 4);
      box(g, 0.012, 0.08, 0.14, m.redPaint, [0.115, 1.31, -0.06]);
      break;
    }
    case "mailSacks": {
      const sacks: [V3, V3][] = [
        [[-0.3, 0.2, -0.2], [0, 0.2, Math.PI / 2]],
        [[0.3, 0.2, -0.15], [0, -0.3, Math.PI / 2]],
        [[0.02, 0.2, 0.3], [0, 1.4, Math.PI / 2]],
        [[0.0, 0.52, -0.12], [0, 0.6, Math.PI / 2 - 0.1]],
      ];
      for (const [p, r] of sacks) {
        const s = new THREE.Group();
        s.position.set(...p);
        s.rotation.set(...r);
        add(s, new THREE.CapsuleGeometry(0.19, 0.4, 4, 10), m.mailCanvas, [0, 0, 0]).scale.set(1, 1, 0.8);
        cyl(s, 0.05, 0.08, 0.14, m.mailCanvas, [0, 0.42, 0], undefined, 7);
        cyl(s, 0.055, 0.055, 0.03, m.leather, [0, 0.42, 0], undefined, 7);
        g.add(s);
      }
      break;
    }
    case "telegraphBox": {
      box(g, 0.12, 1.6, 0.12, m.darkWood, [0, 0.8, -0.12]);
      box(g, 0.5, 0.46, 0.32, m.greenPaint, [0, 1.1, 0.06]);
      box(g, 0.56, 0.05, 0.4, m.greenPaint, [0, 1.36, 0.06], [-0.18, 0, 0]);
      box(g, 0.4, 0.34, 0.02, m.midWood, [0, 1.08, 0.225]);
      box(g, 0.1, 0.05, 0.02, m.brass, [0, 1.18, 0.24]);
      cyl(g, 0.02, 0.02, 0.04, m.brass, [0.14, 1.06, 0.24], [Math.PI / 2, 0, 0], 6);
      cyl(g, 0.04, 0.05, 0.1, m.steel, [0, 1.66, -0.12], undefined, 8);
      rod(g, [0.18, 1.3, -0.04], [0.04, 1.68, -0.12], 0.01, m.iron, 4);
      break;
    }
    case "noticeBoard": {
      for (const x of [-0.82, 0.82]) box(g, 0.12, 2.3, 0.12, m.darkWood, [x, 1.15, 0]);
      box(g, 1.6, 1.1, 0.06, m.midWood, [0, 1.4, 0.03]);
      box(g, 1.7, 0.08, 0.1, m.darkWood, [0, 0.82, 0.05]);
      for (const s of [-1, 1]) box(g, 1.95, 0.05, 0.3, m.greyWood, [0, 2.22 + 0.03, s * 0.13], [s * 0.5, 0, 0]);
      const spots: [number, number, number, number][] = [[-0.5, 1.52, 0.42, 0.06], [0.0, 1.38, 0.4, -0.04], [0.5, 1.56, 0.38, 0.08], [-0.28, 1.14, 0.3, -0.1], [0.36, 1.14, 0.32, 0.03]];
      spots.forEach(([x, y, w, rz], i) => {
        add(g, new THREE.PlaneGeometry(w, w * 1.33), m.posters[(i + seed) % m.posters.length], [x, y, 0.065 + i * 0.002], [0, 0, rz], false);
      });
      break;
    }
    case "signpost": {
      cyl(g, 0.07, 0.08, 2.45, m.greyWood, [0, 1.22, 0], undefined, 8);
      add(g, new THREE.ConeGeometry(0.09, 0.14, 8), m.greyWood, [0, 2.52, 0]);
      const arrow = (len: number) => {
        const h = 0.22;
        const geo = new THREE.ExtrudeGeometry(
          (() => {
            const s = new THREE.Shape();
            s.moveTo(0, -h / 2);
            s.lineTo(len - 0.16, -h / 2);
            s.lineTo(len, 0);
            s.lineTo(len - 0.16, h / 2);
            s.lineTo(0, h / 2);
            s.closePath();
            return s;
          })(),
          { depth: 0.04, bevelEnabled: false },
        );
        geo.translate(0, 0, -0.02);
        const uv = geo.getAttribute("uv") as THREE.BufferAttribute;
        for (let i = 0; i < uv.count; i++) uv.setXY(i, uv.getX(i) / len, (uv.getY(i) + h / 2) / h);
        return geo;
      };
      const boards: [number, number, number, boolean][] = [[2.25, 0.35, 0.95, false], [1.95, -2.4, 0.85, true], [1.65, 1.2, 0.9, false]];
      for (const [y, yaw, len, darkB] of boards) {
        const a = add(g, arrow(len), darkB ? m.arrowDark : m.arrow, [0, y, 0], [0, yaw, 0]);
        a.position.x = Math.cos(yaw) * 0.06;
        a.position.z = -Math.sin(yaw) * 0.06;
      }
      break;
    }
    case "bellPost": {
      for (const x of [-0.58, 0.58]) {
        box(g, 0.14, 2.4, 0.14, m.darkWood, [x, 1.2, 0]);
        rod(g, [x, 0.0, 0.35], [x, 0.9, 0.0], 0.05, m.darkWood, 5);
        rod(g, [x, 0.0, -0.35], [x, 0.9, 0.0], 0.05, m.darkWood, 5);
      }
      box(g, 1.4, 0.16, 0.16, m.darkWood, [0, 2.32, 0]);
      for (const s of [-1, 1]) box(g, 1.55, 0.05, 0.48, m.greyWood, [0, 2.6, s * 0.2], [s * 0.6, 0, 0]);
      add(g, lathe([[0.02, 0], [0.24, 0.02], [0.22, 0.08], [0.16, 0.2], [0.14, 0.34], [0.06, 0.4], [0, 0.41]], 16), m.brass, [0, 1.72, 0]);
      box(g, 0.1, 0.12, 0.1, m.iron, [0, 2.18, 0]);
      add(g, new THREE.SphereGeometry(0.05, 8, 6), m.iron, [0, 1.7, 0]);
      rod(g, [0, 1.72, 0], [0.02, 0.9, 0.05], 0.012, m.rope, 4);
      break;
    }
    case "flagpole": {
      box(g, 0.8, 0.4, 0.8, m.stone, [0, 0.2, 0], undefined, 1.2);
      box(g, 0.6, 0.12, 0.6, m.stone, [0, 0.46, 0], undefined, 1.2);
      cyl(g, 0.04, 0.07, 5.85, m.creamPaint, [0, 0.52 + 2.92, 0], undefined, 8);
      add(g, new THREE.SphereGeometry(0.08, 8, 6), m.brass, [0, 6.42, 0]);
      const flag = new THREE.PlaneGeometry(1.5, 0.9, 14, 4);
      flag.translate(0.75, 0, 0);
      const fp = flag.getAttribute("position") as THREE.BufferAttribute;
      for (let i = 0; i < fp.count; i++) {
        const x = fp.getX(i);
        fp.setZ(i, Math.sin(x * 4.2 + 0.4) * 0.09 * (x / 1.5) + Math.sin(x * 2) * 0.03);
        fp.setY(i, fp.getY(i) - x * x * 0.04);
      }
      flag.computeVertexNormals();
      add(g, flag, m.flag, [0.05, 5.82, 0]);
      const canton = new THREE.PlaneGeometry(0.6, 0.45, 6, 2);
      canton.translate(0.3, 0.225, 0);
      const cp = canton.getAttribute("position") as THREE.BufferAttribute;
      for (let i = 0; i < cp.count; i++) {
        const x = cp.getX(i);
        cp.setZ(i, Math.sin(x * 4.2 + 0.4) * 0.09 * (x / 1.5) + Math.sin(x * 2) * 0.03 + 0.006);
        cp.setY(i, cp.getY(i) - x * x * 0.04);
      }
      canton.computeVertexNormals();
      decal(add(g, canton, m.flagCanton, [0.05, 5.82, 0]));
      break;
    }

    // ------------------------------------------------------------ town and yard
    case "cratePile":
      crateAt(g, m, 0.8, [-0.45, 0, -0.05], range(rng, -0.08, 0.08));
      crateAt(g, m, 0.7, [0.46, 0, 0.08], 0.22);
      crateAt(g, m, 0.6, [-0.3, 0.8, -0.05], -0.32);
      break;
    case "barrelStack":
      for (const x of [-0.62, 0, 0.62]) barrelAt(g, m, [x, 0.3, -0.44], [Math.PI / 2, range(rng, 0, 6), 0]);
      for (const x of [-0.31, 0.31]) barrelAt(g, m, [x, 0.84, -0.44], [Math.PI / 2, range(rng, 0, 6), 0]);
      for (const x of [-0.92, 0.92]) box(g, 0.1, 0.12, 0.9, m.darkWood, [x, 0.06, 0]);
      break;
    case "rainBarrel": {
      for (const x of [-0.18, 0.18]) box(g, 0.14, 0.16, 0.6, m.stoneDark, [x, 0.08, 0]);
      barrelAt(g, m, [0, 0.16, 0], [0, 0, 0], true, 1.05);
      add(g, new THREE.CircleGeometry(0.285, 16), m.waterTop, [0, 0.16 + 0.82, 0], [-Math.PI / 2, 0, 0], false);
      break;
    }
    case "bucket": {
      add(g, scaleUv(lathe([[0.13, 0], [0.15, 0.1], [0.17, 0.3]], 14), 1, 0.4), m.barrelDS, [0, 0, 0]);
      add(g, new THREE.CircleGeometry(0.13, 14), m.darkWood, [0, 0.005, 0], [-Math.PI / 2, 0, 0]);
      for (const y of [0.06, 0.25]) cyl(g, 0.14 + y * 0.12 + 0.01, 0.14 + y * 0.12 + 0.01, 0.025, m.iron, [0, y, 0], undefined, 14);
      add(g, new THREE.TorusGeometry(0.17, 0.008, 4, 14, Math.PI), m.iron, [0, 0.29, 0], [0, 0, 0.15]);
      add(g, new THREE.CircleGeometry(0.16, 14), m.waterTop, [0, 0.24, 0], [-Math.PI / 2, 0, 0], false);
      break;
    }
    case "ladder": {
      for (const x of [-0.28, 0.28]) {
        rod(g, [x, 0, 0.42], [x * 0.8, 1.74, 0.03], 0.03, m.lightWood, 5);
        rod(g, [x, 0, -0.45], [x * 0.8, 1.74, -0.03], 0.03, m.lightWood, 5);
      }
      for (let i = 1; i <= 5; i++) {
        const t = i / 6;
        const x = 0.28 * (1 - 0.2 * t);
        box(g, 2 * x, 0.04, 0.1, m.lightWood, [0, t * 1.74, 0.42 * (1 - t) + 0.03 * t], [0.24, 0, 0]);
      }
      box(g, 0.5, 0.05, 0.22, m.midWood, [0, 1.77, 0]);
      rod(g, [-0.2, 0.7, 0.26], [-0.2, 0.7, -0.27], 0.01, m.rope, 4);
      break;
    }
    case "lanternPost": {
      box(g, 0.11, 2.3, 0.11, m.darkWood, [-0.32, 1.15, 0]);
      const hook = tubeThrough([new THREE.Vector3(-0.32, 2.2, 0), new THREE.Vector3(-0.2, 2.36, 0), new THREE.Vector3(0.05, 2.38, 0), new THREE.Vector3(0.22, 2.24, 0)], 0.025, 16);
      add(g, hook, m.iron, [0, 0, 0]);
      rod(g, [0.22, 2.24, 0], [0.22, 2.08, 0], 0.008, m.iron, 4);
      const glass = glowMat(ctx, 0xf2d8a8, new THREE.Color(1.0, 0.7, 0.3), 2.2);
      box(g, 0.16, 0.2, 0.16, glass, [0.22, 1.92, 0]).castShadow = false;
      for (const dx of [-0.08, 0.08]) for (const dz of [-0.08, 0.08]) box(g, 0.02, 0.22, 0.02, m.iron, [0.22 + dx, 1.92, dz]);
      add(g, new THREE.ConeGeometry(0.13, 0.12, 4), m.iron, [0.22, 2.08, 0], [0, Math.PI / 4, 0]);
      box(g, 0.18, 0.03, 0.18, m.iron, [0.22, 1.81, 0]);
      lampLight(g, ctx, 0xffb060, [0.22, 1.9, 0], 7, true, 8);
      break;
    }
    case "hitchPost":
      cyl(g, 0.08, 0.09, 1.1, m.darkWood, [0, 0.55, 0], undefined, 8);
      add(g, new THREE.SphereGeometry(0.09, 8, 6), m.darkWood, [0, 1.12, 0]);
      add(g, new THREE.TorusGeometry(0.07, 0.013, 4, 12), m.iron, [0, 0.9, 0.09]);
      break;
    case "wheelbarrow": {
      const tray = new THREE.Group();
      tray.position.set(-0.05, 0.5, 0);
      box(tray, 0.8, 0.04, 0.5, m.midWood, [0, 0, 0]);
      for (const s of [-1, 1]) box(tray, 0.85, 0.28, 0.04, m.midWood, [0, 0.13, s * 0.28], [s * 0.25, 0, 0]);
      box(tray, 0.04, 0.3, 0.6, m.midWood, [-0.43, 0.13, 0], [0, 0, -0.25]);
      box(tray, 0.04, 0.32, 0.62, m.midWood, [0.45, 0.15, 0], [0, 0, 0.45]);
      g.add(tray);
      wheel(g, m, 0.24, [0.62, 0.24, 0], 6);
      for (const s of [-1, 1]) {
        rod(g, [0.62, 0.26, s * 0.08], [-0.78, 0.66, s * 0.25], 0.025, m.darkWood, 5);
        rod(g, [-0.32, 0.46, s * 0.2], [-0.38, 0.0, s * 0.22], 0.025, m.darkWood, 5);
      }
      break;
    }
    case "wagonWheel": {
      const w = wheel(g, m, 0.58, [0, 0.58, 0.05], 12);
      w.rotation.x = -0.2;
      w.position.y = 0.58 * Math.cos(0.2) + 0.02;
      rod(g, [0, 0, -0.42], [0, 1.0, -0.1], 0.04, m.greyWood, 5);
      break;
    }
    case "coveredWagon": {
      const bx = -0.3;
      box(g, 2.8, 0.45, 1.3, m.bluePaint, [bx, 1.0, 0]);
      box(g, 2.9, 0.08, 1.36, m.redPaint, [bx, 1.24, 0]);
      box(g, 2.6, 0.1, 0.16, m.darkWood, [bx, 0.72, 0]);
      for (const z of [-0.78, 0.78]) {
        wheel(g, m, 0.65, [-1.2, 0.65, z], 12);
        wheel(g, m, 0.5, [0.65, 0.5, z], 10);
      }
      rod(g, [-1.2, 0.65, -0.8], [-1.2, 0.65, 0.8], 0.04, m.iron);
      rod(g, [0.65, 0.5, -0.8], [0.65, 0.5, 0.8], 0.04, m.iron);
      const bonnet = scaleUv(new THREE.CylinderGeometry(0.8, 0.8, 2.9, 16, 1, true, Math.PI, Math.PI), 2, 2);
      add(g, bonnet, m.canvas, [bx, 1.26, 0], [0, 0, -Math.PI / 2]);
      for (let i = 0; i < 5; i++) {
        const x = bx - 1.4 + i * 0.7;
        add(g, new THREE.TorusGeometry(0.81, 0.02, 4, 16, Math.PI), m.midWood, [x, 1.26, 0], [0, Math.PI / 2, 0]);
      }
      for (const s of [-1, 1]) {
        const hole = new THREE.CircleGeometry(0.6, 14, 0, Math.PI);
        decal(add(g, hole, m.dark, [bx + s * 1.38, 1.27, 0], [0, (s * Math.PI) / 2, 0], false));
      }
      rod(g, [1.05, 0.75, 0], [2.05, 0.42, 0], 0.045, m.darkWood, 6);
      rod(g, [1.9, 0.46, -0.3], [1.9, 0.46, 0.3], 0.03, m.darkWood, 5);
      barrelAt(g, m, [bx - 1.15, 0.6, 0.78], [0, 0, 0], false, 0.5);
      break;
    }
    case "anvil": {
      add(g, new THREE.CylinderGeometry(0.26, 0.31, 0.5, 11), [m.bark, m.rings, m.bark], [0, 0.25, 0]);
      const top = 0.5;
      box(g, 0.34, 0.06, 0.22, m.iron, [0, top + 0.03, 0]);
      box(g, 0.2, 0.16, 0.13, m.iron, [0, top + 0.14, 0]);
      box(g, 0.5, 0.12, 0.17, m.steel, [-0.02, top + 0.28, 0]);
      add(g, new THREE.ConeGeometry(0.075, 0.3, 8), m.steel, [0.38, top + 0.29, 0], [0, 0, -Math.PI / 2]);
      box(g, 0.1, 0.06, 0.12, m.steel, [-0.31, top + 0.31, 0]);
      rod(g, [0.05, top + 0.36, 0.05], [-0.3, top + 0.37, 0.18], 0.015, m.darkWood, 4);
      box(g, 0.1, 0.06, 0.06, m.iron, [0.08, top + 0.36, 0.04]);
      break;
    }
    case "grindstone": {
      for (const z of [-0.22, 0.22]) {
        rod(g, [-0.38, 0, z], [0, 0.78, z], 0.04, m.darkWood, 5);
        rod(g, [0.38, 0, z], [0, 0.78, z], 0.04, m.darkWood, 5);
      }
      rod(g, [-0.3, 0.2, -0.22], [-0.3, 0.2, 0.22], 0.03, m.darkWood, 5);
      add(g, new THREE.CylinderGeometry(0.32, 0.32, 0.11, 20), [m.sandstone, m.sandstone, m.sandstone], [0, 0.72, 0], [Math.PI / 2, 0, 0]);
      cyl(g, 0.07, 0.07, 0.13, m.iron, [0, 0.72, 0], [Math.PI / 2, 0, 0], 8);
      rod(g, [0, 0.72, -0.34], [0, 0.72, 0.32], 0.025, m.iron, 6);
      rod(g, [0, 0.72, 0.32], [0.16, 0.86, 0.32], 0.02, m.iron, 4);
      rod(g, [0.16, 0.86, 0.32], [0.16, 0.86, 0.44], 0.025, m.darkWood, 5);
      box(g, 0.5, 0.14, 0.3, m.darkWood, [0, 0.45, 0]);
      add(g, new THREE.PlaneGeometry(0.44, 0.24), m.waterTop, [0, 0.522, 0], [-Math.PI / 2, 0, 0], false);
      break;
    }
    case "waterPump": {
      box(g, 0.7, 0.34, 0.7, m.stone, [0, 0.17, 0], undefined, 1);
      cyl(g, 0.08, 0.1, 0.78, m.iron, [0, 0.73, -0.12], undefined, 10);
      cyl(g, 0.11, 0.1, 0.06, m.iron, [0, 1.15, -0.12], undefined, 10);
      add(g, new THREE.SphereGeometry(0.05, 8, 6), m.iron, [0, 1.21, -0.12]);
      rod(g, [0, 0.95, -0.06], [0, 0.92, 0.18], 0.04, m.iron, 8);
      rod(g, [0, 0.93, 0.18], [0, 0.84, 0.2], 0.035, m.iron, 8);
      rod(g, [0, 1.17, -0.14], [0, 1.42, -0.55], 0.025, m.iron, 6);
      const b = new THREE.Group();
      b.position.set(0.02, 0.34, 0.18);
      add(b, scaleUv(lathe([[0.11, 0], [0.12, 0.08], [0.13, 0.22]], 12), 1, 0.4), m.barrelDS, [0, 0, 0]);
      cyl(b, 0.13, 0.13, 0.02, m.iron, [0, 0.18, 0], undefined, 12);
      add(b, new THREE.CircleGeometry(0.12, 12), m.waterTop, [0, 0.17, 0], [-Math.PI / 2, 0, 0], false);
      g.add(b);
      break;
    }
    case "well": {
      const ring = scaleUv(new THREE.CylinderGeometry(0.82, 0.86, 0.8, 18, 1, true), 4, 1);
      add(g, ring, m.stone, [0, 0.4, 0]);
      add(g, new THREE.CylinderGeometry(0.64, 0.64, 0.8, 18, 1, true), lam(fieldstoneTex(345, 25, 0.06, 0.36), 0xffffff, { side: THREE.BackSide }), [0, 0.4, 0]);
      add(g, new THREE.RingGeometry(0.62, 0.88, 18), m.stoneDark, [0, 0.805, 0], [-Math.PI / 2, 0, 0]);
      add(g, new THREE.CircleGeometry(0.64, 18), m.dark, [0, 0.35, 0], [-Math.PI / 2, 0, 0], false);
      for (const x of [-0.82, 0.82]) box(g, 0.12, 2.2, 0.12, m.darkWood, [x, 1.1, 0]);
      for (const s of [-1, 1]) box(g, 2.0, 0.05, 0.72, m.greyWood, [0, 2.45, s * 0.3], [s * 0.6, 0, 0]);
      box(g, 1.9, 0.1, 0.1, m.darkWood, [0, 2.2, 0]);
      log(g, m, 0.07, 1.6, [0, 1.55, 0], "x", 8);
      rod(g, [0.82, 1.55, 0], [1.0, 1.55, 0], 0.02, m.iron, 4);
      rod(g, [1.0, 1.55, 0], [1.0, 1.35, 0.1], 0.02, m.iron, 4);
      rod(g, [-0.1, 1.5, 0], [-0.1, 1.05, 0], 0.01, m.rope, 4);
      const b = new THREE.Group();
      b.position.set(-0.1, 0.83, 0);
      add(b, scaleUv(lathe([[0.12, 0], [0.14, 0.1], [0.15, 0.24]], 12), 1, 0.4), m.barrelDS, [0, 0, 0]);
      add(b, new THREE.TorusGeometry(0.15, 0.008, 4, 12, Math.PI), m.iron, [0, 0.24, 0]);
      g.add(b);
      break;
    }
    case "outhouse": {
      box(g, 1.1, 2.0, 1.1, m.greyWoodV, [0, 1.0, 0]);
      box(g, 1.34, 0.07, 1.4, m.tinSheet, [0, 2.2, 0], [0.22, 0, 0]);
      box(g, 0.7, 1.82, 0.04, m.greyWood, [0, 0.95, 0.56]);
      for (const y of [0.4, 1.5]) box(g, 0.72, 0.08, 0.03, m.darkWood, [0, y, 0.585]);
      const moon = new THREE.Shape();
      moon.absarc(0, 0, 0.1, 0, Math.PI * 2, false);
      const bite = new THREE.Path();
      bite.absarc(0.045, 0.02, 0.085, 0, Math.PI * 2, true);
      moon.holes.push(bite);
      decal(add(g, new THREE.ShapeGeometry(moon, 16), m.dark, [0, 1.72, 0.584], undefined, false));
      cyl(g, 0.025, 0.025, 0.06, m.iron, [0.27, 0.95, 0.6], [Math.PI / 2, 0, 0], 6);
      break;
    }
    case "saddleRail": {
      for (const x of [-0.7, 0.7]) box(g, 0.1, 1.0, 0.1, m.darkWood, [x, 0.5, 0]);
      box(g, 1.6, 0.1, 0.12, m.midWood, [0, 1.02, 0]);
      const sx = 0.28;
      add(g, new THREE.SphereGeometry(0.3, 12, 8, 0, Math.PI * 2, 0, Math.PI / 2), m.leather, [sx, 1.03, 0]).scale.set(1.1, 0.4, 0.75);
      for (const s of [-1, 1]) {
        box(g, 0.5, 0.42, 0.03, m.leatherLight, [sx, 0.86, s * 0.2], [s * 0.35, 0, 0]);
        rod(g, [sx, 0.92, s * 0.26], [sx, 0.55, s * 0.34], 0.01, m.leather, 4);
        box(g, 0.12, 0.03, 0.08, m.iron, [sx, 0.54, s * 0.34]);
      }
      cyl(g, 0.035, 0.05, 0.12, m.leather, [sx + 0.26, 1.16, 0], undefined, 6);
      for (const s of [-1, 1]) box(g, 0.5, 0.42, 0.025, m.blanket, [-0.38, 0.86, s * 0.11], [s * 0.18, 0, 0]);
      break;
    }
    case "milkCans": {
      const can = lathe([[0.15, 0], [0.16, 0.04], [0.16, 0.44], [0.1, 0.54], [0.09, 0.62], [0.11, 0.63], [0.11, 0.68], [0, 0.69]], 14);
      for (const [x, z] of [[-0.32, 0.05], [0.02, -0.12], [0.34, 0.08]] as const) {
        add(g, can, m.tinSheet, [x, 0, z]);
        for (const s of [-1, 1]) add(g, new THREE.TorusGeometry(0.05, 0.01, 4, 8, Math.PI), m.steel, [x + s * 0.12, 0.52, z], [0, Math.PI / 2, (s * Math.PI) / 2]);
        cyl(g, 0.165, 0.165, 0.03, m.steel, [x, 0.3, z], undefined, 14);
      }
      break;
    }

    // ---------------------------------------------------------------- furniture
    case "table":
      box(g, 1.4, 0.06, 0.8, m.lightWood, [0, 0.75, 0]);
      for (const x of [-0.62, 0.62]) for (const z of [-0.32, 0.32]) box(g, 0.07, 0.72, 0.07, m.midWood, [x, 0.36, z]);
      for (const z of [-0.32, 0.32]) box(g, 1.2, 0.1, 0.03, m.midWood, [0, 0.67, z]);
      break;
    case "chair":
      box(g, 0.44, 0.04, 0.42, m.midWood, [0, 0.45, 0]);
      for (const x of [-0.19, 0.19]) {
        rod(g, [x, 0, 0.18], [x, 0.44, 0.18], 0.02, m.darkWood, 6);
        rod(g, [x, 0, -0.18], [x, 1.0, -0.2], 0.022, m.darkWood, 6);
      }
      for (const y of [0.64, 0.77, 0.9]) box(g, 0.38, 0.055, 0.02, m.midWood, [0, y, -0.2]);
      for (const z of [-0.18, 0.18]) rod(g, [-0.19, 0.18, z], [0.19, 0.18, z], 0.012, m.darkWood, 4);
      break;
    case "rockingChair": {
      for (const x of [-0.24, 0.24]) {
        const pts = Array.from({ length: 9 }, (_, i) => {
          const z = -0.42 + (i / 8) * 0.84;
          return new THREE.Vector3(x, 0.03 + 0.16 * (z / 0.42) ** 2, z);
        });
        add(g, tubeThrough(pts, 0.025, 16), m.darkWood, [0, 0, 0]);
        rod(g, [x, 0.04, 0.2], [x, 0.44, 0.2], 0.022, m.darkWood, 6);
        rod(g, [x, 0.04, -0.15], [x, 0.42, -0.16], 0.022, m.darkWood, 6);
        rod(g, [x, 0.42, -0.18], [x, 1.08, -0.36], 0.024, m.darkWood, 6);
        rod(g, [x, 0.62, 0.22], [x, 0.66, -0.2], 0.02, m.darkWood, 5);
        rod(g, [x, 0.44, 0.2], [x, 0.62, 0.22], 0.018, m.darkWood, 5);
      }
      box(g, 0.5, 0.04, 0.42, m.midWood, [0, 0.45, 0.01], [-0.06, 0, 0]);
      box(g, 0.52, 0.08, 0.04, m.midWood, [0, 1.05, -0.35], [-0.27, 0, 0]);
      for (let i = 0; i < 5; i++) {
        const x = -0.16 + i * 0.08;
        rod(g, [x, 0.47, -0.19], [x, 1.02, -0.34], 0.01, m.midWood, 4);
      }
      break;
    }
    case "stool": {
      cyl(g, 0.2, 0.2, 0.05, m.lightWood, [0, 0.64, 0], undefined, 14);
      for (let i = 0; i < 3; i++) {
        const a = (i / 3) * Math.PI * 2 + 0.3;
        rod(g, [Math.cos(a) * 0.11, 0.62, Math.sin(a) * 0.11], [Math.cos(a) * 0.19, 0, Math.sin(a) * 0.19], 0.02, m.midWood, 5);
      }
      break;
    }
    case "picnicTable":
      box(g, 1.8, 0.06, 0.78, m.greyWood, [0, 0.76, 0]);
      for (const z of [-0.62, 0.62]) box(g, 1.8, 0.05, 0.28, m.greyWood, [0, 0.44, z]);
      for (const x of [-0.7, 0.7]) {
        for (const s of [-1, 1]) rod(g, [x, 0, s * 0.68], [x, 0.74, s * 0.08], 0.035, m.darkWood, 5);
        box(g, 0.07, 0.07, 1.55, m.darkWood, [x, 0.39, 0]);
      }
      break;
    case "logBench": {
      add(g, new THREE.CylinderGeometry(0.22, 0.22, 1.6, 10, 1, false, 0, Math.PI), [m.bark, m.rings, m.rings], [0, 0.5, 0], [0, 0, -Math.PI / 2]);
      box(g, 1.6, 0.02, 0.44, m.freshWood, [0, 0.5, 0]);
      for (const x of [-0.55, 0.55]) add(g, new THREE.CylinderGeometry(0.16, 0.19, 0.3, 9), [m.bark, m.rings, m.bark], [x, 0.15, 0]);
      break;
    }
    case "flowerBox": {
      box(g, 0.9, 0.26, 0.3, m.greenPaint, [0, 0.13, 0]);
      box(g, 0.84, 0.02, 0.24, m.soil, [0, 0.25, 0]);
      for (let i = 0; i < 11; i++) {
        const x = -0.38 + (i / 10) * 0.76 + range(rng, -0.02, 0.02);
        const z = range(rng, -0.08, 0.08);
        const h = range(rng, 0.12, 0.22);
        rod(g, [x, 0.25, z], [x + range(rng, -0.02, 0.02), 0.25 + h, z], 0.008, m.reed, 4);
        add(g, new THREE.IcosahedronGeometry(range(rng, 0.04, 0.06), 0), m.blooms[Math.floor(rng() * m.blooms.length)], [x, 0.26 + h, z]);
        if (i % 2 === 0) add(g, new THREE.IcosahedronGeometry(0.05, 0), m.leaf, [x + 0.03, 0.29, z]).scale.set(1, 0.6, 1);
      }
      break;
    }

    // ---------------------------------------------------- camp, lumber, mine
    case "tent": {
      const body = scaleUv(gable(2.0, 1.6, 2.6, 1), 1, 1);
      add(g, body, m.canvas, [0, 0, 0]);
      decal(add(g, shapeGeo([[-0.42, 0], [0.42, 0], [0, 1.25]]), m.dark, [0, 0, 1.305], undefined, false));
      for (const s of [-1, 1]) rod(g, [s * 0.47, 0.06, 1.34], [s * 0.06, 1.3, 1.34], 0.05, m.canvas, 6, 0.035);
      rod(g, [0, 0, 1.33], [0, 1.66, 1.33], 0.03, m.darkWood, 5);
      rod(g, [0, 0, -1.33], [0, 1.66, -1.33], 0.03, m.darkWood, 5);
      for (const s of [-1, 1]) {
        rod(g, [0, 1.62, s * 1.33], [0, 0.02, s * 1.4], 0.008, m.rope, 3);
        cyl(g, 0.02, 0.01, 0.12, m.darkWood, [0, 0.03, s * 1.4], undefined, 4);
      }
      break;
    }
    case "campfire": {
      for (let i = 0; i < 8; i++) {
        const a = (i / 8) * Math.PI * 2;
        rockAt(g, m.stoneRough, [Math.cos(a) * 0.48, 0, Math.sin(a) * 0.48], range(rng, 0.11, 0.15), seed + i * 3);
      }
      for (const yaw of [0.3, -0.9, 1.5]) log(g, m, 0.055, 0.7, [0, 0.08, 0], "x", 7).rotation.y = yaw;
      fire(g, ctx, rng, 0.22);
      for (let i = 0; i < 3; i++) {
        const a = (i / 3) * Math.PI * 2 + 0.5;
        rod(g, [Math.cos(a) * 0.62, 0, Math.sin(a) * 0.62], [0, 1.45, 0], 0.025, m.iron, 5);
      }
      rod(g, [0, 1.42, 0], [0, 0.82, 0], 0.008, m.iron, 4);
      const kettle = new THREE.Group();
      kettle.position.set(0, 0.56, 0);
      add(kettle, lathe([[0.0, 0], [0.12, 0.01], [0.17, 0.08], [0.16, 0.2], [0.11, 0.25], [0.0, 0.26]], 12), m.iron, [0, 0, 0]);
      add(kettle, new THREE.TorusGeometry(0.15, 0.008, 4, 12, Math.PI), m.iron, [0, 0.22, 0]);
      g.add(kettle);
      lampLight(g, ctx, 0xff8a3a, [0, 0.6, 0], 14, true, 12);
      smoke.push(new THREE.Vector3(0, 0.9, 0));
      break;
    }
    case "logStack": {
      const at: [number, number][] = [[-0.62, 0.3], [0, 0.3], [0.62, 0.3], [-0.31, 0.82], [0.31, 0.82], [0, 1.34]];
      at.forEach(([z, y], i) => log(g, m, 0.3 - (i % 2) * 0.02, 4.0 - (i % 3) * 0.15, [range(rng, -0.08, 0.08), y, z], "x", 12, range(rng, 0, 6)));
      for (const x of [-1.6, 1.6]) for (const s of [-1, 1]) rod(g, [x, 0, s * 0.95], [x, 0.8, s * 0.95], 0.05, m.darkWood, 5);
      break;
    }
    case "lumberStack": {
      for (const x of [-1.2, 0, 1.2]) box(g, 0.12, 0.12, 1.2, m.darkWood, [x, 0.06, 0]);
      let y = 0.12;
      for (let layer = 0; layer < 6; layer++) {
        for (let i = 0; i < 5; i++) box(g, 3.0 - (layer % 2) * 0.1, 0.07, 0.21, m.freshWood, [range(rng, -0.04, 0.04), y + 0.035, -0.48 + i * 0.24]);
        y += 0.07;
        if (layer < 5) for (const x of [-1.2, 0, 1.2]) box(g, 0.05, 0.05, 1.2, m.midWood, [x, y + 0.025, 0]);
        y += 0.06;
      }
      break;
    }
    case "sawhorse": {
      for (const x of [-0.55, 0.55]) {
        rod(g, [x, 0, -0.3], [x, 0.78, 0.12], 0.035, m.midWood, 5);
        rod(g, [x, 0, 0.3], [x, 0.78, -0.12], 0.035, m.midWood, 5);
      }
      rod(g, [-0.55, 0.3, 0], [0.55, 0.3, 0], 0.03, m.midWood, 5);
      log(g, m, 0.15, 1.4, [0, 0.82, 0], "x", 10);
      const saw = new THREE.Group();
      saw.position.set(0.15, 1.0, 0.12);
      saw.rotation.set(-0.9, 0, 0.1);
      add(saw, new THREE.TorusGeometry(0.3, 0.015, 4, 14, Math.PI), m.midWood, [0, 0, 0]);
      box(saw, 0.62, 0.03, 0.005, m.steel, [0, 0, 0]);
      g.add(saw);
      break;
    }
    case "choppingBlock": {
      add(g, new THREE.CylinderGeometry(0.3, 0.34, 0.5, 11), [m.bark, m.ringsFresh, m.bark], [0, 0.25, 0]);
      rod(g, [0.02, 0.52, 0.0], [0.3, 0.85, 0.12], 0.02, m.lightWood, 5);
      box(g, 0.17, 0.09, 0.03, m.steel, [0.0, 0.53, -0.01], [0, 0.4, 0.85]);
      const piece = new THREE.CylinderGeometry(0.08, 0.08, 0.4, 4);
      for (let i = 0; i < 4; i++) {
        const a = range(rng, 0, Math.PI * 2);
        add(g, piece, [m.bark, m.ringsFresh, m.ringsFresh], [Math.cos(a) * 0.42, 0.06, Math.sin(a) * 0.38], [0, a, Math.PI / 2]);
      }
      break;
    }
    case "toolRack": {
      for (const x of [-0.65, 0.65]) box(g, 0.08, 1.45, 0.08, m.darkWood, [x, 0.72, -0.15]);
      for (const y of [0.3, 1.32]) box(g, 1.38, 0.07, 0.07, m.midWood, [0, y, -0.12]);
      const tool = (x: number, head: "pick" | "shovel" | "axe") => {
        rod(g, [x, 0.05, 0.16], [x - 0.04, 1.55, -0.09], 0.022, m.lightWood, 5);
        if (head === "shovel") box(g, 0.2, 0.28, 0.02, m.steel, [x + 0.002, 0.17, 0.16], [0.17, 0, 0]);
        if (head === "pick") add(g, new THREE.TorusGeometry(0.28, 0.025, 4, 10, Math.PI * 0.7), m.iron, [x - 0.04, 1.4, -0.09], [0.17, 0, Math.PI * 0.15]);
        if (head === "axe") box(g, 0.2, 0.12, 0.03, m.steel, [x + 0.04, 1.5, -0.08], [0.17, 0, 0]);
      };
      tool(-0.42, "shovel");
      tool(-0.14, "pick");
      tool(0.14, "shovel");
      tool(0.42, "axe");
      break;
    }
    case "mineCart": {
      rails(g, m, 1.4, 0.62, "x", 3, 0, 1.1);
      for (const x of [-0.34, 0.34]) for (const z of [-0.31, 0.31]) cyl(g, 0.13, 0.13, 0.06, m.iron, [x, 0.33, z], [Math.PI / 2, 0, 0], 12);
      const tub = new THREE.CylinderGeometry(0.7, 0.52, 0.52, 4, 1);
      tub.rotateY(Math.PI / 4);
      tub.scale(1, 1, 0.75);
      add(g, tub, m.rust, [0, 0.66, 0]);
      for (const y of [0.48, 0.88]) box(g, 1.0 - (0.88 - y) * 0.3, 0.04, 0.74 - (0.88 - y) * 0.2, m.iron, [0, y, 0]);
      const ore = add(g, new THREE.DodecahedronGeometry(0.42, 0), m.ore, [0, 0.9, 0]);
      ore.scale.set(1.05, 0.35, 0.75);
      break;
    }
    case "mineEntrance": {
      // a faceted hill: a low-poly half sphere, jittered by position so shared
      // vertices move together and the facets stay closed
      const hill = new THREE.SphereGeometry(1, 10, 5, 0, Math.PI * 2, 0, Math.PI / 2);
      const hp = hill.getAttribute("position") as THREE.BufferAttribute;
      for (let i = 0; i < hp.count; i++) {
        const x = hp.getX(i);
        const y = hp.getY(i);
        const z = hp.getZ(i);
        const j = y > 0.02 ? 1 + 0.13 * Math.sin(x * 5.1 + z * 3.3 + seed) + 0.08 * Math.sin(y * 7 + x * 2) : 1;
        hp.setXYZ(i, x * j, y * j, z * j);
      }
      hill.computeVertexNormals();
      add(g, hill, m.hill, [0, 0, -1.6]).scale.set(2.5, 3.1, 1.9);
      box(g, 1.7, 2.35, 1.4, m.dark, [0, 1.18, -0.35]);
      for (const s2 of [-1, 1]) box(g, 0.1, 2.45, 1.1, m.darkWood, [s2 * 1.04, 1.22, -0.2]);
      for (const x of [-0.98, 0.98]) {
        log(g, m, 0.15, 2.5, [x, 1.25, 0.4], "y", 9);
        rod(g, [x, 2.2, 0.42], [x * 0.55, 2.62, 0.42], 0.08, m.bark, 6);
      }
      log(g, m, 0.17, 2.6, [0, 2.62, 0.42], "x", 9);
      for (const x of [-0.6, 0, 0.6]) box(g, 0.25, 0.2, 0.5, m.darkWood, [x, 2.85, 0.35]);
      rails(g, m, 2.0, 0.62, "z", 4, 0, 1.0);
      for (let i = 0; i < 4; i++) {
        const s = i < 2 ? -1 : 1;
        rockAt(g, m.rockMat, [s * range(rng, 1.3, 2.0), 0, range(rng, 0.2, 0.9)], range(rng, 0.25, 0.45), seed + 10 + i);
      }
      for (const o of g.children) o.position.z += 1.25;
      break;
    }
    case "rockPile":
      for (let i = 0; i < 7; i++) {
        const big = i < 2;
        rockAt(g, m.rockMat, [range(rng, -0.5, 0.5), big ? 0 : 0.05, range(rng, -0.45, 0.45)], big ? range(rng, 0.4, 0.5) : range(rng, 0.18, 0.3), seed * 13 + i);
      }
      break;

    // -------------------------------------------------------------------- farm
    case "plow": {
      rod(g, [-0.55, 0.42, 0], [0.98, 0.32, 0], 0.045, m.midWood, 6);
      for (const s of [-1, 1]) rod(g, [-0.35, 0.2, s * 0.05], [-0.98, 0.95, s * 0.28], 0.025, m.midWood, 5);
      rod(g, [-0.8, 0.75, -0.24], [-0.8, 0.75, 0.24], 0.02, m.midWood, 4);
      box(g, 0.46, 0.05, 0.2, m.steel, [-0.12, 0.05, 0.04], [0.0, 0.4, -0.1]);
      box(g, 0.4, 0.3, 0.03, m.steel, [-0.22, 0.2, 0.12], [0.3, 0.7, 0.2]);
      rod(g, [-0.1, 0.4, 0], [-0.08, 0.06, 0.02], 0.025, m.iron, 4);
      wheel(g, m, 0.15, [0.9, 0.16, 0.06], 6, m.iron);
      break;
    }
    case "scarecrow": {
      cyl(g, 0.045, 0.055, 2.0, m.greyWood, [0, 1.0, -0.05], undefined, 6);
      rod(g, [-0.66, 1.46, -0.05], [0.66, 1.46, -0.05], 0.035, m.greyWood, 5);
      box(g, 0.46, 0.58, 0.2, m.shirt, [0, 1.22, 0.02]);
      for (const s of [-1, 1]) {
        rod(g, [s * 0.2, 1.42, 0.02], [s * 0.62, 1.44, 0.02], 0.085, m.shirt, 7, 0.07);
        for (let k = 0; k < 4; k++) add(g, new THREE.ConeGeometry(0.03, 0.18, 4), m.straw, [s * 0.68, 1.44 + range(rng, -0.05, 0.05), 0.02], [0, 0, s * (-Math.PI / 2 + range(rng, -0.5, 0.5))]);
        box(g, 0.15, 0.5, 0.14, m.denim, [s * 0.1, 0.74, 0.02], [0, 0, s * 0.06]);
        for (let k = 0; k < 3; k++) add(g, new THREE.ConeGeometry(0.03, 0.14, 4), m.straw, [s * 0.12 + range(rng, -0.04, 0.04), 0.46, 0.02], [Math.PI, 0, 0]);
      }
      add(g, new THREE.SphereGeometry(0.17, 10, 8), m.burlap, [0, 1.72, 0.02]).scale.set(1, 1.08, 0.95);
      for (const x of [-0.06, 0.06]) add(g, new THREE.CircleGeometry(0.025, 8), m.dark, [x, 1.75, 0.18], undefined, false);
      cyl(g, 0.3, 0.3, 0.025, m.straw, [0, 1.87, 0.02], [0.08, 0, 0.06], 14);
      cyl(g, 0.13, 0.15, 0.2, m.straw, [0, 1.97, 0.02], [0.08, 0, 0.06], 12);
      cyl(g, 0.152, 0.152, 0.04, m.redPaint, [0, 1.9, 0.02], [0.08, 0, 0.06], 12);
      break;
    }
    case "chickenCoop": {
      const z0 = -0.15;
      for (const x of [-0.55, 0.55]) for (const z of [-0.45, 0.45]) box(g, 0.08, 0.5, 0.08, m.darkWood, [x, 0.25, z0 + z]);
      box(g, 1.2, 0.8, 1.0, m.redPaintV, [0, 0.9, z0]);
      box(g, 1.4, 0.06, 1.25, m.greyWood, [0, 1.38, z0], [0.22, 0, 0]);
      for (const x of [-0.6, 0.6]) box(g, 0.06, 0.82, 0.06, m.creamPaint, [x, 0.9, z0 + 0.5]);
      decal(add(g, new THREE.PlaneGeometry(0.24, 0.3), m.dark, [0.3, 0.68, z0 + 0.505], undefined, false));
      const ramp = new THREE.Group();
      const dz = 0.45;
      const dy = 0.52;
      ramp.position.set(0.3, dy / 2, z0 + 0.5 + dz / 2);
      ramp.rotation.x = Math.atan2(dy, dz);
      const len = Math.hypot(dy, dz);
      box(ramp, 0.28, 0.03, len, m.greyWood, [0, 0, 0]);
      for (let i = 0; i < 4; i++) box(ramp, 0.28, 0.025, 0.025, m.darkWood, [0, 0.025, -len / 2 + (i + 0.5) * (len / 4)]);
      g.add(ramp);
      box(g, 0.32, 0.38, 0.6, m.redPaintV, [0.76, 0.85, z0]);
      box(g, 0.36, 0.04, 0.66, m.greyWood, [0.78, 1.07, z0], [0, 0, -0.3]);
      break;
    }
    case "haystack": {
      const geo = scaleUv(lathe([[1.05, 0], [1.1, 0.55], [1.02, 1.25], [0.78, 1.85], [0.44, 2.28], [0.16, 2.5], [0, 2.56]], 14), 5, 3);
      add(g, geo, m.straw, [0, 0, 0]);
      cyl(g, 0.035, 0.04, 2.7, m.greyWood, [0, 1.35, 0], undefined, 6);
      for (const [r, y] of [[1.08, 0.9], [0.86, 1.62]] as const) add(g, new THREE.TorusGeometry(r, 0.025, 4, 22), m.twine, [0, y, 0], [Math.PI / 2, 0, 0]);
      break;
    }
    case "beehive": {
      for (const x of [-0.2, 0.2]) for (const z of [-0.2, 0.2]) box(g, 0.06, 0.5, 0.06, m.greyWood, [x, 0.25, z]);
      box(g, 0.56, 0.05, 0.56, m.greyWood, [0, 0.52, 0]);
      const prof: [number, number][] = [];
      for (let i = 0; i <= 8; i++) {
        const a = (i / 8) * (Math.PI / 2);
        prof.push([0.24 * Math.cos(a) + 0.02, 0.5 * Math.sin(a)]);
      }
      prof.push([0, 0.52]);
      add(g, scaleUv(lathe(prof, 14), 3, 2), m.straw, [0, 0.545, 0]);
      for (let k = 0; k < 4; k++) {
        const a = (k / 4.4) * (Math.PI / 2);
        add(g, new THREE.TorusGeometry(0.24 * Math.cos(a) + 0.025, 0.02, 4, 14), m.straw, [0, 0.545 + 0.5 * Math.sin(a), 0], [Math.PI / 2, 0, 0]);
      }
      decal(add(g, new THREE.CircleGeometry(0.05, 10, 0, Math.PI), m.dark, [0, 0.548, 0.262], undefined, false));
      break;
    }
    case "windmill": {
      const top = 5.9;
      const foot = 1.0;
      const head = 0.2;
      const corner = (sx: number, sz: number, t: number): V3 => [sx * (foot + (head - foot) * t), top * t, sz * (foot + (head - foot) * t)];
      const cs: [number, number][] = [[1, 1], [-1, 1], [-1, -1], [1, -1]];
      for (const [sx, sz] of cs) rod(g, corner(sx, sz, 0), corner(sx, sz, 1), 0.05, m.greyWood, 5);
      for (let i = 0; i < 4; i++) {
        const [ax, az] = cs[i];
        const [bx2, bz] = cs[(i + 1) % 4];
        for (const t of [0.25, 0.5, 0.75]) rod(g, corner(ax, az, t), corner(bx2, bz, t), 0.03, m.greyWood, 4);
        rod(g, corner(ax, az, 0.0), corner(bx2, bz, 0.25), 0.022, m.greyWood, 4);
        rod(g, corner(ax, az, 0.25), corner(bx2, bz, 0.5), 0.022, m.greyWood, 4);
      }
      box(g, 0.5, 0.08, 0.5, m.darkWood, [0, top, 0]);
      box(g, 0.24, 0.24, 0.5, m.iron, [0, top + 0.28, 0.05]);
      const fan = new THREE.Group();
      fan.position.set(0, top + 0.3, 0.34);
      fan.rotation.z = seed * 0.37;
      add(fan, new THREE.TorusGeometry(1.08, 0.025, 4, 28), m.iron, [0, 0, 0]);
      add(fan, new THREE.TorusGeometry(0.42, 0.02, 4, 20), m.iron, [0, 0, 0]);
      for (let i = 0; i < 16; i++) {
        const a = (i / 16) * Math.PI * 2;
        const blade = box(fan, 0.15, 0.7, 0.015, m.greyWood, [Math.cos(a) * 0.75, Math.sin(a) * 0.75, 0], [0, 0, a - Math.PI / 2]);
        blade.rotateY(0.35);
      }
      cyl(fan, 0.09, 0.09, 0.14, m.iron, [0, 0, 0], [Math.PI / 2, 0, 0], 10);
      g.add(fan);
      rod(g, [0, top + 0.3, 0], [0, top + 0.3, -1.1], 0.03, m.iron, 4);
      box(g, 0.02, 0.6, 0.9, m.redPaint, [0, top + 0.35, -1.35]);
      rod(g, [0, top, 0.0], [0, 0.4, 0.0], 0.02, m.iron, 4);
      cyl(g, 0.12, 0.14, 0.4, m.iron, [0, 0.2, 0], undefined, 8);
      break;
    }
    case "laundryLine": {
      const posts = [-1.6, 1.6];
      for (const x of posts) {
        rod(g, [x, 0, 0], [x, 1.92, 0], 0.04, m.greyWood, 5);
        rod(g, [x, 1.86, -0.18], [x, 1.86, 0.18], 0.03, m.greyWood, 5);
      }
      const sag = 0.12;
      const lineY = (x: number) => 1.84 - sag * (1 - (x / 1.6) ** 2);
      for (const z of [-0.15, 0.15]) g.add(new THREE.Mesh(wire(new THREE.Vector3(-1.6, 1.84, z), new THREE.Vector3(1.6, 1.84, z), sag, 0.008, 16), m.rope));
      const hang = (x: number, z: number, w: number, pts: [number, number][], mat: THREE.Material, tilt: number) => {
        const geo = shapeGeo(pts.map(([px, py]) => [px * w, py * w]));
        const o = add(g, geo, mat, [x, lineY(x) - 0.01, z], [tilt, 0, 0]);
        return o;
      };
      hang(-1.0, 0.15, 0.8, [[-0.5, 0], [0.5, 0], [0.5, -1.1], [-0.5, -1.1]], m.clothes[0], 0.05);
      hang(-0.15, 0.15, 0.62, [[-0.5, 0], [-0.28, 0], [-0.18, -0.08], [0.18, -0.08], [0.28, 0], [0.5, 0], [0.62, -0.38], [0.38, -0.42], [0.36, -1.0], [-0.36, -1.0], [-0.38, -0.42], [-0.62, -0.38]], m.clothes[1], 0.08);
      hang(0.6, 0.15, 0.6, [[-0.34, 0], [0.34, 0], [0.34, -1.2], [0.06, -1.2], [0.0, -0.5], [-0.06, -1.2], [-0.34, -1.2]], m.clothes[2], 0.03);
      hang(1.15, -0.15, 0.5, [[-0.4, 0], [0.4, 0], [0.4, -0.7], [-0.4, -0.7]], m.clothes[3], -0.04);
      for (const x of [-1.38, -0.62, -0.43, 0.13, 0.42, 0.78, 0.95, 1.35]) box(g, 0.02, 0.07, 0.025, m.lightWood, [x, lineY(x) + 0.01, x > 1.1 ? -0.15 : 0.15]);
      break;
    }

    // ----------------------------------------------------------- fences, walls
    case "picketFence": {
      for (const x of [-1.45, 0, 1.45]) box(g, 0.1, 1.0, 0.1, m.creamPaint, [x, 0.5, -0.04]);
      for (const y of [0.3, 0.75]) box(g, 3.0, 0.08, 0.04, m.creamPaint, [0, y, -0.03]);
      const s = new THREE.Shape();
      s.moveTo(-0.045, 0);
      s.lineTo(0.045, 0);
      s.lineTo(0.045, 0.86);
      s.lineTo(0, 0.95);
      s.lineTo(-0.045, 0.86);
      s.closePath();
      const picket = new THREE.ExtrudeGeometry(s, { depth: 0.025, bevelEnabled: false });
      scaleUv(picket, 1, 1);
      for (let x = -1.38; x <= 1.39; x += 0.15) {
        if (Math.abs(x) < 0.06) continue;
        add(g, picket, m.creamPaint, [x, 0.02, 0], [0, 0, range(rng, -0.02, 0.02)]);
      }
      break;
    }
    case "splitRailFence": {
      const corners: [number, number][] = [[-1.7, 0.35], [-0.57, -0.35], [0.57, 0.35], [1.7, -0.35]];
      for (const [cx, cz] of corners) {
        rod(g, [cx - 0.12, 0, cz - 0.1], [cx + 0.06, 1.3, cz + 0.05], 0.035, m.greyWood, 4);
        rod(g, [cx + 0.12, 0, cz - 0.1], [cx - 0.06, 1.3, cz + 0.05], 0.035, m.greyWood, 4);
      }
      for (let i = 0; i < 3; i++) {
        const [x0, z0] = corners[i];
        const [x1, z1] = corners[i + 1];
        const dx = x1 - x0;
        const dz = z1 - z0;
        const L = Math.hypot(dx, dz);
        const ex = (dx / L) * 0.12;
        const ez = (dz / L) * 0.12;
        for (let k = 0; k < 4; k++) {
          const y = 0.16 + k * 0.27 + (i % 2) * 0.12;
          rod(g, [x0 - ex, y, z0 - ez], [x1 + ex, y + range(rng, 0.0, 0.06), z1 + ez], 0.055, m.greyWood, 4);
        }
      }
      break;
    }
    case "stoneWall": {
      box(g, 3.0, 0.66, 0.5, m.stone, [0, 0.33, 0], undefined, 1.8);
      let x = -1.5;
      while (x < 1.5) {
        const w = Math.min(range(rng, 0.28, 0.46), 1.5 - x);
        if (w < 0.1) break;
        box(g, w - 0.02, range(rng, 0.12, 0.18), range(rng, 0.52, 0.6), m.stoneDark, [x + w / 2, 0.74, range(rng, -0.03, 0.03)], [range(rng, -0.05, 0.05), range(rng, -0.08, 0.08), range(rng, -0.08, 0.08)], 0.9);
        x += w;
      }
      for (let i = 0; i < 4; i++) rockAt(g, m.stone, [range(rng, -1.3, 1.3), 0, range(rng, 0.25, 0.32) * (rng() < 0.5 ? -1 : 1)], range(rng, 0.1, 0.16), seed + i);
      break;
    }

    // ---------------------------------------------------------------- riverside
    case "rowboat": {
      const outer = hullGeo(3.2, 0.5, 0.6, 0.62, 0.18, 0.06);
      add(g, outer, m.greenPaint, [0, 0.5, 0]);
      const inner = hullGeo(3.2, 0.5, 0.6, 0.62, 0.18, 0.06, 0.95);
      add(g, inner, lam(T.planks({ seed: 346, planks: 7, hue: 32, sat: 0.34, light: 0.55 }), 0xffffff, { side: THREE.BackSide }), [0, 0.5, 0]);
      const rim = Array.from({ length: 33 }, (_, i) => {
        const a = (i / 32) * Math.PI * 2;
        const x = Math.cos(a);
        const pinch = x > 0 ? 0.62 : 0.18;
        return new THREE.Vector3(x * 1.6, 0.5 + 0.06 * x ** 4, Math.sin(a) * 0.6 * (1 - pinch * x * x));
      });
      add(g, tubeThrough(rim, 0.03, 64), m.darkWood, [0, 0, 0]);
      for (const x of [-0.5, 0.35]) {
        const half = 0.6 * (1 - (x > 0 ? 0.62 : 0.18) * (x / 1.6) ** 2) * 0.92;
        box(g, 0.22, 0.04, half * 2, m.lightWood, [x, 0.36, 0]);
      }
      for (const s of [-1, 1]) {
        rod(g, [-0.9, 0.42, s * 0.2], [1.1, 0.5, s * 0.3], 0.022, m.lightWood, 5);
        box(g, 0.5, 0.02, 0.14, m.lightWood, [1.25, 0.5, s * 0.31], [0, s * 0.05, 0.04]);
      }
      break;
    }
    case "canoe": {
      add(g, hullGeo(4.0, 0.36, 0.4, 0.85, 0.85, 0.12), m.birch, [0, 0.36, 0]);
      add(g, hullGeo(4.0, 0.36, 0.4, 0.85, 0.85, 0.12, 0.94), lam(T.planks({ seed: 347, planks: 6, hue: 30, sat: 0.36, light: 0.5 }), 0xffffff, { side: THREE.BackSide }), [0, 0.36, 0]);
      const rim = Array.from({ length: 41 }, (_, i) => {
        const a = (i / 40) * Math.PI * 2;
        const x = Math.cos(a);
        return new THREE.Vector3(x * 2.0, 0.36 + 0.12 * x ** 4, Math.sin(a) * 0.4 * (1 - 0.85 * x * x));
      });
      add(g, tubeThrough(rim, 0.022, 80), m.midWood, [0, 0, 0]);
      for (const x of [-0.9, 0, 0.9]) box(g, 0.06, 0.03, 0.8 * (1 - 0.85 * (x / 2) ** 2) * 0.95, m.midWood, [x, 0.34, 0]);
      rod(g, [-0.7, 0.36, 0.1], [0.6, 0.38, -0.12], 0.018, m.lightWood, 5);
      add(g, new THREE.SphereGeometry(0.14, 8, 6), m.lightWood, [0.75, 0.38, -0.14]).scale.set(1.3, 0.12, 0.6);
      break;
    }
    case "dock": {
      const deckY = 0.7;
      for (const x of [-0.9, 0.9]) for (const z of [-2.35, -0.8, 0.8, 2.35]) cyl(g, 0.11, 0.12, 1.3, m.darkWood, [x, deckY - 0.5, z], undefined, 8);
      for (const x of [-0.9, 0.9]) cyl(g, 0.11, 0.11, 0.4, m.darkWood, [x, deckY + 0.2, 2.35], undefined, 8);
      for (const x of [-0.8, 0.8]) box(g, 0.1, 0.16, 5.0, m.darkWood, [x, deckY - 0.12, 0]);
      for (let i = 0; i < 20; i++) box(g, 2.0, 0.07, 0.23, i % 7 === 3 ? m.greyWood : m.midWood, [range(rng, -0.02, 0.02), deckY - 0.01, -2.37 + i * 0.25], [0, range(rng, -0.01, 0.01), 0]);
      add(g, new THREE.TorusGeometry(0.16, 0.025, 4, 12), m.rope, [0.9, deckY + 0.3, 2.35], [Math.PI / 2, 0, 0]);
      break;
    }
    case "footbridge": {
      const half = 2.3;
      const rise = 0.6;
      const yAt = (x: number) => 0.2 + rise * (1 - (x / half) ** 2);
      const slope = (x: number) => Math.atan((-2 * rise * x) / (half * half));
      for (let i = 0; i < 16; i++) {
        const x = -half + (i + 0.5) * ((2 * half) / 16);
        box(g, 0.27, 0.06, 1.4, i % 5 === 2 ? m.greyWood : m.midWood, [x, yAt(x), 0], [0, 0, slope(x)]);
      }
      const arc = (dy: number, z: number) => Array.from({ length: 13 }, (_, i) => {
        const x = -half + (i / 12) * 2 * half;
        return new THREE.Vector3(x, yAt(x) + dy, z);
      });
      for (const z of [-0.6, 0.6]) {
        add(g, tubeThrough(arc(-0.08, z), 0.07, 24), m.darkWood, [0, 0, 0]);
        add(g, tubeThrough(arc(0.9, z * 1.08), 0.04, 24), m.lightWood, [0, 0, 0]);
        for (const x of [-2.1, -1.05, 0, 1.05, 2.1]) rod(g, [x, yAt(x) - 0.05, z * 1.08], [x, yAt(x) + 0.92, z * 1.08], 0.035, m.darkWood, 5);
      }
      for (const s of [-1, 1]) box(g, 0.5, 0.25, 1.6, m.stone, [s * (half + 0.05), 0.125, 0], undefined, 1);
      break;
    }
    case "pond": {
      decal(add(g, blobGeo(rng, 2.0, 1.5), m.mud, [0, 0.01, 0], undefined, false));
      decal(add(g, blobGeo(rng, 1.75, 1.25), m.water, [0, 0.02, 0], undefined, false));
      for (let i = 0; i < 6; i++) {
        const pad = new THREE.CircleGeometry(range(rng, 0.12, 0.2), 10, 0.4, Math.PI * 1.75);
        pad.rotateX(-Math.PI / 2);
        decal(add(g, pad, m.lily, [range(rng, -1.0, 1.0), 0.03, range(rng, -0.7, 0.7)], [0, range(rng, 0, 6), 0], false));
      }
      add(g, new THREE.IcosahedronGeometry(0.04, 0), m.blooms[2], [0.3, 0.05, 0.2], undefined, false);
      for (let i = 0; i < 7; i++) {
        const a = range(rng, 0, Math.PI * 2);
        rockAt(g, m.rockMat, [Math.cos(a) * 1.85, 0, Math.sin(a) * 1.35], range(rng, 0.1, 0.18), seed + i * 5);
      }
      for (const [x, z] of [[-1.5, -0.8], [1.6, 0.4]] as const) {
        for (let k = 0; k < 6; k++) {
          const h = range(rng, 0.6, 1.1);
          add(g, new THREE.ConeGeometry(0.022, h, 4), m.reed, [x + range(rng, -0.15, 0.15), h / 2, z + range(rng, -0.12, 0.12)], [range(rng, -0.15, 0.15), 0, range(rng, -0.15, 0.15)]);
        }
      }
      break;
    }
    case "reeds": {
      for (let k = 0; k < 13; k++) {
        const h = range(rng, 0.7, 1.35);
        const a = range(rng, 0, Math.PI * 2);
        const r = range(rng, 0, 0.3);
        add(g, new THREE.ConeGeometry(0.024, h, 4), m.reed, [Math.cos(a) * r, h / 2, Math.sin(a) * r], [range(rng, -0.2, 0.2), 0, range(rng, -0.2, 0.2)]);
      }
      for (let k = 0; k < 4; k++) {
        const x = range(rng, -0.25, 0.25);
        const z = range(rng, -0.25, 0.25);
        const h = range(rng, 1.05, 1.35);
        rod(g, [x, 0, z], [x, h, z], 0.01, m.reed, 4);
        add(g, new THREE.CapsuleGeometry(0.035, 0.16, 2, 6), m.cattail, [x, h - 0.14, z]);
      }
      break;
    }

    // ------------------------------------------------------------------ nature
    case "shrub": {
      const n = 8 + Math.floor(rng() * 3);
      for (let i = 0; i < n; i++) {
        const a = (i / n) * Math.PI * 4 + range(rng, -0.3, 0.3);
        const r = i === 0 ? 0 : range(rng, 0.2, 0.4);
        const s = i === 0 ? 0.36 : range(rng, 0.18, 0.28);
        const y = i === 0 ? 0.42 : i % 2 ? range(rng, 0.2, 0.3) : range(rng, 0.45, 0.6);
        const b = add(g, new THREE.IcosahedronGeometry(s, 1), i % 4 === 3 ? m.leafDry : m.leaf, [Math.cos(a) * r, y, Math.sin(a) * r], [rng(), rng(), rng()]);
        b.scale.y = 0.85;
      }
      break;
    }
    case "pineTree": {
      cyl(g, 0.12, 0.2, 1.4, m.bark, [0, 0.7, 0], undefined, 8);
      const tiers: [number, number, number][] = [[1.18, 1.9, 1.05], [0.98, 1.7, 2.0], [0.76, 1.5, 2.9], [0.52, 1.3, 3.75], [0.3, 1.0, 4.55]];
      tiers.forEach(([r, h, y], i) => add(g, new THREE.ConeGeometry(r, h, 7), m.leafDark, [range(rng, -0.04, 0.04), y + h / 2 - 0.3, range(rng, -0.04, 0.04)], [0, i * 0.7 + rng(), 0]));
      break;
    }
    case "deadTree": {
      cyl(g, 0.12, 0.24, 2.6, m.barkGrey, [0, 1.3, 0], undefined, 8);
      const branch = (from: V3, a: number, up: number, len: number, r: number, depth: number) => {
        const to: V3 = [from[0] + Math.cos(a) * len * Math.cos(up), from[1] + Math.sin(up) * len, from[2] + Math.sin(a) * len * Math.cos(up)];
        rod(g, from, to, r * 0.6, m.barkGrey, 5, r);
        if (depth > 0) {
          branch(to, a + range(rng, 0.3, 0.8), up + range(rng, -0.1, 0.25), len * 0.6, r * 0.6, depth - 1);
          branch(to, a - range(rng, 0.3, 0.8), up + range(rng, -0.2, 0.15), len * 0.55, r * 0.55, depth - 1);
        }
      };
      for (let i = 0; i < 4; i++) branch([0, 1.5 + i * 0.32, 0], (i / 4) * Math.PI * 2 + rng(), range(rng, 0.35, 0.7), range(rng, 1.0, 1.35), 0.09, 1);
      branch([0, 2.6, 0], rng() * 6, 1.2, 0.9, 0.1, 1);
      break;
    }
    case "saguaro": {
      add(g, scaleUv(new THREE.CapsuleGeometry(0.22, 2.7, 4, 12), 1, 1), m.cactus, [0, 1.57, 0]);
      const arm = (s: number, y0: number, out: number, top: number) => {
        const pts = [new THREE.Vector3(s * 0.12, y0, 0), new THREE.Vector3(s * (out - 0.08), y0 + 0.04, 0), new THREE.Vector3(s * out, y0 + 0.25, 0), new THREE.Vector3(s * out, top, 0)];
        add(g, scaleUv(tubeThrough(pts, 0.14, 20), 1, 1), m.cactusH, [0, 0, 0]);
        add(g, new THREE.SphereGeometry(0.14, 10, 6, 0, Math.PI * 2, 0, Math.PI / 2), m.cactus, [s * out, top, 0]);
      };
      arm(-1, 1.15, 0.5, 2.15);
      arm(1, 1.6, 0.44, 2.45);
      for (let i = 0; i < 3; i++) add(g, new THREE.IcosahedronGeometry(0.045, 0), m.blooms[2], [range(rng, -0.1, 0.1), 3.12, range(rng, -0.1, 0.1)]);
      break;
    }
    case "barrelCactus": {
      add(g, new THREE.SphereGeometry(0.25, 14, 10), m.cactus, [0, 0.21, 0]).scale.set(1, 0.9, 1);
      for (let i = 0; i < 6; i++) {
        const a = (i / 6) * Math.PI * 2;
        add(g, new THREE.ConeGeometry(0.035, 0.08, 5), m.blooms[i % 2 === 0 ? 0 : 1], [Math.cos(a) * 0.08, 0.44, Math.sin(a) * 0.08], [Math.PI, 0, 0]);
      }
      break;
    }
    // ---------------------------------------- story: trains, people, water
    case "locomotive": {
      const K = m.engineBlack;
      const R = m.engineRed;
      const B = m.brass;
      const rD = 0.78; // driving wheels
      const rP = 0.4; // pilot and tender wheels
      const yD = RAIL_TOP + rD;
      const yP = RAIL_TOP + rP;
      const crank = 0.35;
      // frame, wheels, axles (front is +x)
      box(g, 4.7, 0.18, 1.2, K, [0.7, 1.14, 0]);
      for (const s of [-1, 1]) {
        for (const x of [0.9, -0.6]) locoWheel(g, m, rD, [x, yD, s * RAIL_Z], s, 12, crank);
        for (const x of [2.15, 2.95]) locoWheel(g, m, rP, [x, yP, s * RAIL_Z], s, 8);
      }
      for (const x of [0.9, -0.6]) rod(g, [x, yD, -RAIL_Z], [x, yD, RAIL_Z], 0.06, m.iron, 8);
      for (const x of [2.15, 2.95]) rod(g, [x, yP, -RAIL_Z], [x, yP, RAIL_Z], 0.05, m.iron, 8);
      box(g, 1.3, 0.14, 1.2, K, [2.55, yP + 0.14, 0]);
      // steam cylinders and rods
      for (const s of [-1, 1]) {
        const z = s * 1.0;
        cyl(g, 0.22, 0.22, 0.9, K, [2.3, 1.2, z], [0, 0, Math.PI / 2], 14);
        cyl(g, 0.25, 0.25, 0.08, B, [1.9, 1.2, z], [0, 0, Math.PI / 2], 14);
        const zp = s * (RAIL_Z + 0.12);
        const pin = (x: number): V3 => [x + Math.cos(crank) * rD * 0.55, yD + Math.sin(crank) * rD * 0.55, zp];
        rod(g, pin(0.9), pin(-0.6), 0.045, m.steel, 6);
        rod(g, pin(0.9), [1.85, 1.2, zp], 0.04, m.steel, 6);
        rod(g, [1.85, 1.2, zp], [1.85, 1.2, z], 0.04, m.steel, 6);
      }
      // boiler, smokebox, bands, running boards
      const bx = 1.3;
      const by = 1.98;
      const rB = 0.72;
      cyl(g, rB, rB, 3.3, K, [bx, by, 0], [0, 0, Math.PI / 2], 22);
      cyl(g, rB + 0.04, rB + 0.04, 0.5, K, [2.75, by, 0], [0, 0, Math.PI / 2], 22);
      cyl(g, 0.3, 0.3, 0.06, m.iron, [3.02, by, 0], [0, 0, Math.PI / 2], 16);
      for (const x of [0.7, 2.2]) cyl(g, rB + 0.03, rB + 0.03, 0.1, B, [x, by, 0], [0, 0, Math.PI / 2], 22);
      for (const s of [-1, 1]) {
        box(g, 3.4, 0.07, 0.36, K, [1.15, 1.86, s * 0.95]);
        rod(g, [-0.15, 2.7, s * 0.8], [2.9, 2.7, s * 0.8], 0.025, B, 6);
      }
      // balloon stack
      const sx = 2.55;
      const topB = by + rB;
      add(g, lathe([[0.2, 0], [0.2, 0.55], [0.5, 1.1], [0.46, 1.38], [0.36, 1.42], [0.0, 1.42]], 18), K, [sx, topB - 0.05, 0]);
      cyl(g, 0.52, 0.52, 0.06, B, [sx, topB + 1.31, 0], undefined, 18);
      smoke.push(new THREE.Vector3(sx, topB + 1.45, 0));
      // domes, bell and whistle
      add(g, lathe([[0.36, 0], [0.36, 0.26], [0.3, 0.4], [0.0, 0.46]], 16), B, [0.2, topB - 0.08, 0]);
      rod(g, [0.2, topB + 0.36, 0], [0.2, topB + 0.72, 0], 0.045, B, 8);
      add(g, lathe([[0.32, 0], [0.32, 0.3], [0.26, 0.42], [0.0, 0.5]], 16), B, [1.65, topB - 0.08, 0]);
      for (const s of [-1, 1]) rod(g, [1.0 + s * 0.18, topB - 0.04, 0], [1.0, topB + 0.42, 0], 0.025, B, 5);
      add(g, new THREE.ConeGeometry(0.16, 0.26, 12), B, [1.0, topB + 0.2, 0]);
      // headlamp on its platform in front of the stack
      box(g, 0.6, 0.06, 0.6, K, [3.05, topB + 0.02, 0]);
      for (const s of [-1, 1]) rod(g, [3.0, by + 0.5, s * 0.25], [3.3, topB, s * 0.25], 0.025, K, 5);
      box(g, 0.46, 0.46, 0.46, K, [3.1, topB + 0.28, 0]);
      box(g, 0.52, 0.06, 0.52, K, [3.1, topB + 0.53, 0]);
      const lens = glowMat(ctx, 0xf4e0b0, new THREE.Color(1.0, 0.78, 0.4), 1.6);
      cyl(g, 0.17, 0.17, 0.04, lens, [3.34, topB + 0.28, 0], [0, 0, Math.PI / 2], 16).castShadow = false;
      lampLight(g, ctx, 0xffd090, [3.65, topB + 0.28, 0], 3, false, 8);
      // cab
      const cx = -0.9;
      const cy0 = 1.23;
      box(g, 1.5, 1.55, 1.7, R, [cx, cy0 + 0.775, 0]);
      box(g, 1.75, 0.1, 2.05, K, [cx, 2.86, 0]);
      for (const s of [-1, 1]) {
        box(g, 0.6, 0.66, 0.03, m.creamPaint, [cx + 0.15, 2.35, s * 0.855]);
        decal(add(g, new THREE.PlaneGeometry(0.46, 0.52), m.dark, [cx + 0.15, 2.35, s * 0.88], [0, s * Math.PI / 2, 0], false));
        box(g, 1.52, 0.06, 0.03, B, [cx, 1.6, s * 0.855]);
      }
      const num = seed % 2 ? "119" : "60";
      const plate = lam(plateTex(num, "#1a1424", "#e8c870"));
      for (const s of [-1, 1]) decal(add(g, new THREE.PlaneGeometry(0.5, 0.25), plate, [cx - 0.3, 1.95, s * 0.86], [0, s * Math.PI / 2, 0], false));
      decal(add(g, new THREE.PlaneGeometry(0.3, 0.15), plate, [3.1, topB + 0.28, 0.24], undefined, false));
      for (const s of [-1, 1]) for (const y of [0.45, 0.85]) box(g, 0.4, 0.05, 0.3, K, [cx - 0.55, y, s * 0.95]);
      // cowcatcher
      box(g, 0.2, 0.3, 2.0, R, [3.15, 1.05, 0]);
      for (let z = -0.8; z <= 0.81; z += 0.2) {
        const xb = 4.4 - (Math.abs(z) / 0.95) * 1.05;
        rod(g, [3.25, 1.15, z], [xb, 0.32, z], 0.035, R, 5);
      }
      for (const s of [-1, 1]) rod(g, [4.4, 0.32, 0], [3.3, 0.32, s * 0.9], 0.04, R, 5);
      // tender: wood-sided box on two trucks, cordwood and coal heaped on top
      const tc = -3.15;
      box(g, 2.6, 0.16, 1.2, K, [tc, 1.14, 0]);
      truckAt(g, m, -2.45, rP, 0.75);
      truckAt(g, m, -3.85, rP, 0.75);
      box(g, 2.5, 1.0, 1.6, m.redPaintV, [tc, 1.72, 0]);
      box(g, 2.56, 0.08, 1.66, K, [tc, 2.25, 0]);
      for (let i = 0; i < 4; i++) for (let k = 0; k < 2; k++) log(g, m, 0.1, 1.4, [-2.25 - i * 0.22, 2.3 + k * 0.19 + (i % 2) * 0.03, 0], "z", 7, rng() * 6);
      add(g, new THREE.SphereGeometry(0.5, 12, 8), m.coal, [-3.75, 2.2, 0]).scale.set(1.1, 0.7, 1.4);
      box(g, 0.4, 0.3, 1.2, m.darkWood, [-4.25, 2.44, 0]);
      box(g, 0.6, 0.1, 0.16, K, [-1.75, 1.1, 0]);
      break;
    }
    case "passengerCar": {
      const K = m.engineBlack;
      truckAt(g, m, -2.5);
      truckAt(g, m, 2.5);
      box(g, 7.4, 0.2, 1.3, K, [0, 1.14, 0]);
      const fy = 1.24;
      const bh = 1.95;
      const bw = 6.4;
      const bd = 2.2;
      box(g, bw, bh, bd, m.coachPaint, [0, fy + bh / 2, 0]);
      for (const s of [-1, 1]) {
        box(g, bw + 0.02, 0.28, 0.04, m.creamPaint, [0, fy + bh - 0.2, s * (bd / 2)]);
        box(g, bw + 0.02, 0.1, 0.04, m.engineRed, [0, fy + 0.08, s * (bd / 2)]);
        for (let i = 0; i < 8; i++) {
          const x = (i - 3.5) * 0.76;
          box(g, 0.52, 0.8, 0.03, m.creamPaint, [x, fy + 1.0, s * (bd / 2 + 0.005)]);
          decal(add(g, new THREE.PlaneGeometry(0.42, 0.7), m.dark, [x, fy + 1.0, s * (bd / 2 + 0.03)], [0, s * Math.PI / 2, 0], false));
        }
        decal(add(g, new THREE.PlaneGeometry(0.6, 1.5), m.dark, [s * (bw / 2 + 0.005), fy + 0.8, 0], [0, s * Math.PI / 2, 0], false));
      }
      // roof with a clerestory
      const ry = fy + bh;
      box(g, 7.7, 0.14, 2.45, m.coachRoof, [0, ry + 0.07, 0]);
      box(g, 5.6, 0.3, 1.3, m.coachPaint, [0, ry + 0.29, 0]);
      box(g, 5.9, 0.08, 1.5, m.coachRoof, [0, ry + 0.48, 0]);
      for (const s of [-1, 1]) for (let i = 0; i < 7; i++) decal(add(g, new THREE.PlaneGeometry(0.4, 0.16), m.dark, [(i - 3) * 0.76, ry + 0.29, s * 0.655], [0, s * Math.PI / 2, 0], false));
      cyl(g, 0.07, 0.07, 0.5, m.iron, [-2.3, ry + 0.75, 0.5], undefined, 8);
      // end platforms, railings, steps
      for (const s of [-1, 1]) {
        const px = s * 3.6;
        box(g, 0.8, 0.08, 2.0, m.greyWood, [px, fy + 0.04, 0]);
        for (const z of [-0.95, 0.95]) {
          rod(g, [px + s * 0.35, fy, z], [px + s * 0.35, ry, z], 0.03, K, 6);
          rod(g, [px - s * 0.35, fy, z], [px - s * 0.35, fy + 0.9, z], 0.025, K, 6);
          rod(g, [px - s * 0.35, fy + 0.9, z], [px + s * 0.35, fy + 0.9, z], 0.025, K, 6);
          rod(g, [px - s * 0.35, fy + 0.45, z], [px + s * 0.35, fy + 0.45, z], 0.02, K, 6);
          box(g, 0.6, 0.06, 0.4, m.greyWood, [px, fy - 0.3, z * 1.25]);
          box(g, 0.6, 0.06, 0.4, m.greyWood, [px, fy - 0.62, z * 1.25]);
          for (const sx of [-1, 1]) box(g, 0.05, 0.72, 0.46, m.greyWood, [px + sx * 0.32, fy - 0.36, z * 1.25]);
        }
        rod(g, [px + s * 0.35, fy + 0.9, -0.95], [px + s * 0.35, fy + 0.9, 0.95], 0.025, K, 6);
      }
      break;
    }
    case "bystander":
      figureAt(g, seed, 1.5 + (Math.abs(seed) % 7) * 0.05, [0, 0, 0]);
      break;
    case "crowd": {
      const n = 7 + Math.floor(rng() * 3);
      const back = Math.floor(n / 2);
      const front = n - back;
      for (let i = 0; i < front; i++) {
        const t = front > 1 ? (i / (front - 1)) * 2 - 1 : 0;
        figureAt(g, seed * 17 + i, range(rng, 1.5, 1.7), [t * 2.05 + range(rng, -0.1, 0.1), 0, 0.65 - 0.35 * t * t], range(rng, -0.2, 0.2));
      }
      for (let i = 0; i < back; i++) {
        const t = back > 1 ? (i / (back - 1)) * 2 - 1 : 0;
        figureAt(g, seed * 17 + 9 + i, range(rng, 1.72, 1.9), [t * 1.6 + range(rng, -0.1, 0.1), 0, -0.5 - 0.3 * t * t], range(rng, -0.2, 0.2));
      }
      break;
    }
    case "riverWater":
      decal(add(g, scaleUv(new THREE.PlaneGeometry(6, 4), 3, 2), m.river, [0, 0.02, 0], [-Math.PI / 2, 0, 0], false));
      break;
    case "horse": {
      const coats: [Hsl, Hsl][] = [
        [{ hue: 22, sat: 0.5, light: 0.32 }, { hue: 20, sat: 0.3, light: 0.08 }], // bay
        [{ hue: 18, sat: 0.6, light: 0.4 }, { hue: 18, sat: 0.5, light: 0.3 }], // chestnut
        [{ hue: 220, sat: 0.05, light: 0.72 }, { hue: 220, sat: 0.06, light: 0.45 }], // grey
        [{ hue: 250, sat: 0.12, light: 0.12 }, { hue: 250, sat: 0.12, light: 0.07 }], // black
        [{ hue: 40, sat: 0.5, light: 0.6 }, { hue: 42, sat: 0.35, light: 0.88 }], // palomino
      ];
      const [cc, mc] = coats[Math.abs(seed) % coats.length];
      const coat = flat(cc.hue, cc.sat, cc.light);
      const mane = flat(mc.hue, mc.sat, mc.light);
      const hoof = flat(30, 0.15, 0.12);
      const white = flat(40, 0.1, 0.92);
      const blaze = (seed >> 1) % 2 === 0;
      // body (along x), neck, head, ears
      add(g, new THREE.CapsuleGeometry(0.32, 0.8, 4, 14), coat, [0, 1.05, 0], [0, 0, Math.PI / 2]);
      rod(g, [0.42, 1.12, 0], [0.86, 1.58, 0], 0.2, coat, 12, 0.15);
      add(g, new THREE.SphereGeometry(0.17, 12, 10), coat, [0.86, 1.6, 0]);
      rod(g, [0.86, 1.6, 0], [1.2, 1.36, 0], 0.15, coat, 12, 0.11);
      add(g, new THREE.SphereGeometry(0.115, 10, 8), coat, [1.2, 1.36, 0]);
      for (const s of [-1, 1]) {
        add(g, new THREE.ConeGeometry(0.045, 0.16, 6), coat, [0.82, 1.82, s * 0.08], [0, 0, s * -0.25]);
        decal(add(g, new THREE.CircleGeometry(0.03, 8), m.dark, [0.96, 1.6, s * 0.16], [0, s * Math.PI / 2, 0], false));
      }
      if (blaze) decal(box(g, 0.3, 0.02, 0.07, white, [1.11, 1.6, 0], [0, 0, Math.atan2(-0.24, 0.34)]));
      // mane, forelock, tail
      const maneBox = box(g, 0.6, 0.2, 0.1, mane, [0.5, 1.5, 0]);
      maneBox.rotation.z = Math.atan2(0.46, 0.44);
      add(g, new THREE.SphereGeometry(0.09, 8, 6), mane, [0.9, 1.76, 0]);
      rod(g, [-0.6, 1.2, 0], [-0.76, 0.5, 0], 0.08, mane, 8, 0.04);
      // legs and hooves
      for (const x of [-0.42, 0.4]) {
        for (const s of [-1, 1]) {
          rod(g, [x, 0.85, s * 0.17], [x + (x > 0 ? 0.03 : -0.03), 0.08, s * 0.19], 0.095, coat, 8, 0.075);
          cyl(g, 0.085, 0.09, 0.09, hoof, [x + (x > 0 ? 0.03 : -0.03), 0.045, s * 0.19], undefined, 8);
        }
      }
      // red blanket, saddle, stirrups
      add(g, scaleUv(new THREE.CylinderGeometry(0.345, 0.345, 0.56, 14, 1, true, Math.PI, Math.PI), 1, 1), m.blanket, [0.02, 1.05, 0], [0, 0, -Math.PI / 2]);
      add(g, new THREE.CylinderGeometry(0.36, 0.36, 0.4, 12, 1, true, Math.PI + 0.55, Math.PI - 1.1), m.leather, [0.02, 1.05, 0], [0, 0, -Math.PI / 2]);
      add(g, new THREE.SphereGeometry(0.06, 8, 6), m.leather, [0.2, 1.44, 0]);
      box(g, 0.08, 0.14, 0.3, m.leather, [-0.17, 1.44, 0], [0, 0, 0.3]);
      for (const s of [-1, 1]) {
        rod(g, [0.02, 1.2, s * 0.33], [0.02, 0.82, s * 0.37], 0.012, m.leather, 4);
        add(g, new THREE.TorusGeometry(0.05, 0.012, 5, 10), m.iron, [0.02, 0.77, s * 0.37], [0, Math.PI / 2, 0]);
      }
      // bridle: noseband and reins back to the pommel
      const headDir = new THREE.Vector3(0.34, -0.24, 0).normalize();
      const band = mesh(new THREE.TorusGeometry(0.135, 0.013, 5, 14), m.leather, [1.1, 1.43, 0]);
      band.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), headDir);
      g.add(band);
      for (const s of [-1, 1]) rod(g, [1.08, 1.4, s * 0.13], [0.22, 1.42, s * 0.1], 0.01, m.leather, 4);
      break;
    }
  }
  if (smoke.length) g.userData.smoke = smoke;
  return g;
};

// --------------------------------------------------------------- buildings

/** shadow-free canvas for a door: vertical boards, cross braces */
const doorMat = (c: Hsl, seed: number) => lam(T.planks({ seed, planks: 4, hue: c.hue, sat: c.sat, light: c.light, vertical: true }));

/**
 * A styled building. Local origin at the centre of the facade line (ground),
 * facing +z; the body spans local z 0..-d. Dressing (porch, steps, awning,
 * balcony) stands in FRONT of z = 0 — buildingExtent() in partsSpec says how far.
 * Chimney smoke points are on group.userData.smoke (local frame).
 * lit[] indexes ground-floor windows first (left to right), then upper ones.
 */
export const makeBuilding = (piece: BuildingPiece & { style?: BuildingStyle }, m: PartMaterials, ctx: PartCtx): THREE.Group => {
  let b = piece;
  const g = new THREE.Group();
  const r = resolveStyle(b);
  const fac = facadeLayout(b);
  const rng = makeRng(b.seed * 977 + 3);
  const rise = roofRise(b, r);
  const fl = r.floor;
  // Art direction is enforced here, not trusted to the data: no colour the
  // agent picks can go past a muted storybook range (round 2's depot at
  // saturation 0.7 read as a toy).
  const mute = <H extends Hsl>(c: H, sMax = 0.42): H => ({ ...c, sat: Math.min(sMax, c.sat), light: Math.max(0.22, Math.min(0.84, c.light)) });
  b = {
    ...b,
    wall: { ...mute(b.wall, 0.44), painted: b.wall.painted ? { ...mute(b.wall.painted, 0.36), wear: b.wall.painted.wear } : undefined },
    roof: mute(b.roof, 0.34),
  };
  const trim = lam(T.planks({ seed: b.seed + 18, planks: 3, hue: r.trim.hue, sat: r.trim.sat * 0.6, light: r.trim.light * 0.75 }), col(r.trim.hue, r.trim.sat, r.trim.light));
  const wh = b.h - fl; // height of the wall above the floor line

  // ---- walls
  const W = b.wall;
  const wallMat =
    r.wall === "stone" ? lam(fieldstoneTex(b.seed, W.hue, Math.min(0.14, W.sat * 0.4), Math.max(0.5, W.light)))
    : r.wall === "brick" ? lam(brickTex(b.seed, W.hue, Math.min(0.45, W.sat), Math.min(0.48, W.light)))
    : r.wall === "adobe" ? lam(adobeTex(b.seed, W.hue, Math.min(0.38, W.sat), Math.max(0.58, W.light)))
    : r.wall === "logs" ? m.bark
    : lam(T.planks({ seed: b.seed, planks: r.wall === "clapboard" ? 9 : 7, hue: W.hue, sat: W.sat, light: W.light, clapboard: r.wall === "clapboard", painted: W.painted }));
  const texSize = r.wall === "brick" ? 1.6 : r.wall === "stone" ? 2.2 : r.wall === "adobe" ? 3 : r.wall === "clapboard" ? 2.2 : 2;
  if (r.wall === "logs") {
    // a filled core (the chinking) wrapped in horizontal logs that cross and
    // stick out at the corners, alternating courses front/back vs sides
    const lr = 0.16;
    box(g, b.w - 0.1, wh, b.d - 0.1, lam(T.dirt(b.seed + 5, 34, 0.25, 0.62)), [0, fl + wh / 2, -b.d / 2]);
    const courses = Math.floor(wh / (lr * 2));
    for (let i = 0; i < courses; i++) {
      const y = fl + lr + i * lr * 2;
      const front = i % 2 === 0;
      const yy = front ? y : y + lr; // side logs sit half a course higher (the notch)
      if (yy > b.h - lr * 0.5) continue;
      for (const z of [-lr, -b.d + lr]) log(g, m, lr * range(rng, 0.94, 1.04), b.w + 0.5, [range(rng, -0.04, 0.04), front ? y : yy, z], "x", 9, rng() * 6);
      for (const x of [-b.w / 2 + lr, b.w / 2 - lr]) log(g, m, lr * range(rng, 0.94, 1.04), b.d + 0.5, [x, front ? yy : y, -b.d / 2 + range(rng, -0.04, 0.04)], "z", 9, rng() * 6);
    }
  } else {
    box(g, b.w, wh, b.d, wallMat, [0, fl + wh / 2, -b.d / 2], undefined, texSize);
    if (r.wall === "planks" || r.wall === "clapboard") {
      for (const x of [-1, 1]) for (const z of [0, -b.d]) box(g, 0.14, wh, 0.14, trim, [(x * (b.w - 0.1)) / 2, fl + wh / 2, z === 0 ? 0.0 : -b.d]);
    }
    if (r.wall === "brick" || r.wall === "stone") box(g, b.w + 0.08, 0.14, b.d + 0.08, trim, [0, b.h - 0.07, -b.d / 2]);
  }

  // ---- foundation
  if (r.foundation === "stone") box(g, b.w + 0.12, fl + 0.02, b.d + 0.12, m.stoneDark, [0, (fl + 0.02) / 2, -b.d / 2], undefined, 1.4);
  if (r.foundation === "posts") {
    const nx = Math.max(2, Math.round(b.w / 2) + 1);
    const nz = Math.max(2, Math.round(b.d / 2) + 1);
    for (let i = 0; i < nx; i++) for (let k = 0; k < nz; k++) {
      if (i > 0 && i < nx - 1 && k > 0 && k < nz - 1) continue;
      const x = -b.w / 2 + 0.15 + (i / (nx - 1)) * (b.w - 0.3);
      const z = -0.15 - (k / (nz - 1)) * (b.d - 0.3);
      rockAt(g, m.stoneRough, [x, 0, z], 0.2, b.seed + i * 7 + k);
      box(g, 0.2, fl, 0.2, m.darkWood, [x, fl / 2, z]);
    }
    box(g, b.w, 0.18, b.d, m.darkWood, [0, fl - 0.09, -b.d / 2]);
    box(g, b.w - 0.4, 0.02, b.d - 0.4, m.dark, [0, 0.01, -b.d / 2]).userData.noInk = true;
  }

  // ---- roof
  const roofMat =
    r.roofMat === "tin" ? lam(tinTex(b.seed + 100, b.roof.hue, Math.min(0.2, b.roof.sat * 0.3), Math.max(0.5, b.roof.light)))
    : r.roofMat === "planks" ? lam(T.planks({ seed: b.seed + 100, planks: 6, hue: b.roof.hue, sat: b.roof.sat * 0.7, light: b.roof.light, vertical: true }))
    : lam(T.shingles(b.seed + 100, b.roof.hue, b.roof.sat, b.roof.light));
  const gableWallMat = r.wall === "logs" ? lam(T.planks({ seed: b.seed + 9, planks: 6, hue: 28, sat: 0.3, light: 0.4, vertical: true })) : wallMat;
  if (r.roof === "gable" || r.roof === "falseFront") {
    const ff = r.roof === "falseFront";
    if (!ff) g.add(mesh(gable(b.w - (r.wall === "logs" ? 0.1 : 0), rise, 0.2, 2), gableWallMat, [0, b.h, -0.1 - (r.wall === "logs" ? 0.05 : 0)]));
    g.add(mesh(gable(b.w - (r.wall === "logs" ? 0.1 : 0), rise, 0.2, 2), gableWallMat, [0, b.h, -b.d + 0.1 + (r.wall === "logs" ? 0.05 : 0)]));
    // behind a false front the roof starts just behind the board, never through it
    const roof = ff ? pitchedRoof(b.w, rise, b.d - 0.5, roofMat, 0.12) : pitchedRoof(b.w, rise, b.d, roofMat, 0.3);
    roof.position.set(0, b.h, ff ? -b.d / 2 - 0.15 : -b.d / 2);
    g.add(roof);
    if (r.roof === "gable") {
      // a ridge board and fascia boards along the gable's front edge
      const slope = Math.atan2(rise, b.w / 2);
      const len = Math.hypot(b.w / 2 + 0.3, rise + 0.3 * Math.tan(slope));
      for (const s of [-1, 1]) {
        const fb = box(g, len, 0.16, 0.06, trim, [(-s * len * Math.cos(slope)) / 2, b.h + rise - (len * Math.sin(slope)) / 2 + 0.02, 0.32], [0, 0, s * slope]);
        fb.castShadow = false;
      }
    }
  } else if (r.roof === "hip") {
    const o = 0.35;
    const hw = b.w / 2 + o;
    const hd = b.d / 2 + o;
    const ridge = Math.max(0, hd - hw);
    const y0 = b.h;
    const y1 = b.h + rise;
    const zc = -b.d / 2;
    const v = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z + zc);
    const A = v(-hw, y0, hd), B = v(hw, y0, hd), C = v(hw, y0, -hd), Dd = v(-hw, y0, -hd);
    const R1 = v(0, y1, ridge), R2 = v(0, y1, -ridge);
    const tris = [[A, B, R1], [B, C, R2], [B, R2, R1], [C, Dd, R2], [Dd, A, R1], [Dd, R1, R2], [A, Dd, C], [A, C, B]];
    const pos: number[] = [];
    const uvs: number[] = [];
    for (const t of tris) {
      const n = new THREE.Vector3().subVectors(t[1], t[0]).cross(new THREE.Vector3().subVectors(t[2], t[0])).normalize();
      // planar uv in the face: one axis along the eave, one up the slope
      const ax = new THREE.Vector3().subVectors(t[1], t[0]).normalize();
      const ay = new THREE.Vector3().crossVectors(n, ax);
      for (const p of t) {
        pos.push(p.x, p.y, p.z);
        uvs.push(p.dot(ax) / 1.6, p.dot(ay) / 1.6);
      }
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    geo.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
    geo.computeVertexNormals();
    g.add(mesh(geo, roofMat, [0, 0, 0]));
    box(g, b.w + 0.7, 0.12, b.d + 0.7, trim, [0, b.h - 0.06, -b.d / 2]);
  } else if (r.roof === "shed") {
    // high at the front, falling to the back; side wedges fill the gap
    const s = new THREE.Shape();
    s.moveTo(0, 0);
    s.lineTo(b.d, 0);
    s.lineTo(0, rise);
    s.closePath();
    const wedge = new THREE.ExtrudeGeometry(s, { depth: b.w, bevelEnabled: false });
    const uv = wedge.getAttribute("uv") as THREE.BufferAttribute;
    for (let i = 0; i < uv.count; i++) uv.setXY(i, uv.getX(i) / texSize, uv.getY(i) / texSize);
    const wm = mesh(wedge, r.wall === "logs" ? gableWallMat : wallMat, [-b.w / 2, b.h, 0], { rot: [0, Math.PI / 2, 0] });
    g.add(wm);
    const ang = Math.atan2(rise, b.d);
    const len = Math.hypot(rise, b.d) + 0.6;
    box(g, b.w + 0.5, 0.1, len, roofMat, [0, b.h + rise / 2 + 0.05, -b.d / 2], [-ang, 0, 0], 1.6);
    box(g, b.w + 0.5, 0.2, 0.06, trim, [0, b.h + rise + 0.06 + 0.3 * Math.sin(ang), 0.3 * Math.cos(ang)], [-ang, 0, 0]);
  } else {
    // flat: a low parapet, with a cornice on brick/stone/plank and vigas on adobe
    box(g, b.w, 0.08, b.d, r.wall === "adobe" ? wallMat : m.darkWood, [0, b.h + 0.02, -b.d / 2]);
    const pm = r.wall === "logs" ? gableWallMat : wallMat;
    box(g, b.w + 0.1, rise, 0.25, pm, [0, b.h + rise / 2, -0.12], undefined, texSize);
    box(g, b.w + 0.1, rise, 0.25, pm, [0, b.h + rise / 2, -b.d + 0.12], undefined, texSize);
    for (const x of [-1, 1]) box(g, 0.25, rise, b.d, pm, [(x * (b.w - 0.15)) / 2, b.h + rise / 2, -b.d / 2], undefined, texSize);
    if (r.wall === "adobe") {
      const n = Math.max(3, Math.round(b.w / 0.9));
      for (let i = 0; i < n; i++) log(g, m, 0.09, 0.5, [(i - (n - 1) / 2) * (b.w / n), b.h - 0.22, 0.18], "z", 8);
    } else {
      box(g, b.w + 0.3, 0.16, 0.18, trim, [0, b.h + rise + 0.04, 0.0]);
      box(g, b.w + 0.2, 0.1, 0.14, trim, [0, b.h - 0.1, 0.03]);
    }
  }

  // ---- false front: a tall board facade with a cap, hiding the low gable
  if (r.roof === "falseFront") {
    const ffMat = r.wall === "logs" ? gableWallMat : wallMat;
    box(g, b.w + 0.2, r.falseFront + 0.0, 0.25, ffMat, [0, b.h + r.falseFront / 2, -0.12], undefined, texSize);
    box(g, b.w + 0.42, 0.14, 0.38, trim, [0, b.h + r.falseFront + 0.07, -0.08]);
    for (const x of [-1, 1]) box(g, 0.14, r.falseFront, 0.08, trim, [(x * (b.w + 0.1)) / 2, b.h + r.falseFront / 2, 0.03]);
  }

  // ---- belt course between storeys
  if (r.storeys === 2) box(g, b.w + 0.06, 0.14, 0.06, trim, [0, b.h / 2, 0.03]);

  // ---- windows (ground floor, then upper) with trim, sill, panes, shutters
  const lit = b.lit ?? [];
  const front = 0;
  const winAt = (x: number, y: number, idx: number, wide: number) => {
    const isLit = lit.includes(idx);
    box(g, 0.92, 1.12, 0.06, trim, [x, y, front + 0.01]).castShadow = false;
    box(g, 1.02, 0.08, 0.16, trim, [x, y - 0.6, front + 0.06]).castShadow = false;
    const pane = isLit ? glowMat(ctx, 0xfff0c0, new THREE.Color(1.0, 0.6, 0.18), 1.6) : lam(null, col(255, 0.25, 0.18));
    box(g, 0.7, 0.9, 0.06, pane, [x, y, front + 0.05]).castShadow = false;
    box(g, 0.04, 0.9, 0.07, trim, [x, y, front + 0.06]).castShadow = false;
    box(g, 0.7, 0.04, 0.07, trim, [x, y + 0.06, front + 0.06]).castShadow = false;
    if (r.shutters && wide > 0.18) {
      const sw = Math.min(0.36, wide);
      const sm = lam(T.planks({ seed: b.seed + 40, planks: 3, hue: r.shutters.hue, sat: r.shutters.sat, light: r.shutters.light, vertical: true }));
      for (const s of [-1, 1]) {
        box(g, sw, 1.06, 0.04, sm, [x + s * (0.46 + sw / 2 + 0.02), y, front + 0.03]);
        for (const yy of [y - 0.3, y + 0.3]) box(g, sw * 0.8, 0.05, 0.015, trim, [x + s * (0.46 + sw / 2 + 0.02), yy, front + 0.055]);
      }
    }
    if (r.wall === "brick" || r.wall === "stone") box(g, 1.1, 0.16, 0.1, trim, [x, y + 0.64, front + 0.05]);
  };
  const gapAt = (i: number, slots: number[], doorX: number | null) => {
    // free width either side of a window before a neighbour (door or window)
    const x = slots[i];
    let gap = Infinity;
    slots.forEach((o, k) => {
      if (k === i) return;
      const other = doorX !== null && Math.abs(o - doorX) < 1e-6 ? 0.62 : 0.46;
      gap = Math.min(gap, Math.abs(o - x) - 0.46 - other - 0.06);
    });
    gap = Math.min(gap, b.w / 2 - Math.abs(x) - 0.5);
    return gap;
  };
  // a sign wins over anything under it: openings drop to clear its board
  const signLow = b.sign ? signDims(b).cy - signDims(b).sh / 2 : Infinity;
  const upperY = Math.min(fac.upperY, signLow - 0.66);
  const winY = Math.min(fac.winY, signLow - 0.66);
  fac.windows.forEach((x, i) => winAt(x, winY, i, gapAt(fac.slots.indexOf(x), fac.slots, fac.doorX)));
  fac.upper.forEach((x, i) => winAt(x, upperY, fac.windows.length + i, gapAt(i, fac.slots, null)));

  // ---- door
  if (r.door && fac.doorX !== null) {
    const dx = fac.doorX;
    const dw = 1.0;
    const top = Math.max(fl + 1.75, Math.min(fac.doorTop, signLow - 0.12));
    const dh = top - fl;
    box(g, dw + 0.24, dh + 0.12, 0.07, trim, [dx, fl + (dh + 0.12) / 2, front + 0.015]).castShadow = false;
    if (r.door.open) {
      const inside = r.door.lit ? glowMat(ctx, col(30, 0.35, 0.16), new THREE.Color(1.0, 0.55, 0.2), 0.9) : m.dark;
      const opening = box(g, dw, dh, 0.06, inside, [dx, fl + dh / 2, front + 0.03]);
      opening.castShadow = false;
      // the door swung in, seen edge-on near its hinge
      box(g, 0.24, dh - 0.02, 0.07, doorMat(r.door.color, b.seed + 60), [dx - dw / 2 + 0.14, fl + dh / 2, front + 0.04]);
    } else {
      box(g, dw, dh, 0.08, doorMat(r.door.color, b.seed + 60), [dx, fl + dh / 2, front + 0.04]);
      for (const y of [fl + dh * 0.25, fl + dh * 0.75]) box(g, dw - 0.1, 0.07, 0.03, trim, [dx, y, front + 0.09]);
      add(g, new THREE.SphereGeometry(0.04, 6, 4), m.brass, [dx + dw * 0.36, fl + dh * 0.48, front + 0.11]);
    }
    if (!r.awning && !r.porch && r.roof !== "flat" && top + 0.3 < signLow) box(g, dw + 0.5, 0.06, 0.4, trim, [dx, top + 0.18, front + 0.2]);
  }

  // ---- steps
  const stepsAt = (x: number, zFront: number, yTop: number) => {
    const n = Math.max(1, Math.ceil(yTop / 0.2));
    const rh = yTop / n;
    for (let i = 0; i < n; i++) {
      const y = (n - i) * rh;
      box(g, 1.3, y, 0.3, m.greyWood, [x, y / 2, zFront + 0.15 + i * 0.3]);
    }
  };

  // ---- porch: deck, posts, roof, rail
  const signBottom = b.sign ? signDims(b).cy - signDims(b).sh / 2 : Infinity;
  const ceilAttach = Math.min(r.storeys === 2 ? b.h / 2 - 0.05 : b.h - 0.1, signBottom - 0.08, (r.storeys === 2 ? b.h / 2 : b.h) - 0.05);
  if (r.porch) {
    const pd = r.porch.depth;
    const deckY = Math.max(0.22, fl);
    box(g, b.w + 0.1, 0.1, pd, m.midWood, [0, deckY - 0.05, pd / 2], undefined, 1.6);
    box(g, b.w + 0.1, deckY - 0.1, 0.08, m.darkWood, [0, (deckY - 0.1) / 2, pd - 0.04]);
    const n = Math.max(2, Math.round(b.w / 2.2) + 1);
    const postX = Array.from({ length: n }, (_, i) => -b.w / 2 + 0.12 + (i / (n - 1)) * (b.w - 0.24));
    const attach = ceilAttach;
    const outer = r.balcony ? b.h / 2 - 0.06 : attach - 0.35;
    for (const x of postX) box(g, 0.14, outer - deckY, 0.14, trim, [x, deckY + (outer - deckY) / 2, pd - 0.1]);
    if (r.porch.roof && !r.balcony) {
      const ang = Math.atan2(attach - outer, pd);
      const len = Math.hypot(attach - outer, pd) + 0.3;
      box(g, b.w + 0.3, 0.08, len, roofMat, [0, (attach + outer) / 2 + 0.06, pd / 2 + 0.1], [ang, 0, 0], 1.6);
      box(g, b.w + 0.2, 0.16, 0.08, trim, [0, outer - 0.02, pd - 0.08]);
    }
    if (r.porch.rail) {
      const stairX = fac.doorX ?? 0;
      for (let i = 0; i < postX.length - 1; i++) {
        const x0 = postX[i];
        const x1 = postX[i + 1];
        if (stairX > x0 && stairX < x1) {
          // leave a gap for the steps
          const segs: [number, number][] = [[x0, stairX - 0.7], [stairX + 0.7, x1]];
          for (const [a, c] of segs) if (c - a > 0.2) {
            box(g, c - a, 0.07, 0.07, trim, [(a + c) / 2, deckY + 0.85, pd - 0.1]);
            for (let x = a + 0.12; x < c - 0.05; x += 0.18) box(g, 0.04, 0.75, 0.04, trim, [x, deckY + 0.42, pd - 0.1]);
          }
        } else {
          box(g, x1 - x0, 0.07, 0.07, trim, [(x0 + x1) / 2, deckY + 0.85, pd - 0.1]);
          for (let x = x0 + 0.12; x < x1 - 0.05; x += 0.18) box(g, 0.04, 0.75, 0.04, trim, [x, deckY + 0.42, pd - 0.1]);
        }
      }
    }
    if (r.steps) stepsAt(fac.doorX ?? 0, pd, deckY);
  } else if (r.steps && fl > 0.05 && fac.doorX !== null) {
    stepsAt(fac.doorX, 0.0, fl);
  }

  // ---- balcony on the upper floor (its deck roofs the porch)
  if (r.balcony) {
    const bd = 1.3;
    const yb = b.h / 2;
    box(g, b.w + 0.1, 0.12, bd, m.midWood, [0, yb, bd / 2], undefined, 1.6);
    const n = Math.max(2, Math.round(b.w / 2.2) + 1);
    for (let i = 0; i < n; i++) {
      const x = -b.w / 2 + 0.12 + (i / (n - 1)) * (b.w - 0.24);
      if (!r.porch) box(g, 0.14, yb, 0.14, trim, [x, yb / 2, bd - 0.1]);
      box(g, 0.1, 0.95, 0.1, trim, [x, yb + 0.5, bd - 0.08]);
    }
    box(g, b.w + 0.1, 0.08, 0.08, trim, [0, yb + 0.95, bd - 0.08]);
    for (let x = -b.w / 2 + 0.2; x < b.w / 2 - 0.1; x += 0.2) box(g, 0.04, 0.8, 0.04, trim, [x, yb + 0.48, bd - 0.08]);
    for (const s of [-1, 1]) {
      box(g, 0.08, 0.08, bd, trim, [(s * (b.w + 0.02)) / 2, yb + 0.95, bd / 2]);
      for (let z = 0.2; z < bd - 0.1; z += 0.2) box(g, 0.04, 0.8, 0.04, trim, [(s * (b.w + 0.02)) / 2, yb + 0.48, z]);
    }
    if (fac.doorX !== null) {
      // a door out onto it
      box(g, 0.95, 2.0, 0.07, trim, [fac.doorX, yb + 1.05, 0.02]);
      box(g, 0.8, 1.9, 0.08, doorMat(r.door?.color ?? { hue: 22, sat: 0.3, light: 0.3 }, b.seed + 61), [fac.doorX, yb + 1.02, 0.04]);
    }
  }

  // ---- awning over the ground-floor openings
  if (r.awning && !r.porch) {
    const ad = r.awning.depth;
    const attach = Math.min(winY + 0.72, ceilAttach, fac.doorTop + 0.45);
    const drop = r.awning.kind === "canvas" ? 0.5 : 0.35;
    const ang = Math.atan2(drop, ad);
    const len = Math.hypot(drop, ad);
    const aw = fac.slots.length ? Math.min(b.w - 0.2, Math.max(...fac.slots) - Math.min(...fac.slots) + 1.6) : b.w * 0.8;
    const cm = r.awning.kind === "canvas"
      ? lam(clothTex(b.seed + 70, 42, 0.2, 0.82, r.awning.stripe, 7), 0xffffff, { side: THREE.DoubleSide })
      : lam(T.planks({ seed: b.seed + 70, planks: 5, hue: b.roof.hue, sat: b.roof.sat * 0.7, light: b.roof.light, vertical: true }));
    box(g, aw, 0.05, len, cm, [0, attach - drop / 2, ad / 2], [ang, 0, 0], 1.2);
    if (r.awning.kind === "canvas") {
      // a scalloped valance hanging from the front edge
      const n = Math.max(4, Math.round(aw / 0.32));
      const pts: [number, number][] = [[-aw / 2, 0], [aw / 2, 0]];
      for (let i = n; i >= 0; i--) {
        const x = -aw / 2 + (i / n) * aw;
        pts.push([x, -0.22]);
        if (i > 0) pts.push([x - aw / n / 2, -0.14]);
      }
      add(g, shapeGeo(pts), cm, [0, attach - drop, ad + 0.01]);
      for (const s of [-1, 1]) rod(g, [(s * aw) / 2.1, attach - 0.6, 0.02], [(s * aw) / 2.1, attach - drop, ad], 0.015, m.iron, 4);
    } else {
      for (const s of [-1, 1]) {
        rod(g, [(s * aw) / 2.1, attach - 0.75, 0.02], [(s * aw) / 2.1, attach - drop - 0.02, ad - 0.1], 0.04, m.darkWood, 5);
      }
    }
  }

  // ---- sign: same board and height as the round-2 builder (signDims is shared
  // with the checker, so its geometry must not move)
  if (b.sign) {
    const sd = signDims(b);
    const sm = new THREE.MeshLambertMaterial({ map: T.signBoard(b.sign.text, b.sign.bg, b.sign.fg, sd.cw, sd.ch) });
    g.add(mesh(new THREE.BoxGeometry(sd.sw, sd.sh, 0.1), [trim, trim, trim, trim, sm, trim], [0, sd.cy, 0.08]));
  }

  // ---- chimney
  if (r.chimney) {
    const c = chimneyPlace(b, r, rise);
    const cm = r.chimney.kind === "brick" ? lam(brickTex(b.seed + 80, 10, 0.4, 0.42)) : m.stone;
    if (c.outside) {
      // a tapered stone stack against the side wall: wide firebox, narrow flue
      box(g, c.size + 0.3, b.h * 0.55, 0.9, cm, [c.x, (b.h * 0.55) / 2, c.z], undefined, 1.2);
      const hh = c.top - b.h * 0.55;
      box(g, c.size - 0.15, hh, 0.6, cm, [c.x, b.h * 0.55 + hh / 2, c.z], undefined, 1.2);
      box(g, c.size, 0.12, 0.75, m.stoneDark, [c.x, c.top + 0.06, c.z], undefined, 1.2);
      // shoulder
      box(g, c.size + 0.1, 0.3, 0.8, cm, [c.x, b.h * 0.55 + 0.1, c.z], [0, 0, 0], 1.2);
    } else {
      box(g, c.size, c.top - c.bottom, c.size, cm, [c.x, (c.top + c.bottom) / 2, c.z], undefined, 1.2);
      box(g, c.size + 0.14, 0.12, c.size + 0.14, m.stoneDark, [c.x, c.top + 0.06, c.z]);
    }
    g.userData.smoke = [new THREE.Vector3(c.x, c.top + 0.25, c.z)];
  }

  return g;
};
