// Hand-painted look textures drawn on canvases (cached): grass, cobbles, stone courses, deck planks, water,
// river bed, roof tiles, bricks, plaster facades with windows/doors/timber frames, iron chain links.
import * as THREE from "three";

export const rng = (seed: number) => {
  let s = (seed * 9301 + 49297) % 233280 || 1;
  return () => { s = (s * 16807) % 2147483647; return (s - 1) / 2147483646; };
};
const cache = new Map<string, THREE.CanvasTexture>();
export const ctex = (key: string, w: number, h: number, draw: (g: CanvasRenderingContext2D, r: () => number) => void) => {
  let t = cache.get(key);
  if (!t) {
    const cv = document.createElement("canvas");
    cv.width = w; cv.height = h;
    draw(cv.getContext("2d")!, rng(key.length * 131 + key.charCodeAt(0)));
    t = new THREE.CanvasTexture(cv);
    t.colorSpace = THREE.SRGBColorSpace;
    t.anisotropy = 8;
    t.wrapS = t.wrapT = THREE.RepeatWrapping;
    cache.set(key, t);
  }
  return t;
};
/** clone with its own repeat */
export const rep = (t: THREE.Texture, x: number, y: number) => {
  const c = t.clone(); c.repeat.set(x, y); c.needsUpdate = true; return c;
};
const pick = <T,>(r: () => number, a: T[]) => a[Math.floor(r() * a.length) % a.length];
const INKL = "rgba(40,30,40,0.85)";
const _jc = new THREE.Color(), _hsl = { h: 0, s: 0, l: 0 };
/** per-tile colour jitter in sRGB HSL: lightness x(1 +- dv), hue +- dh degrees, saturation x(1 +- ds) -> css hex.
 *  (MAT pass: reviewer saw tiled brick / cobbles / blocks; about +-10 % per tile breaks the repetition) */
export const jit = (r: () => number, hex: string, dv = 0.1, dh = 5, ds = 0.15) => {
  _jc.set(hex).getHSL(_hsl);
  const k = (a: number) => 1 + (r() * 2 - 1) * a;
  _jc.setHSL((_hsl.h + ((r() * 2 - 1) * dh) / 360 + 1) % 1, Math.min(1, _hsl.s * k(ds)), Math.min(0.97, _hsl.l * k(dv)));
  return "#" + _jc.getHexString();
};

export const grass = () => ctex("grass", 512, 512, (g, r) => {
  g.fillStyle = "#79b950"; g.fillRect(0, 0, 512, 512);
  for (let i = 0; i < 70; i++) { g.fillStyle = pick(r, ["rgba(96,160,60,.35)", "rgba(140,205,95,.3)"]); g.beginPath(); g.ellipse(r() * 512, r() * 512, 30 + r() * 60, 18 + r() * 30, r() * 3, 0, 7); g.fill(); }
  g.lineCap = "round";
  for (let i = 0; i < 2600; i++) {
    const x = r() * 512, y = r() * 512, l = 5 + r() * 8;
    g.strokeStyle = pick(r, ["#5f9c3d", "#8fcc5f", "#6aa844", "#9ad46a"]); g.lineWidth = 2;
    g.beginPath(); g.moveTo(x, y); g.lineTo(x + (r() - 0.5) * 4, y - l); g.stroke();
  }
  for (let i = 0; i < 30; i++) { g.fillStyle = pick(r, ["#fff7d0", "#ffe066", "#ffb3c8"]); g.beginPath(); g.arc(r() * 512, r() * 512, 3, 0, 7); g.fill(); }
});

export const cobble = () => ctex("cobble", 512, 512, (g, r) => {
  g.fillStyle = "#8f7b5c"; g.fillRect(0, 0, 512, 512);
  for (let y = 0; y < 16; y++) for (let x = 0; x < 16; x++) {
    const cx = x * 32 + 16 + (y % 2) * 16 + (r() - 0.5) * 6, cy = y * 32 + 16 + (r() - 0.5) * 6;
    g.fillStyle = pick(r, ["#cbb68f", "#bfa982", "#d6c39c", "#b49f79"]);
    g.strokeStyle = "rgba(70,55,40,.8)"; g.lineWidth = 2.5;
    g.beginPath(); g.ellipse(cx % 512, cy, 13 + r() * 2, 12 + r() * 2, r(), 0, 7); g.fill(); g.stroke();
    g.fillStyle = "rgba(255,255,255,.18)"; g.beginPath(); g.ellipse((cx % 512) - 4, cy - 4, 5, 3, 0, 0, 7); g.fill();
  }
});

export const stone = (key = "stone", cols = ["#cbbfa6", "#bdb197", "#d4c8ae", "#b3a88f"]) => ctex(key, 512, 512, (g, r) => {
  g.fillStyle = "#5d5446"; g.fillRect(0, 0, 512, 512);
  for (let row = 0; row < 8; row++) {
    let x = row % 2 ? -60 : 0;
    while (x < 512) {
      const w = 90 + r() * 70;
      g.fillStyle = pick(r, cols);
      g.fillRect(x + 3, row * 64 + 3, w - 6, 58);
      g.fillStyle = "rgba(255,255,255,.12)"; g.fillRect(x + 3, row * 64 + 3, w - 6, 8);
      g.fillStyle = "rgba(0,0,0,.08)"; for (let k = 0; k < 6; k++) g.fillRect(x + 6 + r() * (w - 16), row * 64 + 10 + r() * 44, 4, 3);
      x += w;
    }
  }
});

export const planks = () => ctex("planks", 512, 512, (g, r) => {
  for (let i = 0; i < 16; i++) {
    g.fillStyle = pick(r, ["#c68a52", "#b97c46", "#d39a5f", "#bf8550"]);
    g.fillRect(0, i * 32, 512, 32);
    g.strokeStyle = "rgba(120,70,35,.35)"; g.lineWidth = 1.5;
    for (let k = 0; k < 3; k++) { const y = i * 32 + 6 + r() * 20; g.beginPath(); g.moveTo(0, y); g.bezierCurveTo(170, y + 4, 340, y - 4, 512, y + (r() - 0.5) * 4); g.stroke(); }
    g.fillStyle = "#4a2f1c"; g.fillRect(0, i * 32, 512, 3);
    const cut = r() * 512; g.fillRect(cut, i * 32, 3, 32);
    g.fillStyle = "#3b2618"; for (const x of [20, 492]) { g.beginPath(); g.arc(x, i * 32 + 16, 2.5, 0, 7); g.fill(); }
  }
});

export const beam = () => ctex("beam", 256, 256, (g, r) => {
  g.fillStyle = "#a8743f"; g.fillRect(0, 0, 256, 256);
  g.strokeStyle = "rgba(85,48,20,.16)"; g.lineWidth = 2.5;
  for (let i = 0; i < 22; i++) { const y = r() * 256; g.beginPath(); g.moveTo(0, y); g.bezierCurveTo(90, y + 5, 170, y - 5, 256, y); g.stroke(); }
});

export const water = () => ctex("water", 512, 512, (g, r) => {
  const gr = g.createLinearGradient(0, 0, 0, 512); gr.addColorStop(0, "#3d92da"); gr.addColorStop(0.5, "#3487d0"); gr.addColorStop(1, "#3d92da");
  g.fillStyle = gr; g.fillRect(0, 0, 512, 512);
  g.lineCap = "round";
  for (let i = 0; i < 90; i++) {
    const x = r() * 512, y = r() * 512, l = 30 + r() * 70;
    g.strokeStyle = pick(r, ["rgba(140,205,245,.55)", "rgba(110,185,240,.5)", "rgba(220,245,255,.55)"]); g.lineWidth = 3 + r() * 3;
    g.beginPath(); g.moveTo(x, y); g.quadraticCurveTo(x + l / 2, y - 6, x + l, y); g.stroke();
  }
  for (let i = 0; i < 40; i++) { g.fillStyle = "rgba(255,255,255,.8)"; g.fillRect(r() * 512, r() * 512, 6 + r() * 8, 2); }
});

