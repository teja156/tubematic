// An original second character: a freckled newsboy with a purple flat cap, an
// oversized orange scarf and a satchel of papers. Standing, ~3.5 heads tall.
// Canvas 512 x 1024; the bottom edge is the ground.
import type { DrawFn } from "../kit/Cutout";
import { hand, INK, limb, SKIN, SKIN_SHADE, stroke } from "./operator";

type P = [number, number];
export type BoyPose = "walkA" | "walkB" | "point";
export type BoyExpr = "smile" | "awe";

const CAP = "#7b3fc4";
const SHIRT = "#ffd84a";
const STRIPE = "#ff6a3d";
const PANTS = "#2f6fd6";
const SCARF = "#ff8a1f";
const BAG = "#c4733a";

const POSES: Record<BoyPose, { la: [P, P, P]; ra: [P, P, P]; ll: [P, P, P]; rl: [P, P, P]; raOpen?: boolean }> = {
  walkA: {
    la: [[196, 350], [168, 450], [182, 548]],
    ra: [[316, 350], [352, 446], [378, 530]],
    ll: [[232, 640], [196, 800], [176, 975]],
    rl: [[280, 640], [312, 800], [340, 975]],
  },
  walkB: {
    la: [[196, 350], [150, 440], [132, 528]],
    ra: [[316, 350], [336, 452], [324, 552]],
    ll: [[232, 640], [222, 806], [214, 975]],
    rl: [[280, 640], [286, 806], [296, 975]],
  },
  point: {
    la: [[196, 350], [160, 452], [176, 548]],
    ra: [[316, 350], [384, 260], [430, 150]],
    ll: [[232, 640], [214, 806], [204, 975]],
    rl: [[280, 640], [298, 806], [310, 975]],
    raOpen: false,
  },
};

const face = (ctx: CanvasRenderingContext2D, expr: BoyExpr, blink: boolean) => {
  const ey = expr === "awe" ? 168 : 182;
  for (const x of [208, 304]) {
    // brows
    ctx.beginPath();
    const up = expr === "awe" ? -22 : 0;
    ctx.moveTo(x - 22, ey - 40 + up);
    ctx.quadraticCurveTo(x, ey - 52 + up, x + 22, ey - 40 + up);
    stroke(ctx, 7);
    if (blink) {
      ctx.beginPath();
      ctx.moveTo(x - 20, ey + 2);
      ctx.quadraticCurveTo(x, ey + 14, x + 20, ey + 2);
      stroke(ctx, 6);
      continue;
    }
    ctx.beginPath();
    ctx.ellipse(x, ey, expr === "awe" ? 26 : 22, expr === "awe" ? 32 : 26, 0, 0, Math.PI * 2);
    ctx.fillStyle = "#ffffff";
    ctx.fill();
    stroke(ctx, 5);
    ctx.beginPath();
    ctx.arc(x + (expr === "awe" ? 0 : 3), ey + (expr === "awe" ? -8 : 2), expr === "awe" ? 12 : 11, 0, Math.PI * 2);
    ctx.fillStyle = "#2a1650";
    ctx.fill();
    ctx.beginPath();
    ctx.arc(x + 4, ey - 12, 4, 0, Math.PI * 2);
    ctx.fillStyle = "#ffffff";
    ctx.fill();
  }
  // freckles
  ctx.fillStyle = "#c8643a";
  for (const [fx, fy] of [[176, 228], [190, 238], [168, 242], [336, 228], [322, 238], [344, 242]] as P[]) {
    ctx.beginPath();
    ctx.arc(fx, fy, 3.5, 0, Math.PI * 2);
    ctx.fill();
  }
  // button nose
  ctx.beginPath();
  ctx.arc(256, 226, 11, 0, Math.PI * 2);
  ctx.fillStyle = "#f08a78";
  ctx.fill();
  stroke(ctx, 4);
  ctx.beginPath();
  if (expr === "smile") {
    ctx.moveTo(220, 256);
    ctx.quadraticCurveTo(256, 292, 292, 256);
    ctx.closePath();
    ctx.fillStyle = "#7a1d3a";
    ctx.fill();
    stroke(ctx, 5);
  } else {
    ctx.ellipse(256, 270, 14, 20, 0, 0, Math.PI * 2);
    ctx.fillStyle = "#7a1d3a";
    ctx.fill();
    stroke(ctx, 5);
  }
};

