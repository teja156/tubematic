"use client";

// Settings → Rendering → GPU (TMDEV-178): which GPU the renderer uses, and
// whether it really does.
//
// Self-contained like CostsPanel: it reads and writes its own routes and sits
// outside the settings form's Save/dirty machinery. It never changes the GPU —
// that is `onboard.py --step gpu`, because switching means recreating the
// renderer container and the dashboard has no Docker access by design. What it
// can do is ask the worker to probe again (Test GPU) and show the answer.
//
// "Working" is decided by the worker from Chromium's WebGL renderer string,
// never from a render having finished: on the wrong GL device a render still
// finishes, just slowly. So the renderer string is always shown.

import { useEffect, useRef, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import type { GpuStatus, HostGpu } from "@/lib/types";
import { SectionLabel } from "@/components/SectionLabel";
import { useTimeZone } from "@/components/TimeZoneProvider";
import { formatDateTime } from "@/lib/datetime";

export const GPU_STEP_COMMAND = "python3 onboard.py --step gpu";
const POLL_MS = 3000;

function apiFetch(path: string, init?: RequestInit) {
  return fetch(`/api/proxy${path}`, { cache: "no-store", ...init });
}

const mono = { fontFamily: "var(--mono)" } as const;
const note: CSSProperties = { ...mono, fontSize: 10, color: "var(--mute)", letterSpacing: "0.02em",
                              lineHeight: 1.6 };
const value: CSSProperties = { ...mono, fontSize: 11, color: "var(--text)", wordBreak: "break-word" };
const button: CSSProperties = {
  ...mono, fontSize: 10, color: "var(--blue)", background: "var(--panel)",
  border: "1px solid var(--border)", padding: "4px 10px", cursor: "pointer",
};
const code: CSSProperties = { ...mono, fontSize: 11, color: "var(--blue)" };

const HEADLINE: Record<GpuStatus["status"], { text: string; color: string }> = {
  unknown: { text: "Not tested yet", color: "var(--mute)" },
  not_configured: { text: "Rendering on the CPU", color: "var(--mute)" },
  working: { text: "Rendering on the GPU", color: "var(--green)" },
  not_usable: { text: "GPU not usable — rendering on the CPU", color: "var(--red)" },
};

function isGpuStatus(body: unknown): body is GpuStatus {
  return !!body && typeof body === "object"
    && typeof (body as GpuStatus).status === "string"
    && (body as GpuStatus).status in HEADLINE
    && Array.isArray((body as GpuStatus).host_gpus);
}

/** Plain words for Chromium's WebGL renderer string, which names the GL
 *  stack rather than saying what it means. `status` decides "the chosen GPU":
 *  only the worker's probe knows whether the string matched it. */
export function describeDevice(status: GpuStatus, renderer: string): string {
  if (!renderer) return "No graphics device: Chromium could not create a WebGL context";
  if (/swiftshader/i.test(renderer)) return "Software rendering on the CPU (SwiftShader, Remotion's swangle)";
  if (status.status === "working") return `The chosen GPU${status.gpu ? ` (${status.gpu.name})` : ""}`;
  if (/nvidia/i.test(renderer)) return "A different NVIDIA GPU than the chosen one";
  return "Another graphics device, not the chosen GPU";
}

function gpuLine(g: HostGpu): string {
  const mem = g.memory_mib ? ` · ${Math.round(g.memory_mib / 1024)} GB` : "";
  return `GPU ${g.index}: ${g.name}${mem}`;
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div style={{ display: "flex", gap: 12, alignItems: "baseline", flexWrap: "wrap" }}>
      <span style={{ ...note, minWidth: 110 }}>{label}</span>
      <span style={value}>{children}</span>
    </div>
  );
}

