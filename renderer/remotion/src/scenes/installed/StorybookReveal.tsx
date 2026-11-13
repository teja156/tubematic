/*
 * StorybookReveal: the whole of a Storybook Reveal video, as one scene.
 *
 * A warm tale told page by page on a cream picture-book page. Each page has a
 * short hand-lettered title that wipes in, one large rounded panel holding a
 * square children's-book picture, a page number, and the captions under the panel
 * (the shared Subtitles layer, "fill" look with no plate). The picture is
 * revealed in two steps on the narration's words: its pencil plate wipes in
 * from the left, then its colour floods over the drawing from the left with a
 * soft, ragged watercolour edge, and the picture pushes in slowly until the
 * page ends. A page arrives on a hard cut or turns over from its bottom-right
 * corner (a curl).
 *
 * The agent never writes this file's kind of code: it writes `props.reveal`
 * (the pages, each a generated still and its pencil plate, timed to the
 * narration), which the MCP server validates against
 * ./storybookReveal/contract.ts before the video can render.
 *
 * Kept cheap on the CPU renderer (software GL). Each still is scaled down to
 * the panel ONCE, with its edges feathered, onto a canvas held in memory, so
 * the panel draws it at nearly 1:1 every frame: a full-size still drawn
 * straight into the panel shimmers on its fine pencil lines and costs a
 * full-size image per frame. The panel is one canvas redrawn per frame (the
 * plates, the flood and the push are a few 2D copies), so the push scales only
 * the picture inside its panel, never a CSS-scaled layer. The paper and the
 * panel's rim and vignette are painted once; there is no SVG filter, blend
 * mode, live CSS gradient or blur. A transform or clip-path is set only on the
 * frames something moves.
 *
 * Measured in CPU-seconds per frame over the whole skill example (797 frames,
 * rendered from a prebuilt bundle with software GL, concurrency 2): 0.54 here,
 * 0.23 for System Flow's example on the same day by the same method (2.4x).
 * Most of it is the push redrawing the panel on every frame after the colour.
 */
import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import { AbsoluteFill, cancelRender, continueRender, delayRender, useCurrentFrame, useVideoConfig } from "remotion";
import { COLORS, H, TIMING, W, ZONES, type Page, type RevealData, type UV } from "./storybookReveal/contract";
import {
  clamp01, curlShapes, curlTravel, FLOOD_SOFT, floodFront, floodPolygon, landFrame, pageEnd, pageIndexAt, pencilProgress,
  pictureBox, pushScale, pushedBox, rng, titleProgress, titleSize, type Pt,
} from "./storybookReveal/stage";
import { useFonts, type FontFile } from "./paper/fonts";
import { PaperFinish } from "./paper/PaperFinish";

// The caption face is registered as covering every weight: the captions ask
// for a bold weight, and Lora ships here in its regular cut only, which a
// browser would otherwise thicken into a fake bold.
export const REVEAL_FONTS: FontFile[] = [
  ["Patrick Hand", "fonts/patrick-hand-latin-400-normal.woff2", "400"],
  ["Storybook Lora", "fonts/lora-latin-400-normal.woff2", "100 900"],
];

const HAND = "'Patrick Hand', 'Comic Sans MS', cursive";
const Z = ZONES;
// The panel canvas reaches this far past the panel on every side, for its rough rim.
const M = 12;
const CW = Z.panelWidth + 2 * M;
const CH = Z.panelHeight + 2 * M;

export interface StorybookRevealProps {
  reveal: RevealData;
}

const f1 = (n: number) => n.toFixed(1);

interface Plate {
  canvas: HTMLCanvasElement;
  box: [number, number, number, number];
  paper: string;
}

// ── painting once ────────────────────────────────────────────────────────────
function makeCanvas(w: number, h: number): HTMLCanvasElement {
  const c = document.createElement("canvas");
  c.width = Math.max(1, Math.round(w));
  c.height = Math.max(1, Math.round(h));
  return c;
}

/** A still scaled to its panel box (with room for the push), in halving steps so
 *  fine lines stay smooth, its edges feathered into transparency. */
