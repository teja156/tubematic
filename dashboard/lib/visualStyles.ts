import type { Video, VisualStyle } from "./types";

/**
 * Labels for the visual register (TMDEV-101), and the one place that decides
 * how a video's style reads once the choice is frozen.
 *
 * These are permission sets, not looks: each named option RESTRICTS what the
 * agent may draw from, and "Auto" is the absence of a restriction.
 * Keep in sync: mcp/server.py and renderer/api/pipeline.py's VISUAL_STYLES.
 */
export const VISUAL_STYLE_OPTIONS: { value: VisualStyle; label: string }[] = [
  { value: "auto", label: "Auto" },
  { value: "motion_graphics", label: "Motion Graphics" },
  { value: "stick", label: "Stick Explainer" },
  { value: "illustrated", label: "Illustrated" },
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

/** The picker's options, with Illustrated disabled and saying why when no
 *  OpenAI key is stored. A video already holding "illustrated" still shows it
 *  selected, labelled, so the human can see why its approval is refused. */
export function styleOptions(
  canIllustrate: boolean,
): { value: VisualStyle; label: string; disabled: boolean }[] {
  return VISUAL_STYLE_OPTIONS.map((o) =>
    o.value === "illustrated" && !canIllustrate
      ? { ...o, label: `${o.label} (needs an OpenAI key)`, disabled: true }
      : { ...o, disabled: false });
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
export function videoStyleLabel(video: Pick<Video, "visual_style" | "resolved_visual_style">): string {
  const chosen = video.visual_style ?? "auto";
  if (chosen !== "auto") return styleLabel(chosen);
  const resolved = video.resolved_visual_style ?? "";
  if (!resolved) return "Auto (not yet chosen)";
  return CANVAS_LABELS[resolved] ?? `Auto — ${resolved}`;
}
