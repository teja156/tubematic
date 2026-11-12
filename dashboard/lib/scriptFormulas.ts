import type { Video } from "@/lib/types";

/** What GET /script-formulas returns: every script formula and every hook
 *  type with its label. The lists come from the API's formula files, so the
 *  dashboard holds no copy of either. */
export interface ScriptFormulaNames {
  /** experimental: shipped as data and off for Auto until the setting allows
   *  it; a person can still choose one. Optional: an older API does not send it. */
  formulas: { id: string; label: string; experimental?: boolean }[];
  hook_types: { id: string; label: string }[];
}

/** What a formula picker shows for "no choice": a formula is picked for the
 *  video from its topic, before its script. */
export const AUTO_FORMULA_LABEL = "Auto";

/** A formula's label, or the id itself when the list has not loaded or does
 *  not know it (a video written under a formula a later version dropped). */
export function formulaLabel(id: string, names: ScriptFormulaNames | null): string {
  return names?.formulas.find((f) => f.id === id)?.label ?? id;
}

/** A hook type's label, with the same fallback as formulaLabel. */
export function hookTypeLabel(id: string, names: ScriptFormulaNames | null): string {
  return names?.hook_types.find((h) => h.id === id)?.label ?? id;
}

/** Whether a video's script has anything recorded with it: a formula, drafted
 *  openings or stored warnings. False for a script written before scripts
 *  recorded any of these, which shows nothing extra. */
export function hasScriptRecord(video: Pick<Video, "formula_id" | "hook_alternatives" | "script_warnings">): boolean {
  return (video.formula_id ?? "") !== ""
    || (video.hook_alternatives?.length ?? 0) > 0
    || (video.script_warnings?.length ?? 0) > 0;
}

/** The options of a formula picker: Auto first, then every formula, an
 *  experimental one marked. A held value the list does not know (a formula a
 *  later version dropped, or the list not loaded yet) stays selectable as
 *  itself, so the picker never shows Auto while holding something else. */
export function formulaOptions(names: ScriptFormulaNames | null, held = ""): { value: string; label: string }[] {
  const options = [{ value: "", label: AUTO_FORMULA_LABEL }];
  for (const f of names?.formulas ?? []) {
    options.push({ value: f.id, label: f.experimental ? `${f.label} (experimental)` : f.label });
  }
  if (held !== "" && !options.some((o) => o.value === held)) options.push({ value: held, label: held });
  return options;
}

/** What the formula row says for a script that follows no formula: one
 *  written by hand, or before formulas existed, beside no pick. */
export const NO_FORMULA_LABEL = "No formula";

/** The formula a video is written in, as one label. The pick made before the
 *  script wins over the formula recorded with a stored script, because after
 *  a switch the stored script is the one about to be replaced. "Auto — X"
 *  when Auto picked it, X alone when a person chose it or when the script was
 *  written before formulas were picked ahead of it. With neither, a person's
 *  choice is named only while no script exists yet (at the topic): past it,
 *  a script with no pick and no record follows no formula, whatever was
 *  chosen. A status left out is read as the topic. */
export function videoFormulaLabel(
  video: Pick<Video, "formula_choice" | "formula_pick" | "formula_id"> & { status?: string },
  names: ScriptFormulaNames | null,
): string {
  const choice = video.formula_choice ?? "";
  const pick = video.formula_pick ?? "";
  if (pick !== "") {
    return choice === "" ? `${AUTO_FORMULA_LABEL} — ${formulaLabel(pick, names)}` : formulaLabel(pick, names);
  }
  if ((video.formula_id ?? "") !== "") return formulaLabel(video.formula_id ?? "", names);
  const atTopic = video.status === undefined
    || video.status === "TOPIC_PROPOSED" || video.status === "TOPIC_APPROVED";
  if (!atTopic) return NO_FORMULA_LABEL;
  return choice !== "" ? formulaLabel(choice, names) : `${AUTO_FORMULA_LABEL} (not yet chosen)`;
}

/** Whether anything about a video needs the formula names: a formula chosen,
 *  picked or recorded. */
export function hasFormula(video: Pick<Video, "formula_choice" | "formula_pick" | "formula_id">): boolean {
  return (video.formula_choice ?? "") !== "" || (video.formula_pick ?? "") !== ""
    || (video.formula_id ?? "") !== "";
}

/** What a video's formula_evidence holds: what this install's own watch
 *  figures said about the formula Auto passed when it picked, written by the
 *  server. '' = the pick was made without them. */
interface FormulaEvidence {
  formula: string;
  mode: "learned" | "explore";
  standing: string;
  points: number;
  videos: number;
  accounts: number;
  min_group: number;
}

function parseEvidence(raw: string | undefined): FormulaEvidence | null {
  if (!raw) return null;
  try {
    const value = JSON.parse(raw);
    return value && typeof value === "object" && typeof value.formula === "string" ? value : null;
  } catch {
    return null;
  }
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** The line under "Why this formula" that says whether the pick leaned on
 *  this install's watch figures, and how many videos were behind them. ""
 *  when the pick was made without them, which shows nothing. */
export function formulaEvidenceLine(raw: string | undefined, names: ScriptFormulaNames | null): string {
  const ev = parseEvidence(raw);
  if (!ev) return "";
  const label = formulaLabel(ev.formula, names);
  const behind = `${plural(ev.videos, "video", "videos")} on ${plural(ev.accounts, "account", "accounts")}`;
  if (ev.mode === "explore") {
    return ev.standing === "thin"
      ? `A trial pick: ${label} has fewer than ${ev.min_group} of this domain's videos with watch figures on any one account, so Auto tried it to learn how it holds viewers.`
      : "A trial pick, made without this domain's watch figures.";
  }
  switch (ev.standing) {
    case "better":
      return `Leaned on this install's watch figures: ${label} held more of each video than this domain's videos as a whole (${behind}).`;
    case "worse":
      return `This install's watch figures were read: ${label} held less of each video than this domain's videos as a whole (${behind}). It was picked because it fits the topic best.`;
    case "even":
      return `This install's watch figures were read: ${label} held about as much of each video as this domain's videos as a whole (${behind}).`;
    case "mixed":
      return `This install's watch figures were read: for ${label} the accounts disagree (${behind}), so they did not count.`;
    default:
      return `This install's watch figures were read: ${label} has fewer than ${ev.min_group} of this domain's videos with figures on any one account, so they did not count.`;
  }
}