export const bed = () => ctex("bed", 512, 512, (g, r) => {
  g.fillStyle = "#a88f62"; g.fillRect(0, 0, 512, 512);
  for (let i = 0; i < 260; i++) { g.fillStyle = pick(r, ["#8f7a52", "#bca37a", "#9c8a66", "#7d6c4c"]); g.beginPath(); g.ellipse(r() * 512, r() * 512, 4 + r() * 9, 3 + r() * 6, r() * 3, 0, 7); g.fill(); }
});

export const roof = (col: string) => ctex("roof" + col, 512, 512, (g, r) => {
  g.fillStyle = "#3b2a2a"; g.fillRect(0, 0, 512, 512);
  const base = new THREE.Color(col);
  for (let row = 0; row < 16; row++) for (let i = -1; i < 9; i++) {
    const x = i * 64 + (row % 2) * 32, y = row * 32, c = base.clone().offsetHSL(0, 0, (r() - 0.5) * 0.08);
    g.fillStyle = `#${c.getHexString()}`; g.strokeStyle = INKL; g.lineWidth = 2.5;
    g.beginPath(); g.moveTo(x + 2, y); g.lineTo(x + 62, y); g.lineTo(x + 62, y + 22); g.quadraticCurveTo(x + 32, y + 36, x + 2, y + 22); g.closePath(); g.fill(); g.stroke();
    g.fillStyle = "rgba(255,255,255,.12)"; g.fillRect(x + 6, y + 3, 50, 5);
  }
});

/** MAT round 3: brick colour with strong per-brick value variation (lightness +-24 %), plus ~1 in 8 dark clinker
 *  and ~1 in 10 pale, sun-bleached bricks, so a wall reads as hand-laid bricks rather than a flat red print */
const brickCol = (r: () => number) => {
  const c = jit(r, pick(r, ["#c0583a", "#b44f35", "#c8643f", "#a94a33", "#cf6e45", "#b9603f"]), 0.24, 6, 0.15), u = r();
  return u < 0.12 ? dim(c, 0.68) : u > 0.9 ? dim(c, 1.22) : c;
};
/** scale the HSL lightness of a hex colour */
const dim = (hex: string, k: number) => {
  _jc.set(hex).getHSL(_hsl);
  _jc.setHSL(_hsl.h, _hsl.s, Math.min(0.92, _hsl.l * k));
  return "#" + _jc.getHexString();
};
export const brick = () => ctex("brick", 512, 512, (g, r) => {
  g.fillStyle = "#e6d3b3"; g.fillRect(0, 0, 512, 512);
  for (let row = 0; row < 16; row++) for (let i = 0; i < 8; i++) {
    const c = brickCol(r);
    const x = i * 64 + (row % 2) * 32 + 2, y = row * 32 + 2;
    for (const ox of [0, -512]) { // seamless in x
      g.fillStyle = c; g.fillRect(x + ox, y, 60, 28);
      g.fillStyle = "rgba(255,235,210,0.16)"; g.fillRect(x + ox + 2, y, 56, 3); // light top lip
      g.fillStyle = "rgba(70,30,20,0.14)"; g.fillRect(x + ox + 2, y + 25, 56, 3);
    }
  }
  for (let i = 0; i < 9; i++) { // sparse soot / weathering blotches
    const x = r() * 512, y = r() * 512, rad = 30 + r() * 70;
    for (const ox of [-512, 0, 512]) for (const oy of [-512, 0, 512]) {
      g.save(); g.translate(x + ox, y + oy); g.scale(1.3, 1);
      const gr = g.createRadialGradient(0, 0, 0, 0, 0, rad);
      gr.addColorStop(0, "rgba(70,45,35,0.13)"); gr.addColorStop(1, "rgba(70,45,35,0)");
      g.fillStyle = gr; g.fillRect(-rad, -rad, 2 * rad, 2 * rad); g.restore();
    }
  }
});

export const chainTex = () => ctex("chain", 128, 512, (g) => {
  g.fillStyle = "#2c2f36"; g.fillRect(0, 0, 128, 512);
  for (let i = 0; i < 8; i++) {
    g.strokeStyle = "#565c66"; g.lineWidth = 14;
    g.beginPath(); g.ellipse(64, i * 64 + 32, 34, 26, 0, 0, 7); g.stroke();
    g.strokeStyle = "rgba(255,255,255,.22)"; g.lineWidth = 4;
    g.beginPath(); g.ellipse(64, i * 64 + 32, 34, 26, 0, 3.6, 5.4); g.stroke();
  }
});

/** plaster/brick facade, w x h metres at 48 px/m: floors of shuttered windows, optional door + timber frame */
export const facade = (key: string, wm: number, hm: number, o: { wall: string; shutter: string; door?: boolean; timber?: boolean; brick?: boolean }) =>
  ctex("fac" + key, Math.round(wm * 48), Math.round(hm * 48), (g, r) => {
    const W = Math.round(wm * 48), H = Math.round(hm * 48);
    if (o.brick) { g.fillStyle = g.createPattern(brick().image as HTMLCanvasElement, "repeat")!; g.fillRect(0, 0, W, H); }
    else {
      g.fillStyle = o.wall; g.fillRect(0, 0, W, H);
      for (let i = 0; i < 40; i++) { g.fillStyle = `rgba(${r() > 0.5 ? "255,255,255" : "0,0,0"},.05)`; g.beginPath(); g.ellipse(r() * W, r() * H, 20 + r() * 40, 10 + r() * 20, 0, 0, 7); g.fill(); }
    }
    const floors = Math.max(1, Math.floor(hm / 2.8));
    if (o.timber) {
      g.fillStyle = "#5b3a24";
      g.fillRect(0, 0, 10, H); g.fillRect(W - 10, 0, 10, H); g.fillRect(0, 0, W, 10);
      for (let fl = 1; fl < floors; fl++) g.fillRect(0, H - fl * 2.8 * 48 - 5, W, 10);
    }
    g.fillStyle = "rgba(60,45,40,.35)"; g.fillRect(0, H - 22, W, 22);
    const nWin = Math.max(1, Math.floor(wm / 2.2));
    for (let fl = 0; fl < floors; fl++) for (let i = 0; i < nWin; i++) {
      const cx = ((i + 0.5) * W) / nWin, by = H - fl * 2.8 * 48 - 0.9 * 48;
      if (o.door && fl === 0 && i === Math.floor(nWin / 2)) {
        const dw = 1.1 * 48, dh = 2.1 * 48;
        g.fillStyle = "#7a4a2c"; g.strokeStyle = INKL; g.lineWidth = 3;
        g.beginPath(); g.moveTo(cx - dw / 2, H); g.lineTo(cx - dw / 2, H - dh + dw / 2); g.arc(cx, H - dh + dw / 2, dw / 2, Math.PI, 0); g.lineTo(cx + dw / 2, H); g.fill(); g.stroke();
        g.fillStyle = "#e8c45a"; g.beginPath(); g.arc(cx + dw / 3, H - dh / 2, 3.5, 0, 7); g.fill();
        continue;
      }
      const ww = 0.9 * 48, wh = 1.3 * 48, x0 = cx - ww / 2, y0 = by - wh;
      g.fillStyle = o.shutter; g.strokeStyle = INKL; g.lineWidth = 2.5;
      for (const sx of [x0 - ww / 2 - 2, x0 + ww + 2]) { g.fillRect(sx, y0, ww / 2, wh); g.strokeRect(sx, y0, ww / 2, wh); }
      g.fillStyle = "#f4efe2"; g.fillRect(x0 - 4, y0 - 4, ww + 8, wh + 8);
      const gg = g.createLinearGradient(x0, y0, x0 + ww, y0 + wh); gg.addColorStop(0, "#8fd0f5"); gg.addColorStop(1, "#3f7fc0");
      g.fillStyle = gg; g.fillRect(x0, y0, ww, wh);
      g.fillStyle = "rgba(255,255,255,.55)"; g.beginPath(); g.moveTo(x0 + 6, y0 + wh * 0.55); g.lineTo(x0 + ww * 0.55, y0 + 6); g.lineTo(x0 + ww * 0.75, y0 + 6); g.lineTo(x0 + 6, y0 + wh * 0.8); g.fill();
      g.fillStyle = "#f4efe2"; g.fillRect(cx - 2, y0, 4, wh); g.fillRect(x0, y0 + wh / 2 - 2, ww, 4);
      g.strokeRect(x0 - 4, y0 - 4, ww + 8, wh + 8);
      g.fillStyle = "#e6dccb"; g.fillRect(x0 - 8, by, ww + 16, 7); g.strokeRect(x0 - 8, by, ww + 16, 7);
    }
  });

