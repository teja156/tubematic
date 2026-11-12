import type { Video, VisualStyleInfo } from "./types";
import { videoStyleId } from "./visualStyles";

/**
 * The per-video Inserts setting and how a video's inserts read (TMDEV-224).
 *
 * A video has one main style. With the setting on Auto the agent may add a
 * few short insert scenes (a System Flow diagram, a Terminal Doc string)
 * where the narration reaches what they show best, and it often adds none.
 * None forbids them. Whether a style can carry inserts at all is pack data:
 * GET /visual-styles gives each main style `inserts.host`.
 */

export type InsertMode = "auto" | "none";

/** A style's pack label without the experimental mark, for use inside a sentence;
 *  the id itself when the list does not hold it. */
function nameOf(styleId: string, styles: VisualStyleInfo[] | null): string {
  return styles?.find((x) => x.id === styleId)?.label ?? styleId;
}

export const INSERT_MODE_OPTIONS: { value: InsertMode; label: string }[] = [
  { value: "auto", label: "Auto" },
  { value: "none", label: "None" },
];

/** The picker's tooltip, the same wherever the picker is. */
export const INSERTS_TITLE =
  "Short diagram or text scenes inside the video's style, where the narration reaches what " +
  "they show best. Auto lets the agent decide (many videos get none).";

/** A stored or sent value read as a mode: anything but "none" is Auto, the API's default. */
export function insertMode(raw: string | null | undefined): InsertMode {
  return raw === "none" ? "none" : "auto";
}

/**
 * Whether a video in this style may carry inserts. True while the list has
 * not loaded, for Auto and "" (no preference), and for a style the list does
 * not hold: the API is the authority, and a picker greyed out on a guess
 * would hide a valid choice.
 */
export function styleHostsInserts(styleId: string | null | undefined, styles: VisualStyleInfo[] | null): boolean {
  if (!styles || !styleId) return true;
  const s = styles.find((x) => x.id === styleId);
  if (!s || !s.inserts) return true;
  return s.inserts.host;
}

/** Why the picker is locked to None for this style, or "" when it is not. */
export function insertsLockedReason(styleId: string | null | undefined, styles: VisualStyleInfo[] | null): string {
  if (styleHostsInserts(styleId, styles)) return "";
  return `${nameOf(styleId ?? "", styles)} takes no inserts.`;
}

/**
 * videos.insert_styles as a list: null while the agent has not decided ("",
 * or a value that does not read as a list), [] for none. The API sends the
 * stored JSON text; an already parsed list is taken as it is.
 */
export function parseInsertStyles(raw: string | string[] | null | undefined): string[] | null {
  if (Array.isArray(raw)) return raw.filter((x) => typeof x === "string");
  if (typeof raw !== "string" || raw.trim() === "") return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === "string") : null;
  } catch {
    return null;
  }
}

const BEFORE_APPROVAL = new Set<Video["status"]>(["TOPIC_PROPOSED", "TOPIC_REJECTED"]);

/** " · 2 inserts, 13 s" from the scene config's summary, or "" when it holds none. */
function summaryText(video: Pick<Video, "insert_summary">): string {
  const s = video.insert_summary;
  if (!s || !(s.count > 0)) return "";
  return ` · ${s.count} insert${s.count === 1 ? "" : "s"}, ${Math.round(s.seconds)} s`;
}

/**
 * The video window's Inserts row. The setting comes first (None is a person's
 * choice and says so), then whether the main style can carry inserts at all,
 * then the agent's decision; the reason is shown on its own line beside it.
 */
export function insertsRowText(
  video: Pick<Video, "status" | "insert_mode" | "insert_styles" | "insert_summary"
    | "visual_style" | "resolved_renderer" | "style_pick">,
  styles: VisualStyleInfo[] | null,
): string {
  if (insertMode(video.insert_mode) === "none") return "None (turned off for this video)";
  const main = videoStyleId(video);
  if (!styleHostsInserts(main, styles)) return `None (${nameOf(main, styles)} takes no inserts)`;
  const chosen = parseInsertStyles(video.insert_styles);
  // The agent decides once the topic is approved; before that the setting is all there is.
  if (chosen === null) return BEFORE_APPROVAL.has(video.status) ? "Auto" : "Not decided yet";
  if (chosen.length === 0) return "None";
  return chosen.map((id) => nameOf(id, styles)).join(", ") + summaryText(video);
}