function bake(img: HTMLImageElement): Plate {
  const box = pictureBox(img.naturalWidth, img.naturalHeight);
  const k = 1 + TIMING.push;
  const tw = box[2] * k, th = box[3] * k;
  let src: CanvasImageSource = img;
  let sw = img.naturalWidth, sh = img.naturalHeight;
  while (sw / 2 > tw) {
    const step = makeCanvas(sw / 2, sh / 2);
    const g = step.getContext("2d")!;
    g.imageSmoothingQuality = "high";
    g.drawImage(src, 0, 0, step.width, step.height);
    src = step;
    sw = step.width;
    sh = step.height;
  }
  const out = makeCanvas(tw, th);
  const g = out.getContext("2d")!;
  g.imageSmoothingQuality = "high";
  g.drawImage(src, 0, 0, out.width, out.height);
  // the paper colour: the mean of the four corners, where every still is plain paper
  const px = g.getImageData(0, 0, out.width, out.height).data;
  let r = 0, gr = 0, b = 0, n = 0;
  for (const [cx, cy] of [[4, 4], [out.width - 12, 4], [4, out.height - 12], [out.width - 12, out.height - 12]]) {
    for (let y = cy; y < cy + 8; y++) {
      for (let x = cx; x < cx + 8; x++) {
        const o = (y * out.width + x) * 4;
        r += px[o];
        gr += px[o + 1];
        b += px[o + 2];
        n++;
      }
    }
  }
  const paper = `rgb(${Math.round(r / n)},${Math.round(gr / n)},${Math.round(b / n)})`;
  // feather: each edge fades out over Z.feather (at the bake's scale)
  const f = Z.feather * k;
  g.globalCompositeOperation = "destination-in";
  const fade = (x0: number, y0: number, x1: number, y1: number) => {
    const grad = g.createLinearGradient(x0, y0, x1, y1);
    grad.addColorStop(0, "rgba(0,0,0,0)");
    grad.addColorStop(1, "rgba(0,0,0,1)");
    g.fillStyle = grad;
    g.fillRect(0, 0, out.width, out.height);
  };
  fade(0, 0, f, 0);
  fade(out.width, 0, out.width - f, 0);
  fade(0, 0, 0, f);
  fade(0, out.height, 0, out.height - f);
  g.globalCompositeOperation = "source-over";
  return { canvas: out, box, paper };
}

/** The panel's outline: a rounded rectangle whose edge wobbles a little, like a deckled page. */
function panelPath(): Path2D {
  const r = Z.panelRadius, w = Z.panelWidth, h = Z.panelHeight;
  const pts: Pt[] = [];
  const corner = (cx: number, cy: number, a0: number) => {
    for (let i = 0; i <= 8; i++) {
      const a = a0 + (i / 8) * (Math.PI / 2);
      pts.push([cx + Math.cos(a) * r, cy + Math.sin(a) * r]);
    }
  };
  corner(w - r, r, -Math.PI / 2);
  corner(w - r, h - r, 0);
  corner(r, h - r, Math.PI / 2);
  corner(r, r, Math.PI);
  // subdivide, then push each point along its normal by smoothed seeded noise
  const dense: Pt[] = [];
  for (let i = 0; i < pts.length; i++) {
    const a = pts[i], b = pts[(i + 1) % pts.length];
    const steps = Math.max(1, Math.round(Math.hypot(b[0] - a[0], b[1] - a[1]) / 18));
    for (let j = 0; j < steps; j++) dense.push([a[0] + ((b[0] - a[0]) * j) / steps, a[1] + ((b[1] - a[1]) * j) / steps]);
  }
  const rnd = rng(909);
  const raw = dense.map(() => rnd() * 2 - 1);
  const p = new Path2D();
  dense.forEach((q, i) => {
    const prev = dense[(i - 1 + dense.length) % dense.length], next = dense[(i + 1) % dense.length];
    let nx = -(next[1] - prev[1]), ny = next[0] - prev[0];
    const l = Math.hypot(nx, ny) || 1;
    nx /= l;
    ny /= l;
    const d = ((raw[(i - 1 + raw.length) % raw.length] + 2 * raw[i] + raw[(i + 1) % raw.length]) / 4) * 3;
    const x = M + q[0] + nx * d, y = M + q[1] + ny * d;
    if (i === 0) p.moveTo(x, y);
    else p.lineTo(x, y);
  });
  p.closePath();
  return p;
}

