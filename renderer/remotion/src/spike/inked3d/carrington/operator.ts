// An original character: a young night-shift telegraph operator. Round head,
// green eyeshade, curly moustache, teal waistcoat, red sleeve garters. Drawn
// seated (the desk hides the stool), about 3.5 heads tall standing.
// Canvas space is 512 x 1024; the plane's bottom edge is the porch floor.
import type { DrawFn } from "../kit/Cutout";

export type Pose = "tap" | "recoil" | "reach" | "hold";
export type Expr = "focus" | "smile" | "shock" | "amazed";

export const INK = "#1b1033";
export const SKIN = "#f6b98a";
export const SKIN_SHADE = "#e0906a";
const VEST = "#13a39b";
const SHIRT = "#fff3dc";
const GARTER = "#e8344a";
const TROUSER = "#5a3a8c";
const VISOR = "rgba(40, 210, 120, 0.82)";

type P = [number, number];

export const stroke = (ctx: CanvasRenderingContext2D, w = 6) => {
  ctx.lineWidth = w;
  ctx.strokeStyle = INK;
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  ctx.stroke();
};

export const limb = (ctx: CanvasRenderingContext2D, pts: P[], width: number, color: string) => {
  ctx.beginPath();
  ctx.moveTo(...pts[0]);
  for (const p of pts.slice(1)) ctx.lineTo(...p);
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.strokeStyle = INK;
  ctx.lineWidth = width + 12;
  ctx.stroke();
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.stroke();
};

export const hand = (ctx: CanvasRenderingContext2D, p: P, open = false) => {
  ctx.beginPath();
  ctx.arc(p[0], p[1], 22, 0, Math.PI * 2);
  ctx.fillStyle = SKIN;
  ctx.fill();
  stroke(ctx, 5);
  if (open) {
    for (let i = -1; i <= 1; i++) {
      ctx.beginPath();
      const a = -Math.PI / 2 + i * 0.5;
      ctx.moveTo(p[0] + Math.cos(a) * 18, p[1] + Math.sin(a) * 18);
      ctx.lineTo(p[0] + Math.cos(a) * 36, p[1] + Math.sin(a) * 36);
      ctx.strokeStyle = INK;
      ctx.lineWidth = 15;
      ctx.stroke();
      ctx.strokeStyle = SKIN;
      ctx.lineWidth = 8;
      ctx.stroke();
    }
  }
};

// arm: shoulder -> elbow -> hand, with a red garter on the upper arm
const arm = (ctx: CanvasRenderingContext2D, s: P, e: P, h: P, open = false) => {
  limb(ctx, [s, e, h], 20, SHIRT);
  const g: P = [s[0] + (e[0] - s[0]) * 0.55, s[1] + (e[1] - s[1]) * 0.55];
  ctx.beginPath();
  ctx.arc(g[0], g[1], 12, 0, Math.PI * 2);
  ctx.fillStyle = GARTER;
  ctx.fill();
  stroke(ctx, 4);
  hand(ctx, h, open);
};

const ARMS: Record<Pose, { l: [P, P, P]; r: [P, P, P]; lean: number; lOpen?: boolean; rOpen?: boolean }> = {
  // viewer's left = his right hand on the key
  tap: { l: [[192, 362], [138, 446], [184, 508]], r: [[320, 362], [372, 470], [318, 548]], lean: 0 },
  recoil: { l: [[192, 362], [112, 330], [98, 236]], r: [[320, 362], [400, 330], [414, 236]], lean: -18, lOpen: true, rOpen: true },
  reach: { l: [[192, 362], [138, 446], [184, 508]], r: [[320, 362], [404, 414], [472, 392]], lean: 6 },
  hold: { l: [[192, 362], [140, 440], [176, 512]], r: [[320, 362], [418, 380], [448, 300]], lean: -6, lOpen: true },
};

