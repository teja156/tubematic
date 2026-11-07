// Procedural "hand-painted" textures drawn on 2D canvases. Everything is seeded,
// so the same call always produces the same pixels.
import * as THREE from "three";
import { makeRng, range, Rng } from "./prng";

export const makeCanvas = (w: number, h: number) => {
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  const ctx = c.getContext("2d");
  if (!ctx) throw new Error("2d context unavailable");
  return { c, ctx };
};

export const toTexture = (c: HTMLCanvasElement, repeat = true) => {
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  if (repeat) {
    t.wrapS = THREE.RepeatWrapping;
    t.wrapT = THREE.RepeatWrapping;
  }
  t.anisotropy = 4;
  t.needsUpdate = true;
  return t;
};

const hsl = (h: number, s: number, l: number, a = 1) =>
  `hsla(${h.toFixed(1)},${(s * 100).toFixed(1)}%,${(l * 100).toFixed(1)}%,${a})`;

// Loose painterly strokes over a region: the "brush" pass every texture shares.
const brush = (
  ctx: CanvasRenderingContext2D,
  rng: Rng,
  x: number,
  y: number,
  w: number,
  h: number,
  hue: number,
  sat: number,
  light: number,
  count: number,
  horizontal: boolean,
) => {
  for (let i = 0; i < count; i++) {
    const len = range(rng, 0.2, 0.7) * (horizontal ? w : h);
    const px = x + rng() * w;
    const py = y + rng() * h;
    ctx.strokeStyle = hsl(
      hue + range(rng, -8, 8),
      Math.min(1, sat + range(rng, -0.1, 0.1)),
      light + range(rng, -0.09, 0.09),
      range(rng, 0.12, 0.35),
    );
    ctx.lineWidth = range(rng, 1.5, 5);
    ctx.lineCap = "round";
    ctx.beginPath();
    ctx.moveTo(px, py);
    if (horizontal) {
      ctx.quadraticCurveTo(px + len / 2, py + range(rng, -3, 3), px + len, py + range(rng, -2, 2));
    } else {
      ctx.quadraticCurveTo(px + range(rng, -3, 3), py + len / 2, px + range(rng, -2, 2), py + len);
    }
    ctx.stroke();
  }
};

const GAP = "hsl(22, 60%, 21%)"; // plank gaps / joins: a dark brown TINT (the reference paints seams #571e00-#6b2903 at half ink contrast), never black or violet

export interface PlankOpts {
  seed: number;
  size?: number;
  planks: number; // planks across the texture
  hue: number;
  sat: number;
  light: number;
  vertical?: boolean;
  painted?: { hue: number; sat: number; light: number; wear: number };
  clapboard?: boolean; // overlapping siding with a shadow lip
}

