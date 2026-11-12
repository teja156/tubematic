"use client";

import type { GpuStatus, Mascot } from "@/lib/types";
import { mascotGate, mascotGateNote, mascotOptions } from "@/lib/mascots";

/**
 * The per-video mascot <select>. "No mascot" is always selectable; the
 * mascots themselves are disabled, saying why, until the GPU is working (the
 * API is the authority and refuses otherwise). Cartoon 3D has no mascot layer
 * and Under the Hood has its own presenter, so `locked` shows "No mascot" and
 * disables the whole control.
 */
export function MascotPicker({
  mascots, gpu, value, locked = false, onChange, testId, maxWidth = 140, style,
}: {
  mascots: Pick<Mascot, "id" | "name" | "pickable">[];
  gpu: Pick<GpuStatus, "status"> | null | undefined;
  value: string;
  locked?: boolean;
  onChange: (id: string) => void;
  testId: string;
  maxWidth?: number;
  style?: React.CSSProperties;
}) {
  const note = mascotGateNote(mascotGate(gpu));
  const title = locked
    ? "This visual style takes no mascot"
    : note || "Experimental: a character that reacts to the narration";
  return (
    <select
      data-testid={testId}
      value={locked ? "" : value}
      disabled={locked}
      onChange={(e) => onChange(e.target.value)}
      title={title}
      style={{
        fontFamily: "var(--mono)", fontSize: 11, padding: "7px 8px",
        background: "var(--panel)", color: "var(--ink)", border: "1px solid var(--border-2)",
        // Narrow on purpose: the Quick Actions row wraps its controls and must
        // not crush the title.
        maxWidth, ...style,
      }}
    >
      {mascotOptions(mascots, gpu, value).map((o) => (
        <option key={o.value} value={o.value} disabled={o.disabled}>{o.label}</option>
      ))}
    </select>
  );
}
