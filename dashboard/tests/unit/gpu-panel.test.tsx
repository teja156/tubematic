/**
 * Settings → Rendering → GPU (TMDEV-178). Guards that each of the worker's
 * four answers reads as itself — especially that a configured GPU the probe
 * rejected says so in red with the reason and the device Chromium really got,
 * since renders then still succeed (slowly, on the CPU) and this panel is
 * where that becomes visible. Also: Test GPU posts the request and polls only
 * while it is pending, a queued test says it waits for the current render,
 * the host's GPUs are listed with the chosen one marked, the switch command
 * is the onboarding step (the dashboard cannot recreate a container), and a
 * response of the wrong shape is never drawn as a GPU state.
 */
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { describe, it, expect, vi, afterEach } from "vitest";
import { GpuPanel, GPU_STEP_COMMAND } from "@/components/GpuPanel";

vi.mock("@/components/SectionLabel", () => ({
  SectionLabel: ({ label }: { label: string }) => <div>{label}</div>,
}));
vi.mock("@/components/TimeZoneProvider", () => ({
  useTimeZone: () => ({ timeZone: "UTC", label: "UTC" }),
}));

const GTX = { index: 0, uuid: "GPU-aaaa", name: "NVIDIA GeForce GTX 1650", memory_mib: 4096,
              driver: "595.91.07" };
const RTX = { index: 1, uuid: "GPU-bbbb", name: "NVIDIA GeForce RTX 4090", memory_mib: 24564,
              driver: "595.91.07" };
const NVIDIA = "ANGLE (NVIDIA Corporation, NVIDIA GeForce GTX 1650/PCIe/SSE2, OpenGL ES 3.2)";
const SWIFTSHADER = "ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero)), SwiftShader driver)";

function probe(over: Record<string, unknown> = {}) {
  return { at: "2026-11-05T10:00:00.000000Z", reason: "the worker started", configured: true,
           gpu: { uuid: GTX.uuid, name: GTX.name }, host_gpus: [GTX], renderer: NVIDIA,
           vendor: "Google Inc. (NVIDIA Corporation)", ok: true, error: "", secs: 6.1,
           smi: { name: GTX.name, driver: "595.91.07", memory_mib: 4096 }, ...over };
}

function status(over: Record<string, unknown> = {}) {
  return { status: "working", rendering_on: "gpu", configured: true,
           gpu: { uuid: GTX.uuid, name: GTX.name }, host_gpus: [GTX], probe: probe(),
           requested_at: null, pending: false, waiting_for_render: false, ...over };
}

function stub(...answers: unknown[]) {
  const queue = [...answers];
  const fn = vi.fn().mockImplementation(() => {
    const body = queue.length > 1 ? queue.shift() : queue[0];
    return Promise.resolve({ ok: true, json: async () => body });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("GpuPanel", () => {
  it("names the GPU, the driver and the device Chromium really got when it works", async () => {
    stub(status());
    render(<GpuPanel />);
    expect(await screen.findByTestId("gpu-status")).toHaveTextContent("Rendering on the GPU");
    expect(screen.getByTestId("gpu-status")).toHaveAttribute("data-status", "working");
    expect(screen.getByText(GTX.name)).toBeInTheDocument();
    expect(screen.getByText(/595\.91\.07/)).toBeInTheDocument();
    expect(screen.getByTestId("gpu-renderer")).toHaveTextContent(NVIDIA);
  });

  it("shows a rejected GPU in red with the reason and the device actually used", async () => {
    const intel = "ANGLE (Intel, Mesa Intel(R) UHD Graphics 630, OpenGL ES 3.2)";
    stub(status({ status: "not_usable", rendering_on: "cpu",
                  probe: probe({ ok: false, renderer: intel,
                                 error: `Chromium is rendering on another device: ${intel}` }) }));
    render(<GpuPanel />);
    const head = await screen.findByTestId("gpu-status");
    expect(head).toHaveTextContent("GPU not usable — rendering on the CPU");
    expect(head.style.color).toBe("var(--red)");
    expect(screen.getByTestId("gpu-why")).toHaveTextContent("another device");
    expect(screen.getByTestId("gpu-renderer")).toHaveTextContent(intel);
  });

  it("says CPU and how to add a GPU when none is configured", async () => {
    stub(status({ status: "not_configured", rendering_on: "cpu", configured: false, gpu: null,
                  host_gpus: [], probe: probe({ configured: false, ok: false, gpu: null,
                                                host_gpus: [], renderer: SWIFTSHADER, smi: null }) }));
    render(<GpuPanel />);
    expect(await screen.findByTestId("gpu-status")).toHaveTextContent("Rendering on the CPU");
    expect(screen.getByTestId("gpu-renderer")).toHaveTextContent("SwiftShader");
    expect(screen.getByTestId("gpu-help")).toHaveTextContent(GPU_STEP_COMMAND);
    expect(screen.queryByTestId("gpu-why")).toBeNull();
  });

  it("says it has not tested yet before the worker's first probe", async () => {
    stub(status({ status: "unknown", rendering_on: "cpu", configured: false, gpu: null,
                  host_gpus: [], probe: null }));
    render(<GpuPanel />);
    expect(await screen.findByTestId("gpu-status")).toHaveTextContent("Not tested yet");
  });

  it("lists every host GPU, marks the chosen one and offers the switch command", async () => {
    stub(status({ host_gpus: [GTX, RTX] }));
    render(<GpuPanel />);
    const list = await screen.findByTestId("gpu-host-list");
    expect(list).toHaveTextContent("GPU 0: NVIDIA GeForce GTX 1650 · 4 GB (in use)");
    expect(list).toHaveTextContent("GPU 1: NVIDIA GeForce RTX 4090 · 24 GB");
    expect(list).not.toHaveTextContent("RTX 4090 · 24 GB (in use)");
    expect(screen.getByTestId("gpu-help")).toHaveTextContent(`To use another GPU`);
    expect(screen.getByTestId("gpu-help")).toHaveTextContent(GPU_STEP_COMMAND);
  });

  it("Test GPU posts the request and polls until the answer arrives", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const fn = stub(status(), status({ pending: true, requested_at: "2026-11-05T11:00:00.0Z" }),
                    status({ pending: true }), status({ probe: probe({ at: "2026-11-05T11:00:01.0Z" }) }));
    render(<GpuPanel />);
    fireEvent.click(await screen.findByTestId("gpu-test"));
    await waitFor(() => expect(fn).toHaveBeenCalledWith("/api/proxy/render/gpu/test",
                                                        expect.objectContaining({ method: "POST" })));
    expect(await screen.findByTestId("gpu-pending")).toBeInTheDocument();
    expect(screen.getByTestId("gpu-test")).toBeDisabled();
    await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
    await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
    await waitFor(() => expect(screen.queryByTestId("gpu-pending")).toBeNull());
    expect(screen.getByTestId("gpu-test")).not.toBeDisabled();
    const callsDone = fn.mock.calls.length;
    await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
    expect(fn.mock.calls.length).toBe(callsDone); // no polling once answered
  });

  it("says a queued test waits for the render in progress", async () => {
    stub(status({ pending: true, waiting_for_render: true }));
    render(<GpuPanel />);
    expect(await screen.findByTestId("gpu-pending")).toHaveTextContent("current render finishes");
  });

  it("never draws a response of the wrong shape as a GPU state", async () => {
    stub({ render_timeout_secs: 2400 });
    render(<GpuPanel />);
    expect(await screen.findByTestId("gpu-error")).toHaveTextContent("unexpected response");
    expect(screen.queryByTestId("gpu-status")).toBeNull();
  });
});