/** The panel's rim, vignette and grain, painted once over the panel every frame. */
function paintFrame(path: Path2D): HTMLCanvasElement {
  const c = makeCanvas(CW, CH);
  const g = c.getContext("2d")!;
  g.save();
  g.clip(path);
  const v = g.createRadialGradient(CW / 2, CH * 0.48, Math.min(CW, CH) * 0.36, CW / 2, CH * 0.48, Math.hypot(CW, CH) * 0.52);
  v.addColorStop(0, "rgba(125,98,71,0)");
  v.addColorStop(1, "rgba(125,98,71,0.30)");
  g.fillStyle = v;
  g.fillRect(0, 0, CW, CH);
  const rnd = rng(431);
  for (let i = 0; i < 5200; i++) {
    const dark = rnd() < 0.55;
    g.fillStyle = dark ? `rgba(80,62,40,${(0.04 + rnd() * 0.06).toFixed(3)})` : `rgba(255,252,240,${(0.05 + rnd() * 0.08).toFixed(3)})`;
    const len = 1 + rnd() * 3;
    g.fillRect(rnd() * CW, rnd() * CH, rnd() < 0.5 ? len : 1, rnd() < 0.5 ? 1 : len);
  }
  g.restore();
  g.lineJoin = "round";
  g.strokeStyle = "rgba(125,98,71,0.42)";
  g.lineWidth = 2.2;
  g.stroke(path);
  g.strokeStyle = "rgba(125,98,71,0.16)";
  g.lineWidth = 6;
  g.stroke(path);
  return c;
}

interface Painted {
  plates: Map<string, Plate>;
  path: Path2D;
  frame: HTMLCanvasElement;
}

/** Every plate the video uses, loaded and baked before the first frame; one that will not load fails the render. */
function usePainted(data: RevealData): Painted | null {
  const [painted, setPainted] = useState<Painted | null>(null);
  const [handle] = useState(() => delayRender("StorybookReveal: loading the pages"));
  const key = Array.from(new Set(data.pages.flatMap((p) => [p.image, p.pencil]))).join("|");
  useEffect(() => {
    const srcs = key.split("|");
    Promise.all(srcs.map((src) => {
      const img = new Image();
      img.src = src;
      return img.decode().then(() => [src, bake(img)] as const);
    }))
      .then((baked) => {
        const path = panelPath();
        setPainted({ plates: new Map(baked), path, frame: paintFrame(path) });
        continueRender(handle);
      })
      .catch((err) => cancelRender(err));
    // the pictures are fixed for the whole render; the key changes only with them
  }, [key, handle]);
  return painted;
}

// ── the panel ────────────────────────────────────────────────────────────────
// The flood's soft edge: the front drawn five times, the furthest ahead the faintest.
const SOFT: [number, number][] = [[FLOOD_SOFT, 0.15], [FLOOD_SOFT * 0.75, 0.25], [FLOOD_SOFT * 0.5, 0.4], [FLOOD_SOFT * 0.25, 0.6], [0, 1]];