// ---------------- HD painters (textures.md 5.1, from compare/textures/proto/paint_recipe.ts) ----------------
type R = () => number;
type G = CanvasRenderingContext2D;
const U = (r: R, a: number, b: number) => a + (b - a) * r();
const TAU = Math.PI * 2;

/** run fn at x and again one tile over when [x, x + w] crosses the left / right edge (seamless repeat in x) */
const wrapX = (W: number, x: number, w: number, fn: (x: number) => void) => {
  fn(x);
  if (x + w > W) fn(x - W);
  if (x < 0) fn(x + W);
};
/** same for a scattered mark of radius rad, in x and y */
const wrap2 = (W: number, H: number, x: number, y: number, rad: number, fn: (x: number, y: number) => void) => {
  for (const ox of [0, -W, W]) for (const oy of [0, -H, H]) {
    const X = x + ox, Y = y + oy;
    if (X + rad > 0 && X - rad < W && Y + rad > 0 && Y - rad < H) fn(X, Y);
  }
};
/** rounded-rectangle path */
const rr = (g: G, x: number, y: number, w: number, h: number, k: number) => {
  k = Math.max(0, Math.min(k, w / 2, h / 2));
  g.beginPath();
  g.moveTo(x + k, y);
  g.arcTo(x + w, y, x + w, y + h, k); g.arcTo(x + w, y + h, x, y + h, k);
  g.arcTo(x, y + h, x, y, k); g.arcTo(x, y, x + w, y, k);
  g.closePath();
};
/** soft elliptical blotch (radial gradient) stretched sx along x */
const blotch = (g: G, x: number, y: number, rad: number, sx: number, rgb: string, a: number) => {
  g.save(); g.translate(x, y); g.scale(sx, 1);
  const gr = g.createRadialGradient(0, 0, 0, 0, 0, rad);
  gr.addColorStop(0, `rgba(${rgb},${a})`); gr.addColorStop(1, `rgba(${rgb},0)`);
  g.fillStyle = gr; g.fillRect(-rad, -rad, rad * 2, rad * 2);
  g.restore();
};
/** long, soft wood-grain stroke along +x; random offsets drawn once so the wrapped copy matches */
const grain = (g: G, r: R, W: number, x: number, y: number, len: number, amp: number, lw: number, col: string) => {
  const n = Math.max(2, Math.round(len / 180));
  const dy = Array.from({ length: n + 1 }, () => (r() - 0.5) * 2 * amp);
  wrapX(W, x, len, (xx) => {
    g.strokeStyle = col; g.lineWidth = lw; g.lineCap = "round";
    g.beginPath(); g.moveTo(xx, y + dy[0]);
    for (let i = 1; i <= n; i++) {
      const x1 = xx + (len * i) / n;
      g.quadraticCurveTo(x1 - len / n / 2, y + (dy[i - 1] + dy[i]) / 2 + (i % 2 ? 0.3 : -0.3) * amp, x1, y + dy[i]);
    }
    g.stroke();
  });
};
/** nail / bolt head with a small painted glint (ref: dark dots with a white catch-light) */
const nail = (g: G, x: number, y: number, rad: number, col = "#3a2212") => {
  g.fillStyle = col; g.beginPath(); g.arc(x, y, rad, 0, TAU); g.fill();
  g.fillStyle = "rgba(255,240,215,0.55)"; g.beginPath(); g.arc(x - rad * 0.32, y - rad * 0.32, rad * 0.36, 0, TAU); g.fill();
};

// ---------------------------------------------------------------------------------------------------------------
/** Deck top, transverse boards. 2048 px = 2 m x 2 m (1024 texels/m: the 0.5 m lens then magnifies ~5.8 px per
 *  texel, the same as the reference's closest deck shot, 10-90 % edge ramp ~4.8 px at 1080p).
 *  Canvas y runs along the bridge (z): 8 boards of 0.25 m = 256 px. world.ts deckTop uv -> [0, z / 2, 2.5, z / 2].
 *  Ref: board-to-board L* std 1.2-4.2 (ours 5-6), within-board 1.3-2.6, gaps ~4 % of the pitch (FWHM) dark brown
 *  #571e00-#6b2903 (dL* 40-48), sunlit lip +4..7 L*, shaded lip -3..-6 L*, nails + rare knots. */
