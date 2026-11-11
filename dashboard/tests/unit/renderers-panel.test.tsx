/**
 * Settings → Rendering → Renderers. Guards: one card per renderer with the
 * built-in one first and every chip drawn from the API's fields; CPU, RAM and
 * each GPU with its verdict (verified, the probe's error, not tested yet); the
 * device Chromium really got, with the raw string kept as the evidence; last
 * error and, for remote ones only, the credential's expiry. Actions send the
 * right method and body (Enable/Disable and Rename are PATCH, Remove is a
 * confirmed DELETE that the built-in renderer never offers, Test GPU is a
 * bodiless POST offered only with a GPU), and an API refusal shows on its
 * card. Add renderer is disabled with the onboarding command while remote
 * renderers are off; on, it asks a name, shows the token and the command once
 * with copy buttons, and forgets them on close. Polling is every 20 s, and
 * every 3 s only while a GPU test is outstanding. A response of the wrong
 * shape is never drawn as a renderer list.
 */
import { render, screen, fireEvent, waitFor, act, within } from "@testing-library/react";
import { describe, it, expect, vi, afterEach } from "vitest";
import type { Renderer, RenderersList } from "@/lib/types";
import { RenderersPanel } from "@/components/RenderersPanel";
import { GPU_STEP_COMMAND, RENDERERS_STEP_COMMAND } from "@/lib/renderers";

vi.mock("@/components/SectionLabel", () => ({
  SectionLabel: ({ label }: { label: string }) => <div>{label}</div>,
}));
vi.mock("@/components/TimeZoneProvider", () => ({
  useTimeZone: () => ({ timeZone: "UTC", label: "UTC" }),
}));

const NVIDIA = "ANGLE (NVIDIA Corporation, NVIDIA GeForce GTX 1650/PCIe/SSE2, OpenGL ES 3.2)";
const SWIFTSHADER = "ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero)), SwiftShader driver)";
const GTX = { name: "NVIDIA GeForce GTX 1650", uuid: "GPU-aaaa", memory_mb: 4096 };

function iso(offsetSecs: number) {
  return new Date(Date.now() + offsetSecs * 1000).toISOString();
}

function renderer(over: Partial<Renderer> = {}): Renderer {
  return {
    id: "r1", name: "Studio PC", builtin: false, enabled: true, online: true, state: "idle",
    needs_upgrade: false, gpu_verified: false, last_heartbeat_at: iso(-5),
    current_video_id: null, current_video_title: null, last_error: null,
    credential_expires_at: "2099-12-08T12:00:00Z", version: "2.1.0", gpu_probed: false,
    gpu_configured: false, gpu_error: "", compute: { cpus: 8, memory_bytes: 16 * 1024 ** 3, gpus: [] },
    gpu: null, probe_pending: false, ...over,
  };
}

const BUILTIN = renderer({
  id: "builtin", name: "Built-in renderer", builtin: true, credential_expires_at: null,
  compute: { cpus: 6, memory_bytes: 33_300_000_000, gpus: [] }, gpu_probed: true,
  gpu: { ok: false, error: "", renderer: SWIFTSHADER, name: "", at: "2026-11-08T10:00:00Z" },
});
const GPU_BOX = renderer({
  id: "r2", name: "GPU box", host: "studio-pc", compute: { cpus: 16, memory_bytes: 64 * 1024 ** 3, gpus: [GTX] },
  gpu_probed: true, gpu_configured: true, gpu_verified: true,
  gpu: { ok: true, error: "", renderer: NVIDIA, name: GTX.name, at: "2026-11-08T10:00:00Z" },
});

function list(renderers: Renderer[], over: Partial<RenderersList> = {}): RenderersList {
  return { remote_enabled: true, gateway_address: "main.lan:4443", renderers, ...over };
}

type Reply = { status?: number; body: unknown };

/** GET /renderers answers from `gets` in turn (the last one repeats); any
 *  other call answers from `writes` by "METHOD path", default 200 {}. */
