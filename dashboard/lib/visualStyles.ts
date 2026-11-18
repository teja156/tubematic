import type { GpuStatus, Video, VisualStyleInfo } from "./types";

/**
 * Labels and picker options for the visual styles, and the one place that
 * decides how a video's style reads once the choice is frozen.
 *
 * The list is data: one style pack per style on the API side
 * (tubematic_core/style_packs/), served by GET /visual-styles and shared by
 * VisualStylesProvider. "auto" is not a pack: it is the absence of a
 * restriction, and the agent picks the style itself. Every function here takes
 * the fetched list, and `null` while it has not loaded.
 */

/**
 * Whether a style that needs an OpenAI key can be produced on this install.
 *
 * GET /settings masks every secret to "" when unset and to a dotted mask
 * otherwise, so this reads set-versus-unset without ever seeing the key. One
 * known mismatch: a key supplied only through the API's environment (the test
 * stack does this) reads as unset here while the API accepts it. Settings not
 * loaded (undefined) counts as available, leaving the API, the authority, to
 * refuse with its own message rather than greying out a valid option.
 */
export function illustratedAvailable(
  settings: { openai_api_key?: string } | null | undefined,
): boolean {
  if (!settings) return true;
  return (settings.openai_api_key ?? "") !== "";
}

/**
 * Whether a GPU-only style can be produced: only while the renderers' GPU
 * status says "working". A page that has not loaded GET /render/gpu counts it
 * as available and leaves the refusal to the API.
 */
export function cartoon3dAvailable(gpu: Pick<GpuStatus, "status"> | null | undefined): boolean {
  if (!gpu) return true;
  return gpu.status === "working";
}

/** A style's display label: its pack label, marked when it is experimental. */
function labelOf(s: VisualStyleInfo): string {
  return s.experimental ? `${s.label} (experimental)` : s.label;
}

/** Why a style cannot be chosen on this install right now, or "". */
function unavailableReason(
  s: VisualStyleInfo,
  canUseOpenAI: boolean,
  gpu: Pick<GpuStatus, "status"> | null | undefined,
): string {
  // An installed external style's package problems are known to the API alone (TMDEV-252).
  if (s.external && s.available === false && !s.needs.openai_key && !s.needs.gpu) {
    return s.unavailable_reason || "unavailable";
  }
  if (s.needs.openai_key && !canUseOpenAI) return "needs an OpenAI key";
  if (s.needs.gpu && !cartoon3dAvailable(gpu)) {
    return gpu?.status === "unknown" ? "GPU not tested yet" : "needs a working GPU";
  }
  return "";
}

/** One row of the style picker (TMDEV-226). */
export interface StyleRow {
  value: string;
  label: string;
  experimental: boolean;
  gpu: boolean;
  /** Why the install cannot make it now, or "". */
  why: string;
  /** False for an insert style and for one the install cannot make: shown, never picked. */
  choosable: boolean;
  /** Stem of the preview files, or null when there is none (Auto, a value the list lacks). */
  preview: string | null;
  dimension: "2d" | "3d" | null;
  tagline: string;
  insert: boolean;
  /** An installed external style: its preview is served from its package. */
  external?: boolean;
}

export interface StyleGroup {
  key: "top" | "2d" | "3d" | "insert";
  title: string;
  note: string;
  rows: StyleRow[];
}

/** URL of a style's preview loop and poster, served from dashboard/public. */
export function previewUrls(stem: string, external = false): { video: string; poster: string } {
  // A built-in style's previews are static files of the dashboard image; an
  // installed external style's live in its package, behind the API (TMDEV-252).
  if (external) {
    return { video: `/external-style-previews/${stem}/preview.mp4`,
             poster: `/external-style-previews/${stem}/preview.webp` };
  }
  return { video: `/style-previews/${stem}.mp4`, poster: `/style-previews/${stem}.webp` };
}

function rowOf(s: VisualStyleInfo, canUseOpenAI: boolean, gpu: Pick<GpuStatus, "status"> | null | undefined): StyleRow {
  const insert = s.role === "insert";
  const why = unavailableReason(s, canUseOpenAI, gpu);
  return {
    value: s.id, label: s.label, experimental: s.experimental, gpu: s.needs.gpu, why,
    choosable: !insert && why === "", preview: s.preview ?? null,
    dimension: s.dimension ?? null, tagline: s.tagline ?? "", insert, external: s.external === true,
  };
}

/**
 * The style picker's groups, in order: Auto (and the optional "none" row the
 * caller adds), the 2D styles, the 3D styles, then the insert styles, which are
 * listed so a person can see them but are never a video's style. Every group
 * comes from the pack fields (dimension, role, needs.gpu), so a new pack lands
 * in the right place by itself; a style an older API sends without a dimension
 * counts as 2D, and one without a role as a main style. Empty groups are left
 * out. Until the list loads, the only row is the value held, so the button
 * still names it.
 */