export const planksHD = () => ctex("planksHD", 2048, 2048, (g, r) => {
  const S = 2048, B = 256, GAP = 12;
  // albedo: under the current day light sunlit boards must then measure L* 72-80 on screen (ref #f8bb60, #dea04b,
  // #e28c29, #ffab49). MAT round 3: the merged grade lifts deck chroma ~x1.4 and hue ~+10 deg (the #eaa45a set landed
  // as lemon #f1b333, C* 70, h 80), so these are ochre / tan albedos (Lab L 61-69, C* 31-35, h 64-70): on screen
  // ochre wood about C* 45, h 72-78
  const fills = ["#c99669", "#c18e64", "#d19f6e", "#bb8961", "#c69466", "#c79b6f"];
  for (let i = 0; i < 8; i++) {
    const y = i * B;
    g.save(); g.beginPath(); g.rect(0, y, S, B); g.clip();
    g.fillStyle = jit(r, pick(r, fills), 0.05, 3, 0.08); g.fillRect(0, y, S, B);
    for (let k = 0; k < 5; k++) { // broad tone drift along the board, +-2 L*
      const x = U(r, 0, S), rad = U(r, 120, 260), light = r() > 0.5;
      wrapX(S, x - rad * 3, rad * 6, (xx) => blotch(g, xx + rad * 3, y + B / 2, rad, 3, light ? "255,236,200" : "110,60,25", light ? 0.12 : 0.1));
    }
    for (let k = 0; k < 18; k++) { // grain: long, thin, clearly visible; never as dark or as wide as a seam
      const light = r() < 0.25;
      grain(g, r, S, U(r, 0, S), y + U(r, 16, B - 16), U(r, 500, 1600), U(r, 2, 8), U(r, 2, 4),
        light ? "rgba(255,232,195,0.2)" : "rgba(95,48,18,0.3)");
    }
    for (let k = 0; k < 4; k++) // a few longer figure lines (darker, still thinner than a seam)
      grain(g, r, S, U(r, 0, S), y + U(r, 30, B - 30), U(r, 900, 1900), U(r, 4, 10), 3.5, "rgba(70,32,10,0.4)");
    if (r() < 0.35) { // knot, about one board in three
      const kx = U(r, 120, S - 120), ky = y + U(r, 70, B - 70), rx = U(r, 14, 24), ry = rx * U(r, 0.45, 0.6);
      g.strokeStyle = "rgba(140,82,36,0.20)"; g.lineWidth = 2;
      g.beginPath(); g.ellipse(kx, ky, rx * 2.3, ry * 1.9, 0, 0, TAU); g.stroke();
      g.fillStyle = "rgba(150,88,38,0.30)"; g.beginPath(); g.ellipse(kx, ky, rx, ry, 0, 0, TAU); g.fill();
      g.strokeStyle = "rgba(105,55,22,0.55)"; g.lineWidth = 2.5; g.stroke();
    }
    for (let k = 0; k < 3; k++) blotch(g, U(r, 100, S - 100), y + U(r, 40, B - 40), U(r, 40, 110), 1.6, "120,70,30", 0.06); // wear
    // board edges: sunlit lip on one side, soft darkening on the other
    g.fillStyle = "rgba(255,238,200,0.35)"; g.fillRect(0, y + GAP / 2 + 1, S, 3);
    const sh = g.createLinearGradient(0, y + B - GAP / 2 - 18, 0, y + B - GAP / 2);
    sh.addColorStop(0, "rgba(80,35,10,0)"); sh.addColorStop(1, "rgba(80,35,10,0.24)");
    g.fillStyle = sh; g.fillRect(0, y + B - GAP / 2 - 18, S, 18);
    // one butt joint per board per tile (staggered), nailed both sides; joist nails every 1 m
    const jx = U(r, 90, S - 90);
    g.fillStyle = "#24110a"; g.fillRect(jx - 3, y, 7, B);
    g.fillStyle = "rgba(255,238,200,0.30)"; g.fillRect(jx + 4, y, 2, B);
    for (const nx of [jx - 24, jx + 24]) for (const f of [0.28, 0.72]) nail(g, nx, y + B * f, 5, "#22140c");
    for (const nx of [512, 1536]) for (const f of [0.3, 0.7]) nail(g, nx + U(r, -3, 3), y + B * f, 5, "#22140c");
    g.restore();
  }
  for (let i = 0; i <= 8; i++) { // seams last: 12 px near-black core + 3 px soft rim (~5 % of the pitch: survives mips)
    g.fillStyle = "rgba(40,18,8,0.6)"; g.fillRect(0, i * B - GAP / 2 - 3, S, GAP + 6);
    g.fillStyle = "#1c0c05"; g.fillRect(0, i * B - GAP / 2, S, GAP);
  }
});

/** Deck side beams / stringers: 1024 x 512 = 3 m along the beam x 1 m (matches the side uv: z / 3, height in m).
 *  Ours rendered #231001 (L* 7, reads as a black hole); ref timber in shade stays at L* 27-34 (#77331b, #632918). */
export const beamHD = () => ctex("beamHD", 1024, 512, (g, r) => {
  const W = 1024, H = 512, T = H / 7; // 0.143 m timbers
  for (let k = 0; k < 7; k++) {
    const y = k * T;
    g.save(); g.beginPath(); g.rect(0, y, W, T); g.clip();
    g.fillStyle = pick(r, ["#a8743f", "#9e6b39", "#b07a44"]); g.fillRect(0, y, W, T);
    for (let i = 0; i < 6; i++) {
      const light = r() < 0.3;
      grain(g, r, W, U(r, 0, W), y + U(r, 8, T - 8), U(r, 250, 700), U(r, 1.5, 4), U(r, 1.5, 3), light ? "rgba(255,232,190,0.12)" : "rgba(85,48,20,0.16)");
    }
    g.fillStyle = "rgba(255,235,195,0.30)"; g.fillRect(0, y + 3, W, 3);
    const sh = g.createLinearGradient(0, y + T - 12, 0, y + T);
    sh.addColorStop(0, "rgba(60,28,8,0)"); sh.addColorStop(1, "rgba(60,28,8,0.26)");
    g.fillStyle = sh; g.fillRect(0, y + T - 12, W, 12);
    const jx = U(r, 120, W - 120);
    g.fillStyle = "#4a2510"; g.fillRect(jx - 2, y, 4, T);
    for (const bx of [jx - 30, jx + 30]) nail(g, bx, y + T / 2, 7, "#2f2a2a");
    g.restore();
    g.fillStyle = "#4a2510"; g.fillRect(0, y - 1.5, W, 3); // seam between timbers
  }
});

/** Ashlar courses, 1024 px per tile: with boxGeo tile 2 (towers) courses are 0.25 m at 512 texels/m; with the 4 m
 *  quad tile (quay walls) 0.5 m blocks. Ref: blocks #c2b2a5 / #cdbdb0 (C* 5-12), mortar dL* -14..-20 and only
 *  2.8-3.6 px wide at 1080p (ours #503f26, 5.4 px, yellow C* 18), top bevel +5 L*, bottom -3 L*, 2-4 px speckles,
 *  hairline cracks. Joint = 7 px = 5.5 % of a course. */
/** MAT pass: warm palettes per key. The two-tone shade multiplies by a blue-violet (shade.ts), so the old neutral
 *  greys rendered lavender on every shaded tower / quay face; warm sandstone / cream albedos stay warm in shade. */
