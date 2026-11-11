/*
 * The presenter on screen, drawn as a cached bitmap.
 *
 * Bean Explainer measured a live SVG character at about 0.3 CPU-seconds per
 * frame on the CPU renderer and a bitmap of it at about 0.07, so the
 * presenter is drawn the same way: each distinct look (pose, mouth shape,
 * blink) is drawn once from presenter.tsx, rasterised to a PNG and reused on
 * every frame that looks the same. There are at most 9 poses x 3 mouths x 2
 * blink states, so a whole video draws a few dozen bitmaps at most.
 *
 * The cache lives for the life of a render tab. A miss holds the frame with
 * delayRender until its bitmap exists, so no frame is captured without the
 * presenter; a bitmap that cannot be drawn fails the render.
 */
import React, { useLayoutEffect, useReducer } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { Img, cancelRender, continueRender, delayRender } from "remotion";
import type { Pose } from "./contract";
import { PresenterSvg, VIEW } from "./presenter";

const urls = new Map<string, string>();
const pending = new Map<string, Promise<void>>();

async function rasterise(key: string, pose: Pose, mouth: 0 | 1 | 2, blink: boolean): Promise<void> {
  const svg = renderToStaticMarkup(<PresenterSvg pose={pose} mouth={mouth} blink={blink} />);
  const img = new Image();
  img.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
  await img.decode();
  const canvas = document.createElement("canvas");
  canvas.width = img.naturalWidth;
  canvas.height = img.naturalHeight;
  canvas.getContext("2d")!.drawImage(img, 0, 0);
  const blob = await new Promise<Blob | null>((ok) => canvas.toBlob(ok, "image/png"));
  if (!blob) throw new Error("UnderTheHood presenter: the canvas produced no image");
  urls.set(key, URL.createObjectURL(blob));
}

/** The presenter at body-box position (left, top), at `opacity`. */
export const PresenterSprite: React.FC<{ pose: Pose; mouth: 0 | 1 | 2; blink: boolean; left: number; top: number; opacity?: number }> = ({
  pose, mouth, blink, left, top, opacity = 1,
}) => {
  const key = `${pose}|${mouth}|${blink ? 1 : 0}`;
  const url = urls.get(key);
  const [, rerender] = useReducer((n: number) => n + 1, 0);
  useLayoutEffect(() => {
    if (urls.has(key)) return;
    const handle = delayRender(`UnderTheHood presenter: drawing ${key}`);
    let job = pending.get(key);
    if (!job) {
      job = rasterise(key, pose, mouth, blink).finally(() => pending.delete(key));
      pending.set(key, job);
    }
    job
      .then(() => {
        rerender();
        continueRender(handle);
      })
      .catch((err) => cancelRender(err));
    // pose, mouth and blink are fully described by `key`
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  if (!url) return null;
  return (
    <Img
      src={url}
      style={{ position: "absolute", left: left + VIEW.left, top: top + VIEW.top, width: VIEW.width, height: VIEW.height, opacity: opacity === 1 ? undefined : opacity }}
    />
  );
};
