/*
 * Cached bitmaps: every drawing in this style is drawn once and reused.
 *
 * On the CPU renderer (software GL) a live SVG drawing is paid for on every
 * frame it is on screen, and hatching (SVG patterns) is the dearest part of it.
 * Bean Explainer measured its live SVG character at about 0.3 CPU-seconds per
 * frame and the same character as a bitmap at about 0.07. So each distinct
 * look of the guide, a person, a prop or a backdrop is rendered once to static
 * SVG markup, rasterised to a PNG and shown with <Img> on every frame that
 * looks the same. Motion (a walk, a hop, a push-in) is a transform on the
 * bitmap, never a new drawing.
 *
 * The cache lives for the life of a render tab. A miss holds the frame with
 * delayRender until its bitmap exists, so no frame is captured without it; a
 * drawing that cannot be rasterised fails the render.
 */
import React, { useLayoutEffect, useReducer } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { Img, cancelRender, continueRender, delayRender } from "remotion";
import { InkDefs } from "./ink";

/** A drawing: a unique key for its look, its box in px, and the SVG children that draw it in that box. */
export type Drawing = {
  key: string;
  width: number;
  height: number;
  /** Device pixels per px. Above 1 for drawings shown scaled up (the camera's push-in). */
  density?: number;
  render: () => React.ReactNode;
};

const urls = new Map<string, string>();
const pending = new Map<string, Promise<void>>();

function markup(d: Drawing): string {
  const k = d.density ?? 1;
  const w = Math.ceil(d.width * k), h = Math.ceil(d.height * k);
  return renderToStaticMarkup(
    <svg xmlns="http://www.w3.org/2000/svg" width={w} height={h} viewBox={`0 0 ${d.width} ${d.height}`}>
      <InkDefs />
      {d.render()}
    </svg>,
  );
}

async function rasterise(d: Drawing): Promise<string> {
  const img = new Image();
  img.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(markup(d))}`;
  await img.decode();
  const canvas = document.createElement("canvas");
  canvas.width = img.naturalWidth;
  canvas.height = img.naturalHeight;
  canvas.getContext("2d")!.drawImage(img, 0, 0);
  const blob = await new Promise<Blob | null>((ok) => canvas.toBlob(ok, "image/png"));
  if (!blob) throw new Error(`StorybookAtlas: the canvas produced no image for ${d.key}`);
  return URL.createObjectURL(blob);
}

/** The bitmap's object URL, rasterising it on first use. */
export function bitmapUrl(d: Drawing): Promise<string> {
  const hit = urls.get(d.key);
  if (hit) return Promise.resolve(hit);
  let job = pending.get(d.key);
  if (!job) {
    job = rasterise(d)
      .then((url) => {
        urls.set(d.key, url);
      })
      .finally(() => pending.delete(d.key));
    pending.set(d.key, job);
  }
  return job.then(() => urls.get(d.key)!);
}

/** The URL if the bitmap exists, else holds the frame until it does (and returns null for this render pass). */
export function useBitmap(d: Drawing | null): string | null {
  const key = d?.key ?? null;
  const url = key ? urls.get(key) ?? null : null;
  const [, rerender] = useReducer((n: number) => n + 1, 0);
  useLayoutEffect(() => {
    if (!d || urls.has(d.key)) return;
    const handle = delayRender(`StorybookAtlas: drawing ${d.key}`);
    bitmapUrl(d)
      .then(() => {
        rerender();
        continueRender(handle);
      })
      .catch((err) => cancelRender(err));
    // `d` is fully described by its key
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return url;
}

/** A drawing placed with its box's top-left at (left, top), with an optional transform about `origin` (px in the box). */
export const Bitmap: React.FC<{
  d: Drawing;
  left: number;
  top: number;
  transform?: string;
  origin?: [number, number];
  opacity?: number;
}> = ({ d, left, top, transform, origin, opacity }) => {
  const url = useBitmap(d);
  if (!url) return null;
  return (
    <Img
      src={url}
      style={{
        position: "absolute", left, top, width: d.width, height: d.height,
        transform, transformOrigin: origin ? `${origin[0]}px ${origin[1]}px` : undefined,
        opacity: opacity === undefined || opacity === 1 ? undefined : opacity,
      }}
    />
  );
};

/**
 * A full-frame drawing painted once into a <canvas> that stays mounted.
 * Measured on the CPU renderer: a 1080 x 1920 bitmap shown with <Img> cost
 * about 0.2 CPU-seconds per frame even when it never changed; the same pixels
 * in a canvas painted once cost (see the scene's header comment).
 */
export const CanvasBitmap: React.FC<{ d: Drawing; style?: React.CSSProperties }> = ({ d, style }) => {
  const ref = React.useRef<HTMLCanvasElement>(null);
  const painted = React.useRef<string | null>(null);
  useLayoutEffect(() => {
    const c = ref.current;
    if (!c || painted.current === d.key) return;
    const handle = delayRender(`StorybookAtlas: painting ${d.key}`);
    bitmapUrl(d)
      .then((url) => {
        const img = new Image();
        img.src = url;
        return img.decode().then(() => {
          c.getContext("2d")!.drawImage(img, 0, 0, c.width, c.height);
          painted.current = d.key;
          continueRender(handle);
        });
      })
      .catch((err) => cancelRender(err));
    // `d` is fully described by its key
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [d.key]);
  const k = d.density ?? 1;
  return (
    <canvas ref={ref} width={Math.ceil(d.width * k)} height={Math.ceil(d.height * k)}
      style={{ position: "absolute", left: 0, top: 0, width: d.width, height: d.height, ...style }} />
  );
};
