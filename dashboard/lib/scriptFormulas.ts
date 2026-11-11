import type { Video } from "@/lib/types";

/** What GET /script-formulas returns: every script formula and every hook
 *  type with its label. The lists come from the API's formula files, so the
 *  dashboard holds no copy of either. */
export interface ScriptFormulaNames {
  formulas: { id: string; label: string }[];
  hook_types: { id: string; label: string }[];
}

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
