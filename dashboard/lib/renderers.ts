// Pure helpers for Settings → Rendering's Renderers panel and the Pipeline
// page's "Nothing can render" banner. No React, no fetch: every rule the UI
// shows about a renderer is decided here, so it is unit-testable on its own.

import type { Renderer, RenderersList, Stats } from "@/lib/types";

export const GPU_STEP_COMMAND = "python3 onboard.py --step gpu";
export const RENDERERS_STEP_COMMAND = "python3 onboard.py --step renderers";
export const REMOTE_SCRIPT = "tubematic_remote_renderer.py";
export const REMOTE_UPGRADE_COMMAND = `python3 ${REMOTE_SCRIPT} upgrade`;
export const RENDERING_SETTINGS_HREF = "/settings?tab=rendering";
export const NAME_MAX_CHARS = 60;

export type RendererChip = "disabled" | "credential_expired" | "needs_upgrade" | "offline" | "busy" | "online";

export const CHIP: Record<RendererChip, { label: string; color: string }> = {
  online: { label: "online", color: "var(--green)" },
  busy: { label: "busy", color: "var(--blue)" },
  offline: { label: "offline", color: "var(--red)" },
  disabled: { label: "disabled", color: "var(--mute)" },
  needs_upgrade: { label: "needs upgrade", color: "var(--amber)" },
  credential_expired: { label: "credential expired", color: "var(--red)" },
};

/** Accepts a bare "YYYY-MM-DDTHH:MM:SS" as UTC, like lib/datetime. */
function parseTs(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const normalized = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/.test(iso) ? `${iso}Z` : iso;
  const t = new Date(normalized).getTime();
  return Number.isNaN(t) ? null : t;
}

/** A remote renderer whose credential lapsed can no longer reach main and has
 *  to be added again. The built-in renderer has no expiring credential. */
export function credentialExpired(r: Renderer, now: number): boolean {
  if (r.builtin) return false;
  if (/credential expired/i.test(r.last_error ?? "")) return true;
  const expires = parseTs(r.credential_expires_at);
  return expires !== null && expires <= now;
}

/** The one chip a renderer card shows. Order matters: the first thing that
 *  stops a renderer taking work wins, and "busy" is only said of one that
 *  could otherwise take it. */
export function rendererStatus(r: Renderer, now: number): RendererChip {
  if (!r.enabled) return "disabled";
  if (credentialExpired(r, now)) return "credential_expired";
  if (r.needs_upgrade) return "needs_upgrade";
  if (!r.online) return "offline";
  if (r.state === "rendering") return "busy";
  return "online";
}

/** "just now", "4 min ago", "3 h ago", "2 d ago"; "never" before the first
 *  heartbeat. */
export function lastSeen(iso: string | null | undefined, now: number): string {
  const t = parseTs(iso);
  if (t === null) return "never";
  const secs = Math.max(0, Math.floor((now - t) / 1000));
  if (secs < 60) return "just now";
  if (secs < 3600) return `${Math.floor(secs / 60)} min ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)} h ago`;
  return `${Math.floor(secs / 86400)} d ago`;
}

/** "8 CPUs · 15.6 GB RAM", or "" before the renderer has reported. */
export function computeLine(r: Renderer): string {
  const parts: string[] = [];
  const cpus = r.compute?.cpus;
  const mem = r.compute?.memory_bytes;
  if (cpus) parts.push(`${cpus} CPU${cpus === 1 ? "" : "s"}`);
  if (mem) parts.push(`${(mem / 1024 ** 3).toFixed(1)} GB RAM`);
  return parts.join(" · ");
}

/** "4.0 GB VRAM", or "" when nvidia-smi did not say. */
export function vramLine(memoryMb: number | null | undefined): string {
  return memoryMb ? `${(memoryMb / 1024).toFixed(1)} GB VRAM` : "";
}

/** A renderer worth a GPU test: it reports a GPU, or one is configured. */
export function hasGpu(r: Renderer): boolean {
  return (r.compute?.gpus?.length ?? 0) > 0 || r.gpu_configured;
}

export type GpuVerdict = { kind: "verified" | "failed" | "untested" | "unused"; text: string };

/** What the renderer's last GPU probe says. "Verified" is decided by the
 *  renderer from Chromium's WebGL renderer string, never from a render having
 *  finished: on the wrong device a render still finishes, just slowly. */
export function gpuVerdict(r: Renderer): GpuVerdict {
  if (r.gpu_verified) return { kind: "verified", text: "✓ verified" };
  if (!r.gpu_probed) return { kind: "untested", text: "not tested yet" };
  if (r.gpu_configured) return { kind: "failed", text: r.gpu_error || "the GPU test failed" };
  return { kind: "unused", text: "not in use — renders on the CPU" };
}

/** Plain words for Chromium's WebGL renderer string, which names the GL stack
 *  rather than saying what it means. Only the renderer's probe knows whether
 *  the string matched the configured GPU, hence `verified`. */
export function describeDevice(renderer: string, verified: boolean, gpuName = ""): string {
  if (!renderer) return "No graphics device: Chromium could not create a WebGL context";
  if (/swiftshader/i.test(renderer)) return "Software rendering on the CPU (SwiftShader, Remotion's swangle)";
  if (verified) return `The chosen GPU${gpuName ? ` (${gpuName})` : ""}`;
  if (/nvidia/i.test(renderer)) return "A different NVIDIA GPU than the chosen one";
  return "Another graphics device, not the chosen GPU";
}

/** Can take a render right now (busy or not). An expired credential counts
 *  against it by the same rule, and the same `now`, as rendererStatus: such a
 *  renderer stays "online" until its last good heartbeat ages out, but it can
 *  no longer authenticate, so it claims nothing. */
export function canRender(r: Renderer, now: number): boolean {
  return r.enabled && r.online && !r.needs_upgrade && !credentialExpired(r, now);
}

/** The Pipeline page's banner: videos are waiting to render and no renderer
 *  can take one. An unloaded or failed renderer list never raises it — a
 *  banner that cries wolf on a network blip would be worse than none. */
export function nothingCanRender(stats: Stats, list: RenderersList | null, now: number): boolean {
  if (!list || (stats.RENDER_QUEUED ?? 0) <= 0) return false;
  return !list.renderers.some((r) => canRender(r, now));
}

export function anyProbePending(list: RenderersList | null): boolean {
  return !!list?.renderers.some((r) => r.probe_pending);
}

/** Shape check: a fetch mock or proxy error page that answers every URL with
 *  something else must never be drawn as a renderer list. */
export function isRenderersList(body: unknown): body is RenderersList {
  return !!body && typeof body === "object"
    && typeof (body as RenderersList).remote_enabled === "boolean"
    && Array.isArray((body as RenderersList).renderers);
}

/** The error to show for a name, or "" when it is acceptable. */
export function nameError(name: string): string {
  const n = name.trim();
  if (!n) return "Give it a name.";
  if (n.length > NAME_MAX_CHARS) return `At most ${NAME_MAX_CHARS} characters.`;
  return "";
}