// Wood planks: per-plank colour jitter, wavy grain, knots, dark gaps, nails,
// staggered end joints. Optional paint layer worn through to the wood.
export const planks = (o: PlankOpts) => {
  const S = o.size ?? 512;
  const { c, ctx } = makeCanvas(S, S);
  const rng = makeRng(o.seed);
  ctx.fillStyle = GAP;
  ctx.fillRect(0, 0, S, S);
  const pw = S / o.planks;
  ctx.save();
  if (o.vertical) {
    ctx.translate(S, 0);
    ctx.rotate(Math.PI / 2);
  }
  for (let i = 0; i < o.planks; i++) {
    const y0 = i * pw;
    const gap = o.clapboard ? 0 : Math.max(1.5, pw * 0.04);
    const hh = pw - gap;
    // staggered joints along each plank
    const joint = rng() * S;
    for (const [sx, ex] of [
      [0, joint],
      [joint, S],
    ]) {
      const segW = ex - sx - 2;
      if (segW <= 0) continue;
      const l = o.light + range(rng, -0.06, 0.06);
      const h = o.hue + range(rng, -6, 6);
      ctx.fillStyle = hsl(h, o.sat, l);
      ctx.fillRect(sx + 1, y0, segW, hh);
      // grain
      for (let g = 0; g < 9; g++) {
        const gy = y0 + range(rng, 0.1, 0.9) * hh;
        const amp = range(rng, 0.5, 2.5);
        const freq = range(rng, 0.01, 0.04);
        const ph = rng() * 6.28;
        ctx.strokeStyle = hsl(h - 4, o.sat, l - range(rng, 0.08, 0.16), 0.55);
        ctx.lineWidth = range(rng, 0.8, 1.8);
        ctx.beginPath();
        for (let x = sx; x <= ex; x += 6) {
          const yy = gy + Math.sin(x * freq + ph) * amp;
          if (x === sx) ctx.moveTo(x, yy);
          else ctx.lineTo(x, yy);
        }
        ctx.stroke();
      }
      // knot
      if (rng() < 0.5) {
        const kx = sx + range(rng, 0.2, 0.8) * segW;
        const ky = y0 + hh * range(rng, 0.3, 0.7);
        ctx.strokeStyle = hsl(h - 8, o.sat, l - 0.18, 0.8);
        ctx.lineWidth = 1.5;
        for (let r = 1; r < 4; r++) {
          ctx.beginPath();
          ctx.ellipse(kx, ky, r * 4, r * 1.6, 0, 0, Math.PI * 2);
          ctx.stroke();
        }
      }
      brush(ctx, rng, sx, y0, segW, hh, h, o.sat, l, 14, true);
      // paint, worn at the edges
      if (o.painted) {
        const p = o.painted;
        ctx.fillStyle = hsl(p.hue + range(rng, -4, 4), p.sat, p.light + range(rng, -0.04, 0.04));
        ctx.fillRect(sx + 1, y0, segW, hh);
        brush(ctx, rng, sx, y0, segW, hh, p.hue, p.sat, p.light, 22, true);
        // worn patches reveal the wood underneath
        const wearCount = Math.floor(p.wear * 10);
        for (let k = 0; k < wearCount; k++) {
          ctx.fillStyle = hsl(h, o.sat, l, 0.85);
          ctx.beginPath();
          ctx.ellipse(
            sx + rng() * segW,
            y0 + (rng() < 0.5 ? hh * 0.12 : hh * 0.88),
            range(rng, 6, 26),
            range(rng, 1.5, 4),
            0,
            0,
            Math.PI * 2,
          );
          ctx.fill();
        }
      }
      // nails at the ends
      ctx.fillStyle = "hsl(250, 30%, 20%)";
      for (const nx of [sx + 7, ex - 9]) {
        ctx.beginPath();
        ctx.arc(nx, y0 + hh * 0.5, 2.2, 0, Math.PI * 2);
        ctx.fill();
      }
      // joint line
      ctx.fillStyle = GAP;
      ctx.fillRect(ex - 1.5, y0, 3, hh);
    }
    if (o.clapboard) {
      // shadow lip under each overlapping board
      const g = ctx.createLinearGradient(0, y0 + hh - pw * 0.28, 0, y0 + hh);
      g.addColorStop(0, "hsla(255,50%,15%,0)");
      g.addColorStop(1, "hsla(255,55%,12%,0.85)");
      ctx.fillStyle = g;
      ctx.fillRect(0, y0 + hh - pw * 0.28, S, pw * 0.28);
      ctx.fillStyle = GAP;
      ctx.fillRect(0, y0 + hh - 2, S, 2.5);
    }
  }
  ctx.restore();
  return toTexture(c);
};

// Roof shingles: offset rows, rounded butts, dark joins.
export const shingles = (seed: number, hue: number, sat: number, light: number) => {
  const S = 512;
  const { c, ctx } = makeCanvas(S, S);
  const rng = makeRng(seed);
  ctx.fillStyle = GAP;
  ctx.fillRect(0, 0, S, S);
  const rows = 8;
  const rh = S / rows;
  for (let r = 0; r < rows; r++) {
    const cols = 7;
    const cw = S / cols;
    const off = r % 2 ? cw / 2 : 0;
    for (let k = -1; k <= cols; k++) {
      const x = k * cw + off;
      const l = light + range(rng, -0.07, 0.07);
      const h = hue + range(rng, -7, 7);
      ctx.fillStyle = hsl(h, sat, l);
      ctx.beginPath();
      ctx.moveTo(x + 2, r * rh);
      ctx.lineTo(x + cw - 2, r * rh);
      ctx.lineTo(x + cw - 2, r * rh + rh - 8);
      ctx.quadraticCurveTo(x + cw / 2, r * rh + rh + 2, x + 2, r * rh + rh - 8);
      ctx.closePath();
      ctx.fill();
      brush(ctx, rng, x + 3, r * rh, cw - 6, rh - 6, h, sat, l, 5, false);
      // shadow under the next row
      ctx.fillStyle = hsl(h, sat, l - 0.18, 0.6);
      ctx.fillRect(x + 2, r * rh, cw - 4, 5);
    }
  }
  return toTexture(c);
};