// MAT round 3: saturation -35 % (HSL) on every stone palette -> neutral warm grey / beige, not cream-pink
const STONE_PAL: Record<string, { cols: string[]; mortar: string }> = {
  stoneHD: { cols: ["#d6c4a8", "#cbb89c", "#decfb5", "#c2ae91", "#d0bea2"], mortar: "#a08e76" },
  towerHD: { cols: ["#d6c4a8", "#cbb89c", "#decfb5", "#c2ae91", "#d0bea2"], mortar: "#a08e76" },
  tstoneHD: { cols: ["#e2d5bc", "#d7c8ac", "#e9dec9", "#ccbca1"], mortar: "#a69881" },
  wallHD: { cols: ["#c3b198", "#b8a68b", "#cdbda3", "#af9c83", "#beac94"], mortar: "#887762" },
  copeHD: { cols: ["#e5d9c1", "#dbcdb5", "#ebe1ce", "#d3c4ac"], mortar: "#a99982" },
};
/** keys painted on a 2048 canvas shown at repeat 0.5: same block size and texel density, half as many repeats */
const STONE_BIG = new Set(["towerHD", "tstoneHD", "wallHD", "stoneHD"]);
export const stoneHD = (key = "stoneHD", cols = ["#ddd0bf", "#d3c5b3", "#e5d9c9", "#cabba8"], mortar = "#a39584") => {
  const pal = STONE_PAL[key];
  if (pal) { cols = pal.cols; mortar = pal.mortar; }
  const S = STONE_BIG.has(key) ? 2048 : 1024;
  const t = ctex(key, S, S, (g, r) => {
    const RH = 128, J = 7;
    g.fillStyle = mortar; g.fillRect(0, 0, S, S);
    for (let row = 0; row < S / RH; row++) {
      const y = row * RH, ws: number[] = [];
      let sum = 0;
      while (sum < S) { const w = U(r, 200, 360); ws.push(w); sum += w; }
      const k = S / sum; // stretch so every course closes exactly on the tile width
      let x = (row % 2) * 140 + U(r, 0, 60);
      for (const w0 of ws) {
        const w = w0 * k, col = jit(r, pick(r, cols), 0.1, 5, 0.18), dl = U(r, -1, 1);
        const sp = Array.from({ length: 16 }, () => [r(), r(), U(r, 1, 2.2), r() < 0.6 ? 1 : 0]);
        const crack = r() < 0.15 ? Array.from({ length: 4 }, () => [r(), r()]) : null;
        wrapX(S, x % S, w, (xx) => {
          const X = xx + J / 2, Y = y + J / 2, BW = w - J, BH = RH - J;
          rr(g, X, Y, BW, BH, 5); g.fillStyle = col; g.fill();
          g.fillStyle = dl > 0 ? `rgba(255,252,245,${0.07 * dl})` : `rgba(70,55,45,${-0.06 * dl})`; g.fill();
          g.fillStyle = "rgba(255,252,245,0.22)"; g.fillRect(X + 3, Y, BW - 6, 6);        // top bevel
          g.fillStyle = "rgba(255,252,245,0.10)"; g.fillRect(X, Y + 4, 4, BH - 8);        // left bevel
          g.fillStyle = "rgba(70,55,45,0.14)"; g.fillRect(X + 3, Y + BH - 5, BW - 6, 5); // bottom shade
          for (const [u, v, s, dark] of sp) {
            g.fillStyle = dark ? "rgba(95,82,72,0.38)" : "rgba(255,255,255,0.35)";
            g.beginPath(); g.arc(X + 6 + u * (BW - 12), Y + 8 + v * (BH - 16), s, 0, TAU); g.fill();
          }
          if (crack) {
            g.strokeStyle = "rgba(110,90,70,0.45)"; g.lineWidth = 1.2; g.beginPath();
            crack.forEach(([u, v], i) => { const px = X + 10 + u * (BW - 20), py = Y + 10 + v * (BH - 20); if (i) g.lineTo(px, py); else g.moveTo(px, py); });
            g.stroke();
          }
        });
        x += w;
      }
    }
    // sparse grime: soft dirt patches across several blocks and a few rain streaks (break the tile repetition)
    const n = (S / 1024) ** 2;
    for (let i = 0; i < 14 * n; i++) {
      const x = U(r, 0, S), y = U(r, 0, S), rad = U(r, 50, 170), dark = r() < 0.75;
      wrap2(S, S, x, y, rad * 1.4, (xx, yy) => blotch(g, xx, yy, rad, 1.4, dark ? "105,82,55" : "255,246,225", dark ? U(r, 0.07, 0.13) : 0.09));
    }
    for (let i = 0; i < 8 * n; i++) {
      const x = U(r, 0, S), y = U(r, 0, S * 0.8), w = U(r, 8, 26), h = U(r, 90, 300);
      const gr = g.createLinearGradient(0, y, 0, y + h);
      gr.addColorStop(0, "rgba(95,75,52,0.14)"); gr.addColorStop(1, "rgba(95,75,52,0)");
      wrapX(S, x, w, (xx) => { g.fillStyle = gr; g.fillRect(xx, y, w, h); });
    }
    for (let i = 0; i < 160 * n; i++) { // pebble-size dark / light pits
      const x = U(r, 0, S), y = U(r, 0, S), s = U(r, 1.2, 3), d = r() < 0.65;
      g.fillStyle = d ? "rgba(90,70,50,0.32)" : "rgba(255,248,230,0.35)";
      g.beginPath(); g.arc(x, y, s, 0, TAU); g.fill();
    }
  });
  t.repeat.set(1024 / S, 1024 / S);
  return t;
};

/** Cobbled quay: granite setts in staggered courses, 1024 px = 4 m (256 texels/m; setts 0.19-0.28 x 0.167 m).
 *  Replaces the polka-dot ellipses (ours: regular grid, dark rims, L* std 20): low tone spread, sand-coloured
 *  joints, a soft top-left light and bottom-right shade per sett, no outline ring. */
export const cobbleHD = () => { const t = ctex("cobbleHD", 2048, 2048, (g, r) => {
  // MAT pass: 2048 px = 8 m shown at repeat 0.5 (same sett size, half the repeats), warm granite (neutral greys went
  // lavender in shade), +-10 % per-sett value / hue jitter, sparse dirt, pebbles in the joints
  const S = 2048, N = 48, CH = S / N, J = 5;
  g.fillStyle = "#867967"; g.fillRect(0, 0, S, S);
  const cols = ["#c4b6a0", "#b8aa93", "#cdc1ab", "#af9f88", "#c7baa3", "#bdb19b", "#b8ad9c"]; // round 3: sat -35 %
  for (let row = 0; row < N; row++) {
    const y = row * CH, ws: number[] = [];
    let sum = 0;
    while (sum < S) { const w = U(r, 48, 72); ws.push(w); sum += w; }
    const k = S / sum;
    let x = U(r, 0, 60);
    for (const w0 of ws) {
      const w = w0 * k, col = jit(r, pick(r, cols), 0.1, 6, 0.2), dy = U(r, -1.5, 1.5), rad = U(r, 7, 12);
      const sp = Array.from({ length: 3 }, () => [r(), r(), r() < 0.5 ? 1 : 0]);
      wrapX(S, x % S, w, (xx) => {
        const X = xx + J / 2, Y = y + J / 2 + dy, W = w - J, H = CH - J;
        rr(g, X, Y, W, H, rad); g.fillStyle = col; g.fill();
        g.save(); rr(g, X, Y, W, H, rad); g.clip();
        const gr = g.createLinearGradient(X, Y, X + W * 0.6, Y + H);
        gr.addColorStop(0, "rgba(255,250,240,0.20)"); gr.addColorStop(0.5, "rgba(255,250,240,0)"); gr.addColorStop(1, "rgba(70,58,45,0.16)");
        g.fillStyle = gr; g.fillRect(X, Y, W, H);
        g.restore();
        for (const [u, v, d] of sp) {
          g.fillStyle = d ? "rgba(90,80,68,0.35)" : "rgba(255,255,255,0.3)";
          g.beginPath(); g.arc(X + 5 + u * (W - 10), Y + 5 + v * (H - 10), 1.4, 0, TAU); g.fill();
        }
      });
      x += w;
    }
  }
  for (let i = 0; i < 40; i++) { // damp / worn / sun-bleached patches
    const x = U(r, 0, S), y = U(r, 0, S), rad = U(r, 60, 220), d = r() < 0.7;
    wrap2(S, S, x, y, rad * 1.3, (xx, yy) => blotch(g, xx, yy, rad, 1.3, d ? "90,70,48" : "255,244,220", d ? U(r, 0.06, 0.12) : 0.1));
  }
  for (let i = 0; i < 260; i++) { // pebbles and grit dabs (ref: sparse cream pebble dabs), some dark
    const x = U(r, 0, S), y = U(r, 0, S), rx = U(r, 2, 5), d = r() < 0.4;
    wrap2(S, S, x, y, 8, (xx, yy) => {
      g.fillStyle = d ? "rgba(95,78,58,0.55)" : pick(r, ["rgba(245,232,205,0.8)", "rgba(230,214,185,0.8)"]);
      g.beginPath(); g.ellipse(xx, yy, rx, rx * 0.75, 0, 0, TAU); g.fill();
    });
  }
});
t.repeat.set(0.5, 0.5);
return t; };