export function styleGroups(
  styles: VisualStyleInfo[] | null,
  canUseOpenAI: boolean,
  gpu?: Pick<GpuStatus, "status"> | null,
  current: string = "",
): StyleGroup[] {
  if (!styles) {
    if (!current) return [];
    return [{ key: "top", title: "", note: "", rows: [{
      value: current, label: styleLabel(current, null), experimental: false, gpu: false, why: "",
      choosable: true, preview: null, dimension: null, tagline: "", insert: false,
    }] }];
  }
  const rows = styles.map((s) => rowOf(s, canUseOpenAI, gpu));
  const top = rows.filter((r) => r.value === "auto");
  const rest = rows.filter((r) => r.value !== "auto");
  const groups: StyleGroup[] = [
    { key: "top", title: "", note: "", rows: top },
    { key: "2d", title: "2D", note: "", rows: rest.filter((r) => !r.insert && r.dimension !== "3d") },
    { key: "3d", title: "3D", note: "", rows: rest.filter((r) => !r.insert && r.dimension === "3d") },
    { key: "insert", title: "Inserts", note: "scenes inside another style, never a whole video",
      rows: rest.filter((r) => r.insert) },
  ];
  return groups.filter((g) => g.rows.length > 0);
}

/** Every style with a preview, in picker order: what the preview window steps through. */
export function previewableRows(groups: StyleGroup[]): StyleRow[] {
  return groups.flatMap((g) => g.rows).filter((r) => r.preview);
}

/** The label for a stored value, falling back to the raw string so a value
 *  the list does not hold (not loaded yet, or written by a newer backend)
 *  still shows as itself rather than vanishing. */
export function styleLabel(value: string | undefined | null, styles: VisualStyleInfo[] | null): string {
  const id = value || "auto";
  const s = styles?.find((x) => x.id === id);
  if (s) return labelOf(s);
  return id === "auto" ? "Auto" : id;
}

/** How an auto-resolved canvas reads. The stored value is a canvas, not a
 *  style name: an auto video on a dark canvas may still contain figures, so
 *  naming it "Photo Explainer" would be wrong. */
const CANVAS_LABELS: Record<string, string> = {
  dark: "Auto — dark canvas",
  light: "Auto — light canvas",
};

/** Auto's outcome when it keeps the mixed scene system (no style fit better).
 *  Keep in sync: tubematic_core/visual_styles.py SCENES and SCENES_LABEL. */
export const SCENES = "scenes";
export const SCENES_LABEL = "Mixed scenes";

/** The label of one of Auto's outcomes: a style's label, or "Mixed scenes". */
export function routeLabel(id: string, styles: VisualStyleInfo[] | null): string {
  return id === SCENES ? SCENES_LABEL : styleLabel(id, styles);
}

/** The style a video's frozen style row names, for its preview: the chosen
 *  style, else the style Auto picked, else Cartoon 3D once Auto settled on that
 *  renderer; "" while Auto has not chosen or kept the mixed scene system (which
 *  has no pack). Follows videoStyleLabel's reading. */
export function videoStyleId(
  video: Pick<Video, "visual_style" | "resolved_renderer" | "style_pick">,
): string {
  const chosen = video.visual_style ?? "auto";
  if (chosen !== "auto") return chosen;
  const pick = video.style_pick ?? "";
  if (pick && pick !== SCENES) return pick;
  if (video.resolved_renderer === "cartoon_3d") return "cartoon_3d";
  return "";
}

/**
 * How a video's style reads on a card once the pickers are gone.
 *
 * When Auto picked the style (style_pick, before the script), the label says
 * so: "Auto — System Flow". Under the mixed scene system it also names the
 * canvas once the agent has chosen it. A video scripted before Auto picked
 * styles reads as it always did: the canvas or the world the agent settled
 * on. Before anything is chosen, it says so rather than implying one.
 */
export function videoStyleLabel(
  video: Pick<Video, "visual_style" | "resolved_visual_style" | "resolved_renderer" | "style_pick">,
  styles: VisualStyleInfo[] | null,
): string {
  const chosen = video.visual_style ?? "auto";
  const pick = video.style_pick ?? "";
  if (pick && pick !== SCENES && chosen === pick) return `Auto — ${styleLabel(pick, styles)}`;
  if (chosen !== "auto") return styleLabel(chosen, styles);
  // The renderer is the first thing auto settles (before any scene exists);
  // a Cartoon 3D world has no canvas worth naming.
  if (video.resolved_renderer === "cartoon_3d") return `Auto — ${styleLabel("cartoon_3d", styles)}`;
  const resolved = video.resolved_visual_style ?? "";
  if (pick === SCENES) {
    return resolved ? `Auto — ${SCENES_LABEL}, ${resolved} canvas` : `Auto — ${SCENES_LABEL}`;
  }
  if (!resolved) return "Auto (not yet chosen)";
  return CANVAS_LABELS[resolved] ?? `Auto — ${resolved}`;
}