function drawPanel(g: CanvasRenderingContext2D, painted: Painted, page: Page, first: boolean, frame: number, end: number, seed: number) {
  const colour = painted.plates.get(page.image);
  const pencil = painted.plates.get(page.pencil);
  g.clearRect(0, 0, CW, CH);
  g.save();
  g.clip(painted.path);
  g.fillStyle = COLORS.page;
  g.fillRect(0, 0, CW, CH);
  if (colour && pencil) {
    const focus: UV = page.focus ?? [0.5, 0.5];
    const land = landFrame(page);
    const [bx, by, bw, bh] = pushedBox(colour.box, pushScale(frame, land, end), focus);
    const x = M + bx, y = M + by;
    const k = (frame - page.colourAt) / TIMING.colour;
    // the pencil plate, wiping in from the left, until the colour has covered it
    const p = pencilProgress(page, first, frame);
    if (p > 0 && k < 1) {
      if (p >= 1) g.drawImage(pencil.canvas, x, y, bw, bh);
      else {
        const edge = x - 20 + p * (bw + 40);
        for (const [ahead, alpha] of [[16, 0.45], [0, 1]]) {
          g.save();
          g.beginPath();
          g.rect(0, 0, edge + ahead, CH);
          g.clip();
          g.globalAlpha = alpha;
          g.drawImage(pencil.canvas, x, y, bw, bh);
          g.restore();
        }
      }
    }
    // the colour, flooding across the whole panel with a soft, ragged edge
    if (k >= 1) {
      g.fillStyle = colour.paper;
      g.fillRect(0, 0, CW, CH);
      g.drawImage(colour.canvas, x, y, bw, bh);
    } else if (k > 0) {
      for (const [ahead, alpha] of SOFT) {
        const poly = floodPolygon(floodFront(k, CW, CH, seed, ahead));
        g.save();
        g.beginPath();
        poly.forEach(([px, py], i) => (i ? g.lineTo(px, py) : g.moveTo(px, py)));
        g.closePath();
        g.clip();
        g.globalAlpha = alpha;
        g.fillStyle = colour.paper;
        g.fillRect(0, 0, CW, CH);
        g.drawImage(colour.canvas, x, y, bw, bh);
        g.restore();
      }
      // the wet, pooled edge of the wash while it runs
      const wet = Math.sin(Math.PI * clamp01(k));
      g.lineCap = "round";
      g.lineJoin = "round";
      g.beginPath();
      floodFront(k, CW, CH, seed, FLOOD_SOFT * 0.3).forEach(([px, py], i) => (i ? g.lineTo(px, py) : g.moveTo(px, py)));
      g.strokeStyle = `rgba(125,98,71,${(0.12 * wet).toFixed(3)})`;
      g.lineWidth = 10;
      g.stroke();
      g.strokeStyle = `rgba(125,98,71,${(0.22 * wet).toFixed(3)})`;
      g.lineWidth = 2.2;
      g.stroke();
    }
  }
  g.restore();
  g.drawImage(painted.frame, 0, 0);
}

const Panel: React.FC<{ painted: Painted; page: Page; first: boolean; frame: number; end: number; seed: number }> = ({
  painted, page, first, frame, end, seed,
}) => {
  const ref = useRef<HTMLCanvasElement>(null);
  useLayoutEffect(() => {
    const g = ref.current?.getContext("2d");
    if (g) drawPanel(g, painted, page, first, frame, end, seed);
  }, [painted, page, first, frame, end, seed]);
  return (
    <canvas ref={ref} width={CW} height={CH}
      style={{ position: "absolute", left: Z.panelLeft - M, top: Z.panelTop - M, width: CW, height: CH }} />
  );
};

// ── the title and the page number ────────────────────────────────────────────
/** A pencil swash: one wobbly stroke drawn twice, seeded by the page. */
function swash(width: number, seed: number): string {
  const r = rng(seed);
  const n = 14;
  let d = "";
  for (let pass = 0; pass < 2; pass++) {
    for (let i = 0; i <= n; i++) {
      const x = (i / n) * width;
      const y = Math.sin((i / n) * Math.PI * 1.3 + pass) * 3 + (r() - 0.5) * 2.4 + pass * 2;
      d += `${i ? "L" : "M"}${f1(x)} ${f1(y + 10)}`;
    }
  }
  return d;
}

export const Title: React.FC<{ text: string; progress: number; seed: number }> = ({ text, progress, seed }) => {
  const size = titleSize(text);
  const width = Math.min(Z.titleWidth * 0.7, Math.max(160, text.length * size * 0.42));
  const mid = (Z.titleTop + Z.titleBottom) / 2;
  return (
    <div style={{
      position: "absolute", left: (W - Z.titleWidth) / 2, width: Z.titleWidth, top: Z.titleTop, height: Z.titleBottom - Z.titleTop,
      clipPath: progress < 1 ? `inset(-20px ${f1((1 - progress) * 100)}% -20px -20px)` : undefined,
    }}>
      <div style={{
        position: "absolute", left: 0, right: 0, top: mid - Z.titleTop - size * 0.72, textAlign: "center", whiteSpace: "nowrap",
        fontFamily: HAND, fontSize: size, lineHeight: 1.2, letterSpacing: "0.05em", color: COLORS.ink, textTransform: "uppercase",
      }}>{text}</div>
      <svg width={width} height={24} style={{ position: "absolute", left: (Z.titleWidth - width) / 2, top: Z.swashY - Z.titleTop }}>
        <path d={swash(width, seed)} fill="none" stroke={COLORS.brown} strokeWidth={2.6} strokeLinecap="round" strokeLinejoin="round" opacity={0.8} />
      </svg>
    </div>
  );
};

