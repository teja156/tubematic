import type { GpuStatus, Video, VisualStyle } from "./types";

/**
 * Labels for the visual register (TMDEV-101), and the one place that decides
 * how a video's style reads once the choice is frozen.
 *
 * Four of these are permission sets, not looks: each named option RESTRICTS
 * what the agent may draw from within the one scene system (React components
 * on a canvas). Cartoon 3D is the exception: it REPLACES that system with one
 * painted 3D world authored as data, so it is a different renderer rather than
 * a narrower vocabulary. "Auto" is the absence of a restriction — the agent
 * picks the register, the renderer included.
 * Keep in sync: mcp/server.py and renderer/api/pipeline.py's VISUAL_STYLES.
 */
export const VISUAL_STYLE_OPTIONS: { value: VisualStyle; label: string }[] = [
  { value: "auto", label: "Auto" },
  { value: "motion_graphics", label: "Motion Graphics" },
  { value: "stick", label: "Stick Explainer" },
  { value: "illustrated", label: "Illustrated" },
  { value: "cartoon_3d", label: "Cartoon 3D (experimental)" },
];

/**
 * Whether the Illustrated style can be produced on this install.
 *
 * Its characters are drawn by OpenAI, the only provider with a transparent
 * background, so without a key the style cannot be made at all — and the API
 * refuses it. GET /settings masks every secret to "" when unset and to a
 * dotted mask otherwise, so this reads set-versus-unset without ever seeing
 * the key. One known mismatch: a key supplied only through the API's
 * environment (the test stack does this) reads as unset here while the API
 * accepts it. Settings not loaded (undefined) counts as available, leaving the
 * API — the authority — to refuse with its own message rather than greying out
 * an option that may be valid.
 */
export function illustratedAvailable(
  settings: { openai_api_key?: string } | null | undefined,
): boolean {
  if (!settings) return true;
  return (settings.openai_api_key ?? "") !== "";
}

/**
 * Whether the Cartoon 3D style can be produced on this install: only while
 * the renderer's GPU probe says "working". The API refuses the style on every
 * other status, so, as with illustratedAvailable, a page that has not loaded
 * GET /render/gpu counts it as available and leaves the refusal to the API.
 * "unknown" (the worker has not tested its GPU yet) is a different fix from
 * "no GPU", so the picker says which.
 */
export function cartoon3dAvailable(gpu: Pick<GpuStatus, "status"> | null | undefined): boolean {
  if (!gpu) return true;
  return gpu.status === "working";
}

/** The picker's options, with Illustrated disabled and saying why when no
 *  OpenAI key is stored, and Cartoon 3D disabled and saying why while the
 *  renderer's GPU is not working. A video already holding a disabled style
 *  still shows it selected, labelled, so the human can see why its approval
 *  is refused. `gpu` omitted or null = not loaded = available. */
export function styleOptions(
  canIllustrate: boolean,
  gpu?: Pick<GpuStatus, "status"> | null,
): { value: VisualStyle; label: string; disabled: boolean }[] {
  return VISUAL_STYLE_OPTIONS.map((o) => {
    if (o.value === "illustrated" && !canIllustrate) {
      return { ...o, label: `${o.label} (needs an OpenAI key)`, disabled: true };
    }
    if (o.value === "cartoon_3d" && !cartoon3dAvailable(gpu)) {
      const why = gpu?.status === "unknown" ? "GPU not tested yet" : "needs a working GPU";
      return { ...o, label: `${o.label} (${why})`, disabled: true };
    }
    return { ...o, disabled: false };
  });
}

const LABELS: Record<string, string> = Object.fromEntries(
  VISUAL_STYLE_OPTIONS.map((o) => [o.value, o.label]),
);

/** The label for a stored value, falling back to the raw string so a value
 *  written by a newer backend still shows as itself rather than vanishing. */
export function styleLabel(value: string | undefined | null): string {
  if (!value) return LABELS.auto;
  return LABELS[value] ?? value;
}

/** How an auto-resolved canvas reads. The stored value is a canvas, not a
 *  register name — an auto video on a dark canvas may still contain figures,
 *  so naming it "Motion Graphics" would be wrong. */
const CANVAS_LABELS: Record<string, string> = {
  dark: "Auto — dark canvas",
  light: "Auto — light canvas",
};

/**
 * How a video's style reads on a card once the pickers are gone.
 *
 * Under "auto" this says which canvas the agent actually chose, and marks it
 * as automatic — without that the dashboard cannot explain why two videos look
 * different, which is the whole reason the resolution is recorded at all.
 * Before the agent has chosen, it says so rather than implying one.
 */
export function videoStyleLabel(video: Pick<Video, "visual_style" | "resolved_visual_style" | "resolved_renderer">): string {
  const chosen = video.visual_style ?? "auto";
  if (chosen !== "auto") return styleLabel(chosen);
  // The renderer is the first thing auto settles (before any scene exists);
  // a Cartoon 3D world has no canvas worth naming.
  if (video.resolved_renderer === "cartoon_3d") return "Auto — Cartoon 3D (experimental)";
  const resolved = video.resolved_visual_style ?? "";
  if (!resolved) return "Auto (not yet chosen)";
  return CANVAS_LABELS[resolved] ?? `Auto — ${resolved}`;
}