export const drawNewsboy =
  (pose: BoyPose, expr: BoyExpr, blink: boolean): DrawFn =>
  (ctx) => {
    const p = POSES[pose];
    // legs + shoes
    limb(ctx, p.ll, 30, PANTS);
    limb(ctx, p.rl, 30, PANTS);
    for (const leg of [p.ll, p.rl]) {
      const f = leg[2];
      ctx.beginPath();
      ctx.ellipse(f[0], f[1] + 14, 32, 15, 0, 0, Math.PI * 2);
      ctx.fillStyle = "#8a3a2a";
      ctx.fill();
      stroke(ctx, 5);
    }
    // satchel strap + bag behind the arm
    ctx.beginPath();
    ctx.moveTo(206, 340);
    ctx.lineTo(330, 560);
    ctx.strokeStyle = INK;
    ctx.lineWidth = 18;
    ctx.stroke();
    ctx.strokeStyle = BAG;
    ctx.lineWidth = 10;
    ctx.stroke();
    // body: striped shirt
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(190, 340);
    ctx.quadraticCurveTo(256, 318, 322, 340);
    ctx.lineTo(312, 650);
    ctx.quadraticCurveTo(256, 664, 200, 650);
    ctx.closePath();
    ctx.fillStyle = SHIRT;
    ctx.fill();
    ctx.clip();
    ctx.fillStyle = STRIPE;
    for (let y = 360; y < 660; y += 44) ctx.fillRect(150, y, 220, 16);
    ctx.restore();
    ctx.beginPath();
    ctx.moveTo(190, 340);
    ctx.quadraticCurveTo(256, 318, 322, 340);
    ctx.lineTo(312, 650);
    ctx.quadraticCurveTo(256, 664, 200, 650);
    ctx.closePath();
    stroke(ctx, 6);
    // bag with newspapers
    ctx.beginPath();
    ctx.roundRect(296, 520, 92, 86, 12);
    ctx.fillStyle = BAG;
    ctx.fill();
    stroke(ctx, 5);
    ctx.beginPath();
    ctx.rect(306, 498, 70, 30);
    ctx.fillStyle = "#f4f0e2";
    ctx.fill();
    stroke(ctx, 4);
    for (let i = 0; i < 3; i++) {
      ctx.beginPath();
      ctx.moveTo(312, 506 + i * 8);
      ctx.lineTo(368, 506 + i * 8);
      ctx.strokeStyle = "#8a8aa8";
      ctx.lineWidth = 2;
      ctx.stroke();
    }
    // arms (thin) with mitten hands
    limb(ctx, p.la, 20, SHIRT);
    hand(ctx, p.la[2]);
    limb(ctx, p.ra, 20, SHIRT);
    if (pose === "point") {
      // pointing finger
      const h = p.ra[2];
      ctx.beginPath();
      ctx.moveTo(h[0], h[1]);
      ctx.lineTo(h[0] + 18, h[1] - 40);
      ctx.strokeStyle = INK;
      ctx.lineWidth = 16;
      ctx.lineCap = "round";
      ctx.stroke();
      ctx.strokeStyle = SKIN;
      ctx.lineWidth = 8;
      ctx.stroke();
    }
    hand(ctx, p.ra[2], p.raOpen);
    // neck + scarf
    ctx.beginPath();
    ctx.rect(240, 290, 32, 40);
    ctx.fillStyle = SKIN_SHADE;
    ctx.fill();
    stroke(ctx, 5);
    ctx.beginPath();
    ctx.ellipse(256, 334, 80, 30, 0, 0, Math.PI * 2);
    ctx.fillStyle = SCARF;
    ctx.fill();
    stroke(ctx, 5);
    ctx.beginPath();
    ctx.moveTo(218, 344);
    ctx.lineTo(198, 450);
    ctx.lineTo(232, 446);
    ctx.lineTo(244, 350);
    ctx.closePath();
    ctx.fillStyle = SCARF;
    ctx.fill();
    stroke(ctx, 5);
    // head, ears
    for (const x of [120, 392]) {
      ctx.beginPath();
      ctx.arc(x, 196, 26, 0, Math.PI * 2);
      ctx.fillStyle = SKIN_SHADE;
      ctx.fill();
      stroke(ctx, 5);
    }
    ctx.beginPath();
    ctx.arc(256, 170, 138, 0, Math.PI * 2);
    ctx.fillStyle = SKIN;
    ctx.fill();
    stroke(ctx, 7);
    ctx.fillStyle = "rgba(240, 110, 120, 0.35)";
    for (const x of [172, 340]) {
      ctx.beginPath();
      ctx.ellipse(x, 236, 20, 12, 0, 0, Math.PI * 2);
      ctx.fill();
    }
    face(ctx, expr, blink);
    // flat cap with a stubby peak
    ctx.beginPath();
    ctx.moveTo(112, 128);
    ctx.quadraticCurveTo(140, 28, 262, 26);
    ctx.quadraticCurveTo(392, 30, 404, 118);
    ctx.quadraticCurveTo(256, 92, 112, 128);
    ctx.closePath();
    ctx.fillStyle = CAP;
    ctx.fill();
    stroke(ctx, 6);
    ctx.beginPath();
    ctx.moveTo(150, 118);
    ctx.quadraticCurveTo(250, 82, 350, 112);
    ctx.quadraticCurveTo(370, 140, 330, 138);
    ctx.quadraticCurveTo(250, 116, 168, 142);
    ctx.quadraticCurveTo(130, 138, 150, 118);
    ctx.closePath();
    ctx.fillStyle = "#5a2a9a";
    ctx.fill();
    stroke(ctx, 5);
    ctx.beginPath();
    ctx.arc(262, 34, 10, 0, Math.PI * 2);
    ctx.fillStyle = "#ffd84a";
    ctx.fill();
    stroke(ctx, 4);
  };

export const NEWSBOY_STATES: Record<string, DrawFn> = {
  "walkA:smile": drawNewsboy("walkA", "smile", false),
  "walkB:smile": drawNewsboy("walkB", "smile", false),
  "walkA:smile:blink": drawNewsboy("walkA", "smile", true),
  "point:awe": drawNewsboy("point", "awe", false),
  "point:awe:blink": drawNewsboy("point", "awe", true),
  "point:smile": drawNewsboy("point", "smile", false),
};
