"use client";

import { useEffect, useState } from "react";
import type { ScriptFormulaNames } from "@/lib/scriptFormulas";

/** Every script formula and hook type with its label, from GET
 *  /script-formulas, or null until it answers (or if it failed: labels then
 *  fall back to ids and pickers offer only Auto and the value they hold).
 *  Fetched once per mount while `enabled`; the list changes only with the
 *  installed version. */
export function useScriptFormulaNames(enabled: boolean): ScriptFormulaNames | null {
  const [names, setNames] = useState<ScriptFormulaNames | null>(null);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    fetch("/api/proxy/script-formulas", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        // Shape-checked: a test double or a proxy error page that answers
        // every URL must not be taken for the list.
        if (!cancelled && Array.isArray(data?.formulas) && Array.isArray(data?.hook_types)) {
          setNames(data as ScriptFormulaNames);
        }
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [enabled]);

  return names;
}
