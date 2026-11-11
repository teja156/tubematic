/*
 * The count card's icons, drawn on one Canvas 2D layer (forty small SVGs cost
 * more on the CPU renderer than one canvas). Each icon fits a box of side `s`
 * centred on (cx, cy); `fill` is its body colour and `ink` its detail colour.
 */
import type { Icon } from "./contract";

type Draw = (c: CanvasRenderingContext2D, cx: number, cy: number, s: number, fill: string, ink: string) => void;

function rr(c: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  c.beginPath();
  c.moveTo(x + r, y);
  c.lineTo(x + w - r, y);
  c.arcTo(x + w, y, x + w, y + r, r);
  c.lineTo(x + w, y + h - r);
  c.arcTo(x + w, y + h, x + w - r, y + h, r);
  c.lineTo(x + r, y + h);
  c.arcTo(x, y + h, x, y + h - r, r);
  c.lineTo(x, y + r);
  c.arcTo(x, y, x + r, y, r);
  c.closePath();
}

export const ICON_DRAW: Record<Icon, Draw> = {
  bill(c, cx, cy, s, fill, ink) {
    c.fillStyle = fill;
    rr(c, cx - s * 0.46, cy - s * 0.24, s * 0.92, s * 0.48, s * 0.05);
    c.fill();
    c.strokeStyle = ink;
    c.lineWidth = s * 0.035;
    c.beginPath();
    c.arc(cx, cy, s * 0.12, 0, Math.PI * 2);
    c.stroke();
  },
  coin(c, cx, cy, s, fill, ink) {
    c.fillStyle = fill;
    c.beginPath();
    c.arc(cx, cy, s * 0.36, 0, Math.PI * 2);
    c.fill();
    c.strokeStyle = ink;
    c.lineWidth = s * 0.04;
    c.beginPath();
    c.arc(cx, cy, s * 0.24, 0, Math.PI * 2);
    c.stroke();
  },
  envelope(c, cx, cy, s, fill, ink) {
    c.fillStyle = fill;
    rr(c, cx - s * 0.42, cy - s * 0.28, s * 0.84, s * 0.56, s * 0.05);
    c.fill();
    c.strokeStyle = ink;
    c.lineWidth = s * 0.04;
    c.beginPath();
    c.moveTo(cx - s * 0.4, cy - s * 0.24);
    c.lineTo(cx, cy + s * 0.06);
    c.lineTo(cx + s * 0.4, cy - s * 0.24);
    c.stroke();
  },
  person(c, cx, cy, s, fill) {
    c.fillStyle = fill;
    c.beginPath();
    c.arc(cx, cy - s * 0.2, s * 0.16, 0, Math.PI * 2);
    c.fill();
    c.beginPath();
    c.arc(cx, cy + s * 0.38, s * 0.3, Math.PI, 0);
    c.closePath();
    c.fill();
  },
  box(c, cx, cy, s, fill, ink) {
    c.fillStyle = fill;
    rr(c, cx - s * 0.36, cy - s * 0.3, s * 0.72, s * 0.6, s * 0.04);
    c.fill();
    c.fillStyle = ink;
    c.fillRect(cx - s * 0.06, cy - s * 0.3, s * 0.12, s * 0.6);
  },
  card(c, cx, cy, s, fill, ink) {
    c.fillStyle = fill;
    rr(c, cx - s * 0.44, cy - s * 0.28, s * 0.88, s * 0.56, s * 0.07);
    c.fill();
    c.fillStyle = ink;
    c.fillRect(cx - s * 0.44, cy - s * 0.14, s * 0.88, s * 0.11);
  },
  phone(c, cx, cy, s, fill, ink) {
    c.fillStyle = fill;
    rr(c, cx - s * 0.24, cy - s * 0.42, s * 0.48, s * 0.84, s * 0.08);
    c.fill();
    c.fillStyle = ink;
    c.fillRect(cx - s * 0.08, cy + s * 0.3, s * 0.16, s * 0.04);
  },
  document(c, cx, cy, s, fill, ink) {
    c.fillStyle = fill;
    rr(c, cx - s * 0.3, cy - s * 0.4, s * 0.6, s * 0.8, s * 0.04);
    c.fill();
    c.fillStyle = ink;
    for (let i = 0; i < 3; i++) c.fillRect(cx - s * 0.2, cy - s * 0.22 + i * s * 0.17, s * (i === 2 ? 0.26 : 0.4), s * 0.05);
  },
  key(c, cx, cy, s, fill) {
    c.strokeStyle = fill;
    c.lineWidth = s * 0.1;
    c.beginPath();
    c.arc(cx - s * 0.22, cy, s * 0.15, 0, Math.PI * 2);
    c.stroke();
    c.fillStyle = fill;
    c.fillRect(cx - s * 0.07, cy - s * 0.05, s * 0.5, s * 0.1);
    c.fillRect(cx + s * 0.2, cy, s * 0.08, s * 0.16);
    c.fillRect(cx + s * 0.35, cy, s * 0.08, s * 0.13);
  },
  goldbar(c, cx, cy, s, fill, ink) {
    c.fillStyle = fill;
    c.beginPath();
    c.moveTo(cx - s * 0.3, cy - s * 0.2);
    c.lineTo(cx + s * 0.3, cy - s * 0.2);
    c.lineTo(cx + s * 0.44, cy + s * 0.2);
    c.lineTo(cx - s * 0.44, cy + s * 0.2);
    c.closePath();
    c.fill();
    c.fillStyle = ink;
    c.fillRect(cx - s * 0.18, cy - s * 0.02, s * 0.36, s * 0.05);
  },
};

/** The body colour of each icon on the cream card. */
export const ICON_FILL: Record<Icon, string> = {
  bill: "#8CAC7C", coin: "#D9A93C", envelope: "#C9BFA9", person: "#5E6B7A", box: "#B98A5A",
  card: "#4D6FA8", phone: "#3B3F47", document: "#A9B8C8", key: "#8E8576", goldbar: "#D9A93C",
};
