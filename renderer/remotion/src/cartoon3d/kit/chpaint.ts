// Chicago's painted textures, in the skill's paint.ts manner (flat painted fields, seams as dark tints, light lips,
// soft blotches, nothing noisy): brick shopfronts with their signs, mud, fill, painted signs and notices, wallpaper,
// the earth section. Ours; the helpers (ctex, rng, jit) are the skill's.
import * as THREE from "three";
import { ctex, jit } from "./paint";

const U = (r: () => number, a: number, b: number) => a + (b - a) * r();
const blot = (g: CanvasRenderingContext2D, x: number, y: number, rad: number, sx: number, rgb: string, a: number) => {
  g.save(); g.translate(x, y); g.scale(sx, 1);
  const gr = g.createRadialGradient(0, 0, 0, 0, 0, rad);
  gr.addColorStop(0, `rgba(${rgb},${a})`); gr.addColorStop(1, `rgba(${rgb},0)`);
  g.fillStyle = gr; g.fillRect(-rad, -rad, 2 * rad, 2 * rad); g.restore();
};
export const SERIF = "'DejaVu Serif', 'Liberation Serif', Georgia, serif";
export const SANS = "'DejaVu Sans', 'Liberation Sans', Arial, sans-serif";

/** painted lettering: centred, fitted to width, with a thin dark keyline under a light face (or the reverse) */
export const letter = (g: CanvasRenderingContext2D, text: string, cx: number, cy: number, maxW: number, h: number, face: string, key = "rgba(40,25,20,0.55)", font = SERIF) => {
  let size = h;
  g.font = `bold ${size}px ${font}`;
  const w = g.measureText(text).width;
  if (w > maxW) { size = (size * maxW) / w; g.font = `bold ${size}px ${font}`; }
  g.textAlign = "center"; g.textBaseline = "middle";
  g.fillStyle = key; g.fillText(text, cx + size * 0.04, cy + size * 0.05);
  g.fillStyle = face; g.fillText(text, cx, cy);
};

