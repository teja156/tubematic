/*
 * A paper finish for the paper styles (TMDEV-228..231): fibre grain and a soft
 * vignette, painted ONCE onto a canvas when the scene mounts and never again.
 *
 * Measured traps this avoids (software GL): a full-frame CSS radial gradient
 * costs over 2x a frame, and per-frame SVG noise (feTurbulence) 10 to 100x.
 * A canvas painted once is a plain bitmap to the compositor, so the finish
 * costs about nothing per frame as long as it sits UNDER the scene's content,
 * on the paper. Laid over content that changes, it is blended again on every
 * frame (measured: about two thirds of a System Flow frame on its own). Its
 * grain is faint dark and light specks at low alpha, so it reads as paper on
 * any colour without a blend mode.
 */
import React, { useLayoutEffect, useRef } from "react";

export interface PaperFinishProps {
  /** Fibre speck strength, 0 to 1. */
  grain?: number;
  /** Edge darkening at the corners, 0 to 1. */
  vignette?: number;
  /** The vignette's colour (the paper's shadow tone). */
  edge?: string;
  /** Seed, so a style's finish is the same picture every render. */
  seed?: number;
  width?: number;
  height?: number;
}

/** A small deterministic random sequence (mulberry32). */
export function seeded(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export const PaperFinish: React.FC<PaperFinishProps> = ({
  grain = 0.5, vignette = 0.5, edge = "#6E5E44", seed = 7, width = 1080, height = 1920,
}) => {
  const ref = useRef<HTMLCanvasElement>(null);
  useLayoutEffect(() => {
    const c = ref.current;
    const g = c?.getContext("2d");
    if (!c || !g) return;
    g.clearRect(0, 0, width, height);
    if (vignette > 0) {
      const v = g.createRadialGradient(width / 2, height * 0.45, height * 0.3, width / 2, height * 0.45, height * 0.75);
      v.addColorStop(0, `${edge}00`);
      v.addColorStop(1, edge + Math.round(vignette * 0.55 * 255).toString(16).padStart(2, "0"));
      g.fillStyle = v;
      g.fillRect(0, 0, width, height);
    }
    if (grain > 0) {
      const rnd = seeded(seed);
      const n = Math.round(width * height * 0.012 * grain);
      for (let i = 0; i < n; i++) {
        const x = rnd() * width;
        const y = rnd() * height;
        const dark = rnd() < 0.55;
        g.fillStyle = dark ? `rgba(60,48,30,${(0.05 + rnd() * 0.08).toFixed(3)})` : `rgba(255,252,240,${(0.05 + rnd() * 0.1).toFixed(3)})`;
        const len = 1 + rnd() * 3;
        g.fillRect(x, y, rnd() < 0.5 ? len : 1, rnd() < 0.5 ? 1 : len);
      }
    }
  }, [grain, vignette, edge, seed, width, height]);
  return (
    <canvas ref={ref} width={width} height={height}
      style={{ position: "absolute", inset: 0, width, height, pointerEvents: "none" }} />
  );
};
