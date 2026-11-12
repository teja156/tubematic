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
  if (s.needs.openai_key && !canUseOpenAI) return "needs an OpenAI key";
  if (s.needs.gpu && !cartoon3dAvailable(gpu)) {
    return gpu?.status === "unknown" ? "GPU not tested yet" : "needs a working GPU";
  }
  return "";
}

/** The picker's options. A style the install cannot make is disabled and
 *  says why; a video already holding it still shows it selected, labelled, so
 *  the human can see why its approval is refused. Until the list loads, the
 *  picker offers only the value it holds. `gpu` omitted or null = not loaded =
 *  available. */
export function styleOptions(
  styles: VisualStyleInfo[] | null,
  canUseOpenAI: boolean,
  gpu?: Pick<GpuStatus, "status"> | null,
  current: string = "",
): { value: string; label: string; disabled: boolean }[] {
  if (!styles) return current ? [{ value: current, label: styleLabel(current, null), disabled: false }] : [];
  return styles.map((s) => {
    const why = unavailableReason(s, canUseOpenAI, gpu);
    return { value: s.id, label: why ? `${labelOf(s)} (${why})` : labelOf(s), disabled: why !== "" };
  });
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
 *  naming it "Motion Graphics" would be wrong. */
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