export type Front = {
  /** brick body colour (muted brick / ochre / cream stucco) */
  wall: string; brick?: boolean;
  /** shopfront paint (frame of the display windows) and the sign board's ground */
  frame: string; board: string; ink: string;
  name: string; goods: "cloth" | "hats" | "jars" | "tools" | "books" | "none";
  floors: number; groundH: number; floorH: number;
  /** hotel: no shopfront, an arched entrance and a grand sign band */
  hotel?: boolean;
};
const GLASS_TOP = "#7f8fc6", GLASS_BOT = "#4c5694";
/** a brick or stucco commercial front, `wm` x `hm` metres, ground floor shopfront + upper sash windows */
export const frontHD = (key: string, wm: number, hm: number, o: Front) => {
  const PX = Math.min(72, 2048 / Math.max(wm, hm));
  const W = Math.round(wm * PX), H = Math.round(hm * PX), m = (v: number) => v * PX, yOf = (h: number) => H - m(h);
  return ctex("front" + key, W, H, (g, r) => {
    // body: real-size bricks 0.22 x 0.075 m on a warm mortar, or a stucco wash
    if (o.brick !== false) {
      g.fillStyle = jit(r, "#d6bf9c", 0.03, 2, 0.05); g.fillRect(0, 0, W, H);
      const bw = m(0.22), bh = m(0.075);
      for (let y = 0, row = 0; y < H; y += bh, row++) for (let x = -(row % 2) * bw / 2; x < W; x += bw) {
        g.fillStyle = jit(r, o.wall, 0.07, 3, 0.1);
        g.fillRect(x + 1, y + 1, bw - 1.6, bh - 1.6);
      }
      for (let i = 0; i < Math.round((wm * hm) / 14) + 3; i++) blot(g, U(r, 0, W), U(r, 0, H), m(U(r, 0.5, 1.6)), 1.4, "60,35,28", U(r, 0.05, 0.1));
    } else {
      g.fillStyle = o.wall; g.fillRect(0, 0, W, H);
      for (let i = 0; i < Math.round((wm * hm) / 4) + 6; i++) { const l = r() > 0.5; blot(g, U(r, 0, W), U(r, 0, H), m(U(r, 0.4, 1.5)), 1.5, l ? "255,255,255" : "120,90,60", l ? 0.07 : 0.05); }
      g.strokeStyle = "rgba(110,85,65,0.22)"; g.lineWidth = 1.5; // ashlar joints scored into the stucco
      for (let y = H; y > 0; y -= m(0.55)) { g.beginPath(); g.moveTo(0, y); g.lineTo(W, y); g.stroke(); }
    }
    const top = o.groundH + (o.floors - 1) * o.floorH;
    // upper floors: sash windows with stone lintels and sills
    const nWin = Math.max(2, Math.floor(wm / 2.3));
    for (let fl = 1; fl < o.floors; fl++) for (let i = 0; i < nWin; i++) {
      const cx = ((i + 0.5) * W) / nWin, sill = o.groundH + (fl - 1) * o.floorH + 0.75, wh = Math.min(2.1, o.floorH - 1.0), ww = Math.min(1.05, wm / nWin - 0.9);
      const x0 = cx - m(ww / 2), y0 = yOf(sill + wh), y1 = yOf(sill);
      g.fillStyle = "#3a2c2c"; g.fillRect(x0 - m(0.06), y0 - m(0.06), m(ww + 0.12), y1 - y0 + m(0.06)); // reveal
      const gl = g.createLinearGradient(0, y0, 0, y1); gl.addColorStop(0, GLASS_TOP); gl.addColorStop(1, GLASS_BOT);
      g.fillStyle = gl; g.fillRect(x0, y0, m(ww), y1 - y0);
      if (r() < 0.45) { // a blind half down, or curtains
        g.fillStyle = r() < 0.5 ? "#efe2c4" : "#d9b77a"; g.fillRect(x0, y0, m(ww), (y1 - y0) * U(r, 0.2, 0.45));
      }
      g.save(); g.beginPath(); g.rect(x0, y0, m(ww), y1 - y0); g.clip();
      g.fillStyle = "rgba(255,255,255,0.4)"; g.save(); g.translate(x0 + m(ww) * 0.3, (y0 + y1) / 2); g.rotate(Math.PI / 4); g.fillRect(-m(0.05), -m(3), m(0.1), m(6)); g.restore();
      g.restore();
      g.fillStyle = "#f1e8d6"; // sash bars: 2 over 2
      g.fillRect(cx - m(0.025), y0, m(0.05), y1 - y0); g.fillRect(x0, (y0 + y1) / 2 - m(0.035), m(ww), m(0.07));
      g.strokeStyle = "#f1e8d6"; g.lineWidth = m(0.06); g.strokeRect(x0, y0, m(ww), y1 - y0);
      g.fillStyle = "#e9dcc2"; g.fillRect(x0 - m(0.16), y0 - m(0.3), m(ww + 0.32), m(0.24)); // lintel
      g.fillStyle = "rgba(60,40,30,0.4)"; g.fillRect(x0 - m(0.16), y0 - m(0.08), m(ww + 0.32), m(0.03));
      g.fillStyle = "#e9dcc2"; g.fillRect(x0 - m(0.1), y1, m(ww + 0.2), m(0.1)); // sill
      g.fillStyle = "rgba(60,40,30,0.35)"; g.fillRect(x0 - m(0.1), y1 + m(0.1), m(ww + 0.2), m(0.03));
    }
    // string course under each upper floor
    for (let fl = 1; fl < o.floors; fl++) { const y = yOf(o.groundH + (fl - 1) * o.floorH); g.fillStyle = "rgba(233,220,194,0.85)"; g.fillRect(0, y - m(0.12), W, m(0.12)); }
    g.fillStyle = "rgba(60,40,30,0.3)"; g.fillRect(0, yOf(top + 0.05), W, m(0.05));
    if (o.hotel) {
      // grand sign band across the whole front, arched entrance at the centre, tall ground windows
      const by = yOf(o.groundH + 0.05);
      g.fillStyle = o.board; g.fillRect(m(0.2), by - m(0.95), W - m(0.4), m(0.95));
      g.strokeStyle = "#d7b25a"; g.lineWidth = m(0.06); g.strokeRect(m(0.32), by - m(0.85), W - m(0.64), m(0.75));
      letter(g, o.name, W / 2, by - m(0.47), W - m(1.4), m(0.62), "#f3e2b0", "rgba(20,10,10,0.6)");
      const nG = Math.max(3, Math.floor(wm / 2.6));
      for (let i = 0; i < nG; i++) {
        const cx = ((i + 0.5) * W) / nG, ww = m(1.3), wh = m(o.groundH - 1.6), y1 = H - m(0.5);
        const mid = i === Math.floor(nG / 2);
        g.fillStyle = mid ? "#5a3a2a" : "#3a2c2c";
        g.beginPath(); g.moveTo(cx - ww / 2, y1); g.lineTo(cx - ww / 2, y1 - wh + ww / 2); g.arc(cx, y1 - wh + ww / 2, ww / 2, Math.PI, 0); g.lineTo(cx + ww / 2, y1); g.closePath(); g.fill();
        if (!mid) {
          const gl = g.createLinearGradient(0, y1 - wh, 0, y1); gl.addColorStop(0, GLASS_TOP); gl.addColorStop(1, GLASS_BOT);
          g.fillStyle = gl; g.beginPath(); g.moveTo(cx - ww / 2 + m(0.08), y1); g.lineTo(cx - ww / 2 + m(0.08), y1 - wh + ww / 2); g.arc(cx, y1 - wh + ww / 2, ww / 2 - m(0.08), Math.PI, 0); g.lineTo(cx + ww / 2 - m(0.08), y1); g.closePath(); g.fill();
          g.fillStyle = "#f1e8d6"; g.fillRect(cx - m(0.025), y1 - wh, m(0.05), wh);
        } else {
          g.fillStyle = "#7a4a2c"; g.fillRect(cx - ww / 2 + m(0.12), y1 - wh + ww / 2, ww - m(0.24), wh - ww / 2);
          g.fillStyle = "rgba(255,225,170,0.85)"; g.beginPath(); g.arc(cx, y1 - wh + ww / 2, ww / 2 - m(0.12), Math.PI, 0); g.fill(); // fanlight
        }
        g.strokeStyle = "#e9dcc2"; g.lineWidth = m(0.12); g.beginPath(); g.arc(cx, y1 - wh + ww / 2, ww / 2 + m(0.05), Math.PI, 0); g.stroke();
      }
      return;
    }
    // shopfront: painted frame, two display windows, a glazed door in the middle, sign board above
    const sb = o.groundH - 0.75; // sign board bottom
    g.fillStyle = o.frame; g.fillRect(0, yOf(o.groundH), W, m(o.groundH));
    g.fillStyle = "rgba(255,240,220,0.12)"; g.fillRect(0, yOf(o.groundH), W, m(0.06));
    g.fillStyle = o.board; g.fillRect(m(0.25), yOf(o.groundH - 0.08), W - m(0.5), m(0.66));
    g.strokeStyle = "rgba(30,20,15,0.45)"; g.lineWidth = 2; g.strokeRect(m(0.25), yOf(o.groundH - 0.08), W - m(0.5), m(0.66));
    letter(g, o.name, W / 2, yOf(o.groundH - 0.41), W - m(0.9), m(0.46), o.ink);
    const dw = 1.15, dh = 2.45, wy0 = 0.65, wy1 = sb - 0.2;
    const dx = W / 2;
    for (const s of [-1, 1]) { // display windows
      const xa = s < 0 ? m(0.35) : dx + m(dw / 2 + 0.3), xb = s < 0 ? dx - m(dw / 2 + 0.3) : W - m(0.35);
      const gl = g.createLinearGradient(0, yOf(wy1), 0, yOf(wy0)); gl.addColorStop(0, "#5f6aa8"); gl.addColorStop(1, "#353c70");
      g.fillStyle = gl; g.fillRect(xa, yOf(wy1), xb - xa, m(wy1 - wy0));
      goods(g, o.goods, xa, yOf(wy0), xb - xa, m(wy1 - wy0), m, r);
      g.save(); g.beginPath(); g.rect(xa, yOf(wy1), xb - xa, m(wy1 - wy0)); g.clip();
      g.fillStyle = "rgba(255,255,255,0.32)";
      g.save(); g.translate(xa + (xb - xa) * 0.25, yOf((wy0 + wy1) / 2)); g.rotate(Math.PI / 4); g.fillRect(-m(0.08), -m(4), m(0.16), m(8)); g.restore();
      g.restore();
      g.strokeStyle = "#efe2c4"; g.lineWidth = m(0.05);
      g.strokeRect(xa, yOf(wy1), xb - xa, m(wy1 - wy0));
      for (let k = 1; k < 3; k++) { const x = xa + ((xb - xa) * k) / 3; g.beginPath(); g.moveTo(x, yOf(wy1)); g.lineTo(x, yOf(wy0)); g.stroke(); }
    }
    // the door: dark wood, glazed upper half
    g.fillStyle = "#5a3424"; g.fillRect(dx - m(dw / 2), yOf(dh), m(dw), m(dh));
    const gd = g.createLinearGradient(0, yOf(dh - 0.15), 0, yOf(1.2)); gd.addColorStop(0, GLASS_TOP); gd.addColorStop(1, GLASS_BOT);
    g.fillStyle = gd; g.fillRect(dx - m(dw / 2 - 0.14), yOf(dh - 0.15), m(dw - 0.28), m(dh - 1.35));
    g.strokeStyle = "rgba(30,15,10,0.6)"; g.lineWidth = 2; g.strokeRect(dx - m(dw / 2), yOf(dh), m(dw), m(dh));
    g.fillStyle = "#d9b04a"; g.beginPath(); g.arc(dx + m(dw / 2 - 0.15), yOf(1.05), m(0.04), 0, 7); g.fill();
    g.fillStyle = "rgba(255,235,190,0.8)"; g.fillRect(dx - m(dw / 2), yOf(dh + 0.45), m(dw), m(0.4)); // transom
    g.fillStyle = "rgba(0,0,0,0.18)"; g.fillRect(0, H - m(0.62), W, m(0.62)); // stall riser below the windows
  });
};
/** what the display windows show, painted flat behind the glass */
const goods = (g: CanvasRenderingContext2D, kind: Front["goods"], x: number, yb: number, w: number, h: number, m: (v: number) => number, r: () => number) => {
  if (kind === "none") return;
  const cols = ["#c45a4a", "#e0b85a", "#5a8fc2", "#7aa65a", "#c2809a", "#e8dcc0"];
  g.save(); g.beginPath(); g.rect(x, yb - h, w, h); g.clip();
  g.fillStyle = "rgba(40,30,30,0.5)"; g.fillRect(x, yb - m(0.35), w, m(0.35)); // shelf
  const n = Math.max(3, Math.round(w / m(0.42)));
  for (let i = 0; i < n; i++) {
    const cx = x + ((i + 0.5) * w) / n, c = cols[Math.floor(r() * cols.length)];
    g.fillStyle = c; g.strokeStyle = "rgba(30,20,20,0.5)"; g.lineWidth = 1.5;
    if (kind === "cloth") { const bh = m(U(r, 0.5, 0.9)); g.fillRect(cx - m(0.16), yb - m(0.35) - bh, m(0.32), bh); g.strokeRect(cx - m(0.16), yb - m(0.35) - bh, m(0.32), bh); }
    else if (kind === "hats") { const hy = yb - m(0.35) - m(U(r, 0.2, 0.9)); g.fillRect(cx - m(0.11), hy - m(0.24), m(0.22), m(0.24)); g.fillRect(cx - m(0.18), hy - m(0.03), m(0.36), m(0.05)); }
    else if (kind === "jars") { const jy = yb - m(0.35); g.beginPath(); g.ellipse(cx, jy - m(0.2), m(0.12), m(0.2), 0, 0, 7); g.fill(); g.stroke(); g.fillStyle = "#e8dcc0"; g.fillRect(cx - m(0.08), jy - m(0.44), m(0.16), m(0.06)); }
    else if (kind === "tools") { g.fillRect(cx - m(0.02), yb - m(1.3), m(0.04), m(0.95)); g.fillStyle = "#7a7f88"; g.fillRect(cx - m(0.1), yb - m(1.36), m(0.2), m(0.12)); }
    else if (kind === "books") { const bh = m(U(r, 0.25, 0.4)); g.fillRect(cx - m(0.07), yb - m(0.35) - bh, m(0.14), bh); }
  }
  g.restore();
};

