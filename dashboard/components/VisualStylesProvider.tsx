"use client";

import { createContext, useContext, useEffect, useState } from "react";
import type { VisualStyleInfo } from "@/lib/types";

const Ctx = createContext<VisualStyleInfo[] | null>(null);

/** Every visual style, "auto" first, or null until GET /visual-styles has
 *  answered (or if it failed: pickers then offer only the value they hold, and
 *  the API stays the authority on what may be chosen). */
export function useVisualStyles(): VisualStyleInfo[] | null {
  return useContext(Ctx);
}

/** Fetches the style list once on mount. The list changes only with the
 *  installed version, so there is no polling; whether a style is available
 *  right now is worked out per page from the settings and GPU status it loads. */
export function VisualStylesProvider({ children }: { children: React.ReactNode }) {
  const [styles, setStyles] = useState<VisualStyleInfo[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/proxy/visual-styles", { cache: "no-store" });
        if (!res.ok) return;
        const data = await res.json();
        if (!cancelled && Array.isArray(data?.styles)) setStyles(data.styles as VisualStyleInfo[]);
      } catch {
        // leave null
      }
    })();
    return () => { cancelled = true; };
  }, []);

  return <Ctx.Provider value={styles}>{children}</Ctx.Provider>;
}