function stub(gets: unknown[], writes: Record<string, Reply> = {}) {
  const queue = [...gets];
  const fn = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    const path = url.replace("/api/proxy", "");
    let reply: Reply;
    if (method === "GET" && path === "/renderers") {
      reply = { body: queue.length > 1 ? queue.shift() : queue[0] };
    } else {
      reply = writes[`${method} ${path}`] ?? { status: 200, body: {} };
    }
    const status = reply.status ?? 200;
    return Promise.resolve({ ok: status < 400, status, json: async () => reply.body });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

function callsTo(fn: ReturnType<typeof vi.fn>, method: string, path: string) {
  return fn.mock.calls.filter(([url, init]) =>
    url === `/api/proxy${path}` && ((init as RequestInit | undefined)?.method ?? "GET") === method);
}

async function card(id: string) {
  return within(await screen.findByTestId(`renderer-card-${id}`));
}

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("RenderersPanel", () => {
  it("lists the built-in renderer first, with its machine, its CPU device and how to add a GPU", async () => {
    stub([list([GPU_BOX, BUILTIN])]);
    render(<RenderersPanel />);
    const cards = await screen.findAllByTestId(/^renderer-card-/);
    expect(cards.map((c) => c.dataset.testid)).toEqual(["renderer-card-builtin", "renderer-card-r2"]);
    const b = await card("builtin");
    expect(b.getByTestId("renderer-chip")).toHaveTextContent("online");
    expect(b.getByTestId("renderer-compute")).toHaveTextContent("6 CPUs · 31.0 GB RAM");
    expect(b.getByTestId("renderer-gpu")).toHaveTextContent("None — renders on the CPU");
    expect(b.getByTestId("renderer-device")).toHaveTextContent("Software rendering on the CPU");
    expect(b.getByTestId("renderer-raw-device")).toHaveTextContent("SwiftShader");
    expect(b.getByTestId("renderer-help")).toHaveTextContent(GPU_STEP_COMMAND);
    expect(b.queryByTestId("renderer-remove")).toBeNull();
    expect(b.queryByTestId("renderer-test-gpu")).toBeNull();
    expect(b.queryByTestId("renderer-credential")).toBeNull();
  });

  it("shows a verified GPU, its VRAM, the device Chromium got and the credential's expiry", async () => {
    stub([list([BUILTIN, GPU_BOX])]);
    render(<RenderersPanel />);
    const g = await card("r2");
    expect(g.getByTestId("renderer-gpu")).toHaveTextContent("NVIDIA GeForce GTX 1650 · 4.0 GB VRAM — ✓ verified");
    expect(g.getByTestId("renderer-gpu")).toHaveAttribute("data-verdict", "verified");
    expect(g.getByTestId("renderer-device")).toHaveTextContent("The chosen GPU (NVIDIA GeForce GTX 1650)");
    expect(g.getByTestId("renderer-raw-device")).toHaveTextContent(NVIDIA);
    expect(g.getByTestId("renderer-compute")).toHaveTextContent("16 CPUs · 64.0 GB RAM");
    expect(g.getByTestId("renderer-host")).toHaveTextContent("studio-pc");
    expect(g.getByTestId("renderer-credential")).toHaveTextContent("Dec 8, 2099");
    expect(g.getByTestId("renderer-test-gpu")).toBeInTheDocument();
    expect(g.getByTestId("renderer-remove")).toBeInTheDocument();
  });

  it("shows a failed probe's error in red and an untested GPU as not tested yet", async () => {
    const failed = renderer({ id: "f", compute: { gpus: [GTX] }, gpu_probed: true, gpu_configured: true,
                              gpu_error: "Chromium is rendering on another device" });
    const untested = renderer({ id: "u", compute: { gpus: [GTX] }, gpu_configured: true });
    stub([list([failed, untested])]);
    render(<RenderersPanel />);
    const f = await card("f");
    expect(f.getByTestId("renderer-gpu")).toHaveTextContent("Chromium is rendering on another device");
    expect(f.getByTestId("renderer-gpu-verdict").style.color).toBe("var(--red)");
    expect((await card("u")).getByTestId("renderer-gpu")).toHaveTextContent("not tested yet");
  });

  it("draws every chip with its detail", async () => {
    stub([list([
      renderer({ id: "on" }),
      renderer({ id: "busy", state: "rendering", current_video_title: "How DNS works" }),
      renderer({ id: "off", online: false, last_heartbeat_at: iso(-600) }),
      renderer({ id: "dis", enabled: false }),
      renderer({ id: "up", needs_upgrade: true, version: "2.0.0" }),
      renderer({ id: "exp", last_error: "credential expired — re-enroll" }),
    ])]);
    render(<RenderersPanel />);
    const chip = async (id: string) => (await card(id)).getByTestId("renderer-chip");
    expect(await chip("on")).toHaveTextContent("online");
    expect(await chip("busy")).toHaveTextContent("busy");
    expect((await card("busy")).getByTestId("renderer-current")).toHaveTextContent("How DNS works");
    expect(await chip("off")).toHaveTextContent("offline");
    expect((await card("off")).getByTestId("renderer-seen")).toHaveTextContent("10 min ago");
    expect(await chip("dis")).toHaveTextContent("disabled");
    expect((await card("dis")).getByTestId("renderer-toggle")).toHaveTextContent("Enable");
    expect(await chip("up")).toHaveTextContent("needs upgrade");
    expect((await card("up")).getByTestId("renderer-help")).toHaveTextContent("tubematic_remote_renderer.py upgrade");
    expect(await chip("exp")).toHaveTextContent("credential expired");
    expect((await card("exp")).getByTestId("renderer-last-error")).toHaveTextContent("credential expired — re-enroll");
    expect((await card("exp")).getByTestId("renderer-help")).toHaveTextContent("add it again with a new token");
  });

  it("Disable and Enable send a PATCH with enabled", async () => {
    const fn = stub([list([BUILTIN, GPU_BOX])]);
    render(<RenderersPanel />);
    fireEvent.click((await card("r2")).getByTestId("renderer-toggle"));
    await waitFor(() => expect(callsTo(fn, "PATCH", "/renderers/r2")).toHaveLength(1));
    const init = callsTo(fn, "PATCH", "/renderers/r2")[0][1] as RequestInit;
    expect(JSON.parse(init.body as string)).toEqual({ enabled: false });
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
  });

  it("Rename saves on Enter with the trimmed name, and refuses an empty one without a request", async () => {
    const fn = stub([list([GPU_BOX])]);
    render(<RenderersPanel />);
    const g = await card("r2");
    fireEvent.click(g.getByTestId("renderer-rename"));
    expect(g.queryByTestId("renderer-rename-save")).toBeNull();
    fireEvent.change(g.getByTestId("renderer-rename-input"), { target: { value: "  " } });
    fireEvent.keyDown(g.getByTestId("renderer-rename-input"), { key: "Enter" });
    expect(g.getByTestId("renderer-name-error")).toBeInTheDocument();
    expect(callsTo(fn, "PATCH", "/renderers/r2")).toHaveLength(0);
    fireEvent.change(g.getByTestId("renderer-rename-input"), { target: { value: " Render box " } });
    fireEvent.keyDown(g.getByTestId("renderer-rename-input"), { key: "Enter" });
    await waitFor(() => expect(callsTo(fn, "PATCH", "/renderers/r2")).toHaveLength(1));
    expect(JSON.parse((callsTo(fn, "PATCH", "/renderers/r2")[0][1] as RequestInit).body as string))
      .toEqual({ name: "Render box" });
    await waitFor(() => expect(g.queryByTestId("renderer-rename-input")).toBeNull());
  });

  it("a new name also saves when the field loses focus; Escape and Cancel drop it", async () => {
    const fn = stub([list([GPU_BOX])]);
    render(<RenderersPanel />);
    const g = await card("r2");
    fireEvent.click(g.getByTestId("renderer-rename"));
    fireEvent.change(g.getByTestId("renderer-rename-input"), { target: { value: "Dropped" } });
    fireEvent.keyDown(g.getByTestId("renderer-rename-input"), { key: "Escape" });
    fireEvent.click(g.getByTestId("renderer-rename"));
    fireEvent.change(g.getByTestId("renderer-rename-input"), { target: { value: "Also dropped" } });
    // Pressing Cancel must not blur the field first and save the name.
    const cancel = g.getByTestId("renderer-rename-cancel");
    expect(fireEvent.mouseDown(cancel)).toBe(false);
    fireEvent.click(cancel);
    // Tab onto Cancel blurs the field towards it, which must not save either.
    fireEvent.click(g.getByTestId("renderer-rename"));
    fireEvent.change(g.getByTestId("renderer-rename-input"), { target: { value: "Tabbed away" } });
    fireEvent.blur(g.getByTestId("renderer-rename-input"), { relatedTarget: g.getByTestId("renderer-rename-cancel") });
    fireEvent.click(g.getByTestId("renderer-rename-cancel"));
    expect(callsTo(fn, "PATCH", "/renderers/r2")).toHaveLength(0);

    fireEvent.click(g.getByTestId("renderer-rename"));
    fireEvent.change(g.getByTestId("renderer-rename-input"), { target: { value: "Studio" } });
    fireEvent.blur(g.getByTestId("renderer-rename-input"));
    await waitFor(() => expect(callsTo(fn, "PATCH", "/renderers/r2")).toHaveLength(1));
    expect(JSON.parse((callsTo(fn, "PATCH", "/renderers/r2")[0][1] as RequestInit).body as string))
      .toEqual({ name: "Studio" });
    await waitFor(() => expect(g.getByTestId("renderer-status")).toHaveTextContent("✓ Saved"));
  });

  it("Remove asks first, naming the renderer, then sends a DELETE", async () => {
    const fn = stub([list([BUILTIN, GPU_BOX])]);
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    render(<RenderersPanel />);
    const g = await card("r2");
    fireEvent.click(g.getByTestId("renderer-remove"));
    expect(confirm.mock.calls[0][0]).toContain('"GPU box"');
    expect(callsTo(fn, "DELETE", "/renderers/r2")).toHaveLength(0);
    fireEvent.click(g.getByTestId("renderer-remove"));
    await waitFor(() => expect(callsTo(fn, "DELETE", "/renderers/r2")).toHaveLength(1));
  });

  it("shows an API refusal on the renderer's card", async () => {
    stub([list([GPU_BOX])], { "PATCH /renderers/r2": { status: 400, body: { error: "name must be 1-60 characters" } } });
    render(<RenderersPanel />);
    const g = await card("r2");
    fireEvent.click(g.getByTestId("renderer-toggle"));
    expect(await g.findByTestId("renderer-error")).toHaveTextContent("name must be 1-60 characters");
  });

  it("Test GPU posts bodiless, polls every 3 s while pending and slows down once settled", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const pending = { ...GPU_BOX, probe_pending: true };
    const fn = stub([list([GPU_BOX]), list([pending]), list([pending]), list([GPU_BOX])],
                    { "POST /renderers/r2/gpu-test": { status: 202, body: {} } });
    render(<RenderersPanel />);
    const g = await card("r2");
    fireEvent.click(g.getByTestId("renderer-test-gpu"));
    await waitFor(() => expect(callsTo(fn, "POST", "/renderers/r2/gpu-test")).toHaveLength(1));
    expect((callsTo(fn, "POST", "/renderers/r2/gpu-test")[0][1] as RequestInit).body).toBeUndefined();
    expect(await screen.findByTestId("renderer-probe-pending")).toBeInTheDocument();
    expect(screen.getByTestId("renderer-test-gpu")).toBeDisabled();
    await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
    await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
    await waitFor(() => expect(screen.queryByTestId("renderer-probe-pending")).toBeNull());
    const settled = callsTo(fn, "GET", "/renderers").length;
    await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });
    expect(callsTo(fn, "GET", "/renderers").length).toBe(settled); // no 3 s polling once answered
    await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });
    expect(callsTo(fn, "GET", "/renderers").length).toBe(settled + 1); // the 20 s poll
  });

  it("says a queued test waits for the render in progress", async () => {
    stub([list([{ ...GPU_BOX, probe_pending: true, state: "rendering" }])]);
    render(<RenderersPanel />);
    expect(await screen.findByTestId("renderer-probe-pending")).toHaveTextContent("current render finishes");
  });

  it("disables Add renderer with the onboarding command while remote renderers are off", async () => {
    stub([list([BUILTIN], { remote_enabled: false, gateway_address: "" })]);
    render(<RenderersPanel />);
    expect(await screen.findByTestId("renderers-add")).toBeDisabled();
    expect(screen.getByTestId("renderers-add-hint"))
      .toHaveTextContent(`Turn on remote renderers first: ${RENDERERS_STEP_COMMAND}`);
  });

  it("Add renderer shows the token and the command once, copyable, and forgets them on close", async () => {
    const command = "python3 tubematic_remote_renderer.py install";
    const fn = stub([list([BUILTIN])], {
      "POST /renderers/enrollments": { status: 201,
                                       body: { token: "tok-123", expires_at: "2026-11-08T13:00:00Z", command } },
    });
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    render(<RenderersPanel />);
    expect(screen.getByTestId("renderers-panel")).toBeInTheDocument();
    fireEvent.click(await screen.findByTestId("renderers-add"));
    expect(await screen.findByTestId("add-renderer-requirements")).toHaveTextContent("Docker");
    expect(screen.getByTestId("add-renderer-submit")).toBeDisabled();
    fireEvent.change(screen.getByTestId("add-renderer-name"), { target: { value: " Studio PC " } });
    fireEvent.click(screen.getByTestId("add-renderer-submit"));
    expect(await screen.findByTestId("add-renderer-token")).toHaveTextContent("tok-123");
    expect(JSON.parse((callsTo(fn, "POST", "/renderers/enrollments")[0][1] as RequestInit).body as string))
      .toEqual({ name: "Studio PC" });
    expect(screen.getByTestId("add-renderer-command")).toHaveTextContent(command);
    // The token is pasted when the script asks, never typed into the command.
    expect(screen.getByTestId("add-renderer-command")).not.toHaveTextContent("tok-123");
    expect(screen.getByTestId("add-renderer-paste")).toHaveTextContent("When it asks for the enrollment token");
    expect(screen.getByTestId("add-renderer-once")).toHaveTextContent("valid for 1 hour, single use");
    fireEvent.click(screen.getByTestId("copy-command"));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(command));
    expect(await screen.findByTestId("copy-command-done")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("copy-token"));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("tok-123"));

    fireEvent.click(screen.getByTestId("add-renderer-done"));
    await waitFor(() => expect(screen.queryByTestId("add-renderer-token")).toBeNull());
    fireEvent.click(screen.getByTestId("renderers-add"));
    expect(await screen.findByTestId("add-renderer-name")).toHaveValue("");
    expect(screen.queryByTestId("add-renderer-token")).toBeNull();
  });

  it("Add renderer says why when the API refuses", async () => {
    stub([list([BUILTIN])], { "POST /renderers/enrollments": { status: 409, body: { error: "remote_renderers_off" } } });
    render(<RenderersPanel />);
    fireEvent.click(await screen.findByTestId("renderers-add"));
    fireEvent.change(await screen.findByTestId("add-renderer-name"), { target: { value: "Studio PC" } });
    fireEvent.click(screen.getByTestId("add-renderer-submit"));
    expect(await screen.findByTestId("add-renderer-error")).toHaveTextContent(RENDERERS_STEP_COMMAND);
    expect(screen.queryByTestId("add-renderer-token")).toBeNull();
  });

  it("never draws a response of the wrong shape as a renderer list", async () => {
    stub([{ render_timeout_secs: 2400 }]);
    render(<RenderersPanel />);
    expect(await screen.findByTestId("renderers-error")).toHaveTextContent("unexpected response");
    expect(screen.queryAllByTestId(/^renderer-card-/)).toHaveLength(0);
    expect(screen.queryByTestId("renderers-add")).toBeNull();
  });
});