const face = (ctx: CanvasRenderingContext2D, expr: Expr, blink: boolean) => {
  const ey = 212;
  const ex = [204, 308];
  const big = expr === "shock" || expr === "amazed";
  // brows
  for (const [i, x] of ex.entries()) {
    ctx.beginPath();
    const up = big ? -26 : expr === "focus" ? 2 : -8;
    const tilt = expr === "focus" ? (i === 0 ? 6 : -6) : 0;
    ctx.moveTo(x - 26, ey - 46 + up + tilt);
    ctx.quadraticCurveTo(x, ey - 60 + up, x + 26, ey - 46 + up - tilt);
    stroke(ctx, 7);
  }
  for (const x of ex) {
    if (blink) {
      ctx.beginPath();
      ctx.moveTo(x - 24, ey + 4);
      ctx.quadraticCurveTo(x, ey + 18, x + 24, ey + 4);
      stroke(ctx, 6);
      continue;
    }
    const ry = big ? 40 : expr === "focus" ? 22 : 30;
    const rx = big ? 31 : 26;
    ctx.beginPath();
    ctx.ellipse(x, ey, rx, ry, 0, 0, Math.PI * 2);
    ctx.fillStyle = "#ffffff";
    ctx.fill();
    stroke(ctx, 5);
    const pr = expr === "shock" ? 8 : expr === "amazed" ? 15 : 12;
    const py = expr === "focus" ? ey + 8 : expr === "amazed" ? ey - 6 : ey;
    ctx.beginPath();
    ctx.arc(x + (expr === "focus" ? -4 : 0), py, pr, 0, Math.PI * 2);
    ctx.fillStyle = "#2a1650";
    ctx.fill();
    if (expr === "amazed") {
      ctx.beginPath();
      ctx.arc(x + 5, py - 6, 5, 0, Math.PI * 2);
      ctx.fillStyle = "#ffffff";
      ctx.fill();
    }
    if (expr === "focus") {
      // heavy upper lid
      ctx.beginPath();
      ctx.ellipse(x, ey - 8, rx + 2, ry - 6, 0, Math.PI, Math.PI * 2);
      ctx.fillStyle = SKIN_SHADE;
      ctx.fill();
      stroke(ctx, 5);
    }
  }
  // nose
  ctx.beginPath();
  ctx.ellipse(256, 262, 20, 16, 0, 0, Math.PI * 2);
  ctx.fillStyle = "#f08a78";
  ctx.fill();
  stroke(ctx, 5);
  // curly moustache
  ctx.beginPath();
  ctx.moveTo(256, 280);
  ctx.bezierCurveTo(230, 300, 196, 300, 190, 278);
  ctx.bezierCurveTo(186, 266, 200, 262, 204, 272);
  ctx.moveTo(256, 280);
  ctx.bezierCurveTo(282, 300, 316, 300, 322, 278);
  ctx.bezierCurveTo(326, 266, 312, 262, 308, 272);
  ctx.strokeStyle = "#7a3d1f";
  ctx.lineWidth = 12;
  ctx.stroke();
  stroke(ctx, 3);
  // mouth
  ctx.beginPath();
  if (expr === "smile") {
    ctx.moveTo(232, 306);
    ctx.quadraticCurveTo(256, 328, 280, 306);
    stroke(ctx, 6);
  } else if (expr === "focus") {
    ctx.moveTo(244, 312);
    ctx.lineTo(268, 310);
    stroke(ctx, 6);
  } else if (expr === "shock") {
    ctx.moveTo(228, 312);
    for (let i = 0; i <= 6; i++) ctx.lineTo(228 + i * 9, 312 + (i % 2 ? 14 : 0));
    ctx.lineTo(282, 340);
    ctx.lineTo(228, 340);
    ctx.closePath();
    ctx.fillStyle = "#7a1d3a";
    ctx.fill();
    stroke(ctx, 5);
  } else {
    ctx.ellipse(256, 322, 16, 22, 0, 0, Math.PI * 2);
    ctx.fillStyle = "#7a1d3a";
    ctx.fill();
    stroke(ctx, 5);
  }
};