/** Roof tiles (or slates with slate = true), 1024 px = 4 m (256 texels/m; keep the 4 m roof uv), courses 0.25 m.
 *  No per-tile ink outline: ref tile joints are 3.3 px at 1080p and only dL* 10 (ours 9.4 px, dL* 15, INKL stroke);
 *  the course shadow carries the pattern. Canvas y runs down the slope (flip the course if v runs the other way). */
export const roofHD = (col: string, slate = false) => ctex("roofHD" + col, 1024, 1024, (g, r) => {
  const S = 1024, C = 64, TW = slate ? 52 : 77;
  g.fillStyle = col; g.fillRect(0, 0, S, S);
  for (let row = 0; row < S / C; row++) {
    const y = row * C, off = (row % 2) * TW / 2 + U(r, -6, 6);
    const n = Math.ceil(S / TW) + 1;
    for (let i = 0; i < n; i++) {
      const x = i * TW - off, tone = U(r, -1, 1);
      const fill = tone > 0 ? `rgba(255,240,225,${0.10 * tone})` : `rgba(60,25,20,${-0.10 * tone})`;
      wrapX(S, x, TW, (xx) => {
        g.fillStyle = fill; g.fillRect(xx, y, TW, C);
        const gr = g.createLinearGradient(xx, 0, xx + TW, 0); // rounded pan: light left, darker right
        gr.addColorStop(0, "rgba(255,240,225,0.12)"); gr.addColorStop(0.55, "rgba(255,240,225,0)"); gr.addColorStop(1, slate ? "rgba(20,25,35,0.10)" : "rgba(60,25,20,0.12)");
        g.fillStyle = gr; g.fillRect(xx, y, TW, C);
        g.fillStyle = slate ? "rgba(20,25,35,0.25)" : "rgba(60,25,20,0.22)"; g.fillRect(xx, y, 2, C); // thin soft joint
      });
    }
    g.fillStyle = slate ? "rgba(220,230,245,0.18)" : "rgba(255,235,220,0.22)"; g.fillRect(0, y + C - 9, S, 3); // lower-lip light
    g.fillStyle = slate ? "rgba(15,20,30,0.32)" : "rgba(55,22,18,0.32)"; g.fillRect(0, y + C - 5, S, 5);        // course shadow
  }
  for (let i = 0; i < 18; i++) { // weathering
    const x = U(r, 0, S), y = U(r, 0, S), rad = U(r, 40, 120);
    wrap2(S, S, x, y, rad * 1.5, (xx, yy) => blotch(g, xx, yy, rad, 1.5, "70,60,40", 0.08));
  }
});

/** Grass bank: 1024 px = 4 m (256 texels/m). Ref lawns: flat, saturated (#71b038 / #7dbf3f, L* 62-66, C* 55-64),
 *  broad soft variation (autocorrelation ~40 px at 1080p, +-4 L*), sparse tufts and flowers, low fine noise.
 *  Ours had the right hue (#6dad37) but only fine uniform noise (autocorrelation 6 px). */
export const grassHD = () => ctex("grassHD", 1024, 1024, (g, r) => {
  const S = 1024;
  g.fillStyle = "#73b23d"; g.fillRect(0, 0, S, S);
  for (let i = 0; i < 16; i++) {
    const x = U(r, 0, S), y = U(r, 0, S), rad = U(r, 120, 320), light = r() > 0.5;
    wrap2(S, S, x, y, rad * 1.4, (xx, yy) => blotch(g, xx, yy, rad, 1.4, light ? "140,198,80" : "92,154,48", 0.35));
  }
  g.lineWidth = 2; g.lineCap = "round"; g.lineJoin = "round";
  for (let i = 0; i < 1400; i++) { // tufts ~90 per m2
    const x = U(r, 0, S), y = U(r, 0, S), h = U(r, 7, 16), lean = U(r, -3, 3), light = r() < 0.4;
    wrap2(S, S, x, y, 20, (xx, yy) => {
      g.strokeStyle = light ? "rgba(165,218,98,0.35)" : "rgba(78,138,38,0.45)";
      g.beginPath(); g.moveTo(xx - 3 + lean, yy - h); g.lineTo(xx, yy); g.lineTo(xx + 3 + lean, yy - h * 0.8); g.stroke();
    });
  }
  for (let i = 0; i < 12; i++) { // flowers ~0.75 per m2
    const x = U(r, 0, S), y = U(r, 0, S), c = pick(r, ["#f7f3e8", "#f4d24a", "#f3a9bb", "#f7f3e8"]);
    wrap2(S, S, x, y, 8, (xx, yy) => {
      g.fillStyle = c; g.beginPath(); g.arc(xx, yy, 3.5, 0, TAU); g.fill();
      g.fillStyle = "rgba(240,190,60,0.9)"; g.beginPath(); g.arc(xx, yy, 1.3, 0, TAU); g.fill();
    });
  }
});

/** Plaster / timber / brick facade at 96 px/m (2x the old 48, capped at 2048 px a side). Windows as in the ref:
 *  white trim with a thin dark line (no heavy ink), mid-tone blue-violet glass (never near-black), two diagonal
 *  glints, curtains in about a third, louvred shutters. Same options object as facade(). */