/** plain brick side/back wall, a few small windows */
export const sideHD = (key: string, wm: number, hm: number, wall: string, wins = true) => {
  const PX = Math.min(40, 1024 / Math.max(wm, hm));
  const W = Math.round(wm * PX), H = Math.round(hm * PX), m = (v: number) => v * PX;
  return ctex("side" + key, W, H, (g, r) => {
    g.fillStyle = "#d6bf9c"; g.fillRect(0, 0, W, H);
    const bw = m(0.22), bh = m(0.075);
    for (let y = 0, row = 0; y < H; y += bh, row++) for (let x = -(row % 2) * bw / 2; x < W; x += bw) { g.fillStyle = jit(r, wall, 0.06, 3, 0.1); g.fillRect(x, y, bw - 1, bh - 1); }
    for (let i = 0; i < Math.round((wm * hm) / 12) + 2; i++) blot(g, U(r, 0, W), U(r, 0, H), m(U(r, 0.8, 2.2)), 1.5, "60,35,28", U(r, 0.05, 0.1));
    if (!wins) return;
    for (let y = 5; y < hm - 1.5; y += 3.3) for (let x = 2.5; x < wm - 1.5; x += 4.5) {
      g.fillStyle = "#3a2c2c"; g.fillRect(m(x), H - m(y + 1.6), m(0.8), m(1.6));
      g.fillStyle = "#5a64a0"; g.fillRect(m(x + 0.06), H - m(y + 1.54), m(0.68), m(1.48));
      g.fillStyle = "#e9dcc2"; g.fillRect(m(x - 0.1), H - m(y + 1.85), m(1.0), m(0.2));
    }
  });
};

