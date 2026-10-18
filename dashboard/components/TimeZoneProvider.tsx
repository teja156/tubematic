"use client";

import { createContext, useContext, useEffect, useState } from "react";
import type { PipelineStatus } from "@/lib/types";
import { isValidTimeZone } from "@/lib/datetime";

interface TimeZoneCtx {
  timeZone: string;
  label: string;
  degraded: boolean;
}

// Always a valid ICU zone string — there is no code path where null/undefined/a
// label (e.g. "EDT (UTC-04:00)") reaches Intl.DateTimeFormat and throws.
const DEFAULT: TimeZoneCtx = { timeZone: "UTC", label: "UTC", degraded: true };

const Ctx = createContext<TimeZoneCtx>(DEFAULT);

export function useTimeZone(): TimeZoneCtx {
  return useContext(Ctx);
}

/** Fetches the host's IANA timezone from the API once on mount — the name is
 * immutable for the container's lifetime, and Intl handles DST transitions
 * from the name itself, so no polling. On any failure (older API, network
 * error, an invalid/missing zone) this degrades to UTC and says so, rather
 * than risk rendering a local-looking time under an unconfirmed zone. */
export function TimeZoneProvider({ children }: { children: React.ReactNode }) {
  const [ctx, setCtx] = useState<TimeZoneCtx>(DEFAULT);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/proxy/pipeline/status", { cache: "no-store" });
        if (!res.ok) return;
        const data: Partial<PipelineStatus> = await res.json();
        if (cancelled) return;
        if (isValidTimeZone(data.timezone)) {
          setCtx({
            timeZone: data.timezone as string,
            label: data.timezone_label || (data.timezone as string),
            degraded: false,
          });
        }
      } catch {
        // leave DEFAULT
      }
    })();
    return () => { cancelled = true; };
  }, []);

  return <Ctx.Provider value={ctx}>{children}</Ctx.Provider>;
}
