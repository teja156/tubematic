/*
 * The bean on stage, drawn as a cached bitmap.
 *
 * Measured on the CPU renderer (software GL): the bean drawn as live SVG cost
 * about 0.3 CPU-seconds per frame, the same when it did not move, the same at
 * a seventh of the size and the same with hairline strokes, while a bitmap of
 * it cost nothing measurable. So each distinct look of the bean (its blended
 * pose, face, gaze, blink, accessory, tint and scale) is drawn once from the
 * same SVG rig (bean.tsx), rasterised to a PNG, and reused on every frame
 * that looks the same. The look of this style is snap-then-hold, so most
 * frames are a cache hit; a swap costs one draw for each of its two blend
 * frames. Squash, the entrance pop and hops are a transform on the bitmap,
 * never a new drawing. The marks stay vector, drawn beside the head by the
 * scene, because they animate on every frame.
 *
 * The cache lives for the life of a render tab. A miss holds the frame with
 * delayRender until its bitmap exists, so no frame is captured without it; a
 * bitmap that cannot be drawn fails the render, never a frame with no bean.
 */
import React, { useLayoutEffect, useReducer } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { Img, cancelRender, continueRender, delayRender } from "remotion";
import { Bean, WAVE_FRAMES, blinkAt, type BeanProps } from "./bean";

/** The sprite's box in body coordinates: wide enough for any reach, tall enough for any hat or raised hand. */
export const SPRITE = { left: -380, top: -880, width: 760, height: 940 } as const;

const urls = new Map<string, string>();
const pending = new Map<string, Promise<void>>();

type Look = Omit<BeanProps, "x" | "y" | "marks" | "enter" | "swapFrame" | "frame" | "fps" | "seed" | "font" | "uid"> & {
  blink: number;
  waveFrame: number;
};

function lookOf(p: BeanProps): Look {
  const r = (v: number) => Math.round(v * 100) / 100;
  return {
    scale: r(p.scale), pose: p.pose, prevPose: p.prevPose, poseT: r(p.poseT), face: p.face, look: p.look,
    aim: p.aim ? [Math.round(p.aim[0] / 4) * 4, Math.round(p.aim[1] / 4) * 4] : undefined,
    accessory: p.accessory, tint: p.tint, blink: r(p.blink ?? blinkAt(p.frame, p.seed)),
    // the hand waves for WAVE_FRAMES after the pose begins, then holds: a fixed set of phases
    waveFrame: p.pose === "wave" ? Math.max(0, Math.min(Math.round(p.frame - (p.poseAt ?? 0)), WAVE_FRAMES)) : 0,
  };
}

function markup(l: Look): string {
  const w = Math.ceil(SPRITE.width * l.scale), h = Math.ceil(SPRITE.height * l.scale);
  return renderToStaticMarkup(
    <svg xmlns="http://www.w3.org/2000/svg" width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
      <Bean frame={l.waveFrame} fps={30} x={-SPRITE.left * l.scale} y={-SPRITE.top * l.scale} scale={l.scale}
        pose={l.pose} prevPose={l.prevPose} poseT={l.poseT} face={l.face} look={l.look} swapFrame={-100}
        aim={l.aim} marks={[]} enter={1} accessory={l.accessory} tint={l.tint} seed={0} font="sans-serif"
        uid="s" blink={l.blink} poseAt={0} />
    </svg>,
  );
}

async function rasterise(key: string, l: Look): Promise<void> {
  const img = new Image();
  img.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(markup(l))}`;
  await img.decode();
  const canvas = document.createElement("canvas");
  canvas.width = img.naturalWidth;
  canvas.height = img.naturalHeight;
  canvas.getContext("2d")!.drawImage(img, 0, 0);
  const blob = await new Promise<Blob | null>((ok) => canvas.toBlob(ok, "image/png"));
  if (!blob) throw new Error("BeanSprite: the canvas produced no image");
  urls.set(key, URL.createObjectURL(blob));
}

/** The bean at `p`, as an absolutely placed bitmap with its squash and pop as a transform. */
export const BeanSprite: React.FC<{ p: BeanProps; squash: [number, number] }> = ({ p, squash }) => {
  const l = lookOf(p);
  const key = JSON.stringify(l);
  const url = urls.get(key);
  const [, rerender] = useReducer((n: number) => n + 1, 0);
  useLayoutEffect(() => {
    if (urls.has(key)) return;
    const handle = delayRender(`BeanSprite: drawing ${p.pose}/${p.face}`);
    let job = pending.get(key);
    if (!job) {
      job = rasterise(key, l).finally(() => pending.delete(key));
      pending.set(key, job);
    }
    job
      .then(() => {
        rerender();
        continueRender(handle);
      })
      .catch((err) => cancelRender(err));
    // `l` is fully described by `key`
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  if (!url) return null;
  const s = l.scale;
  const left = p.x + SPRITE.left * s, top = p.y + SPRITE.top * s;
  const [sx, sy] = squash;
  const k = p.enter;
  const moved = sx !== 1 || sy !== 1 || k !== 1;
  return (
    <Img
      src={url}
      style={{
        position: "absolute", left, top, width: SPRITE.width * s, height: SPRITE.height * s,
        transform: moved ? `scale(${sx * k}, ${sy * k})` : undefined,
        transformOrigin: `${-SPRITE.left * s}px ${-SPRITE.top * s}px`,
      }}
    />
  );
};
