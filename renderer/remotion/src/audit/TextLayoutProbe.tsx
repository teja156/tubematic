import { useEffect, useLayoutEffect, useState } from "react";
import { continueRender, delayRender, useCurrentFrame } from "remotion";

// Text-layout measurement probe (VQA-9).
//
// Mounted ONLY by the "TextLayoutAudit" composition in Root.tsx, never by the
// real "Composition" render path. It walks the DOM and prints one JSON line per
// commit; audit/run-text-layout-audit.mjs collects those via renderFrames'
// onBrowserLog and hands them to mcp/text_audit.py.
//
// THIS FILE EMITS MEASUREMENTS, NOT VERDICTS — deliberately. Every threshold
// (overlap fraction, safe-zone bounds, the opacity floor) lives in
// mcp/text_audit.py, where it is covered by pytest. This host cannot run
// Remotion at all (Node 18 vs @tailwindcss/oxide's >=20), so keeping policy out
// of the browser is what makes any of it testable outside a container. Do not
// move a threshold in here.

/** Prefix that identifies our console lines to the Node driver. */
export const PROBE_LOG_PREFIX = "__TUBEMATIC_TEXT_AUDIT__";

/** Longest text excerpt reported per element, so a report stays readable. */
const MAX_TEXT_CHARS = 80;

interface MeasuredElement {
  /** Stable-ish identity within one frame: index in document order. */
  index: number;
  tag: string;
  text: string;
  x: number;
  y: number;
  width: number;
  height: number;
  /** Computed font-size in px. */
  fontSize: number;
  /**
   * Computed line-height in px, or null when it is `normal`.
   *
   * The Python side subtracts half-leading from each rect before testing for
   * collisions, because getBoundingClientRect() measures the LINE BOX, not the
   * glyphs — so text stacked slightly tighter than its own line-height has
   * intersecting rects while looking perfectly clean on screen.
   *
   * null is reported rather than resolved to a number on purpose: `normal` has
   * no px value in getComputedStyle, and it does not need one. At `normal` the
   * line box is barely larger than the font's ascent+descent (for Liberation
   * Sans, the face `sans-serif` resolves to in the renderer image, 1.149em vs
   * 1.117em — under 2% per side), so there is no meaningful leading to remove.
   * Leading only matters when a scene sets line-height explicitly, and that is
   * exactly the case where a px value comes back.
   */
  lineHeight: number | null;
  /** Product of computed opacity from this element up through its ancestors. */
  opacity: number;
  /** True when the element (or an ancestor) applies a rotation or skew. */
  rotated: boolean;
  /** Document-order indices of ancestors that are themselves measured. */
  ancestorIndices: number[];
}

/**
 * Is this element a leaf text node for auditing purposes?
 *
 * Requires EVERY child node to be text. A <span> inside a <div> would otherwise
 * be reported alongside its parent, whose rect *contains* it — i.e. a 100%
 * "overlap" on every scene that nests text at all. Whitespace-only content
 * doesn't count as text.
 *
 * Known limit: <div>text<span>more</span></div> contributes only the <span>.
 * No installed scene or skill example has that shape.
 */
const isLeafTextElement = (el: Element): boolean => {
  const children = Array.from(el.childNodes);
  if (children.length === 0) {
    return false;
  }
  if (!children.every((n) => n.nodeType === Node.TEXT_NODE)) {
    return false;
  }
  return (el.textContent ?? "").trim().length > 0;
};

/**
 * Does this element's own transform rotate or skew it?
 *
 * getBoundingClientRect() returns the axis-aligned bounding box, which for
 * rotated text is much larger than the glyphs — so a rotated element would
 * report a box far bigger than what a viewer sees. Such elements are flagged
 * here and skipped by the Python side rather than guessed at with a transformed
 * quad. A pure translate/scale matrix keeps b and c at 0, which is the common
 * case (ImageFX, spring entrances) and must NOT be treated as rotation.
 */
const hasRotation = (el: Element): boolean => {
  const transform = window.getComputedStyle(el).transform;
  if (!transform || transform === "none") {
    return false;
  }
  const nums = transform
    .slice(transform.indexOf("(") + 1, transform.lastIndexOf(")"))
    .split(",")
    .map((v) => Number(v.trim()));
  // matrix(a, b, c, d, e, f) — b/c are the skew/rotation terms.
  // matrix3d(...) is 16 long; its equivalents sit at indices 1 and 4.
  if (nums.length === 6) {
    return Math.abs(nums[1]) > 1e-6 || Math.abs(nums[2]) > 1e-6;
  }
  if (nums.length === 16) {
    return Math.abs(nums[1]) > 1e-6 || Math.abs(nums[4]) > 1e-6;
  }
  return false;
};