export const facadeHD = (key: string, wm: number, hm: number, o: { wall: string; shutter: string; door?: boolean; timber?: boolean; brick?: boolean }) => {
  const PX = Math.min(72, 2048 / Math.max(wm, hm)); // 72 px/m: half the GPU memory of 96 (textures.md 4)
  const W = Math.round(wm * PX), H = Math.round(hm * PX), m = (v: number) => v * PX;
  return ctex("facHD" + key, W, H, (g, r) => {
    if (o.brick) { // real-size bricks 0.25 x 0.085 m with light mortar (ref brick #cf5e30 / mortar #f6d9b1)
      g.fillStyle = "#e9d3b4"; g.fillRect(0, 0, W, H);
      const bw = m(0.25), bh = m(0.085);
      for (let y = 0, row = 0; y < H; y += bh, row++) for (let x = -(row % 2) * bw / 2; x < W; x += bw) {
        g.fillStyle = brickCol(r);
        g.fillRect(x + 1, y + 1, bw - 2, bh - 2);
      }
      const n = Math.round((wm * hm) / 12) + 3;
      for (let i = 0; i < n; i++) blotch(g, U(r, 0, W), U(r, 0, H), m(U(r, 0.4, 1.4)), 1.4, "70,40,30", U(r, 0.06, 0.12)); // soot
    } else {
      g.fillStyle = o.wall; g.fillRect(0, 0, W, H);
      const n = Math.round((wm * hm) / 3) + 6;
      for (let i = 0; i < n; i++) {
        const light = r() > 0.5;
        blotch(g, U(r, 0, W), U(r, 0, H), m(U(r, 0.4, 1.5)), 1.5, light ? "255,255,255" : "120,90,60", light ? 0.07 : 0.05);
      }
      for (let i = 0; i < 4; i++) { // hairline cracks
        let x = U(r, 0, W), y = U(r, 0, H * 0.8);
        g.strokeStyle = "rgba(120,100,80,0.35)"; g.lineWidth = 1; g.beginPath(); g.moveTo(x, y);
        for (let k = 0; k < 4; k++) { x += m(U(r, -0.08, 0.08)); y += m(U(r, 0.04, 0.12)); g.lineTo(x, y); }
        g.stroke();
      }
    }
    const floors = Math.max(1, Math.floor(hm / 2.8));
    const nWin = Math.max(1, Math.floor(wm / 2.2));
    g.fillStyle = "rgba(70,55,45,0.28)"; g.fillRect(0, H - m(0.45), W, m(0.45)); // plinth
    g.fillStyle = "rgba(70,55,45,0.35)"; g.fillRect(0, H - m(0.45), W, 2);
    const timberBeam = (x: number, y: number, w: number, h: number) => {
      g.fillStyle = "#6e4a30"; g.fillRect(x, y, w, h);
      g.strokeStyle = "rgba(40,25,15,0.5)"; g.lineWidth = 2; g.strokeRect(x + 1, y + 1, w - 2, h - 2);
      g.fillStyle = "rgba(255,230,200,0.22)"; g.fillRect(x + 2, y + 2, w - 4, 2);
    };
    if (o.timber) {
      const t = m(0.18);
      timberBeam(0, 0, t, H); timberBeam(W - t, 0, t, H); timberBeam(0, 0, W, t);
      for (let fl = 1; fl < floors; fl++) timberBeam(0, H - m(fl * 2.8) - t / 2, W, t);
      for (let i = 1; i < nWin; i++) timberBeam((i * W) / nWin - t / 2, 0, t, H - m(2.8)); // posts, upper floors
    }
    const door = (cx: number) => {
      const dw = m(1.1), dh = m(2.1);
      const path = (k: number) => {
        g.beginPath(); g.moveTo(cx - dw / 2 - k, H); g.lineTo(cx - dw / 2 - k, H - dh + dw / 2);
        g.arc(cx, H - dh + dw / 2, dw / 2 + k, Math.PI, 0); g.lineTo(cx + dw / 2 + k, H); g.closePath();
      };
      path(m(0.1)); g.fillStyle = "#e9e2d4"; g.fill(); g.strokeStyle = "rgba(60,45,40,0.6)"; g.lineWidth = 1.5; g.stroke();
      path(0); g.fillStyle = "#7a4a2c"; g.fill();
      g.save(); path(0); g.clip();
      for (let x = cx - dw / 2 + m(0.14); x < cx + dw / 2; x += m(0.14)) {
        g.fillStyle = "rgba(40,20,10,0.45)"; g.fillRect(x - 1, H - dh, 2, dh);
        g.fillStyle = "rgba(255,225,190,0.15)"; g.fillRect(x + 1, H - dh, 2, dh);
      }
      g.restore();
      path(0); g.strokeStyle = "rgba(40,25,15,0.7)"; g.lineWidth = 2; g.stroke();
      nail(g, cx + dw / 3, H - dh / 2, m(0.035), "#d9b04a");
    };
    for (let fl = 0; fl < floors; fl++) for (let i = 0; i < nWin; i++) {
      const cx = ((i + 0.5) * W) / nWin, by = H - m(fl * 2.8 + 0.9);
      if (o.door && fl === 0 && i === Math.floor(nWin / 2)) { door(cx); continue; }
      const ww = m(0.85), wh = m(1.25), x0 = cx - ww / 2, y0 = by - wh, tr = m(0.08), sw = m(0.45);
      for (const sx of [x0 - tr - sw - m(0.02), x0 + ww + tr + m(0.02)]) { // louvred shutters
        g.fillStyle = o.shutter; g.fillRect(sx, y0, sw, wh);
        const lw = Math.max(1.5, m(0.012));
        for (let ly = y0 + m(0.06); ly < y0 + wh - m(0.04); ly += m(0.06)) {
          g.fillStyle = "rgba(0,0,0,0.22)"; g.fillRect(sx + m(0.04), ly, sw - m(0.08), lw);
          g.fillStyle = "rgba(255,255,255,0.14)"; g.fillRect(sx + m(0.04), ly + lw, sw - m(0.08), 1);
        }
        g.strokeStyle = "rgba(0,0,0,0.18)"; g.lineWidth = m(0.03); g.strokeRect(sx + m(0.015), y0 + m(0.015), sw - m(0.03), wh - m(0.03));
        g.strokeStyle = "rgba(40,30,40,0.55)"; g.lineWidth = 1.5; g.strokeRect(sx, y0, sw, wh);
      }
      g.fillStyle = "#f7f2e8"; g.fillRect(x0 - tr, y0 - tr, ww + 2 * tr, wh + 2 * tr); // trim
      const gl = g.createLinearGradient(0, y0, 0, y0 + wh);
      gl.addColorStop(0, "#8d9cdb"); gl.addColorStop(1, "#5761a8"); // ref glass #6670b0
      g.fillStyle = gl; g.fillRect(x0, y0, ww, wh);
      if (r() < 0.35) { // curtains from the top corners
        g.fillStyle = pick(r, ["#f5c4c8", "#f3e3c6", "#d7e6cf"]);
        g.beginPath(); g.moveTo(x0, y0); g.lineTo(x0 + ww * 0.42, y0); g.lineTo(x0, y0 + wh * 0.75); g.fill();
        g.beginPath(); g.moveTo(x0 + ww, y0); g.lineTo(x0 + ww * 0.58, y0); g.lineTo(x0 + ww, y0 + wh * 0.75); g.fill();
      }
      g.save(); g.beginPath(); g.rect(x0, y0, ww, wh); g.clip(); // two diagonal glints
      g.fillStyle = "rgba(255,255,255,0.5)";
      for (const [a, b] of [[0.3, m(0.07)], [0.58, m(0.035)]]) {
        g.save(); g.translate(x0 + ww * a, y0 + wh * 0.5); g.rotate(Math.PI / 4); g.fillRect(-b / 2, -wh, b, wh * 2); g.restore();
      }
      g.restore();
      g.fillStyle = "#f7f2e8"; g.fillRect(cx - m(0.02), y0, m(0.04), wh); g.fillRect(x0, y0 + wh * 0.45 - m(0.02), ww, m(0.04)); // mullions
      g.strokeStyle = "rgba(60,45,40,0.6)"; g.lineWidth = 1.5; g.strokeRect(x0 - tr, y0 - tr, ww + 2 * tr, wh + 2 * tr);
      g.strokeStyle = "rgba(60,45,40,0.45)"; g.strokeRect(x0, y0, ww, wh);
      g.fillStyle = "#ebe3d4"; g.fillRect(x0 - tr - m(0.06), by + tr, ww + 2 * tr + m(0.12), m(0.07)); // sill
      g.fillStyle = "rgba(60,45,40,0.35)"; g.fillRect(x0 - tr - m(0.06), by + tr + m(0.07), ww + 2 * tr + m(0.12), m(0.03));
    }
  });
};

/** River marks as a DATA texture for the water shader (world.ts): R = crest, G = trough, B = glint; 1024 px = 8 m.
 *  Two instances: a sparse one for the near band and a dense one sampled at 40 m tiles for the far band, because the
 *  ref thins the marks out towards the camera (area far 1.5-5 %, mid 0-1.6 %, near 0-0.9 %; ours 4-12 % everywhere).
 *  Ref marks: 12-30 px wide at 1080p (p90 36-97), 3-6 px tall, aspect 3-6, crest +8..+13 L* with a trough
 *  -8..-9 L* right under it, thin glint lines 1-3 x 30-100 px. The marks are short, deep, randomly turned arcs
 *  (isotropic on average): foreshortening alone then makes horizontal dashes on screen from ANY heading (aspect
 *  1 / sin(grazing) = 3.4 at 17 deg, 5.8 at 10 deg); ours drew 30-100 px strokes along u, which turn into dots /
 *  vertical streaks when the camera looks along the river. In reel-kit set colorSpace = THREE.NoColorSpace. */