export function GpuPanel() {
  const { timeZone } = useTimeZone();
  const [status, setStatus] = useState<GpuStatus | null>(null);
  const [error, setError] = useState("");
  const [requesting, setRequesting] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  async function load() {
    try {
      const r = await apiFetch("/render/gpu");
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const body = await r.json();
      // Shape-checked: a fetch mock (or a proxy error page) that answers every
      // URL with something else must not render as a GPU state.
      if (!isGpuStatus(body)) throw new Error("unexpected response");
      setStatus(body);
      setError("");
      return body;
    } catch (e) {
      setError(`Could not read the GPU status: ${(e as Error).message}`);
      return null;
    }
  }

  // Poll only while a Test is outstanding; the answer arrives on the
  // worker's next pass, or after the render it is busy with.
  function schedule(body: GpuStatus | null) {
    if (timer.current) clearTimeout(timer.current);
    if (body?.pending) timer.current = setTimeout(async () => schedule(await load()), POLL_MS);
  }

  useEffect(() => {
    load().then(schedule);
    return () => { if (timer.current) clearTimeout(timer.current); };
  }, []);

  async function test() {
    setRequesting(true);
    try {
      const r = await apiFetch("/render/gpu/test", { method: "POST" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const body = await r.json();
      if (!isGpuStatus(body)) throw new Error("unexpected response");
      setStatus(body);
      setError("");
      schedule(body);
    } catch (e) {
      setError(`Could not start a test: ${(e as Error).message}`);
    } finally {
      setRequesting(false);
    }
  }

  const headline = status ? HEADLINE[status.status] : null;
  const probe = status?.probe;
  const selected = status?.gpu?.uuid;
  const hosts = status?.host_gpus ?? [];

  return (
    <div data-testid="gpu-panel">
      <SectionLabel label="GPU" />
      {error && <div data-testid="gpu-error" style={{ ...note, color: "var(--red)" }}>{error}</div>}
      {status && headline && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 12 }}>
          <div data-testid="gpu-status" data-status={status.status}
               style={{ ...mono, fontSize: 12, fontWeight: 700, color: headline.color }}>
            ● {headline.text}
          </div>

          {status.gpu && <Field label="Chosen GPU">{status.gpu.name}</Field>}
          {probe?.smi?.driver && (
            <Field label="Driver">
              {probe.smi.driver}
              {probe.smi.memory_mib ? ` · ${Math.round(probe.smi.memory_mib / 1024)} GB` : ""}
            </Field>
          )}
          {probe && (
            <Field label="Chromium sees">
              <span style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                <span data-testid="gpu-device">{describeDevice(status, probe.renderer)}</span>
                {/* The raw string stays: it is the evidence the label is read from. */}
                <span data-testid="gpu-renderer" style={{ ...note, wordBreak: "break-word" }}>
                  {probe.renderer || "no WebGL device"}
                </span>
              </span>
            </Field>
          )}
          {status.status === "not_usable" && probe?.error && (
            <Field label="Why">
              <span data-testid="gpu-why" style={{ color: "var(--red)" }}>{probe.error}</span>
            </Field>
          )}
          {probe && (
            <Field label="Last tested">
              {formatDateTime(probe.at, timeZone)}
              {probe.secs != null ? ` · ${probe.secs}s` : ""}
            </Field>
          )}

          {hosts.length > 0 && (
            <div data-testid="gpu-host-list" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <span style={note}>NVIDIA GPUs on this machine (when onboarding last ran)</span>
              {hosts.map((g) => (
                <span key={g.uuid} style={{ ...value, color: g.uuid === selected ? "var(--green)" : "var(--mute)" }}>
                  {g.uuid === selected ? "▸ " : "  "}{gpuLine(g)}{g.uuid === selected ? "  (in use)" : ""}
                </span>
              ))}
            </div>
          )}

          <div data-testid="gpu-help" style={note}>
            {status.status === "not_configured" || status.status === "unknown"
              ? <>To render on an NVIDIA GPU, install the driver and the NVIDIA Container Toolkit, then run{" "}
                  <span style={code}>{GPU_STEP_COMMAND}</span> on the host. See the GPU rendering guide in the docs.</>
              : hosts.length > 1
                ? <>To use another GPU, or go back to the CPU, run <span style={code}>{GPU_STEP_COMMAND}</span> on the host.</>
                : <>To stop using the GPU, run <span style={code}>{GPU_STEP_COMMAND}</span> on the host and choose the CPU.</>}
          </div>
        </div>
      )}

      {/* Only with a GPU chosen. Without one a test can only re-confirm the CPU,
          and choosing a GPU (onboard.py --step gpu) recreates the renderer,
          which tests as it starts. With one, a driver update or a failed
          render can change the answer while the container keeps running. */}
      {status?.configured && (
      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <button type="button" data-testid="gpu-test" onClick={test}
                disabled={requesting || !!status?.pending}
                style={{ ...button, opacity: requesting || status?.pending ? 0.5 : 1 }}>
          {status?.pending ? "Testing…" : "Test GPU"}
        </button>
        {status?.pending && (
          <span data-testid="gpu-pending" style={note}>
            {status.waiting_for_render
              ? "Queued — the renderer runs the test once the current render finishes."
              : "The renderer runs the test on its next pass, usually within a minute."}
          </span>
        )}
      </div>
      )}
    </div>
  );
}
