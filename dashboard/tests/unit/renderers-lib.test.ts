/**
 * lib/renderers.ts: the rules the Renderers panel and the Pipeline page's
 * "Nothing can render" banner show. Guards the chip precedence (the first
 * thing that stops a renderer taking work wins, so a disabled renderer with
 * an expired credential reads "disabled", and "busy" is only said of one that
 * could take work), that the built-in renderer never reads as credential
 * expired, the GPU verdicts (verified only from the renderer's probe), and
 * that the banner is raised only when a video is queued and no renderer is
 * enabled, online and current — and never on a list it could not read.
 */
import { describe, it, expect } from "vitest";
import type { Renderer, RenderersList } from "@/lib/types";
import {
  canRender, computeLine, credentialExpired, describeDevice, gpuVerdict, hasGpu, isRenderersList, lastSeen,
  nameError, nothingCanRender, rendererStatus, vramLine, anyProbePending,
} from "@/lib/renderers";

const NOW = Date.parse("2026-11-08T12:00:00Z");

function renderer(over: Partial<Renderer> = {}): Renderer {
  return {
    id: "r1", name: "Studio PC", builtin: false, enabled: true, online: true, state: "idle",
    needs_upgrade: false, gpu_verified: false, last_heartbeat_at: "2026-11-08T11:59:50Z",
    current_video_id: null, current_video_title: null, last_error: null,
    credential_expires_at: "2026-12-08T12:00:00Z", version: "2.1.0", gpu_probed: false,
    gpu_configured: false, gpu_error: "", compute: { cpus: 8, memory_bytes: 16 * 1024 ** 3, gpus: [] },
    gpu: null, probe_pending: false, ...over,
  };
}

function list(renderers: Renderer[]): RenderersList {
  return { remote_enabled: true, gateway_address: "main.lan:4443", renderers };
}

describe("rendererStatus", () => {
  it("reads every chip", () => {
    expect(rendererStatus(renderer(), NOW)).toBe("online");
    expect(rendererStatus(renderer({ state: "rendering" }), NOW)).toBe("busy");
    expect(rendererStatus(renderer({ online: false }), NOW)).toBe("offline");
    expect(rendererStatus(renderer({ needs_upgrade: true }), NOW)).toBe("needs_upgrade");
    expect(rendererStatus(renderer({ enabled: false }), NOW)).toBe("disabled");
    expect(rendererStatus(renderer({ last_error: "credential expired — re-enroll" }), NOW))
      .toBe("credential_expired");
    expect(rendererStatus(renderer({ credential_expires_at: "2026-11-08T11:00:00Z" }), NOW))
      .toBe("credential_expired");
  });

  it("lets the first thing that stops work win", () => {
    const everything = { enabled: false, last_error: "credential expired — re-enroll", needs_upgrade: true,
                         online: false, state: "rendering" as const };
    expect(rendererStatus(renderer(everything), NOW)).toBe("disabled");
    expect(rendererStatus(renderer({ ...everything, enabled: true }), NOW)).toBe("credential_expired");
    expect(rendererStatus(renderer({ ...everything, enabled: true, last_error: null }), NOW)).toBe("needs_upgrade");
    expect(rendererStatus(renderer({ online: false, state: "rendering" }), NOW)).toBe("offline");
  });

  it("never calls the built-in renderer's credential expired", () => {
    const builtin = renderer({ builtin: true, credential_expires_at: "2020-01-01T00:00:00Z",
                               last_error: "credential expired — re-enroll" });
    expect(credentialExpired(builtin, NOW)).toBe(false);
    expect(rendererStatus(builtin, NOW)).toBe("online");
    expect(credentialExpired(renderer({ credential_expires_at: "" }), NOW)).toBe(false);
  });
});

describe("lastSeen", () => {
  it("says how long ago, in words", () => {
    expect(lastSeen("2026-11-08T11:59:30Z", NOW)).toBe("just now");
    expect(lastSeen("2026-11-08T11:56:00Z", NOW)).toBe("4 min ago");
    expect(lastSeen("2026-11-08T09:00:00Z", NOW)).toBe("3 h ago");
    expect(lastSeen("2026-11-06T12:00:00Z", NOW)).toBe("2 d ago");
    expect(lastSeen("2026-11-08T11:56:00", NOW)).toBe("4 min ago"); // bare = UTC
    expect(lastSeen("", NOW)).toBe("never");
    expect(lastSeen(null, NOW)).toBe("never");
  });
});