const PageNumber: React.FC<{ n: number }> = ({ n }) => (
  <div style={{
    position: "absolute", left: 0, width: W, top: Z.pageNoY - 26, textAlign: "center", fontFamily: HAND, fontSize: 44,
    lineHeight: 1.2, letterSpacing: "0.14em", color: COLORS.olive,
  }}>~ {n} ~</div>
);

// ── a page ───────────────────────────────────────────────────────────────────
const PageLayer: React.FC<{
  painted: Painted; page: Page; n: number; frame: number; end: number; clip?: Pt[];
}> = ({ painted, page, n, frame, end, clip }) => {
  const first = n === 1;
  return (
    <AbsoluteFill style={{
      background: COLORS.page,
      clipPath: clip ? `polygon(${clip.map(([x, y]) => `${f1(x)}px ${f1(y)}px`).join(",")})` : undefined,
    }}>
      <PaperFinish grain={0.4} vignette={0.6} edge="#8C7652" seed={2031} />
      <Title text={page.title} progress={titleProgress(page, first, frame)} seed={300 + n} />
      <Panel painted={painted} page={page} first={first} frame={frame} end={end} seed={4242 + 97 * n} />
      <PageNumber n={n} />
    </AbsoluteFill>
  );
};

const pts = (p: Pt[]) => p.map(([x, y]) => `${f1(x)},${f1(y)}`).join(" ");

/** The turning flap of a curl and the shadow its fold casts: flat fills only. */
const Flap: React.FC<{ s: number }> = ({ s }) => {
  const { flap, bands, shade } = curlShapes(s);
  if (flap.length < 3) return null;
  return (
    <svg width={W} height={H} style={{ position: "absolute", left: 0, top: 0 }}>
      {shade.length > 2 && <polygon points={pts(shade)} fill={COLORS.shade} opacity={0.14} />}
      {bands.map(([band, colour], k) => <polygon key={k} points={pts(band)} fill={colour} stroke={colour} strokeWidth={1} />)}
      <polygon points={pts(flap)} fill="none" stroke={COLORS.flapEdge} strokeWidth={1.6} opacity={0.8} />
    </svg>
  );
};

export default function StorybookReveal({ reveal }: StorybookRevealProps) {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  useFonts("StorybookReveal", REVEAL_FONTS);
  const painted = usePainted(reveal);
  const pages = reveal.pages;
  const i = pageIndexAt(pages, frame);
  const page = pages[i];
  if (!painted || !page) return <AbsoluteFill style={{ background: COLORS.page }} />;
  const end = pageEnd(pages, i, durationInFrames);
  const curling = i > 0 && page.turn === "curl" && frame < page.start + TIMING.curl;
  const s = curling ? curlTravel(frame, page.start) : 0;
  return (
    <AbsoluteFill style={{ background: COLORS.page, overflow: "hidden" }}>
      <PageLayer key={i} painted={painted} page={page} n={i + 1} frame={frame} end={end} />
      {curling && s > 0 && (
        <>
          {/* the page before, held as it was on its last frame, folding away */}
          <PageLayer key={i - 1} painted={painted} page={pages[i - 1]} n={i} frame={page.start - 1} end={page.start}
            clip={curlShapes(s).keep} />
          <Flap s={s} />
        </>
      )}
      {curling && s === 0 && (
        <PageLayer key={i - 1} painted={painted} page={pages[i - 1]} n={i} frame={page.start - 1} end={page.start} />
      )}
    </AbsoluteFill>
  );
}