export const waterMarks = (key: string, nCrest: number, nGlint: number) => ctex("waterMarks" + key, 1024, 1024, (g, r) => {
  const S = 1024;
  g.fillStyle = "#000"; g.fillRect(0, 0, S, S);
  g.globalCompositeOperation = "lighter"; // channels add independently
  g.lineCap = "round";
  for (let i = 0; i < nCrest; i++) {
    const x = U(r, 0, S), y = U(r, 0, S), w = U(r, 18, 44), sag = w * U(r, 0.3, 0.45), lw = U(r, 3, 5), a = U(r, 0, Math.PI);
    wrap2(S, S, x, y, w, (xx, yy) => {
      g.save(); g.translate(xx, yy); g.rotate(a);
      const arc = (dy: number, col: string, k: number) => {
        g.strokeStyle = col; g.lineWidth = lw * k;
        g.beginPath(); g.moveTo(-w / 2, dy); g.quadraticCurveTo(0, dy - sag * 2, w / 2, dy); g.stroke();
      };
      arc(0, "rgb(255,0,0)", 1);          // crest
      arc(lw * 1.5, "rgb(0,255,0)", 0.9); // trough right under it
      g.restore();
    });
  }
  for (let i = 0; i < nGlint; i++) { // glints: long thin straight lines
    const x = U(r, 0, S), y = U(r, 0, S), len = U(r, 40, 140), lw = U(r, 1.2, 2.4), a = U(r, 0, Math.PI);
    wrap2(S, S, x, y, len, (xx, yy) => {
      g.save(); g.translate(xx, yy); g.rotate(a); g.strokeStyle = "rgb(0,0,255)"; g.lineWidth = lw;
      g.beginPath(); g.moveTo(-len / 2, 0); g.lineTo(len / 2, 0); g.stroke(); g.restore();
    });
  }
  g.globalCompositeOperation = "source-over";
});
export const waterNear = () => waterMarks("near", 28, 5);  // ~0.3 % crest area
export const waterFar = () => waterMarks("far", 220, 30);  // ~2.5 % crest + glints, at 40 m tiles

/** Cloud sprite, 1024 x 512, three painted tones and a flat soft bottom, no outline.
 *  Ref cumulus: lit crown #f1f6fc-#fbfafd (L* 96-98, warm in haze #faedd7), mid #dadae9-#e5edf9, lavender-blue
 *  underside #b6c1f2 / #c7cedf / #d1d4e1 (L* 79-86) mostly in the bottom third, edge ramp 8-20 px at 1080p
 *  (median ~10), no dark rim in 9 of 11 clouds. Ours: one flat tone (#f0f0f0 = 83 % of the cloud), 4-5 px edge.
 *  Golden: use CLOUD_GOLD instead of multiplying the white sprite by #ffd6b8 (a tint cannot make the cool belly). */
export const CLOUD_DAY = { lit: "#fbf8f1", mid: "#e1e5f3", shade: "#c3cbe9" };
export const CLOUD_GOLD = { lit: "#ffd2a8", mid: "#f2a08f", shade: "#a98fc4" };
export const cloudHD = (seed: number, pal = CLOUD_DAY) => ctex(`cloudHD_${pal.lit}_${seed}`, 1024, 512, (g) => {
  const r = rng(seed * 7919 + 17); // own seed: ctex keys of equal length would otherwise share shapes
  const W = 1024, H = 512, base = 400;
  const n = 6 + Math.floor(r() * 4), lobes: { x: number; y: number; r: number }[] = [];
  for (let i = 0; i < n; i++) { // main row, biggest in the middle
    const t = (i + 0.5) / n, rad = (60 + 110 * Math.sin(Math.PI * t) ** 0.8) * U(r, 0.75, 1.15);
    lobes.push({ x: 150 + t * 724 + U(r, -30, 30), y: base - rad * U(r, 0.35, 0.65), r: rad });
  }
  for (let i = 0; i < Math.floor(n / 2); i++) { // crown
    const t = U(r, 0.25, 0.75), rad = U(r, 60, 110);
    lobes.push({ x: 150 + t * 724, y: base - 150 - rad * U(r, 0.3, 0.7), r: rad });
  }
  const layer = (dx: number, dy: number, k: number, col: string, blur: number) => {
    g.save(); g.filter = `blur(${blur}px)`; g.fillStyle = col; g.beginPath();
    for (const l of lobes) { const x = l.x + dx * l.r, y = l.y + dy * l.r; g.moveTo(x + l.r * k, y); g.arc(x, y, l.r * k, 0, TAU); }
    g.fill(); g.restore();
  };
  layer(0, 0, 1.0, pal.shade, 6);         // silhouette in the underside tone
  layer(-0.04, -0.12, 0.9, pal.mid, 8);   // mid band
  layer(-0.1, -0.26, 0.72, pal.lit, 10);  // sunlit crown, offset up-left
  g.globalCompositeOperation = "destination-in"; // flat, soft bottom
  const m = g.createLinearGradient(0, base - 18, 0, base + 6);
  m.addColorStop(0, "rgba(0,0,0,1)"); m.addColorStop(1, "rgba(0,0,0,0)");
  g.fillStyle = m; g.fillRect(0, 0, W, H);
  g.globalCompositeOperation = "source-over";
});

/** Chain strand: 4 faces side by side (Strand uv: u = k / 4 around the tube), 1024 px = 2 m along (512 texels/m).
 *  Ref iron: blue-grey with a painted matcap-like bright band (#e3d5c6-#e8e7df, ~25-30 % of the area), mids
 *  #586076 / #8790a6, darks #282f41 (L* 19). Ours renders #040d16 / #050b1b (L* 3-5). */
export const chainHD = () => ctex("chainHD", 256, 1024, (g) => {
  // MAT pass: slate blue-grey (was saturated navy #262c3e / #5f6880). Only a fallback now: build.ts Strand builds
  // real link geometry for the chain material (lam("chainHD")), this map is used if anything else asks for it.
  const F = 64, P = 128; // face width, link pitch 0.25 m
  g.fillStyle = "#4a5160"; g.fillRect(0, 0, 256, 1024);
  for (let f = 0; f < 4; f++) {
    const cx = f * F + F / 2;
    for (let i = 0; i < 1024 / P; i++) {
      const cy = i * P + P / 2;
      if (i % 2 === 0) { // face-on link
        g.lineWidth = 15; g.strokeStyle = "#8a93a3"; g.beginPath(); g.ellipse(cx, cy, 22, 58, 0, 0, TAU); g.stroke();
        g.lineWidth = 2.5; g.strokeStyle = "#3a404d";
        for (const d of [-7.5, 7.5]) { g.beginPath(); g.ellipse(cx, cy, 22 + d, 58 + d, 0, 0, TAU); g.stroke(); }
        g.lineWidth = 5; g.strokeStyle = "#e4e6ea"; g.beginPath(); g.ellipse(cx, cy, 22, 58, 0, Math.PI * 1.05, Math.PI * 1.55); g.stroke();
        g.fillStyle = "#fbfaf4"; g.beginPath(); g.arc(cx - 15, cy - 40, 2.5, 0, TAU); g.fill();
      } else { // edge-on link
        rr(g, cx - 8, cy - 62, 16, 124, 8); g.fillStyle = "#7d8696"; g.fill();
        g.strokeStyle = "#3a404d"; g.lineWidth = 2.5; g.stroke();
        g.fillStyle = "#d9dce3"; g.fillRect(cx - 5, cy - 52, 3, 104);
      }
    }
  }
});

