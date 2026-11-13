/*
 * The house critter as paper pieces: a boxy clay body with eyes only and
 * four stubby legs, after the papercut-explainer kit's Critter (MIT). Each
 * expression and accessory is a different piece list, painted once and
 * swapped in a frame, like the kit's rigid cut-out poses.
 */
import { CRITTER, type Accessory, type ColorName, type Expression, type Piece, type PropDef } from "./contract";

const U = CRITTER.size / 10;
const HAT_ROOM = 2.6 * U;                 // room above the body for a hat
export const CRITTER_W = 11.2 * U;
export const CRITTER_H = HAT_ROOM + 7 * U + 2.2 * U;

const SHADES: Record<string, ColorName> = {
  hero: "heroLo", cap: "capLo", sage: "sageLo", amber: "amberDim", purple: "screen", pink: "heroLo",
};

/** The critter in one expression, standing with its feet on the box's bottom edge. */
export function critterDef(body: ColorName, acc: Accessory, expr: Expression | "blink"): PropDef {
  const shade = SHADES[body] ?? "heroLo";
  const ox = 0.6 * U, top = HAT_ROOM;
  const x = (v: number) => ox + v * U;
  const y = (v: number) => top + v * U;
  const p: Piece[] = [];
  for (const lx of [1.2, 3.3, 5.7, 7.8]) {
    p.push({ shape: "rect", fill: body, shade, shadeH: 0.35, x: x(lx), y: y(6.7), w: U, h: 2.5 * U, r: 3 });
  }
  p.push({ shape: "rect", fill: body, shade, shadeH: 0.16, x: x(0), y: y(0), w: 10 * U, h: 7 * U, r: 6 });
  // arms, down at the sides
  p.push({ shape: "rect", fill: body, shade, shadeH: 0.3, x: x(-0.5), y: y(3), w: 1.2 * U, h: 2.6 * U, r: 4 });
  p.push({ shape: "rect", fill: body, shade, shadeH: 0.3, x: x(9.3), y: y(3), w: 1.2 * U, h: 2.6 * U, r: 4 });

  const eyes = [3, 6];
  if (expr === "sleep" || expr === "blink" || expr === "happy") {
    for (const ex of eyes) {
      p.push({ shape: "rect", fill: "ink", x: x(ex - 0.15), y: y(expr === "happy" ? 2.3 : 2.8), w: 1.3 * U, h: 0.3 * U, r: 2,
        rot: expr === "happy" ? (ex === 3 ? -10 : 10) : 0 });
    }
  } else {
    const big = expr === "shock";
    for (const [i, ex] of eyes.entries()) {
      const ew = big ? 1.3 : 1, eh = expr === "squint" ? 0.6 : big ? 2.1 : 1.6;
      const lean = expr === "worried" ? (i ? -0.2 : 0.2) : 0;
      p.push({ shape: "rect", fill: "ink", x: x(ex + lean + (1 - ew) / 2), y: y(2 + (expr === "squint" ? 0.5 : 0)), w: ew * U, h: eh * U, r: 3,
        rot: expr === "worried" ? (i ? 8 : -8) : 0 });
    }
  }
  if (expr === "shock") p.push({ shape: "ellipse", fill: "ink", x: x(4.4), y: y(4.5), w: 1.1 * U, h: 1.1 * U });
  if (expr === "happy") p.push({ shape: "rect", fill: "ink", x: x(4), y: y(4.4), w: 2 * U, h: 0.3 * U, r: 3 });

  switch (acc) {
    case "cap":
      p.push({ shape: "rect", fill: "cap", shade: "capLo", shadeH: 0.28, x: x(1.4), y: y(-2.1), w: 7.2 * U, h: 2.4 * U, r: 26 });
      p.push({ shape: "rect", fill: "capLo", x: x(6.2), y: y(0), w: 4.4 * U, h: 0.75 * U, r: 8 });
      break;
    case "hardhat":
      p.push({ shape: "rect", fill: "amber", shade: "amberDim", shadeH: 0.22, x: x(1), y: y(-2.3), w: 8 * U, h: 2.6 * U, r: 30 });
      p.push({ shape: "rect", fill: "amberDim", x: x(0.2), y: y(0), w: 9.6 * U, h: 0.7 * U, r: 3 });
      break;
    case "headset":
      p.push({ shape: "rect", fill: "board", x: x(-0.3), y: y(1.4), w: 1.3 * U, h: 2.2 * U, r: 8 });
      p.push({ shape: "rect", fill: "board", x: x(0.2), y: y(-0.9), w: 9.6 * U, h: 0.55 * U, r: 4 });
      p.push({ shape: "rect", fill: "board", x: x(0.4), y: y(3.6), w: 3.2 * U, h: 0.3 * U, r: 2, rot: 16 });
      break;
    case "glasses":
      for (const gx of [2.4, 5.6]) p.push({ shape: "ellipse", fill: "ink", x: x(gx), y: y(1.6), w: 2.1 * U, h: 2.1 * U });
      for (const gx of [2.7, 5.9]) p.push({ shape: "ellipse", fill: "metal", x: x(gx), y: y(1.9), w: 1.5 * U, h: 1.5 * U });
      p.push({ shape: "rect", fill: "ink", x: x(4.4), y: y(2.5), w: 1.3 * U, h: 0.3 * U, r: 1 });
      break;
    case "bowtie":
      p.push({ shape: "poly", fill: "nogo", points: [[x(3.4), y(5.8)], [x(5), y(6.6)], [x(3.4), y(7.4)]] });
      p.push({ shape: "poly", fill: "nogo", points: [[x(6.6), y(5.8)], [x(5), y(6.6)], [x(6.6), y(7.4)]] });
      p.push({ shape: "ellipse", fill: "nogoDim", x: x(4.6), y: y(6.2), w: 0.8 * U, h: 0.8 * U });
      break;
    case "beret":
      p.push({ shape: "ellipse", fill: "ink", x: x(1.4), y: y(-1.6), w: 7.8 * U, h: 2 * U, rot: -6 });
      p.push({ shape: "rect", fill: "ink", x: x(4.8), y: y(-2.2), w: 0.6 * U, h: 0.9 * U, r: 3 });
      break;
    case "visor":
      p.push({ shape: "rect", fill: "go", shade: "goDim", shadeH: 0.4, x: x(0.8), y: y(-0.8), w: 9.6 * U, h: 1.2 * U, r: 6 });
      break;
    default:
      break;
  }
  return { w: CRITTER_W, h: CRITTER_H, pieces: p };
}

/** The critter's offset at a frame while idle: a small bob, never still. */
export function bob(frame: number, phase = 0): number {
  return Math.round(Math.sin(((frame + phase) / CRITTER.bobPeriod) * Math.PI * 2) * CRITTER.bobAmp);
}

/** Whether an idle critter's eyes are shut at a frame. */
export function blinking(frame: number): boolean {
  return frame % CRITTER.blinkEvery < CRITTER.blinkFrames;
}