/**
 * Effective opacity as actually seen, and whether anything up the chain rotates.
 *
 * Opacity has to be accumulated because it is inherited multiplicatively and
 * lives on an ANCESTOR in every real case: CompositionBuilder's SceneWithFades
 * puts the scene crossfade on a wrapping AbsoluteFill, and scenes routinely put
 * their own entrance fade on another one. A rect-only audit would report text
 * no viewer can see.
 */
const accumulateFromAncestors = (
  el: Element,
): { opacity: number; rotated: boolean } => {
  let opacity = 1;
  let rotated = false;
  let node: Element | null = el;
  while (node) {
    const style = window.getComputedStyle(node);
    const own = Number.parseFloat(style.opacity);
    if (Number.isFinite(own)) {
      opacity *= own;
    }
    if (style.visibility === "hidden" || style.display === "none") {
      opacity = 0;
    }
    if (hasRotation(node)) {
      rotated = true;
    }
    node = node.parentElement;
  }
  return { opacity, rotated };
};

/**
 * The rect of the TEXT, not of the element's box.
 *
 * element.getBoundingClientRect() on a block-level element returns the whole
 * container: a `<div style={{left: 350, width: 780}}>COURTESY</div>` measures
 * 780px wide no matter how short the word is. That produced a real false
 * positive on the first clean video audited — six "text runs off the right
 * edge" findings on a scene whose glyphs all sat comfortably inside the frame,
 * because the container it inherited its width from ended at x=1130.
 *
 * A Range over the element's contents measures the laid-out text instead:
 * horizontally tight to the longest line, vertically the union of the line
 * boxes (whose leading the Python side already deflates). Inline elements are
 * unaffected — their box was already the text.
 */
const inkRect = (el: Element): DOMRect => {
  const range = document.createRange();
  try {
    range.selectNodeContents(el);
    const rect = range.getBoundingClientRect();
    if (rect.width > 0 && rect.height > 0) {
      return rect;
    }
  } catch {
    // Fall through to the element box.
  } finally {
    range.detach();
  }
  return el.getBoundingClientRect();
};

/**
 * A picture element of the scene layer, for the first-frame pass (TMDEV-215).
 * kind "picture" is an image, a canvas, a video, an SVG shape or an element
 * whose background is an image; "background" is an element filled with a
 * colour or a gradient. Python decides which of them is a subject.
 */
interface MeasuredVisual {
  tag: string;
  kind: "picture" | "background";
  x: number;
  y: number;
  width: number;
  height: number;
  opacity: number;
}

const PICTURE_TAGS = new Set([
  "img", "canvas", "video", "path", "circle", "rect", "ellipse", "line", "polyline", "polygon", "image", "use",
]);

/** How long a picture frame must be quiet before its last measurement. */
const VISUAL_SETTLE_MS = 300;

/** The largest pictures reported per frame, so a scene drawn from thousands
 *  of SVG paths still yields a short line. */
const MAX_VISUALS = 300;

const colourAlpha = (colour: string): number => {
  if (!colour || colour === "transparent") {
    return 0;
  }
  const m = colour.match(/rgba?\(([^)]+)\)/);
  if (!m) {
    return 1;
  }
  const parts = m[1].split(/[\s,/]+/).filter(Boolean);
  return parts.length >= 4 ? Number.parseFloat(parts[3]) : 1;
};

const measureVisuals = (): MeasuredVisual[] => {
  const out: MeasuredVisual[] = [];
  document.querySelectorAll('[data-tm-layer="scene"]').forEach((layer) => {
    layer.querySelectorAll("*").forEach((el) => {
      const tag = el.tagName.toLowerCase();
      let kind: MeasuredVisual["kind"] | null = null;
      if (PICTURE_TAGS.has(tag)) {
        kind = "picture";
      } else {
        const style = window.getComputedStyle(el);
        const image = style.backgroundImage;
        if (image && image !== "none") {
          kind = image.includes("url(") ? "picture" : "background";
        } else if (colourAlpha(style.backgroundColor) > 0) {
          kind = "background";
        }
      }
      if (!kind) {
        return;
      }
      const rect = el.getBoundingClientRect();
      if (rect.width < 1 || rect.height < 1) {
        return;
      }
      const { opacity } = accumulateFromAncestors(el);
      out.push({ tag, kind, x: rect.x, y: rect.y, width: rect.width, height: rect.height, opacity });
    });
  });
  out.sort((a, b) => b.width * b.height - a.width * a.height);
  return out.slice(0, MAX_VISUALS);
};

