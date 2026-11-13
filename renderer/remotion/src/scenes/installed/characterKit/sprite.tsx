/*
 * Cached bitmaps for the code-drawn character styles.
 *
 * Measured on the CPU renderer (software GL) for Bean Explainer: a character
 * drawn as live SVG cost about 0.3 CPU-seconds per frame whatever its size or
 * stroke, while the same drawing as a bitmap cost nothing measurable. So every
 * character, prop and card of these styles is drawn once per distinct look from
 * its SVG, rasterised to a PNG, and reused on every frame that looks the same.
 * The styles hold poses and step their wobble on twos through a few fixed
 * phases, so most frames are cache hits. Motion that changes every frame (a
 * hop, a squash, a slide, a pop) is a transform on the bitmap, never a new
 * drawing.
 *
 * The cache lives for the life of a render tab. A miss holds the frame with
 * delayRender until its bitmap exists, so no frame is captured without it; a
 * drawing that cannot be rasterised fails the render, never a frame without it.
 *
 * Text inside a sprite needs its fonts inlined (`fonts`), because an SVG drawn
 * as an image cannot see the document's fonts.
 */
import React, { useLayoutEffect, useReducer } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { Img, cancelRender, continueRender, delayRender } from "remotion";
import { fontFaceCss, type FontFile } from "./fonts";

/** A drawing's extent in its own coordinates: every pixel it can reach. */
export type SpriteBox = { left: number; top: number; width: number; height: number };

const urls = new Map<string, string>();
const pending = new Map<string, Promise<void>>();

/** The rasterised sprites in this tab, for tests and the sheets. */
export const spriteCount = () => urls.size;

async function rasterise(key: string, draw: () => React.ReactElement, box: SpriteBox, scale: number, fonts?: readonly FontFile[]) {
  const w = Math.max(1, Math.ceil(box.width * scale));
  const h = Math.max(1, Math.ceil(box.height * scale));
  const css = fonts && fonts.length ? await fontFaceCss(fonts) : "";
  const body = renderToStaticMarkup(
    <g transform={`scale(${scale}) translate(${-box.left} ${-box.top})`}>{draw()}</g>,
  );
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">` +
    (css ? `<style>${css}</style>` : "") +
    body +
    "</svg>";
  const img = new Image();
  img.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
  await img.decode();
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  canvas.getContext("2d")!.drawImage(img, 0, 0);
  const blob = await new Promise<Blob | null>((ok) => canvas.toBlob(ok, "image/png"));
  if (!blob) throw new Error(`sprite ${key}: the canvas produced no image`);
  urls.set(key, URL.createObjectURL(blob));
}

export type SpriteProps = {
  /** Everything that changes the drawing, as one string. Two looks never share a key. */
  id: string;
  draw: () => React.ReactElement;
  box: SpriteBox;
  /** Where the drawing's (0, 0) lands on the frame, and its size there. */
  x: number;
  y: number;
  scale?: number;
  /** A CSS transform around the drawing's (0, 0): squash, pop, tilt. Absent when at rest. */
  transform?: string;
  opacity?: number;
  /** Mirror the bitmap left to right around the drawing's (0, 0). */
  flip?: boolean;
  fonts?: readonly FontFile[];
};

/** A drawing at (x, y) as a cached bitmap. */
export const Sprite: React.FC<SpriteProps> = ({ id, draw, box, x, y, scale = 1, transform, opacity, flip, fonts }) => {
  const s = Math.round(scale * 100) / 100;
  // the box is part of the key: two looks that round to one id but need different boxes never share a bitmap
  const key = `${id}@${s}@${box.left},${box.top},${box.width},${box.height}`;
  const url = urls.get(key);
  const [, rerender] = useReducer((n: number) => n + 1, 0);
  useLayoutEffect(() => {
    if (urls.has(key)) return;
    const handle = delayRender(`Sprite: drawing ${id}`);
    let job = pending.get(key);
    if (!job) {
      job = rasterise(key, draw, box, s, fonts).finally(() => pending.delete(key));
      pending.set(key, job);
    }
    job
      .then(() => {
        rerender();
        continueRender(handle);
      })
      .catch((err) => cancelRender(err));
    // the drawing is fully described by `key`
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  if (!url || opacity === 0) return null;
  const parts = [transform, flip ? "scaleX(-1)" : ""].filter(Boolean).join(" ");
  return (
    <Img
      src={url}
      style={{
        position: "absolute",
        left: x + box.left * s,
        top: y + box.top * s,
        width: Math.ceil(box.width * s),
        height: Math.ceil(box.height * s),
        opacity: opacity === undefined || opacity >= 1 ? undefined : opacity,
        transform: parts || undefined,
        transformOrigin: `${-box.left * s}px ${-box.top * s}px`,
      }}
    />
  );
};