/** street mud: dark wet brown, wheel ruts along u, hoof prints, wet sheen, straw; 1024 px = 8 m, seamless */
export const mudHD = () => ctex("mudHD", 1024, 1024, (g, r) => {
  g.fillStyle = "#7c654f"; g.fillRect(0, 0, 1024, 1024);
  const wrap = (fn: (ox: number, oy: number) => void) => { for (const ox of [-1024, 0, 1024]) for (const oy of [-1024, 0, 1024]) fn(ox, oy); };
  for (let i = 0; i < 40; i++) { const x = r() * 1024, y = r() * 1024, rad = 40 + r() * 110, l = r() > 0.45; wrap((ox, oy) => blot(g, x + ox, y + oy, rad, 1.6, l ? "130,98,70" : "45,30,22", l ? 0.22 : 0.25)); }
  for (const yc of [300, 420, 690, 810]) { // ruts: dark troughs with a lit lip on the far side
    g.strokeStyle = "rgba(40,26,18,0.42)"; g.lineWidth = 26; g.beginPath();
    for (let x = -20; x <= 1044; x += 32) { const y = yc + 10 * Math.sin(x / 140 + yc); if (x < 0) g.moveTo(x, y); else g.lineTo(x, y); } g.stroke();
    g.strokeStyle = "rgba(160,125,92,0.28)"; g.lineWidth = 6; g.beginPath();
    for (let x = -20; x <= 1044; x += 32) { const y = yc - 15 + 10 * Math.sin(x / 140 + yc); if (x < 0) g.moveTo(x, y); else g.lineTo(x, y); } g.stroke();
  }
  for (let i = 0; i < 26; i++) { // standing water in the ruts: sky sheen
    const x = r() * 1024, y = [300, 420, 690, 810][i % 4] + 4, w = 30 + r() * 70;
    wrap((ox) => { g.fillStyle = "rgba(150,165,180,0.4)"; g.beginPath(); g.ellipse(x + ox, y, w, 7, 0, 0, 7); g.fill(); });
  }
  for (let i = 0; i < 60; i++) { const x = r() * 1024, y = r() * 1024; wrap((ox, oy) => { g.fillStyle = "rgba(35,22,15,0.35)"; g.beginPath(); g.ellipse(x + ox, y + oy, 9, 7, 0, 0, 7); g.fill(); }); } // hoof prints
  g.strokeStyle = "rgba(214,184,110,0.55)"; g.lineWidth = 2; // straw
  for (let i = 0; i < 70; i++) { const x = r() * 1024, y = r() * 1024, a = r() * 3.14, l = 10 + r() * 18; g.beginPath(); g.moveTo(x, y); g.lineTo(x + Math.cos(a) * l, y + Math.sin(a) * l); g.stroke(); }
});
/** fresh fill (sand and clay dredged from the river): lighter, drier, shovel marks */
export const fillHD = () => ctex("fillHD", 1024, 1024, (g, r) => {
  g.fillStyle = "#8f7a62"; g.fillRect(0, 0, 1024, 1024);
  for (let i = 0; i < 46; i++) { const x = r() * 1024, y = r() * 1024, rad = 40 + r() * 100, l = r() > 0.5; for (const ox of [-1024, 0, 1024]) for (const oy of [-1024, 0, 1024]) blot(g, x + ox, y + oy, rad, 1.5, l ? "200,170,125" : "110,80,55", l ? 0.25 : 0.22); }
  g.strokeStyle = "rgba(90,65,45,0.3)"; g.lineWidth = 4;
  for (let i = 0; i < 50; i++) { const x = r() * 1024, y = r() * 1024; g.beginPath(); g.arc(x, y, 14 + r() * 10, 3.6, 5.8); g.stroke(); }
});
/** wood-block / cobble paving of the finished street: warm grey setts with dark joints */
export const pavingHD = () => ctex("pavingHD", 1024, 1024, (g, r) => {
  g.fillStyle = "#6b5f55"; g.fillRect(0, 0, 1024, 1024);
  const bw = 64, bh = 42;
  for (let y = 0, row = 0; y < 1024; y += bh, row++) for (let x = -(row % 2) * bw / 2; x < 1024; x += bw) {
    g.fillStyle = jit(r, "#b0907a", 0.08, 4, 0.14); g.beginPath(); (g as CanvasRenderingContext2D & { roundRect: (x: number, y: number, w: number, h: number, r: number) => void }).roundRect(x + 3, y + 3, bw - 6, bh - 6, 8); g.fill();
    g.fillStyle = "rgba(255,245,230,0.18)"; g.fillRect(x + 8, y + 5, bw - 16, 4);
  }
});
/** the earth section: road surface, fill strata, the old mud line */
export const strataHD = () => ctex("strataHD", 512, 1024, (g, r) => {
  const bands: [number, string][] = [[0, "#6b5f55"], [40, "#a0805a"], [300, "#8f6f4c"], [560, "#a68660"], [760, "#5e4331"], [1024, "#4a3426"]];
  for (let i = 0; i < bands.length - 1; i++) { g.fillStyle = bands[i][1]; g.fillRect(0, bands[i][0], 512, bands[i + 1][0] - bands[i][0]); }
  for (let i = 0; i < 90; i++) { const x = r() * 512, y = 40 + r() * 960; g.fillStyle = `rgba(${r() > 0.5 ? "60,40,25" : "200,170,130"},0.35)`; g.beginPath(); g.ellipse(x, y, 4 + r() * 10, 3 + r() * 6, r() * 3, 0, 7); g.fill(); }
  for (const y of [40, 300, 560, 760]) { g.fillStyle = "rgba(40,25,15,0.45)"; g.fillRect(0, y - 2, 512, 4); }
});