const measure = (frame: number, visualFrames: number[]): string => {
  const all = Array.from(document.querySelectorAll("*"));
  const leaves: Element[] = all.filter(isLeafTextElement);
  // Document-order position of each measured element, so ancestor/descendant
  // pairs can be excluded on the Python side without re-walking the DOM.
  const positions = new Map<Element, number>();
  leaves.forEach((el, i) => positions.set(el, i));

  const elements: MeasuredElement[] = [];
  leaves.forEach((el, index) => {
    const rect = inkRect(el);
    if (rect.width <= 0 || rect.height <= 0) {
      return;
    }
    const { opacity, rotated } = accumulateFromAncestors(el);
    const style = window.getComputedStyle(el);
    const lineHeightPx = Number.parseFloat(style.lineHeight);
    const ancestorIndices: number[] = [];
    let parent = el.parentElement;
    while (parent) {
      const pos = positions.get(parent);
      if (pos !== undefined) {
        ancestorIndices.push(pos);
      }
      parent = parent.parentElement;
    }
    elements.push({
      index,
      tag: el.tagName.toLowerCase(),
      text: (el.textContent ?? "").trim().slice(0, MAX_TEXT_CHARS),
      x: rect.x,
      y: rect.y,
      width: rect.width,
      height: rect.height,
      fontSize: Number.parseFloat(style.fontSize) || 0,
      lineHeight: Number.isFinite(lineHeightPx) ? lineHeightPx : null,
      opacity,
      rotated,
      ancestorIndices,
    });
  });

  const visuals = visualFrames.includes(frame) ? measureVisuals() : undefined;
  return `${PROBE_LOG_PREFIX}${JSON.stringify({ frame, elements, visuals })}`;
};

export const TextLayoutProbe: React.FC<{ visualFrames?: number[] }> = ({ visualFrames = [] }) => {
  const frame = useCurrentFrame();
  const [fontHandle] = useState(() => delayRender("Text audit: waiting for fonts"));
  const [fontsReady, setFontsReady] = useState(false);

  // Fonts decide text width, and a font loading does NOT trigger a React
  // re-render — so re-measure once they're settled. Agent-authored scenes may
  // loadFont() a Google font whose face only registers after their module
  // loads, which is why this can't be assumed done at mount.
  useEffect(() => {
    let cancelled = false;
    document.fonts.ready
      .then(() => {
        if (!cancelled) {
          setFontsReady(true);
        }
        continueRender(fontHandle);
      })
      .catch(() => {
        continueRender(fontHandle);
      });
    return () => {
      cancelled = true;
    };
  }, [fontHandle]);

  // No dependency array: this re-measures on EVERY commit and the driver keeps
  // the last line for a given frame. That is what makes the measurement correct
  // without any settle heuristic — CompositionBuilder's GeneratedScene resolves
  // its dynamic import() and calls setComponent, which triggers another commit,
  // so the final line for a frame always reflects the fully-loaded scene.
  useLayoutEffect(() => {
    console.log(measure(frame, visualFrames));
    if (!visualFrames.includes(frame)) {
      return;
    }
    // A picture frame is measured again once the page has been quiet for
    // VISUAL_SETTLE_MS, holding the frame open until then. The probe only
    // re-renders with the frame, so a scene whose lazy import commits after
    // the probe's last commit (always the case on the first frame rendered)
    // would otherwise be measured as an empty layer. Each new commit restarts
    // the wait; the last line for the frame is the one the driver keeps.
    const handle = delayRender(`Text audit: settling frame ${frame}`);
    const timer = setTimeout(() => {
      console.log(measure(frame, visualFrames));
      continueRender(handle);
    }, VISUAL_SETTLE_MS);
    return () => {
      clearTimeout(timer);
      continueRender(handle);
    };
  });

  // fontsReady is read so the fonts.ready resolution produces a commit (and
  // therefore a fresh measurement) rather than being invisible to React.
  return <span style={{ display: "none" }} data-fonts-ready={String(fontsReady)} />;
};

export default TextLayoutProbe;