describe("machine and GPU lines", () => {
  it("formats CPUs, RAM and VRAM to one decimal", () => {
    expect(computeLine(renderer())).toBe("8 CPUs · 16.0 GB RAM");
    expect(computeLine(renderer({ compute: { cpus: 1, memory_bytes: 3_500_000_000 } }))).toBe("1 CPU · 3.3 GB RAM");
    expect(computeLine(renderer({ compute: null }))).toBe("");
    expect(vramLine(4096)).toBe("4.0 GB VRAM");
    expect(vramLine(24564)).toBe("24.0 GB VRAM");
    expect(vramLine(null)).toBe("");
  });

  it("has a GPU when it reports one or one is configured", () => {
    expect(hasGpu(renderer())).toBe(false);
    expect(hasGpu(renderer({ compute: { gpus: [{ name: "GTX 1650", uuid: "GPU-a", memory_mb: 4096 }] } }))).toBe(true);
    expect(hasGpu(renderer({ gpu_configured: true, compute: null }))).toBe(true);
  });

  it("reads the GPU verdict from the probe only", () => {
    expect(gpuVerdict(renderer({ gpu_verified: true, gpu_probed: true, gpu_configured: true })).kind).toBe("verified");
    expect(gpuVerdict(renderer({ gpu_configured: true, gpu_probed: false })))
      .toEqual({ kind: "untested", text: "not tested yet" });
    expect(gpuVerdict(renderer({ gpu_configured: true, gpu_probed: true, gpu_error: "Chromium used the iGPU" })))
      .toEqual({ kind: "failed", text: "Chromium used the iGPU" });
    expect(gpuVerdict(renderer({ gpu_probed: true })).kind).toBe("unused");
  });

  it("names each kind of device in plain words", () => {
    const NVIDIA = "ANGLE (NVIDIA Corporation, NVIDIA GeForce GTX 1650/PCIe/SSE2, OpenGL ES 3.2)";
    const SWIFTSHADER = "ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero)), SwiftShader driver)";
    expect(describeDevice(NVIDIA, true, "NVIDIA GeForce GTX 1650")).toBe("The chosen GPU (NVIDIA GeForce GTX 1650)");
    expect(describeDevice(SWIFTSHADER, false)).toMatch(/^Software rendering on the CPU/);
    expect(describeDevice(NVIDIA, false)).toBe("A different NVIDIA GPU than the chosen one");
    expect(describeDevice("ANGLE (Mesa, llvmpipe)", false)).toBe("Another graphics device, not the chosen GPU");
    expect(describeDevice("", false)).toMatch(/^No graphics device/);
  });
});

describe("nothingCanRender", () => {
  const queued = { RENDER_QUEUED: 2 };

  it("is raised when videos are queued and no renderer can take one", () => {
    expect(nothingCanRender(queued, list([renderer({ online: false })]), NOW)).toBe(true);
    expect(nothingCanRender(queued, list([renderer({ enabled: false }), renderer({ id: "r2", needs_upgrade: true })]),
                            NOW)).toBe(true);
    expect(nothingCanRender(queued, list([]), NOW)).toBe(true);
  });

  it("is raised when the only online renderer's credential has expired", () => {
    // Still "online" (its last good heartbeat is recent), but it can no longer
    // authenticate, so it claims nothing — the card says so, and so must the banner.
    const lapsed = renderer({ credential_expires_at: "2026-11-08T11:59:00Z" });
    expect(rendererStatus(lapsed, NOW)).toBe("credential_expired");
    expect(canRender(lapsed, NOW)).toBe(false);
    expect(nothingCanRender(queued, list([lapsed]), NOW)).toBe(true);
    const refused = renderer({ last_error: "credential expired — re-enroll" });
    expect(nothingCanRender(queued, list([refused]), NOW)).toBe(true);
    // The same renderer a minute before expiry can still render.
    expect(nothingCanRender(queued, list([lapsed]), Date.parse("2026-11-08T11:58:00Z"))).toBe(false);
  });

  it("is not raised while one renderer can render, busy or not", () => {
    expect(nothingCanRender(queued, list([renderer({ online: false }), renderer({ id: "r2", state: "rendering" })]),
                            NOW)).toBe(false);
    expect(canRender(renderer({ state: "rendering" }), NOW)).toBe(true);
  });

  it("is not raised with nothing queued, or on a list it could not read", () => {
    expect(nothingCanRender({}, list([renderer({ online: false })]), NOW)).toBe(false);
    expect(nothingCanRender({ RENDER_QUEUED: 0 }, list([]), NOW)).toBe(false);
    expect(nothingCanRender(queued, null, NOW)).toBe(false);
  });
});

describe("helpers", () => {
  it("shape-checks the list", () => {
    expect(isRenderersList(list([]))).toBe(true);
    expect(isRenderersList([])).toBe(false);
    expect(isRenderersList({ render_timeout_secs: 2400 })).toBe(false);
    expect(isRenderersList(null)).toBe(false);
  });

  it("sees an outstanding GPU test", () => {
    expect(anyProbePending(list([renderer(), renderer({ id: "r2", probe_pending: true })]))).toBe(true);
    expect(anyProbePending(list([renderer()]))).toBe(false);
    expect(anyProbePending(null)).toBe(false);
  });

  it("checks a name is 1 to 60 characters", () => {
    expect(nameError("Studio PC")).toBe("");
    expect(nameError("   ")).not.toBe("");
    expect(nameError("x".repeat(61))).toMatch(/60/);
    expect(nameError(` ${"x".repeat(60)} `)).toBe("");
  });
});