/** a painted board: background, border, lines of text (each [text, rel. size, colour]) */
export const boardTex = (key: string, w: number, h: number, bg: string, lines: [string, number, string][], o: { border?: string; font?: string; rough?: boolean } = {}) =>
  ctex("board" + key, w, h, (g, r) => {
    g.fillStyle = bg; g.fillRect(0, 0, w, h);
    if (o.rough) for (let y = 0; y < h; y += h / 5) { g.fillStyle = `rgba(40,25,15,${0.18 + r() * 0.12})`; g.fillRect(0, y, w, 3); g.fillStyle = "rgba(255,230,190,0.12)"; g.fillRect(0, y + 3, w, 2); }
    if (o.border) { g.strokeStyle = o.border; g.lineWidth = Math.max(4, w * 0.02); g.strokeRect(w * 0.03, h * 0.04, w * 0.94, h * 0.92); }
    const total = lines.reduce((a, l) => a + l[1], 0);
    let y = h * 0.12;
    for (const [t, s, c] of lines) { const lh = (h * 0.76 * s) / total; letter(g, t, w / 2, y + lh / 2, w * 0.86, lh * 0.82, c, "rgba(20,10,10,0.35)", o.font ?? SERIF); y += lh; }
  });

/** the city engineer's drawing: old street line, pipe on top, new street line above, arrows (a section) */
export const planTex = () => ctex("planSection", 900, 640, (g) => {
  g.fillStyle = "#e9e4d2"; g.fillRect(0, 0, 900, 640);
  g.strokeStyle = "#9fb6d6"; g.lineWidth = 1; for (let x = 0; x < 900; x += 30) { g.beginPath(); g.moveTo(x, 0); g.lineTo(x, 640); g.stroke(); } for (let y = 0; y < 640; y += 30) { g.beginPath(); g.moveTo(0, y); g.lineTo(900, y); g.stroke(); }
  g.fillStyle = "#8a6a4a"; g.fillRect(60, 470, 780, 90); // old ground
  g.fillStyle = "rgba(160,128,90,0.55)"; g.fillRect(60, 290, 780, 180); // new fill (hatched)
  g.strokeStyle = "rgba(90,60,40,0.6)"; g.lineWidth = 3; for (let x = 60; x < 840; x += 26) { g.beginPath(); g.moveTo(x, 470); g.lineTo(x + 40, 290); g.stroke(); }
  g.strokeStyle = "#2a2a55"; g.lineWidth = 6; g.beginPath(); g.moveTo(40, 470); g.lineTo(860, 470); g.stroke(); // old street line
  g.setLineDash([22, 14]); g.beginPath(); g.moveTo(40, 290); g.lineTo(860, 290); g.stroke(); g.setLineDash([]); // new street line
  g.fillStyle = "#e9e4d2"; g.strokeStyle = "#2a2a55"; g.lineWidth = 7; g.beginPath(); g.arc(450, 400, 66, 0, 7); g.fill(); g.stroke(); // the pipe ON the old street
  g.lineWidth = 4; g.beginPath(); g.arc(450, 400, 46, 0, 7); g.stroke();
  g.fillStyle = "#b8332e"; for (const x of [170, 730]) { g.beginPath(); g.moveTo(x, 450); g.lineTo(x - 24, 380); g.lineTo(x - 9, 380); g.lineTo(x - 9, 310); g.lineTo(x + 9, 310); g.lineTo(x + 9, 380); g.lineTo(x + 24, 380); g.closePath(); g.fill(); }
  letter(g, "RAISE THE GRADE", 450, 120, 760, 76, "#2a2a55", "rgba(0,0,0,0)");
  letter(g, "SEWER", 450, 400, 110, 30, "#2a2a55", "rgba(0,0,0,0)", SANS);
});