// Cobblestones: jittered grid of rounded stones on a dark joint bed.
export const cobbles = (seed: number) => {
  const S = 1024;
  const { c, ctx } = makeCanvas(S, S);
  const rng = makeRng(seed);
  ctx.fillStyle = "hsl(258, 30%, 34%)";
  ctx.fillRect(0, 0, S, S);
  // irregular setts in staggered courses of varying length
  const rows = 14;
  const rh = S / rows;
  for (let j = 0; j < rows; j++) {
    let x = -rng() * rh;
    while (x < S) {
      const w = rh * range(rng, 0.9, 1.6);
      const hue = range(rng, 14, 40);
      const l = range(rng, 0.47, 0.57);
      const pts: [number, number][] = [];
      const cx = x + w / 2;
      const cy = j * rh + rh / 2;
      for (let k = 0; k < 7; k++) {
        const a = (k / 7) * Math.PI * 2;
        const rr = range(rng, 0.82, 1.0);
        pts.push([cx + Math.cos(a) * (w / 2 - 3) * rr, cy + Math.sin(a) * (rh / 2 - 3) * rr]);
      }
      for (const dx of [0, -S, S]) {
        ctx.fillStyle = hsl(hue, 0.45, l);
        ctx.beginPath();
        pts.forEach(([px, py], k) => (k === 0 ? ctx.moveTo(px + dx, py) : ctx.lineTo(px + dx, py)));
        ctx.closePath();
        ctx.fill();
        ctx.fillStyle = hsl(hue + 10, 0.55, l + 0.12, 0.55);
        ctx.beginPath();
        ctx.ellipse(cx + dx - w * 0.1, cy - rh * 0.12, w * 0.28, rh * 0.18, 0, 0, Math.PI * 2);
        ctx.fill();
      }
      x += w;
    }
  }
  brush(ctx, makeRng(seed + 1), 0, 0, S, S, 30, 0.4, 0.5, 120, true);
  return toTexture(c);
};

