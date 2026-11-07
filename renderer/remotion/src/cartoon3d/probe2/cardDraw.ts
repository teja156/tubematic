// Canvas drawings for flat cards: the number plate and the background figure.
// Shared by the hand-built parts (parts.ts) and the part compiler, whose
// `card` primitive names one of these by `draw` (see partCompile.ts).
import * as T from "../kit/textures";
import { makeRng } from "../kit/prng";

/** a small lettered number plate */
export const plateTex = (text: string, bg: string, fg: string) => {
  const { c, ctx } = T.makeCanvas(256, 128);
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, 256, 128);
  ctx.strokeStyle = fg;
  ctx.lineWidth = 8;
  ctx.strokeRect(10, 10, 236, 108);
  ctx.fillStyle = fg;
  ctx.font = "700 86px Georgia, 'Times New Roman', serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(text, 128, 68);
  return T.toTexture(c, false);
};

/** A background figure drawn ONCE on a 256 x 512 design canvas (drawn at 2x):
 *  big round head, flat fills, bold ink outline, in the style of the hand-drawn
 *  characters. Everything about it (sex, hat, colours, skin) comes from seed. */
const FIG_INK = "#14102a";
const FIG_OUTFITS: { coat: string; legs: string; shirt: string; hat: string }[] = [
  { coat: "#4a3b8c", legs: "#2a2140", shirt: "#f4ead6", hat: "#2a2140" },
  { coat: "#2f6b5e", legs: "#5a3a2a", shirt: "#f0e2c0", hat: "#3a2a20" },
  { coat: "#8a3a3a", legs: "#2b2b3c", shirt: "#f6eedc", hat: "#8a3a3a" },
  { coat: "#b08a4a", legs: "#3c4a6a", shirt: "#fff4e0", hat: "#6a5030" },
  { coat: "#3b4f7a", legs: "#2a2a30", shirt: "#eee6d0", hat: "#1e1e2a" },
  { coat: "#6a5a4a", legs: "#403020", shirt: "#f2e8d0", hat: "#2c2418" },
  { coat: "#c05a3a", legs: "#3a3050", shirt: "#f8f0dc", hat: "#c05a3a" },
  { coat: "#55683a", legs: "#30261c", shirt: "#f0e8d2", hat: "#55683a" },
];
export const figureTex = (seed: number) => {
  const S = 2;
  const { c, ctx } = T.makeCanvas(256 * S, 512 * S);
  ctx.scale(S, S);
  const rng = makeRng(seed * 31 + 7);
  const pick = <X,>(a: X[]): X => a[Math.floor(rng() * a.length) % a.length];
  const o = FIG_OUTFITS[Math.abs(seed) % FIG_OUTFITS.length];
  const skin = pick(["#f6c9a2", "#e6a97c", "#c98a5e", "#8d5a3b", "#f1b893", "#d9956a"]);
  const hair = pick(["#2a1a10", "#5a3a1e", "#a8702c", "#d8c8a8", "#1a1420"]);
  const female = rng() < 0.4;
  const hat = female ? pick(["bonnet", "bonnet", "hair", "slouch"]) : pick(["top", "bowler", "cap", "slouch", "hair", "top"]);
  const beard = !female && rng() < 0.45;
  ctx.lineWidth = 9;
  ctx.strokeStyle = FIG_INK;
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  const shape = (fill: string, f: () => void, w = 9) => {
    ctx.beginPath();
    f();
    ctx.closePath();
    ctx.fillStyle = fill;
    ctx.fill();
    ctx.lineWidth = w;
    ctx.strokeStyle = FIG_INK;
    ctx.stroke();
  };
  const limb = (a: [number, number], b: [number, number], w: number, color: string) => {
    ctx.beginPath();
    ctx.moveTo(...a);
    ctx.lineTo(...b);
    ctx.lineWidth = w + 16;
    ctx.strokeStyle = FIG_INK;
    ctx.stroke();
    ctx.lineWidth = w;
    ctx.strokeStyle = color;
    ctx.stroke();
  };
  const X = 128;
  const headR = 70;
  const headY = 150;
  const shY = 236;
  const hipY = 372;
  const footY = 500;
  // legs or skirt
  if (female) {
    shape(o.legs, () => {
      ctx.moveTo(X - 52, shY + 70);
      ctx.lineTo(X + 52, shY + 70);
      ctx.lineTo(X + 96, footY - 6);
      ctx.lineTo(X - 96, footY - 6);
    });
    for (const s of [-1, 1]) shape(FIG_INK, () => ctx.ellipse(X + s * 36, footY - 8, 24, 9, 0, 0, Math.PI * 2), 4);
  } else {
    for (const s of [-1, 1]) {
      limb([X + s * 24, hipY], [X + s * 30, footY - 22], 22, o.legs);
      shape("#2b1d14", () => ctx.roundRect(X + s * 30 - 24, footY - 30, 48, 28, 9));
    }
  }
  // coat
  shape(o.coat, () => {
    ctx.moveTo(X - 60, shY);
    ctx.quadraticCurveTo(X, shY - 30, X + 60, shY);
    ctx.lineTo(X + 68, hipY + 12);
    ctx.lineTo(X - 68, hipY + 12);
  });
  // shirt front
  shape(o.shirt, () => {
    ctx.moveTo(X - 20, shY - 6);
    ctx.lineTo(X + 20, shY - 6);
    ctx.lineTo(X, shY + 50);
  }, 7);
  // arms by the sides, hands
  for (const s of [-1, 1]) {
    limb([X + s * 54, shY + 14], [X + s * 76, hipY - 20], 22, o.coat);
    shape(skin, () => ctx.arc(X + s * 78, hipY - 6, 16, 0, Math.PI * 2), 7);
  }
  // bonnet back (behind the head)
  if (hat === "bonnet") shape(o.shirt, () => ctx.arc(X, headY - 8, headR + 18, 0, Math.PI * 2));
  // neck and head
  shape(skin, () => ctx.rect(X - 16, headY + headR - 16, 32, 36), 7);
  shape(skin, () => ctx.arc(X, headY, headR, 0, Math.PI * 2));
  // face: eyes, mouth
  ctx.fillStyle = FIG_INK;
  for (const s of [-1, 1]) {
    ctx.beginPath();
    ctx.arc(X + s * 26, headY - 4, 7, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.beginPath();
  ctx.arc(X, headY + 26, 16, 0.25, Math.PI - 0.25);
  ctx.lineWidth = 6;
  ctx.strokeStyle = FIG_INK;
  ctx.stroke();
  if (beard) {
    shape(hair, () => {
      ctx.moveTo(X - 36, headY + 18);
      ctx.quadraticCurveTo(X, headY + 10, X + 36, headY + 18);
      ctx.quadraticCurveTo(X + 30, headY + 70, X, headY + 74);
      ctx.quadraticCurveTo(X - 30, headY + 70, X - 36, headY + 18);
    }, 7);
    ctx.beginPath();
    ctx.arc(X, headY + 30, 14, 0.3, Math.PI - 0.3);
    ctx.lineWidth = 5;
    ctx.strokeStyle = FIG_INK;
    ctx.stroke();
  } else if (!female && rng() < 0.5) {
    // moustache
    shape(hair, () => ctx.ellipse(X, headY + 18, 30, 7, 0, 0, Math.PI * 2), 5);
  }
  // hair or hat
  const top = headY - headR;
  if (hat === "hair" || hat === "bonnet") {
    shape(hair, () => {
      ctx.arc(X, headY - 8, headR + 2, Math.PI, 0);
      ctx.quadraticCurveTo(X, headY - 20, X - headR - 2, headY - 8);
    });
    if (female) shape(hair, () => ctx.arc(X + 50, headY - 56, 24, 0, Math.PI * 2));
  }
  if (hat === "bonnet") {
    // ribbon bow under the chin
    for (const s of [-1, 1]) shape(o.shirt, () => ctx.ellipse(X + s * 18, headY + headR + 10, 16, 10, s * 0.6, 0, Math.PI * 2), 5);
  }
  if (hat === "top") {
    shape(o.hat, () => ctx.rect(X - 50, top - 68, 100, 86));
    shape(o.hat, () => ctx.ellipse(X, top + 16, 82, 12, 0, 0, Math.PI * 2));
    ctx.fillStyle = "#b8a070";
    ctx.fillRect(X - 46, top + 2, 92, 9);
  } else if (hat === "bowler") {
    shape(o.hat, () => {
      ctx.arc(X, top + 18, 56, Math.PI, 0);
      ctx.lineTo(X + 56, top + 18);
    });
    shape(o.hat, () => ctx.ellipse(X, top + 18, 76, 11, 0, 0, Math.PI * 2));
  } else if (hat === "cap") {
    shape(o.hat, () => {
      ctx.arc(X, top + 22, 60, Math.PI, 0);
      ctx.lineTo(X + 60, top + 22);
    });
    shape(o.hat, () => ctx.ellipse(X, top + 26, 70, 9, 0, 0, Math.PI * 2));
  } else if (hat === "slouch") {
    shape(o.hat, () => ctx.ellipse(X, top + 16, 96, 16, 0, 0, Math.PI * 2));
    shape(o.hat, () => {
      ctx.moveTo(X - 50, top + 16);
      ctx.quadraticCurveTo(X - 44, top - 60, X, top - 56);
      ctx.quadraticCurveTo(X + 44, top - 60, X + 50, top + 16);
    });
  }
  return T.toTexture(c, false);
};