/** dining-room wallpaper: warm stripes with a small damask dot; 512 px = 1 m */
export const wallpaperHD = () => ctex("wallpaperHD", 512, 512, (g) => {
  g.fillStyle = "#b9544a"; g.fillRect(0, 0, 512, 512);
  for (let x = 0; x < 512; x += 128) { g.fillStyle = "#a8473f"; g.fillRect(x + 80, 0, 48, 512); g.fillStyle = "rgba(240,200,140,0.5)"; g.fillRect(x + 76, 0, 4, 512); }
  g.fillStyle = "rgba(240,200,140,0.55)";
  for (let y = 32; y < 512; y += 96) for (let x = 40; x < 512; x += 128) { g.beginPath(); g.moveTo(x, y - 14); g.lineTo(x + 10, y); g.lineTo(x, y + 14); g.lineTo(x - 10, y); g.closePath(); g.fill(); }
});
/** a measuring post: feet marks and numbers (the Lake Street gauge) */
export const gaugeTex = () => ctex("gaugeFeet", 128, 1024, (g) => {
  g.fillStyle = "#efe6cf"; g.fillRect(0, 0, 128, 1024);
  const pxPerFt = 1024 / 6;
  for (let ft = 0; ft <= 6; ft++) for (let i = 0; i < 12; i++) {
    const y = 1024 - (ft + i / 12) * pxPerFt; const big = i === 0;
    g.fillStyle = "#2a1a1a"; g.fillRect(0, y - (big ? 3 : 1), big ? 70 : i === 6 ? 45 : 25, big ? 6 : 2);
    if (big && ft > 0 && ft < 6) { g.font = `bold 46px ${SERIF}`; g.textAlign = "center"; g.textBaseline = "middle"; g.fillText(String(ft), 98, y + 2); }
  }
  g.fillStyle = "#c0352e"; g.fillRect(0, 1024 - (4 + 8 / 12) * pxPerFt - 4, 128, 8); // 4 ft 8 in
});
export const glowTex = () => ctex("lampGlow", 128, 128, (g) => {
  const gr = g.createRadialGradient(64, 64, 0, 64, 64, 64); gr.addColorStop(0, "rgba(255,230,170,1)"); gr.addColorStop(0.35, "rgba(255,190,110,0.5)"); gr.addColorStop(1, "rgba(255,160,80,0)");
  g.fillStyle = gr; g.fillRect(0, 0, 128, 128);
});
export const texRepeat = (t: THREE.Texture, x: number, y: number) => { const c = t.clone(); c.wrapS = c.wrapT = THREE.RepeatWrapping; c.repeat.set(x, y); c.needsUpdate = true; return c; };

