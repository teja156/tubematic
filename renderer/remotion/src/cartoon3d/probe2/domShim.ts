// A just-enough DOM for building parts in Node (headless QA, the gate's deterministic check, the stager): the
// kit's textures draw on 2D canvases, and a code part may too. Nothing is rasterised; every drawing call is a
// no-op, so Box3 and triangle counts come out right and pixels do not exist. Installed only where `document`
// is missing, so the browser path is untouched. Call installDomShim() first in every Node entry that builds
// parts (an explicit call, because the package's sideEffects list lets the bundler drop a bare import).
/* eslint-disable @typescript-eslint/no-explicit-any */
export const installDomShim = () => {
  const g = globalThis as any;
  if (typeof g.document !== "undefined") return;
  const ctx2d = (canvas: any) =>
    new Proxy({}, {
      get: (_t, k: string) => {
        if (k === "canvas") return canvas;
        if (k === "measureText") return (s: string) => ({ width: 8 * String(s).length, actualBoundingBoxAscent: 8, actualBoundingBoxDescent: 2 });
        if (k === "getImageData" || k === "createImageData") return (_x: number, _y: number, w = 1, h = 1) => ({ data: new Uint8ClampedArray(Math.max(1, (w | 0) * (h | 0)) * 4), width: w, height: h });
        if (k === "createLinearGradient" || k === "createRadialGradient" || k === "createConicGradient") return () => ({ addColorStop() {} });
        if (k === "createPattern") return () => ({ setTransform() {} });
        if (k === "getTransform") return () => ({ a: 1, b: 0, c: 0, d: 1, e: 0, f: 0 });
        if (k === "isPointInPath" || k === "isPointInStroke") return () => false;
        return () => undefined;
      },
      set: () => true,
    });
  const canvas = () => {
    const c: any = { width: 1, height: 1, style: {}, toDataURL: () => "data:,", toBlob: () => undefined, addEventListener() {}, removeEventListener() {} };
    c.getContext = () => ctx2d(c);
    return c;
  };
  g.document = {
    createElement: (tag: string) => (tag === "canvas" ? canvas() : { style: {}, appendChild() {}, setAttribute() {}, addEventListener() {} }),
    createElementNS: (_ns: string, tag: string) => (tag === "canvas" ? canvas() : { style: {}, setAttribute() {} }),
    body: { appendChild() {}, removeChild() {} },
    addEventListener() {},
  };
  if (typeof g.window === "undefined") g.window = g;
  if (typeof g.self === "undefined") g.self = g;
  if (typeof g.OffscreenCanvas === "undefined") g.OffscreenCanvas = function (this: any, w: number, h: number) { const c = canvas(); c.width = w; c.height = h; return c; };
  if (typeof g.requestAnimationFrame === "undefined") g.requestAnimationFrame = (fn: (t: number) => void) => setTimeout(() => fn(0), 0);
  if (typeof g.Image === "undefined") g.Image = function (this: any) { return { addEventListener() {}, set src(_v: string) {} }; };
};
