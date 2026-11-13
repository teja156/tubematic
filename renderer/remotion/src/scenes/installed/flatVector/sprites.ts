/*
 * Flat Vector Science's bitmaps: every prop (library or the video's own) is
 * rendered once to static SVG markup, rasterised to a canvas at the size it
 * is drawn, and then only moved, scaled and rotated on the scene's canvas.
 * A live SVG drawing is paid for on every frame on the CPU renderer; a bitmap
 * costs one image draw.
 *
 * Bitmaps are drawn at their largest on-screen size (the size `l` plus the
 * room a pop and a zoom need), so a prop is never scaled up past its pixels.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

export type Sprite = { canvas: HTMLCanvasElement; width: number; height: number };

/** Rasterises a drawing centred on (0, 0) in a w x h box, at `scale` device pixels per px. */
export async function rasterise(node: React.ReactNode, w: number, h: number, scale: number): Promise<Sprite> {
  const pw = Math.max(1, Math.ceil(w * scale)), ph = Math.max(1, Math.ceil(h * scale));
  const markup = renderToStaticMarkup(
    React.createElement(
      "svg",
      { xmlns: "http://www.w3.org/2000/svg", width: pw, height: ph, viewBox: `${-w / 2} ${-h / 2} ${w} ${h}` },
      node,
    ),
  );
  const img = new Image();
  img.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(markup)}`;
  await img.decode();
  const canvas = document.createElement("canvas");
  canvas.width = pw;
  canvas.height = ph;
  canvas.getContext("2d")!.drawImage(img, 0, 0, pw, ph);
  return { canvas, width: w, height: h };
}

/** A soft round halo for lights, drawn once per colour. */
export function halo(color: string, size = 256): HTMLCanvasElement {
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const ctx = c.getContext("2d")!;
  const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  g.addColorStop(0, hexA(color, 0.55));
  g.addColorStop(0.35, hexA(color, 0.22));
  g.addColorStop(1, hexA(color, 0));
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, size, size);
  return c;
}

export function hexA(hex: string, a: number): string {
  const v = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  return `rgba(${v[0]},${v[1]},${v[2]},${a})`;
}