export const drawOperator =
  (pose: Pose, expr: Expr, blink: boolean): DrawFn =>
  (ctx) => {
    const a = ARMS[pose];
    ctx.save();
    // lean: rotate the upper body about the hips
    ctx.translate(256, 640);
    ctx.rotate((a.lean * Math.PI) / 180 / 4);
    ctx.translate(-256, -640);

    // legs (seated, knees forward, mostly hidden by the desk)
    limb(ctx, [[226, 630], [214, 820], [210, 990]], 30, TROUSER);
    limb(ctx, [[286, 630], [298, 820], [302, 990]], 30, TROUSER);
    for (const x of [200, 312]) {
      ctx.beginPath();
      ctx.ellipse(x, 996, 34, 16, 0, 0, Math.PI * 2);
      ctx.fillStyle = "#6b2e2e";
      ctx.fill();
      stroke(ctx, 5);
    }

    // arms behind the body for poses where they hang back
    // torso: shirt + waistcoat
    ctx.beginPath();
    ctx.moveTo(180, 352);
    ctx.quadraticCurveTo(256, 334, 332, 352);
    ctx.lineTo(320, 640);
    ctx.quadraticCurveTo(256, 656, 192, 640);
    ctx.closePath();
    ctx.fillStyle = SHIRT;
    ctx.fill();
    stroke(ctx);
    ctx.beginPath();
    ctx.moveTo(186, 362);
    ctx.lineTo(236, 372);
    ctx.lineTo(256, 470);
    ctx.lineTo(276, 372);
    ctx.lineTo(326, 362);
    ctx.lineTo(318, 640);
    ctx.quadraticCurveTo(256, 656, 194, 640);
    ctx.closePath();
    ctx.fillStyle = VEST;
    ctx.fill();
    stroke(ctx, 5);
    ctx.fillStyle = "#ffd34d";
    for (let i = 0; i < 4; i++) {
      ctx.beginPath();
      ctx.arc(256, 500 + i * 36, 7, 0, Math.PI * 2);
      ctx.fill();
      stroke(ctx, 3);
    }
    // watch chain
    ctx.beginPath();
    ctx.moveTo(256, 540);
    ctx.quadraticCurveTo(290, 570, 312, 548);
    ctx.strokeStyle = "#ffd34d";
    ctx.lineWidth = 4;
    ctx.stroke();

    // neck + bow tie
    ctx.beginPath();
    ctx.rect(238, 300, 36, 52);
    ctx.fillStyle = SKIN_SHADE;
    ctx.fill();
    stroke(ctx, 5);
    ctx.beginPath();
    ctx.moveTo(256, 360);
    ctx.lineTo(224, 344);
    ctx.lineTo(224, 378);
    ctx.closePath();
    ctx.moveTo(256, 360);
    ctx.lineTo(288, 344);
    ctx.lineTo(288, 378);
    ctx.closePath();
    ctx.fillStyle = GARTER;
    ctx.fill();
    stroke(ctx, 4);

    arm(ctx, ...a.l, a.lOpen);
    arm(ctx, ...a.r, a.rOpen);

    // head
    for (const x of [116, 396]) {
      ctx.beginPath();
      ctx.arc(x, 222, 30, 0, Math.PI * 2);
      ctx.fillStyle = SKIN_SHADE;
      ctx.fill();
      stroke(ctx, 5);
    }
    ctx.beginPath();
    ctx.arc(256, 196, 140, 0, Math.PI * 2);
    ctx.fillStyle = SKIN;
    ctx.fill();
    stroke(ctx, 7);
    // hair tufts at the sides
    ctx.fillStyle = "#c2552b";
    for (const s of [-1, 1]) {
      ctx.beginPath();
      ctx.moveTo(256 + s * 132, 150);
      ctx.quadraticCurveTo(256 + s * 162, 180, 256 + s * 140, 226);
      ctx.quadraticCurveTo(256 + s * 122, 190, 256 + s * 112, 150);
      ctx.closePath();
      ctx.fill();
      stroke(ctx, 4);
    }
    // cheeks
    ctx.fillStyle = "rgba(240, 110, 120, 0.35)";
    for (const x of [176, 336]) {
      ctx.beginPath();
      ctx.ellipse(x, 262, 22, 14, 0, 0, Math.PI * 2);
      ctx.fill();
    }
    face(ctx, expr, blink);
    // eyeshade: band + translucent bill
    ctx.beginPath();
    ctx.moveTo(118, 136);
    ctx.quadraticCurveTo(256, 96, 394, 136);
    ctx.lineTo(394, 112);
    ctx.quadraticCurveTo(256, 70, 118, 112);
    ctx.closePath();
    ctx.fillStyle = "#1e7f4f";
    ctx.fill();
    stroke(ctx, 5);
    ctx.beginPath();
    ctx.moveTo(100, 140);
    ctx.quadraticCurveTo(256, 100, 412, 140);
    ctx.quadraticCurveTo(420, 172, 380, 176);
    ctx.quadraticCurveTo(256, 150, 132, 176);
    ctx.quadraticCurveTo(92, 172, 100, 140);
    ctx.closePath();
    ctx.fillStyle = VISOR;
    ctx.fill();
    stroke(ctx, 5);
    ctx.restore();
  };

export const OPERATOR_STATES: Record<string, DrawFn> = {
  "tap:focus": drawOperator("tap", "focus", false),
  "tap:focus:blink": drawOperator("tap", "focus", true),
  "tap:smile": drawOperator("tap", "smile", false),
  "tap:smile:blink": drawOperator("tap", "smile", true),
  "recoil:shock": drawOperator("recoil", "shock", false),
  "reach:shock": drawOperator("reach", "shock", false),
  "hold:shock": drawOperator("hold", "shock", false),
  "hold:amazed": drawOperator("hold", "amazed", false),
  "hold:amazed:blink": drawOperator("hold", "amazed", true),
};