/** the road's exposed edge while the street is raised: the old mud road at the foot, fresh fill above, the new surface on
 *  top; v = 0 at the old grade, 1 at the fill top (the face is scaled to the fill height) */
export const roadEdgeHD = () => ctex("roadEdgeHD", 512, 512, (g, r) => {
  g.fillStyle = "#8f7a62"; g.fillRect(0, 0, 512, 512);
  for (let i = 0; i < 60; i++) { const x = r() * 512, y = r() * 380; g.fillStyle = `rgba(${r() > 0.5 ? "70,50,35" : "190,165,130"},0.35)`; g.beginPath(); g.ellipse(x, y, 6 + r() * 14, 3 + r() * 6, 0, 0, 7); g.fill(); }
  for (const y of [120, 250]) { g.fillStyle = "rgba(70,50,35,0.35)"; g.fillRect(0, y, 512, 5); }
  g.fillStyle = "#4e3c2e"; g.fillRect(0, 400, 512, 112); // the old mud road
  g.fillStyle = "rgba(30,20,12,0.6)"; g.fillRect(0, 396, 512, 7);
  g.fillStyle = "#6b5f55"; g.fillRect(0, 0, 512, 18); // the new surface
});

/** boards with their gaps painted as warm brown tints, not black (round-3 verifier: seams must never read as ink);
 *  1024 px = 2 m, boards 0.2 m along v */
export const boardsHD = () => ctex("boardsHD", 1024, 1024, (g, r) => {
  g.fillStyle = "#c99a62"; g.fillRect(0, 0, 1024, 1024);
  for (let y = 0; y < 1024; y += 102.4) {
    g.fillStyle = jit(r, "#c99a62", 0.08, 4, 0.12); g.fillRect(0, y + 4, 1024, 96);
    g.fillStyle = "rgba(255,235,200,0.16)"; g.fillRect(0, y + 6, 1024, 6);
    g.fillStyle = "rgba(110,60,25,0.55)"; g.fillRect(0, y, 1024, 4); // the gap: a tint
    for (let i = 0; i < 6; i++) { const x = r() * 1024; g.strokeStyle = "rgba(120,75,40,0.18)"; g.lineWidth = 2; g.beginPath(); g.moveTo(x, y + 20 + r() * 50); g.bezierCurveTo(x + 80, y + 30, x + 160, y + 70, x + 260, y + 40); g.stroke(); }
    for (let x = (y / 102.4) % 2 ? 300 : 700; x < 1024; x += 800) { g.fillStyle = "rgba(110,60,25,0.45)"; g.fillRect(x, y + 4, 3, 96); }
  }
});