// Packed dirt with ruts and pebbles.
export const dirt = (seed: number, hue: number, sat: number, light: number) => {
  // Round 4: a richer ground. Large soft mottling (damp / dry patches), a
  // scatter of pebbles with a lit top and a shadowed base, dark flecks, pale
  // grit and a few grass stalks, so the ground reads as stuff rather than a
  // flat tone. 1024 px so the tile can cover 8 m without going soft.
  const S = 1024;
  const { c, ctx } = makeCanvas(S, S);
  const rng = makeRng(seed);
  ctx.fillStyle = hsl(hue, sat, light);
  ctx.fillRect(0, 0, S, S);
  for (let i = 0; i < 70; i++) {
    const g = ctx.createRadialGradient(0, 0, 0, 0, 0, 1);
    const dl = range(rng, -0.09, 0.07);
    g.addColorStop(0, hsl(hue + range(rng, -8, 8), sat * range(rng, 0.8, 1.1), light + dl, 0.5));
    g.addColorStop(1, hsl(hue, sat, light + dl, 0));
    ctx.save();
    ctx.translate(rng() * S, rng() * S);
    ctx.rotate(rng() * 3);
    ctx.scale(range(rng, 60, 220), range(rng, 30, 120));
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(0, 0, 1, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }
  for (let i = 0; i < 500; i++) {
    ctx.fillStyle = hsl(hue + range(rng, -10, 10), sat, light + range(rng, -0.1, 0.08), range(rng, 0.12, 0.35));
    ctx.beginPath();
    ctx.ellipse(rng() * S, rng() * S, range(rng, 8, 60), range(rng, 3, 18), rng() * 3, 0, Math.PI * 2);
    ctx.fill();
  }
  // pebbles: shadow, body, highlight
  for (let i = 0; i < 420; i++) {
    const x = rng() * S;
    const y = rng() * S;
    const r = range(rng, 2, 7);
    ctx.fillStyle = hsl(hue, sat * 0.5, light - 0.28, 0.55);
    ctx.beginPath();
    ctx.ellipse(x + r * 0.3, y + r * 0.45, r * 1.1, r * 0.8, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = hsl(hue + range(rng, -20, 20), sat * 0.4, light + range(rng, -0.12, 0.1));
    ctx.beginPath();
    ctx.ellipse(x, y, r, r * 0.78, rng() * 3, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = hsl(hue, sat * 0.3, light + 0.22, 0.6);
    ctx.beginPath();
    ctx.ellipse(x - r * 0.25, y - r * 0.3, r * 0.4, r * 0.25, 0, 0, Math.PI * 2);
    ctx.fill();
  }
  for (let i = 0; i < 700; i++) {
    ctx.fillStyle = rng() < 0.5 ? hsl(hue + 5, sat * 0.6, light - 0.22, 0.7) : hsl(hue, sat * 0.4, light + 0.18, 0.7);
    ctx.beginPath();
    ctx.arc(rng() * S, rng() * S, range(rng, 1, 2.5), 0, Math.PI * 2);
    ctx.fill();
  }
  // sparse grass stalks
  for (let i = 0; i < 90; i++) {
    const x = rng() * S;
    const y = rng() * S;
    ctx.strokeStyle = hsl(hue + 55 + range(rng, -10, 10), 0.4, light - 0.2, 0.8);
    ctx.lineWidth = 2;
    for (let k = 0; k < 4; k++) {
      ctx.beginPath();
      ctx.moveTo(x + k * 3 - 4, y);
      ctx.lineTo(x + k * 3 - 4 + range(rng, -5, 5), y - range(rng, 8, 16));
      ctx.stroke();
    }
  }
  brush(ctx, rng, 0, 0, S, S, hue, sat, light, 80, true);
  return toTexture(c);
};

// Stone foundation blocks with mortar joins.
export const stoneBlocks = (seed: number) => {
  const S = 512;
  const { c, ctx } = makeCanvas(S, S);
  const rng = makeRng(seed);
  ctx.fillStyle = "hsl(255, 30%, 22%)";
  ctx.fillRect(0, 0, S, S);
  const rows = 6;
  const rh = S / rows;
  for (let r = 0; r < rows; r++) {
    let x = r % 2 ? -rh * 0.6 : 0;
    while (x < S) {
      const w = rh * range(rng, 1.1, 2.0);
      const l = range(rng, 0.5, 0.64);
      const hue = range(rng, 200, 240);
      ctx.fillStyle = hsl(hue, 0.22, l);
      ctx.beginPath();
      ctx.roundRect(x + 3, r * rh + 3, w - 6, rh - 6, 6);
      ctx.fill();
      brush(ctx, rng, x + 4, r * rh + 4, w - 8, rh - 8, hue, 0.25, l, 6, true);
      x += w;
    }
  }
  return toTexture(c);
};

// Bark-ish vertical grain for poles and trunks.
export const bark = (seed: number, hue: number, light: number) => {
  const S = 256;
  const { c, ctx } = makeCanvas(S, S);
  const rng = makeRng(seed);
  ctx.fillStyle = hsl(hue, 0.45, light);
  ctx.fillRect(0, 0, S, S);
  for (let i = 0; i < 40; i++) {
    const x = rng() * S;
    ctx.strokeStyle = hsl(hue - 5, 0.5, light - range(rng, 0.1, 0.2), 0.7);
    ctx.lineWidth = range(rng, 1, 3);
    ctx.beginPath();
    ctx.moveTo(x, 0);
    for (let y = 0; y <= S; y += 16) ctx.lineTo(x + Math.sin(y * 0.05 + i) * 3, y);
    ctx.stroke();
  }
  brush(ctx, rng, 0, 0, S, S, hue, 0.45, light, 30, false);
  return toTexture(c);
};

// Painted sign board with lettering.
export const signBoard = (text: string, bg: string, fg: string, w = 1024, h = 256) => {
  const { c, ctx } = makeCanvas(w, h);
  const rng = makeRng(text.length * 97);
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, w, h);
  brush(ctx, rng, 0, 0, w, h, 45, 0.7, 0.55, 50, true);
  ctx.strokeStyle = fg;
  ctx.lineWidth = 10;
  ctx.strokeRect(14, 14, w - 28, h - 28);
  ctx.fillStyle = fg;
  ctx.font = `bold ${Math.floor(h * 0.52)}px serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(text, w / 2, h / 2 + 6);
  return toTexture(c, false);
};

// Soft round puff (smoke, glow) with alpha.
export const softDot = (inner: string, outer: string) => {
  const S = 128;
  const { c, ctx } = makeCanvas(S, S);
  const g = ctx.createRadialGradient(S / 2, S / 2, 0, S / 2, S / 2, S / 2);
  g.addColorStop(0, inner);
  g.addColorStop(1, outer);
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, S, S);
  return toTexture(c, false);
};

// Foliage blotches for tree crowns.
export const foliage = (seed: number, hue: number) => {
  const S = 256;
  const { c, ctx } = makeCanvas(S, S);
  const rng = makeRng(seed);
  ctx.fillStyle = hsl(hue, 0.6, 0.35);
  ctx.fillRect(0, 0, S, S);
  for (let i = 0; i < 140; i++) {
    ctx.fillStyle = hsl(hue + range(rng, -12, 12), 0.65, range(rng, 0.25, 0.5), 0.6);
    ctx.beginPath();
    ctx.ellipse(rng() * S, rng() * S, range(rng, 5, 16), range(rng, 3, 9), rng() * 3, 0, Math.PI * 2);
    ctx.fill();
  }
  return toTexture(c);
};
