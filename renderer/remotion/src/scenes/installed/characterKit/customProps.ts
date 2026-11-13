/*
 * The props an agent drew for one video of a character style, imported from
 * generated/<video_id>/prop-<name>.tsx and held until they load: the frame
 * waits, and a prop that will not load fails the render (a frame without a
 * prop the narration names would ship silently).
 */
import type React from "react";
import { useEffect, useState } from "react";
import { cancelRender, continueRender, delayRender } from "remotion";

export type CustomPropSpec = { id: string; src: string; w: number; h: number; text?: number; acts?: string[] };

export function useCustomDrawings<P>(label: string, list: readonly CustomPropSpec[]): Record<string, React.FC<P>> | null {
  const [drawings, setDrawings] = useState<Record<string, React.FC<P>> | null>(list.length ? null : {});
  const [handle] = useState(() => (list.length ? delayRender(`${label}: loading the video's own props`) : null));
  useEffect(() => {
    if (handle === null) return;
    Promise.all(
      list.map((c) => import(`../../generated/${c.src}.tsx`).then((m: { default: React.FC<P> }) => [c.id, m.default] as const)),
    )
      .then((pairs) => {
        setDrawings(Object.fromEntries(pairs));
        continueRender(handle);
      })
      .catch((err) => cancelRender(err));
    // The props are static for the whole render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [handle]);
  return drawings;
}
