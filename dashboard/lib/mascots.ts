import type { GpuStatus, Mascot } from "./types";

/**
 * Mascot helpers shared by the Mascots page and every picker.
 *
 * A mascot is drawn on the GPU only (no CPU fallback), so every picker is
 * gated on the renderer's GPU probe the way Cartoon 3D is. Unlike
 * cartoon3dAvailable, a page that has not loaded GET /render/gpu yet counts as
 * NOT available: an untouched picker must never be able to send a mascot the
 * API would refuse, and "None" stays selectable the whole time.
 */

export type MascotGate = "ok" | "loading" | "unknown" | "unavailable";

export function mascotGate(gpu: Pick<GpuStatus, "status"> | null | undefined): MascotGate {
  if (!gpu) return "loading";
  if (gpu.status === "working") return "ok";
  return gpu.status === "unknown" ? "unknown" : "unavailable";
}

/** Why mascots cannot be picked right now, or "" when they can. */
export function mascotGateNote(gate: MascotGate): string {
  if (gate === "ok") return "";
  if (gate === "loading") return "Checking the GPU…";
  if (gate === "unknown") return "GPU not tested yet";
  return "Mascots need a working GPU";
}

export const MASCOT_SETTINGS_HREF = "/settings?tab=rendering";

/** Sheet URLs arrive API-relative ("/mascots/<id>/versions/<v>/sheets/<name>");
 *  the browser reaches them through the dashboard's authenticated image route. */
export function mascotSheetUrl(apiUrl: string): string {
  return apiUrl.replace(/^\/mascots\//, "/mascot-sheets/");
}

export interface MascotOption {
  value: string;
  label: string;
  disabled: boolean;
}

/**
 * A per-video picker's options: None, then each pickable mascot (disabled and
 * saying why while the GPU is not working). `leading` are the always-selectable
 * non-mascot choices (None; for a default, also "use the install default"). A value the video holds that is
 * not offered shows as "Unavailable mascot" rather than silently reading as
 * None, so the human can see why its approval is refused.
 */
export function mascotOptions(
  mascots: Pick<Mascot, "id" | "name" | "pickable">[],
  gpu: Pick<GpuStatus, "status"> | null | undefined,
  current: string,
  leading: { value: string; label: string }[] = [{ value: "", label: "No mascot" }],
): MascotOption[] {
  const note = mascotGateNote(mascotGate(gpu));
  const pickable = mascots.filter((m) => m.pickable);
  const out: MascotOption[] = leading.map((o) => ({ ...o, disabled: false }));
  if (!leading.some((o) => o.value === current) && !pickable.some((m) => m.id === current)) {
    const name = mascots.find((m) => m.id === current)?.name;
    out.push({ value: current, label: name ? `${name} (unavailable)` : "Unavailable mascot", disabled: true });
  }
  for (const m of pickable) {
    out.push({ value: m.id, label: note ? `${m.name} (${note})` : m.name, disabled: note !== "" && m.id !== current });
  }
  return out;
}

/** Whether a picker is worth showing: something to pick, or something held. */
export function showMascotPicker(mascots: Pick<Mascot, "pickable">[], current: string): boolean {
  return current !== "" || mascots.some((m) => m.pickable);
}

/** The mascot_id an approve-topic carries: Cartoon 3D has no mascot layer. */
export function approvalMascot(style: string | undefined, picked: string): string {
  return style === "cartoon_3d" ? "" : picked;
}
