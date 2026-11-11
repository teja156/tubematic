import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Mock heavy child components
vi.mock("@/components/SectionLabel", () => ({
  SectionLabel: ({ label, count }: { label: string; count?: string }) => (
    <div data-testid="section-label">{label}{count && ` — ${count}`}</div>
  ),
}));

// next/navigation is not used directly by settings/page.tsx (only by TopBar)
// but mock it defensively in case any transitive import requires it
vi.mock("next/navigation", () => ({ usePathname: () => "/settings" }));

import SettingsPage from "@/app/settings/page";
import type { Agent, Settings, PipelineStatus, RetentionBacklog } from "@/lib/types";

const MOCK_SETTINGS: Settings = {
  pipeline_paused: false,
  gemini_review_enabled: true,
  max_render_retries: 1,
  ai_review_model: "gemini-2.5-flash",
  ai_review_fps: 10,
  ai_review_max_loops: 1,
  max_curriculum_per_run: 2,
  max_trending_per_run: 2,
  max_mining_per_run: 2,
  research_pending_cap: 15,
  max_research_runs_per_day: 8,
  trending_sources: ["GitHub Trending", "Hacker News"],
  elevenlabs_voices: [{ name: "Narrator", voice_id: "abc123", model_id: "eleven_multilingual_v2" }],
  elevenlabs_voice_id: "abc123",
  image_model: "gpt-image-2.5-flare",
  character_model: "gpt-image-2.5-flare",
  render_timeout_secs: 2400,
  render_stall_timeout_secs: 600,
  watermark_enabled: true,
  max_concurrent_agent_sessions: 3,
  agent_session_timeout_secs: 5400,
  elevenlabs_api_key: "••••••••4f2a",
  gemini_api_key: "••••••••9b21",
  openai_api_key: "",
  youtube_transcript_api_key: "",
  postforme_api_key: "",
  publishing_enabled: false,
  log_retention_days: 14,
  retention_days: 7,
  unpublished_retention_days: 0,
  discord_webhook_url: "",
  notify_topic_proposed: false,
  notify_script_ready: false,
  notify_video_ready: false,
  notify_partially_published: false,
  notify_failed: false,
  dashboard_base_url: "",
  user_preferences: "",
  auto_pilot_enabled: false,
  auto_pilot_gap_mins: 240,
  auto_pilot_max_in_flight: 0,
};

const MOCK_STATUS: PipelineStatus = {
  paused: false,
  workable_count: 0,
  proposed_count: 0,
  video_counts: {},
  last_research_at: null,
  active_strategies: ["curriculum", "trending", "mining"],
  research_pending_cap: 15,
  research_runs_today: 0,
  max_research_runs_per_day: 8,
  research_window_resets_at: null,
  pending_script_profiles: 0,
  timezone: "UTC",
  timezone_label: "UTC",
};

const MOCK_BACKLOG: RetentionBacklog = {
  failed: { count: 0, bytes: 0 },
  rejected: { count: 0, bytes: 0 },
};

const MOCK_RENDERERS = {
  remote_enabled: false, gateway_address: "",
  renderers: [{ id: "builtin", name: "Built-in renderer", builtin: true, enabled: true, online: true,
                state: "idle", needs_upgrade: false, gpu_verified: false, last_heartbeat_at: null,
                current_video_id: null, current_video_title: null, last_error: null,
                credential_expires_at: null, version: "develop", gpu_probed: false, gpu_configured: false,
                gpu_error: "", compute: { cpus: 6, memory_bytes: 0, gpus: [] }, gpu: null, probe_pending: false }],
};

/** Routes /settings, /pipeline/status, /renderers, /agents, /retention/backlog and
 * /voices/*\/preview to their own mock bodies — a click on a VoicePreviewButton
 * must not be misrouted to the settings/status branches below and receive a
 * settings object back. A null backlog answers that route with a 500. */
function stubFetch(settings = MOCK_SETTINGS, status = MOCK_STATUS, agents: Agent[] = [],
                   backlog: RetentionBacklog | null = MOCK_BACKLOG, mascots: unknown[] = [],
                   gpuStatus = "working") {
  vi.stubGlobal("fetch", vi.fn().mockImplementation((url: string) => {
    if (url.endsWith("/render/gpu")) {
      return Promise.resolve({ ok: true, json: async () => ({ status: gpuStatus }) });
    }
    if (url.endsWith("/renderers")) {
      return Promise.resolve({ ok: true, json: async () => MOCK_RENDERERS });
    }
    if (url.endsWith("/mascots")) {
      return Promise.resolve({ ok: true, json: async () => mascots });
    }
    if (url.endsWith("/retention/backlog")) {
      return Promise.resolve(backlog
        ? { ok: true, json: async () => backlog }
        : { ok: false, status: 500, json: async () => ({ error: "boom" }) });
    }
    if (url.endsWith("/agents")) {
      return Promise.resolve({ ok: true, json: async () => agents });
    }
    if (url.includes("/preview")) {
      return Promise.resolve({
        ok: true,
        json: async () => ({ path: "/output_videos/voice-previews/abc123.mp3", cached: false, credits: 117 }),
      });
    }
    return Promise.resolve({
      ok: true,
      json: async () => (url.includes("/pipeline/status") ? status : settings),
    });
  }));
}


// ── Tab helpers (settings are behind tabs since the Save-button rework) ──────
// Each tab renders only its own fields, so a test that touches a field has to
// open its tab first. Every change then saves itself (TMDEV-218).

const TAB_OF: Record<string, string> = {
  "toggle-gemini-review": "ai-review",
  "toggle-watermark": "rendering",
  "select-ai-review-model": "ai-review",
  "input-ai-review-fps": "ai-review",
  "input-ai-review-max-loops": "ai-review",
  "input-max-curriculum-per-run": "research",
  "input-max-trending-per-run": "research",
  "input-max-mining-per-run": "research",
  "input-research-pending-cap": "research",
  "input-max-research-runs-per-day": "research",
  "trending-sources-editor": "research",
  "select-elevenlabs-model-id": "voice",
  "select-image-model": "images",
  "input-render-timeout-mins": "rendering",
  "input-render-stall-timeout-mins": "rendering",
  "input-max-render-retries": "rendering",
  "input-max-concurrent-agent-sessions": "scheduling",
  "input-agent-session-timeout-mins": "scheduling",
  "input-postforme-api-key": "api-keys",
  "toggle-publishing": "publishing",
  "input-log-retention-days": "logs",
  "input-retention-days": "retention",
  "input-unpublished-retention-days": "retention",
  "input-discord-webhook-url": "notifications",
  "input-dashboard-base-url": "notifications",
  "toggle-notify-topic-proposed": "notifications",
  "toggle-notify-script-ready": "notifications",
  "toggle-notify-video-ready": "notifications",
  "toggle-notify-partially-published": "notifications",
  "toggle-notify-failed": "notifications",
  "input-user-preferences": "preferences",
};

async function openTab(key: string) {
  await act(async () => {
    fireEvent.click(screen.getByTestId(`tab-${key}`));
  });
}

/** Every change saves itself (TMDEV-218): let the save it started settle. */
async function flushSaves() {
  await act(async () => {
    await new Promise((r) => setTimeout(r, 0));
  });
}

/** Render, open a tab, and wait for its fields to exist. */
async function renderTab(key: string) {
  render(<SettingsPage />);
  await waitFor(() => screen.getByTestId(`tab-${key}`));
  await openTab(key);
}

/** The body of the first POST /settings made. */
function savedBody(fetchMock: ReturnType<typeof vi.mocked<typeof fetch>>) {
  const post = fetchMock.mock.calls.find(
    ([url, init]) =>
      String(url).includes("/settings") &&
      (init as RequestInit | undefined)?.method === "POST",
  );
  return post ? JSON.parse((post[1] as RequestInit).body as string) : null;
}

/** Makes POST /settings wait until the returned function is called with
 *  the answer to give; every other route answers as stubFetch does. */
function holdPosts() {
  const base = vi.mocked(fetch).getMockImplementation()!;
  const waiting: Array<(r: Partial<Response>) => void> = [];
  vi.mocked(fetch).mockImplementation(((url: string, init?: RequestInit) => {
    if (String(url).includes("/settings") && init?.method === "POST") {
      return new Promise((resolve) => waiting.push(resolve as (r: Partial<Response>) => void));
    }
    return base(url, init);
  }) as typeof fetch);
  return {
    count: () => waiting.length,
    answer: async (i: number, r: Partial<Response>) => {
      await act(async () => { waiting[i](r); await new Promise((x) => setTimeout(x, 0)); });
    },
  };
}

const okAnswer = (settings: Settings = MOCK_SETTINGS) =>
  ({ ok: true, status: 200, json: async () => settings }) as Partial<Response>;

function postedBodies(fetchMock: ReturnType<typeof vi.mocked<typeof fetch>>) {
  return fetchMock.mock.calls
    .filter(([url, init]) => String(url).includes("/settings") && (init as RequestInit | undefined)?.method === "POST")
    .map(([, init]) => JSON.parse((init as RequestInit).body as string));
}


describe("SettingsPage", () => {
  beforeEach(() => {
    stubFetch();
    // happy-dom's HTMLMediaElement.play() rejects with "not implemented" —
    // stub it so a VoicePreviewButton click doesn't produce an unhandled
    // rejection unrelated to what these tests assert.
    HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue(undefined);
    HTMLMediaElement.prototype.pause = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("renders pipeline pause toggle after loading", async () => {
    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByTestId("toggle-pipeline-pause")).toBeTruthy();
    });
  });

  it("labels AI review experimental beside its switch and in its heading", async () => {
    await renderTab("ai-review");
    expect(screen.getByTestId("ai-review-experimental").textContent).toBe("Experimental");
    const section = screen.getByTestId("section-ai-review");
    // The heading's tag plus the one beside the switch.
    expect(section.textContent!.match(/Experimental/g)!.length).toBe(2);
    // The fail-open behaviour is what "experimental" warns about; say it here.
    expect(section.textContent).toMatch(/If the review itself fails/);
  });

  it("renders the AI review toggle and the render retry cap on their own tabs", async () => {
    await renderTab("ai-review");
    expect(screen.getByTestId("toggle-gemini-review")).toBeTruthy();
    await openTab("rendering");
    expect(screen.getByTestId("input-max-render-retries")).toBeTruthy();
  });

  it("shows the Renderers panel, with the built-in renderer, on the Rendering tab", async () => {
    await renderTab("rendering");
    expect(await screen.findByTestId("renderers-panel")).toBeTruthy();
    expect(await screen.findByTestId("renderer-card-builtin")).toHaveTextContent("Built-in renderer");
    expect(screen.queryByTestId("renderers-error")).toBeNull();
  });

  it("renders all four topic limit inputs", async () => {
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("tab-research"));
    await openTab("research");
    await waitFor(() => {
      expect(screen.getByTestId("input-max-curriculum-per-run")).toBeTruthy();
      expect(screen.getByTestId("input-max-trending-per-run")).toBeTruthy();
      expect(screen.getByTestId("input-max-mining-per-run")).toBeTruthy();
      expect(screen.getByTestId("input-research-pending-cap")).toBeTruthy();
    });
  });

  it("renders the max-research-runs-per-day input", async () => {
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("tab-research"));
    await openTab("research");
    await waitFor(() => {
      const input = screen.getByTestId("input-max-research-runs-per-day") as HTMLInputElement;
      expect(input).toBeTruthy();
      expect(input.value).toBe("8");
    });
  });

  it("blurring the max-research-runs-per-day input calls POST /settings", async () => {
    const fetchMock = vi.mocked(fetch);
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("tab-research"));
    await openTab("research");
    await waitFor(() => screen.getByTestId("input-max-research-runs-per-day"));

    const input = screen.getByTestId("input-max-research-runs-per-day");
    fireEvent.change(input, { target: { value: "3" } });
    await act(async () => {
      fireEvent.blur(input);
    });

    await flushSaves();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/settings"),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ max_research_runs_per_day: 3 }),
      }),
    );
  });

  it("renders the research-window readout from /pipeline/status", async () => {
    stubFetch(MOCK_SETTINGS, {
      ...MOCK_STATUS,
      research_runs_today: 2,
      max_research_runs_per_day: 8,
      research_window_resets_at: null,
      last_research_at: null,
    });
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("tab-scheduling"));
    await openTab("scheduling");
    await waitFor(() => {
      expect(screen.getByTestId("research-runs-used").textContent).toBe("2 / 8");
      expect(screen.getByTestId("research-window-resets").textContent).toBe("slots available now");
      expect(screen.getByTestId("last-research-at").textContent).toBe("never");
    });
  });

  it("shows the next reset time once the run cap is exhausted", async () => {
    stubFetch(MOCK_SETTINGS, {
      ...MOCK_STATUS,
      research_runs_today: 8,
      max_research_runs_per_day: 8,
      research_window_resets_at: "2026-07-27T12:00:00Z",
      last_research_at: "2026-07-27T09:00:00Z",
    });
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("tab-scheduling"));
    await openTab("scheduling");
    await waitFor(() => {
      expect(screen.getByTestId("research-runs-used").textContent).toBe("8 / 8");
      expect(screen.getByTestId("research-window-resets").textContent).not.toBe("slots available now");
      expect(screen.getByTestId("last-research-at").textContent).not.toBe("never");
    });
  });

  it("renders the trending sources editor with all four source checkboxes", async () => {
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("tab-research"));
    await openTab("research");
    await waitFor(() => {
      expect(screen.getByTestId("trending-sources-editor")).toBeTruthy();
      expect(screen.getByTestId("trending-source-checkbox-github-trending")).toBeTruthy();
      expect(screen.getByTestId("trending-source-checkbox-hacker-news")).toBeTruthy();
      expect(screen.getByTestId("trending-source-checkbox-lobsters")).toBeTruthy();
      expect(screen.getByTestId("trending-source-checkbox-dev-to")).toBeTruthy();
    });
  });

  it("pre-checks sources that are in the current settings", async () => {
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("tab-research"));
    await openTab("research");
    await waitFor(() => screen.getByTestId("trending-source-checkbox-github-trending"));

    // Mock returns ["GitHub Trending", "Hacker News"] — those should be checked
    const ghCheckbox = screen.getByTestId("trending-source-checkbox-github-trending").querySelector("input");
    const hnCheckbox = screen.getByTestId("trending-source-checkbox-hacker-news").querySelector("input");
    const lobCheckbox = screen.getByTestId("trending-source-checkbox-lobsters").querySelector("input");
    expect((ghCheckbox as HTMLInputElement).checked).toBe(true);
    expect((hnCheckbox as HTMLInputElement).checked).toBe(true);
    expect((lobCheckbox as HTMLInputElement).checked).toBe(false);
  });

  it("renders one row per configured voice, with the default selected", async () => {
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("tab-voice"));
    await openTab("voice");
    await waitFor(() => {
      expect(screen.getByTestId("voices-editor")).toBeTruthy();
      expect(screen.getByTestId("voice-row-0")).toBeTruthy();
      expect((screen.getByTestId("voice-name-0") as HTMLInputElement).value).toBe("Narrator");
      expect((screen.getByTestId("voice-id-0") as HTMLInputElement).value).toBe("abc123");
      const radio = screen.getByTestId("voice-default-0").querySelector("input") as HTMLInputElement;
      expect(radio.checked).toBe(true);
    });
  });

  it("renders the add-voice row and disables Add until both fields are filled", async () => {
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("tab-voice"));
    await openTab("voice");
    await waitFor(() => screen.getByTestId("voice-add-row"));
    const addBtn = screen.getByTestId("voice-add") as HTMLButtonElement;
    expect(addBtn.disabled).toBe(true);

    fireEvent.change(screen.getByTestId("voice-add-name"), { target: { value: "Energetic" } });
    fireEvent.change(screen.getByTestId("voice-add-id"), { target: { value: "def456" } });
    expect(addBtn.disabled).toBe(false);
  });

  it("clicking Add posts the new voice appended to the existing roster", async () => {
    const fetchMock = vi.mocked(fetch);
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("tab-voice"));
    await openTab("voice");
    await waitFor(() => screen.getByTestId("voice-add-row"));

    fireEvent.change(screen.getByTestId("voice-add-name"), { target: { value: "Energetic" } });
    fireEvent.change(screen.getByTestId("voice-add-id"), { target: { value: "def456" } });
    await act(async () => {
      fireEvent.click(screen.getByTestId("voice-add"));
    });

    await flushSaves();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/settings"),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          elevenlabs_voices: [
            { name: "Narrator", voice_id: "abc123", model_id: "eleven_multilingual_v2" },
            { name: "Energetic", voice_id: "def456", model_id: "eleven_multilingual_v2" },
          ],
          elevenlabs_voice_id: "abc123",
        }),
      }),
    );
  });

  it("blurring an edited voice name/id commits the whole updated roster", async () => {
    const fetchMock = vi.mocked(fetch);
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("tab-voice"));
    await openTab("voice");
    await waitFor(() => screen.getByTestId("voice-name-0"));

    const nameInput = screen.getByTestId("voice-name-0");
    fireEvent.change(nameInput, { target: { value: "Main Narrator" } });
    await act(async () => {
      fireEvent.blur(nameInput);
    });

    await flushSaves();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/settings"),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          elevenlabs_voices: [{ name: "Main Narrator", voice_id: "abc123", model_id: "eleven_multilingual_v2" }],
          elevenlabs_voice_id: "abc123",
        }),
      }),
    );
  });

  it("removing the current default voice blanks the default in the same request", async () => {
    const fetchMock = vi.mocked(fetch);
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("tab-voice"));
    await openTab("voice");
    await waitFor(() => screen.getByTestId("voice-remove-0"));

    await act(async () => {
      fireEvent.click(screen.getByTestId("voice-remove-0"));
    });

    await flushSaves();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/settings"),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ elevenlabs_voices: [], elevenlabs_voice_id: "" }),
      }),
    );
  });

  it("removing a voice offers an Undo that saves the roster and default back", async () => {
    const fetchMock = vi.mocked(fetch);
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("tab-voice"));
    await openTab("voice");
    await waitFor(() => screen.getByTestId("voice-remove-0"));

    await act(async () => { fireEvent.click(screen.getByTestId("voice-remove-0")); });
    await flushSaves();
    const toast = screen.getByTestId("toast-success");
    expect(toast.textContent).toContain('Removed voice "Narrator".');

    await act(async () => { fireEvent.click(screen.getByTestId("toast-action")); });
    await flushSaves();
    expect(postedBodies(fetchMock)).toEqual([
      { elevenlabs_voices: [], elevenlabs_voice_id: "" },
      { elevenlabs_voices: MOCK_SETTINGS.elevenlabs_voices, elevenlabs_voice_id: "abc123" },
    ]);
    expect(screen.queryByTestId("toast-success")).toBeNull();
  });

  it("renders a preview button per voice row that POSTs /voices/<id>/preview", async () => {
    const fetchMock = vi.mocked(fetch);
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("tab-voice"));
    await openTab("voice");
    await waitFor(() => screen.getByTestId("voice-preview-abc123"));

    await act(async () => {
      fireEvent.click(screen.getByTestId("voice-preview-abc123"));
    });

    // The row's model rides along, so an unsaved model change is what plays.
    expect(fetchMock).toHaveBeenCalledWith("/api/proxy/voices/abc123/preview", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model_id: "eleven_multilingual_v2" }),
    });
  });

  it("keeps the add-voice row below the 10-voice maximum", async () => {
    const nineVoices = Array.from({ length: 9 }, (_, i) => ({
      name: `v${i}`, voice_id: `id${i}`, model_id: "eleven_multilingual_v2" }));
    stubFetch({ ...MOCK_SETTINGS, elevenlabs_voices: nineVoices, elevenlabs_voice_id: "id0" });
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("tab-voice"));
    await openTab("voice");
    await waitFor(() => expect(screen.getByTestId("voice-add-row")).toBeTruthy());
    expect(screen.queryByTestId("voice-cap-note")).toBeNull();
  });

  it("hides the add-voice row and shows a cap note at the 10-voice maximum", async () => {
    const tenVoices = Array.from({ length: 10 }, (_, i) => ({
      name: `v${i}`, voice_id: `id${i}`, model_id: "eleven_multilingual_v2" }));
    stubFetch({ ...MOCK_SETTINGS, elevenlabs_voices: tenVoices, elevenlabs_voice_id: "id0" });
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("tab-voice"));
    await openTab("voice");
    await waitFor(() => {
      expect(screen.getByTestId("voice-cap-note")).toBeTruthy();
      expect(screen.queryByTestId("voice-add-row")).toBeNull();
    });
  });

  it("has no install-wide model or pronunciation mode select — the model is per voice", async () => {
    await renderTab("voice");
    expect(screen.queryByTestId("select-elevenlabs-model-id")).toBeNull();
    expect(screen.queryByTestId("select-pronunciation-mode")).toBeNull();
    expect(screen.getByTestId("voice-model-0")).toBeInTheDocument();
  });

  it("each voice row picks its own model from the full catalog", async () => {
    stubFetch({ ...MOCK_SETTINGS, elevenlabs_voices: [
      { name: "Narrator", voice_id: "abc123", model_id: "eleven_turbo_v2" }] });
    await renderTab("voice");
    const modelSelect = screen.getByTestId("voice-model-0") as HTMLSelectElement;
    expect(modelSelect.value).toBe("eleven_turbo_v2");
    expect([...modelSelect.options].map((o) => o.value)).toEqual(
      expect.arrayContaining(["eleven_multilingual_v2", "eleven_v3", "eleven_v4", "eleven_flash_v2"]));
    expect(modelSelect.title).toMatch(/<phoneme>/);
  });

  it("the legend says eleven_v3 and eleven_v4 take exact IPA", async () => {
    await renderTab("voice");
    expect(screen.getByTestId("voice-model-legend").textContent).toMatch(/eleven_v3\/eleven_v4 exact IPA/);
  });

  it("changing a voice's model saves the roster with it, and no install-wide model", async () => {
    const fetchMock = vi.mocked(fetch);
    await renderTab("voice");
    await act(async () => {
      fireEvent.change(screen.getByTestId("voice-model-0"), { target: { value: "eleven_v3" } });
    });
    await flushSaves();
    const body = savedBody(fetchMock);
    expect(body.elevenlabs_voices).toEqual([
      { name: "Narrator", voice_id: "abc123", model_id: "eleven_v3" }]);
    expect(body).not.toHaveProperty("elevenlabs_model_id");
    expect(body).not.toHaveProperty("pronunciation_mode");
  });

  it("a new voice is added with the model picked beside it", async () => {
    const fetchMock = vi.mocked(fetch);
    await renderTab("voice");
    await act(async () => {
      fireEvent.change(screen.getByTestId("voice-add-name"), { target: { value: "Adam" } });
      fireEvent.change(screen.getByTestId("voice-add-id"), { target: { value: "a1" } });
      fireEvent.change(screen.getByTestId("voice-add-model"), { target: { value: "eleven_v3" } });
      fireEvent.click(screen.getByTestId("voice-add"));
    });
    await flushSaves();
    const posted = fetchMock.mock.calls.find(([url, init]) =>
      String(url).includes("/settings") && (init as RequestInit | undefined)?.method === "POST");
    expect(JSON.parse(String((posted![1] as RequestInit).body)).elevenlabs_voices[1])
      .toEqual({ name: "Adam", voice_id: "a1", model_id: "eleven_v3" });
  });

  it("the Images tab has no provider control: OpenAI is the only image provider", async () => {
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("tab-images"));
    await openTab("images");
    await waitFor(() => screen.getByTestId("select-image-model"));
    expect(screen.queryByTestId("select-image-provider")).toBeNull();
  });

  it("image model select lists the OpenAI catalog and patches image_model alone", async () => {
    const fetchMock = vi.mocked(fetch);
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("tab-images"));
    await openTab("images");
    await waitFor(() => screen.getByTestId("select-image-model"));

    const modelSelect = screen.getByTestId("select-image-model") as HTMLSelectElement;
    expect(modelSelect.value).toBe("gpt-image-2.5-flare");
    expect([...modelSelect.options].map((o) => o.value))
      .toEqual(["gpt-image-2.5-flare", "gpt-image-2.5-sunburst"]);

    await act(async () => {
      fireEvent.change(modelSelect, { target: { value: "gpt-image-2.5-sunburst" } });
    });
    await flushSaves();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/settings"),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ image_model: "gpt-image-2.5-sunburst" }),
      }),
    );
  });

  it("the character model offers the OpenAI catalog", async () => {
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("tab-images"));
    await openTab("images");
    await waitFor(() => screen.getByTestId("select-character-model"));

    const select = screen.getByTestId("select-character-model") as HTMLSelectElement;
    expect(select.value).toBe("gpt-image-2.5-flare");
    expect([...select.options].map((o) => o.value))
      .toEqual(["gpt-image-2.5-flare", "gpt-image-2.5-sunburst"]);
  });

  it("changing the character model patches character_model alone", async () => {
    const fetchMock = vi.mocked(fetch);
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("tab-images"));
    await openTab("images");
    await waitFor(() => screen.getByTestId("select-character-model"));

    await act(async () => {
      fireEvent.change(screen.getByTestId("select-character-model"),
        { target: { value: "gpt-image-2.5-sunburst" } });
    });

    await flushSaves();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/settings"),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ character_model: "gpt-image-2.5-sunburst" }),
      }),
    );
  });

  it("clicking pipeline pause toggle calls POST /pipeline/pause", async () => {
    const fetchMock = vi.mocked(fetch);
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("toggle-pipeline-pause"));

    await act(async () => {
      fireEvent.click(screen.getByTestId("toggle-pipeline-pause"));
    });

    // Should call /api/proxy/pipeline/pause with paused: true
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/pipeline/pause"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("clicking AI review toggle calls POST /settings", async () => {
    const fetchMock = vi.mocked(fetch);
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("tab-ai-review"));
    await openTab("ai-review");
    await waitFor(() => screen.getByTestId("toggle-gemini-review"));

    await act(async () => {
      fireEvent.click(screen.getByTestId("toggle-gemini-review"));
    });

    await flushSaves();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/settings"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("blurring a number input calls POST /settings", async () => {
    const fetchMock = vi.mocked(fetch);
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("tab-rendering"));
    await openTab("rendering");
    await waitFor(() => screen.getByTestId("input-max-render-retries"));

    const input = screen.getByTestId("input-max-render-retries");
    fireEvent.change(input, { target: { value: "4" } });
    await act(async () => {
      fireEvent.blur(input);
    });

    await flushSaves();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/settings"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("renders the AI review model select with the configured value", async () => {
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("tab-ai-review"));
    await openTab("ai-review");
    await waitFor(() => {
      const sel = screen.getByTestId("select-ai-review-model") as HTMLSelectElement;
      expect(sel.value).toBe("gemini-2.5-flash");
      expect([...sel.options].map((o) => o.value)).toEqual([
        "gemini-2.5-flash",
        "gemini-3.5-flash",
        "gemini-3.6-flash",
      ]);
    });
  });

  it("choosing an AI review model patches ai_review_model", async () => {
    const fetchMock = vi.mocked(fetch);
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("tab-ai-review"));
    await openTab("ai-review");
    await waitFor(() => screen.getByTestId("select-ai-review-model"));

    await act(async () => {
      fireEvent.change(screen.getByTestId("select-ai-review-model"), {
        target: { value: "gemini-3.6-flash" },
      });
    });

    await flushSaves();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/settings"),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ ai_review_model: "gemini-3.6-flash" }),
      }),
    );
  });

  it("renders the sampling rate bounded to Gemini's valid fps range", async () => {
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("tab-ai-review"));
    await openTab("ai-review");
    await waitFor(() => {
      const input = screen.getByTestId("input-ai-review-fps") as HTMLInputElement;
      expect(input.value).toBe("10");
      expect(input.min).toBe("1");
      expect(input.max).toBe("24"); // (0, 24] — outside it Gemini 400s
    });
  });

  it("committing a sampling rate patches ai_review_fps", async () => {
    const fetchMock = vi.mocked(fetch);
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("tab-ai-review"));
    await openTab("ai-review");
    await waitFor(() => screen.getByTestId("input-ai-review-fps"));

    const input = screen.getByTestId("input-ai-review-fps");
    fireEvent.change(input, { target: { value: "20" } });
    await act(async () => {
      fireEvent.blur(input);
    });

    await flushSaves();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/settings"),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ ai_review_fps: 20 }),
      }),
    );
  });

  it("shows the review loop cap and the render retry cap as separate controls", async () => {
    // The VQA-7 split: one knob used to cap both, so lowering the review loop
    // silently halved the render retry budget. They sit on different tabs now,
    // which makes conflating them harder still.
    await renderTab("ai-review");
    const loops = screen.getByTestId("input-ai-review-max-loops") as HTMLInputElement;
    expect(loops.value).toBe("1");
    expect(loops.max).toBe("2");
    await openTab("rendering");
    expect((screen.getByTestId("input-max-render-retries") as HTMLInputElement).value).toBe("1");
  });

  it("renders render timeout input converted to minutes", async () => {
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("tab-rendering"));
    await openTab("rendering");
    await waitFor(() => {
      const input = screen.getByTestId("input-render-timeout-mins") as HTMLInputElement;
      expect(input.value).toBe("40"); // 2400s / 60
    });
  });

  it("renders the stall timeout in minutes and patches render_stall_timeout_secs on commit", async () => {
    const fetchMock = vi.mocked(fetch);
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("tab-rendering"));
    await openTab("rendering");
    await waitFor(() => screen.getByTestId("input-render-stall-timeout-mins"));

    const input = screen.getByTestId("input-render-stall-timeout-mins") as HTMLInputElement;
    expect(input.value).toBe("10"); // 600s / 60
    fireEvent.change(input, { target: { value: "15" } });
    await act(async () => {
      fireEvent.blur(input);
    });

    await flushSaves();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/settings"),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ render_stall_timeout_secs: 900 }),
      }),
    );
  });

  it("accepts the 180-minute default render timeout (the input's ceiling is above it)", async () => {
    const fetchMock = vi.mocked(fetch);
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("tab-rendering"));
    await openTab("rendering");
    await waitFor(() => screen.getByTestId("input-render-timeout-mins"));

    const input = screen.getByTestId("input-render-timeout-mins") as HTMLInputElement;
    expect(input.max).toBe("600");
    fireEvent.change(input, { target: { value: "180" } });
    await act(async () => {
      fireEvent.blur(input);
    });

    await flushSaves();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/settings"),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ render_timeout_secs: 10800 }),
      }),
    );
  });

  it("switching the watermark off patches watermark_enabled", async () => {
    const fetchMock = vi.mocked(fetch);
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("tab-rendering"));
    await openTab("rendering");
    await waitFor(() => screen.getByTestId("toggle-watermark"));

    const toggle = screen.getByTestId("toggle-watermark");
    expect(toggle.textContent).toBe("ON");
    fireEvent.click(toggle);
    expect(toggle.textContent).toBe("OFF");

    await flushSaves();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/settings"),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ watermark_enabled: false }),
      }),
    );
  });

  it("the default mascot picker lists only pickable mascots and patches default_mascot_id", async () => {
    stubFetch(MOCK_SETTINGS, MOCK_STATUS, [], MOCK_BACKLOG, [
      { id: "tubi", name: "Tubi", pickable: true },
      { id: "moss", name: "Moss", pickable: false },
    ]);
    const fetchMock = vi.mocked(fetch);
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("tab-rendering"));
    await openTab("rendering");
    const select = (await waitFor(() => screen.getByTestId("select-default-mascot"))) as HTMLSelectElement;
    await waitFor(() => expect([...select.options].map((o) => o.value)).toEqual(["", "tubi"]));
    expect(select.value).toBe("");
    fireEvent.change(select, { target: { value: "tubi" } });
    await flushSaves();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/settings"),
      expect.objectContaining({ method: "POST", body: JSON.stringify({ default_mascot_id: "tubi" }) }),
    );
  });

  it.each([
    ["not_usable", "Tubi (Mascots need a working GPU)"],
    ["unknown", "Tubi (GPU not tested yet)"],
  ])("disables the default-mascot choices while the GPU is %s, keeping No mascot and a held value", async (status, label) => {
    stubFetch({ ...MOCK_SETTINGS, default_mascot_id: "tubi" }, MOCK_STATUS, [], MOCK_BACKLOG, [
      { id: "tubi", name: "Tubi", pickable: true },
      { id: "pip", name: "Pip", pickable: true },
    ], status);
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("tab-rendering"));
    await openTab("rendering");
    const select = (await waitFor(() => screen.getByTestId("select-default-mascot"))) as HTMLSelectElement;
    await waitFor(() => expect([...select.options].find((o) => o.value === "pip")?.textContent)
      .toBe(label.replace("Tubi", "Pip")));
    const by = (v: string) => [...select.options].find((o) => o.value === v)!;
    expect(by("pip").disabled).toBe(true);
    expect(by("").disabled).toBe(false);
    // The held default stays shown and selectable, so it is never stripped.
    expect(select.value).toBe("tubi");
    expect(by("tubi").disabled).toBe(false);
  });

  it("committing render timeout in minutes patches render_timeout_secs", async () => {
    const fetchMock = vi.mocked(fetch);
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("tab-rendering"));
    await openTab("rendering");
    await waitFor(() => screen.getByTestId("input-render-timeout-mins"));

    const input = screen.getByTestId("input-render-timeout-mins");
    fireEvent.change(input, { target: { value: "45" } });
    await act(async () => {
      fireEvent.blur(input);
    });

    await flushSaves();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/settings"),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ render_timeout_secs: 2700 }),
      }),
    );
  });

  it("shows the agent-session settings on the Scheduling tab, timeout in minutes", async () => {
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("tab-scheduling"));
    await openTab("scheduling");
    const slots = screen.getByTestId("input-max-concurrent-agent-sessions") as HTMLInputElement;
    expect(slots.value).toBe("3");
    expect(slots.min).toBe("1");
    expect(slots.max).toBe("10");
    const timeout = screen.getByTestId("input-agent-session-timeout-mins") as HTMLInputElement;
    expect(timeout.value).toBe("90"); // 5400s / 60
  });

  it("each agent-session field saves its own key, the timeout in seconds", async () => {
    const fetchMock = vi.mocked(fetch);
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("tab-scheduling"));
    await openTab("scheduling");
    const slots = screen.getByTestId("input-max-concurrent-agent-sessions");
    fireEvent.change(slots, { target: { value: "1" } });
    await act(async () => { fireEvent.blur(slots); });
    const timeout = screen.getByTestId("input-agent-session-timeout-mins");
    fireEvent.change(timeout, { target: { value: "30" } });
    await act(async () => { fireEvent.blur(timeout); });

    await flushSaves();
    expect(postedBodies(fetchMock)).toEqual([
      { max_concurrent_agent_sessions: 1 },
      { agent_session_timeout_secs: 1800 },
    ]);
  });

  it("shows loading state before data loads", () => {
    // Fetch never resolves in this test
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => new Promise(() => {})));
    render(<SettingsPage />);
    expect(screen.getByText(/loading/i)).toBeTruthy();
  });
});

// ── API keys (TMDEV-73) ─────────────────────────────────────────────────────
// Keys live in the settings table now. The server returns only a mask, so the
// browser never receives a usable key — these tests pin the two behaviours
// that make rendering it as a field value safe.

describe("SettingsPage — API keys", () => {
  beforeEach(() => {
    stubFetch();
    HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue(undefined);
    HTMLMediaElement.prototype.pause = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  function body(fetchMock: ReturnType<typeof vi.mocked<typeof fetch>>) {
    const post = fetchMock.mock.calls.find(
      ([, init]) => (init as RequestInit | undefined)?.method === "POST",
    );
    return post ? JSON.parse((post[1] as RequestInit).body as string) : null;
  }

  it("renders the mask the server returned, never a raw key", async () => {
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("tab-api-keys"));
    await openTab("api-keys");
    await waitFor(() => screen.getByTestId("input-elevenlabs-api-key"));
    const input = screen.getByTestId("input-elevenlabs-api-key") as HTMLInputElement;
    expect(input.value).toBe("••••••••4f2a");
  });

  it("hides the value until the field is focused", async () => {
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("tab-api-keys"));
    await openTab("api-keys");
    await waitFor(() => screen.getByTestId("input-gemini-api-key"));
    const input = screen.getByTestId("input-gemini-api-key") as HTMLInputElement;
    expect(input.type).toBe("password");
    await act(async () => { fireEvent.focus(input); });
    expect(input.type).toBe("text");
  });

  it("blurring without editing posts nothing", async () => {
    const fetchMock = vi.mocked(fetch);
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("tab-api-keys"));
    await openTab("api-keys");
    await waitFor(() => screen.getByTestId("input-gemini-api-key"));
    fetchMock.mockClear();

    const input = screen.getByTestId("input-gemini-api-key");
    await act(async () => {
      fireEvent.focus(input);
      fireEvent.blur(input);
    });

    // Posting the untouched mask back would be harmless (the server no-ops it)
    // but pointless — and if that server guard ever regressed, this is what
    // would have overwritten every stored key with its own mask.
    await flushSaves();
    expect(body(fetchMock)).toBeNull();
  });

  it("typing a new key posts the raw value for that key alone", async () => {
    const fetchMock = vi.mocked(fetch);
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("tab-api-keys"));
    await openTab("api-keys");
    await waitFor(() => screen.getByTestId("input-gemini-api-key"));
    fetchMock.mockClear();

    const input = screen.getByTestId("input-gemini-api-key");
    fireEvent.change(input, { target: { value: "sk-gemini-brand-new" } });
    await act(async () => { fireEvent.blur(input); });

    await flushSaves();
    expect(body(fetchMock)).toEqual({ gemini_api_key: "sk-gemini-brand-new" });
  });

  it("clearing the field posts an empty string to remove the key", async () => {
    const fetchMock = vi.mocked(fetch);
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("tab-api-keys"));
    await openTab("api-keys");
    await waitFor(() => screen.getByTestId("input-elevenlabs-api-key"));
    fetchMock.mockClear();

    const input = screen.getByTestId("input-elevenlabs-api-key");
    fireEvent.change(input, { target: { value: "" } });
    await act(async () => { fireEvent.blur(input); });

    await flushSaves();
    expect(body(fetchMock)).toEqual({ elevenlabs_api_key: "" });
  });

  it("trims a pasted key", async () => {
    const fetchMock = vi.mocked(fetch);
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("tab-api-keys"));
    await openTab("api-keys");
    await waitFor(() => screen.getByTestId("input-openai-api-key"));
    fetchMock.mockClear();

    const input = screen.getByTestId("input-openai-api-key");
    fireEvent.change(input, { target: { value: "  sk-openai-pasted \n" } });
    await act(async () => { fireEvent.blur(input); });

    await flushSaves();
    expect(body(fetchMock)).toEqual({ openai_api_key: "sk-openai-pasted" });
  });

  it("shows an unset key as empty with a not-set placeholder", async () => {
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("tab-api-keys"));
    await openTab("api-keys");
    await waitFor(() => screen.getByTestId("input-openai-api-key"));
    const input = screen.getByTestId("input-openai-api-key") as HTMLInputElement;
    expect(input.value).toBe("");
    expect(input.placeholder).toBe("not set");
  });
});

// ── Scheduling: the agent model moved to the agents table ──────────────────

describe("SettingsPage — scheduling tab", () => {
  beforeEach(() => stubFetch());
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("no longer offers an agent model", async () => {
    // agent_model is no longer a settings key — POST /settings would 400 on
    // it — so the field cannot remain. The tab's Save bar belongs to the
    // agent-session settings added since (TMDEV-129).
    await renderTab("scheduling");
    await waitFor(() => screen.getByTestId("research-runs-used"));
    expect(screen.queryByTestId("input-agent-model")).toBeNull();
  });
});

// ── Agents tab ─────────────────────────────────────────────────────────────

function makeAgent(over: Partial<Agent> = {}): Agent {
  return {
    id: "claude",
    name: "Claude Code",
    binary: "claude",
    run_path: "~/.tubematic-agent",
    install_scope: "user",
    models: ["sonnet", "opus", "haiku"],
    effort: "high",
    is_default: true,
    weight: 100,
    verified_at: "2026-09-01T00:00:00Z",
    archived_at: null,
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
    ...over,
  };
}

describe("SettingsPage — agents tab", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  /** GET /agents returns `agents`; a PATCH to /agents/<id> returns
   *  `mutation` (default: 200 echoing the first agent). Everything else falls
   *  through to the settings/status bodies. */
  function stubAgents(agents: Agent[], mutation?: { status: number; body: unknown }) {
    const fn = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes("/agents/") && init?.method) {
        const m = mutation ?? { status: 200, body: agents[0] };
        return Promise.resolve({ ok: m.status < 400, status: m.status, json: async () => m.body });
      }
      if (url.endsWith("/agents")) return Promise.resolve({ ok: true, status: 200, json: async () => agents });
      return Promise.resolve({
        ok: true, status: 200,
        json: async () => (url.includes("/pipeline/status") ? MOCK_STATUS : MOCK_SETTINGS),
      });
    });
    vi.stubGlobal("fetch", fn);
    return fn;
  }

  function mutations(fn: ReturnType<typeof vi.fn>) {
    return fn.mock.calls.filter(([url, init]) =>
      String(url).includes("/agents/") && (init as RequestInit | undefined)?.method);
  }

  it("lists each agent with its details and marks models[0] as the default", async () => {
    stubAgents([makeAgent()]);
    await renderTab("agents");
    const row = await screen.findByTestId("agent-row-claude");
    const text = row.textContent ?? "";
    for (const s of ["Claude Code", "claude", "~/.tubematic-agent", "user", "sonnet", "opus", "haiku"]) {
      expect(text).toContain(s);
    }
    // Exactly one default marker, on the first model's chip.
    const marker = screen.getByTestId("agent-model-default-claude");
    expect(marker.parentElement!.textContent).toContain("sonnet");
    expect(screen.getAllByTestId("agent-model-default-claude")).toHaveLength(1);
    expect(screen.getByTestId("agents-weight-hint").textContent).toMatch(/exact shares/i);
    expect(screen.getByTestId("agents-models-note").textContent)
      .toContain("python onboard.py --install-agent <agent>");
    // Saves through its own endpoints, not the settings Save bar.
    expect(screen.queryByTestId("save-agents")).toBeNull();
  });

  it("the default radio PATCHes {is_default: true}", async () => {
    const fn = stubAgents([
      makeAgent(),
      makeAgent({ id: "other", name: "Other", is_default: false, weight: 0 }),
    ]);
    await renderTab("agents");
    const radio = within(await screen.findByTestId("agent-default-other")).getByRole("radio");
    await act(async () => { fireEvent.click(radio); });

    const [call] = mutations(fn);
    expect(String(call[0])).toContain("/agents/other");
    expect((call[1] as RequestInit).method).toBe("PATCH");
    expect(JSON.parse((call[1] as RequestInit).body as string)).toEqual({ is_default: true });
  });

  it("reloads after a change, so the previous default's radio clears too", async () => {
    // Making one agent the default clears is_default on the one that held it,
    // which is why a mutation reloads the list rather than splicing one row.
    const before = [makeAgent(), makeAgent({ id: "other", name: "Other", is_default: false })];
    const after = [makeAgent({ is_default: false }), makeAgent({ id: "other", name: "Other", is_default: true })];
    let listed = before;
    vi.stubGlobal("fetch", vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes("/agents/") && init?.method) {
        listed = after;
        return Promise.resolve({ ok: true, status: 200, json: async () => after[1] });
      }
      if (url.endsWith("/agents")) return Promise.resolve({ ok: true, status: 200, json: async () => listed });
      return Promise.resolve({
        ok: true, status: 200,
        json: async () => (url.includes("/pipeline/status") ? MOCK_STATUS : MOCK_SETTINGS),
      });
    }));
    await renderTab("agents");
    const radioOf = (id: string) =>
      within(screen.getByTestId(`agent-default-${id}`)).getByRole("radio") as HTMLInputElement;
    await waitFor(() => expect(radioOf("claude").checked).toBe(true));
    await act(async () => { fireEvent.click(radioOf("other")); });
    await waitFor(() => {
      expect(radioOf("claude").checked).toBe(false);
      expect(radioOf("other").checked).toBe(true);
    });
  });

  it("the weight saves on blur as a PATCH of {weight}, and an untouched blur sends nothing", async () => {
    const fn = stubAgents([makeAgent()]);
    await renderTab("agents");
    const input = await screen.findByTestId("agent-weight-claude");
    expect(screen.queryByTestId("agent-weight-save-claude")).toBeNull();
    await act(async () => { fireEvent.blur(input); });
    expect(mutations(fn)).toHaveLength(0);
    fireEvent.change(input, { target: { value: "40" } });
    await act(async () => { fireEvent.blur(input); });

    const [call] = mutations(fn);
    expect(String(call[0])).toContain("/agents/claude");
    expect((call[1] as RequestInit).method).toBe("PATCH");
    expect(JSON.parse((call[1] as RequestInit).body as string)).toEqual({ weight: 40 });
  });

  it("refuses to save a weight outside 0..100, and says why beside the row", async () => {
    const fn = stubAgents([makeAgent()]);
    await renderTab("agents");
    const input = await screen.findByTestId("agent-weight-claude");
    fireEvent.change(input, { target: { value: "101" } });
    await act(async () => { fireEvent.keyDown(input, { key: "Enter" }); });
    expect(mutations(fn)).toHaveLength(0);
    expect(screen.getByTestId("agent-error-claude").textContent).toMatch(/0 to 100/);
    // What was typed stays, so it can be corrected.
    expect((input as HTMLInputElement).value).toBe("101");
  });

  it("the default-model select lists the agent's models with models[0] selected", async () => {
    stubAgents([makeAgent()]);
    await renderTab("agents");
    const select = (await screen.findByTestId("agent-default-model-claude")) as HTMLSelectElement;
    expect([...select.options].map((o) => o.value)).toEqual(["sonnet", "opus", "haiku"]);
    expect(select.value).toBe("sonnet");
    expect(select.disabled).toBe(false);
  });

  it("changing the default model PATCHes {default_model} and the reload moves the marker", async () => {
    // The API moves the pick to the front of models, so models[0] stays the
    // default; the dashboard only has to reload.
    let listed = [makeAgent()];
    const fn = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes("/agents/") && init?.method) {
        listed = [makeAgent({ models: ["opus", "sonnet", "haiku"] })];
        return Promise.resolve({ ok: true, status: 200, json: async () => listed[0] });
      }
      if (url.endsWith("/agents")) return Promise.resolve({ ok: true, status: 200, json: async () => listed });
      return Promise.resolve({
        ok: true, status: 200,
        json: async () => (url.includes("/pipeline/status") ? MOCK_STATUS : MOCK_SETTINGS),
      });
    });
    vi.stubGlobal("fetch", fn);
    await renderTab("agents");
    const select = (await screen.findByTestId("agent-default-model-claude")) as HTMLSelectElement;
    await act(async () => { fireEvent.change(select, { target: { value: "opus" } }); });

    const [call] = mutations(fn);
    expect(String(call[0])).toContain("/agents/claude");
    expect((call[1] as RequestInit).method).toBe("PATCH");
    expect(JSON.parse((call[1] as RequestInit).body as string)).toEqual({ default_model: "opus" });
    await waitFor(() => {
      expect((screen.getByTestId("agent-default-model-claude") as HTMLSelectElement).value).toBe("opus");
      expect(screen.getByTestId("agent-model-default-claude").parentElement!.textContent).toContain("opus");
    });
  });

  it("shows the API's error when a default-model change is rejected", async () => {
    stubAgents([makeAgent()], { status: 400, body: { error: "default_model must be one of the agent's models" } });
    await renderTab("agents");
    const select = await screen.findByTestId("agent-default-model-claude");
    await act(async () => { fireEvent.change(select, { target: { value: "haiku" } }); });
    expect((await screen.findByTestId("agent-error-claude")).textContent)
      .toContain("default_model must be one of the agent's models");
  });

  it("offers no uninstall control and never issues a DELETE", async () => {
    const fn = stubAgents([makeAgent()]);
    await renderTab("agents");
    const row = await screen.findByTestId("agent-row-claude");
    expect(screen.queryByTestId("agent-archive-claude")).toBeNull();
    expect(within(row).queryByRole("button", { name: /archive|uninstall|delete|remove/i })).toBeNull();
    expect(screen.getByTestId("agents-uninstall-note").textContent)
      .toContain("python onboard.py --uninstall-agent <agent>");
    await act(async () => {
      fireEvent.click(within(screen.getByTestId("agent-default-claude")).getByRole("radio"));
      fireEvent.change(screen.getByTestId("agent-default-model-claude"), { target: { value: "opus" } });
    });
    expect(fn.mock.calls.some(([, init]) => (init as RequestInit | undefined)?.method === "DELETE")).toBe(false);
  });

  it("shows an uninstalled agent with a badge and every control disabled", async () => {
    stubAgents([makeAgent({ archived_at: "2026-09-05T00:00:00Z", is_default: false })]);
    await renderTab("agents");
    expect((await screen.findByTestId("agent-archived-claude")).textContent).toMatch(/uninstalled/i);
    const radio = within(screen.getByTestId("agent-default-claude")).getByRole("radio") as HTMLInputElement;
    expect(radio.disabled).toBe(true);
    expect((screen.getByTestId("agent-weight-claude") as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByTestId("agent-default-model-claude") as HTMLSelectElement).disabled).toBe(true);
    expect((screen.getByTestId("agent-effort-claude") as HTMLSelectElement).disabled).toBe(true);
  });

  it("the effort select lists the five CLI levels, on the agent's stored one", async () => {
    stubAgents([makeAgent({ effort: "xhigh" })]);
    await renderTab("agents");
    const select = (await screen.findByTestId("agent-effort-claude")) as HTMLSelectElement;
    expect([...select.options].map((o) => o.value))
      .toEqual(["low", "medium", "high", "xhigh", "max"]);
    expect(select.value).toBe("xhigh");
    expect(select.disabled).toBe(false);
  });

  it("changing the effort PATCHes {effort} and the reload shows the new level", async () => {
    let listed = [makeAgent()];
    const fn = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes("/agents/") && init?.method) {
        listed = [makeAgent({ effort: "max" })];
        return Promise.resolve({ ok: true, status: 200, json: async () => listed[0] });
      }
      if (url.endsWith("/agents")) return Promise.resolve({ ok: true, status: 200, json: async () => listed });
      return Promise.resolve({
        ok: true, status: 200,
        json: async () => (url.includes("/pipeline/status") ? MOCK_STATUS : MOCK_SETTINGS),
      });
    });
    vi.stubGlobal("fetch", fn);
    await renderTab("agents");
    const select = (await screen.findByTestId("agent-effort-claude")) as HTMLSelectElement;
    await act(async () => { fireEvent.change(select, { target: { value: "max" } }); });

    const [call] = mutations(fn);
    expect(String(call[0])).toContain("/agents/claude");
    expect((call[1] as RequestInit).method).toBe("PATCH");
    expect(JSON.parse((call[1] as RequestInit).body as string)).toEqual({ effort: "max" });
    await waitFor(() => {
      expect((screen.getByTestId("agent-effort-claude") as HTMLSelectElement).value).toBe("max");
    });
  });

  it("shows the API's error when an effort change is rejected", async () => {
    stubAgents([makeAgent()], { status: 400, body: { error: "effort must be one of ..." } });
    await renderTab("agents");
    const select = await screen.findByTestId("agent-effort-claude");
    await act(async () => { fireEvent.change(select, { target: { value: "max" } }); });
    expect((await screen.findByTestId("agent-error-claude")).textContent)
      .toContain("effort must be one of");
  });

  it("offers an effort select even when the agent has no usable model list", async () => {
    /* The levels come from the CLI, not from what this install probed — so a
       broken models column must not also take the effort control away. */
    stubAgents([makeAgent({ models: [] })]);
    await renderTab("agents");
    expect(((await screen.findByTestId("agent-default-model-claude")) as HTMLSelectElement)
      .disabled).toBe(true);
    expect((screen.getByTestId("agent-effort-claude") as HTMLSelectElement).disabled)
      .toBe(false);
  });

  it("shows the install command when no agent is installed", async () => {
    stubAgents([]);
    await renderTab("agents");
    const empty = await screen.findByTestId("agents-empty");
    expect(empty.textContent).toContain("No agent installed");
    expect(empty.textContent).toContain("python onboard.py --install-agent <agent>");
  });

  it("surfaces the API's error message inline", async () => {
    stubAgents(
      [makeAgent(), makeAgent({ id: "other", name: "Other", is_default: false })],
      { status: 409, body: { error: "agent is uninstalled" } },
    );
    await renderTab("agents");
    const radio = within(await screen.findByTestId("agent-default-other")).getByRole("radio");
    await act(async () => { fireEvent.click(radio); });
    expect((await screen.findByTestId("agent-error-other")).textContent).toContain("agent is uninstalled");
  });
});

// ── Tabs, manual save, and toasts ───────────────────────────────────────────
// The page used to auto-save on every blur and discard failures silently.
// Edits are now staged per tab and committed by an explicit Save.

describe("SettingsPage — save behaviour", () => {
  beforeEach(() => {
    stubFetch();
    HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue(undefined);
    HTMLMediaElement.prototype.pause = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it("shows every settings tab", async () => {
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("tab-ai-review"));
    for (const key of ["ai-review", "research", "voice", "images",
                        "rendering", "api-keys", "scheduling", "agents", "preferences",
                        "auto-pilot"]) {
      expect(screen.getByTestId(`tab-${key}`)).toBeTruthy();
    }
  });

  it("a committed field saves itself, sending only that key, with no Save button anywhere", async () => {
    const fetchMock = vi.mocked(fetch);
    await renderTab("rendering");
    expect(screen.queryByTestId("save-rendering")).toBeNull();

    const input = screen.getByTestId("input-max-render-retries");
    fireEvent.change(input, { target: { value: "5" } });
    await act(async () => { fireEvent.blur(input); });
    await flushSaves();

    // render_timeout_secs is deliberately absent: resending an untouched value
    // would make one save clobber a change made elsewhere in between.
    expect(postedBodies(fetchMock)).toEqual([{ max_render_retries: 5 }]);
  });

  it("a blur with nothing changed sends nothing", async () => {
    const fetchMock = vi.mocked(fetch);
    await renderTab("rendering");
    const input = screen.getByTestId("input-max-render-retries");
    await act(async () => { fireEvent.blur(input); });
    await flushSaves();
    expect(postedBodies(fetchMock)).toEqual([]);
  });

  it("shows Saving… beside the field and in the header, then ✓ Saved and all changes saved", async () => {
    await renderTab("rendering");
    const held = holdPosts();
    const input = screen.getByTestId("input-max-render-retries");
    fireEvent.change(input, { target: { value: "5" } });
    await act(async () => { fireEvent.blur(input); });

    expect(screen.getByTestId("status-input-max-render-retries").textContent).toBe("Saving…");
    expect(screen.getByTestId("saves-summary").textContent).toContain("Saving…");

    await held.answer(0, okAnswer({ ...MOCK_SETTINGS, max_render_retries: 5 }));

    expect(screen.getByTestId("status-input-max-render-retries").textContent).toBe("✓ Saved");
    expect(screen.getByTestId("saves-summary").textContent).toContain("All changes saved");
    expect((input as HTMLInputElement).value).toBe("5");
  });

  it("a refused save shows the API's reason beside the field and keeps what was typed", async () => {
    await renderTab("rendering");
    const held = holdPosts();
    const input = screen.getByTestId("input-max-render-retries");
    fireEvent.change(input, { target: { value: "5" } });
    await act(async () => { fireEvent.blur(input); });
    await held.answer(0, {
      ok: false, status: 400, json: async () => ({ error: "max_render_retries must be non-negative" }),
    });

    const status = screen.getByTestId("status-input-max-render-retries");
    expect(status.textContent).toBe("Not saved: max_render_retries must be non-negative");
    expect(screen.getByTestId("saves-summary").textContent).toContain("1 change not saved");
    // Kept, so it can be corrected; the stored value stays in force meanwhile.
    expect((input as HTMLInputElement).value).toBe("5");
  });

  it("an out-of-range number is not sent, and says so beside the field", async () => {
    const fetchMock = vi.mocked(fetch);
    await renderTab("rendering");
    const input = screen.getByTestId("input-max-render-retries");
    fireEvent.change(input, { target: { value: "99" } });
    await act(async () => { fireEvent.blur(input); });
    await flushSaves();

    expect(postedBodies(fetchMock)).toEqual([]);
    expect(screen.getByTestId("status-input-max-render-retries").textContent)
      .toBe("Not saved: must be a whole number from 0 to 10");
    expect((input as HTMLInputElement).value).toBe("99");
  });

  it("saves wait for the one before: a late answer can never overwrite a newer one", async () => {
    await renderTab("rendering");
    const held = holdPosts();
    const retries = screen.getByTestId("input-max-render-retries");
    fireEvent.change(retries, { target: { value: "5" } });
    await act(async () => { fireEvent.blur(retries); });
    const timeout = screen.getByTestId("input-render-timeout-mins");
    fireEvent.change(timeout, { target: { value: "90" } });
    await act(async () => { fireEvent.blur(timeout); });

    // The second is queued behind the first, not sent beside it.
    expect(held.count()).toBe(1);
    await held.answer(0, okAnswer({ ...MOCK_SETTINGS, max_render_retries: 5 }));
    expect(held.count()).toBe(2);
    await held.answer(1, okAnswer({ ...MOCK_SETTINGS, max_render_retries: 5, render_timeout_secs: 5400 }));
    expect((screen.getByTestId("input-max-render-retries") as HTMLInputElement).value).toBe("5");
    expect((screen.getByTestId("input-render-timeout-mins") as HTMLInputElement).value).toBe("90");
  });

  it("a switch shows its new value at once and goes back when the API refuses it", async () => {
    await renderTab("rendering");
    const held = holdPosts();
    const toggle = screen.getByTestId("toggle-watermark");
    expect(toggle.textContent).toBe("ON");
    await act(async () => { fireEvent.click(toggle); });
    expect(toggle.textContent).toBe("OFF");

    await held.answer(0, { ok: false, status: 500, json: async () => ({ error: "database is locked" }) });

    expect(toggle.textContent).toBe("ON");
    expect(screen.getByTestId("status-toggle-watermark").textContent).toBe("Not saved: database is locked");
  });

  it("switching tabs never asks, and a refused change's message does not follow you", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    await renderTab("rendering");
    const input = screen.getByTestId("input-max-render-retries");
    fireEvent.change(input, { target: { value: "99" } });
    await act(async () => { fireEvent.blur(input); });
    expect(screen.getByTestId("saves-summary").textContent).toContain("not saved");

    await openTab("ai-review");
    await openTab("rendering");

    expect(confirmSpy).not.toHaveBeenCalled();
    expect(screen.getByTestId("saves-summary").textContent).toContain("All changes saved");
    expect((screen.getByTestId("input-max-render-retries") as HTMLInputElement).value).toBe("1");
  });

  it("asks before the browser tab closes only while a save is on its way", async () => {
    await renderTab("rendering");
    const held = holdPosts();
    const unload = () => {
      const e = new Event("beforeunload", { cancelable: true });
      window.dispatchEvent(e);
      return e.defaultPrevented;
    };
    expect(unload()).toBe(false);

    const input = screen.getByTestId("input-max-render-retries");
    fireEvent.change(input, { target: { value: "5" } });
    await act(async () => { fireEvent.blur(input); });
    expect(unload()).toBe(true);

    await held.answer(0, okAnswer({ ...MOCK_SETTINGS, max_render_retries: 5 }));
    expect(unload()).toBe(false);
  });

  it("pause stays immediate, pinned above the tabs", async () => {
    const fetchMock = vi.mocked(fetch);
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("toggle-pipeline-pause"));
    fetchMock.mockClear();

    await act(async () => {
      fireEvent.click(screen.getByTestId("toggle-pipeline-pause"));
    });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/pipeline/pause"),
      expect.objectContaining({ method: "POST" }),
    );
  });
});


// ── Publishing (TMDEV-83) ───────────────────────────────────────────────────

describe("SettingsPage — publishing", () => {
  beforeEach(() => {
    HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue(undefined);
    HTMLMediaElement.prototype.pause = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("shows the postforme key alongside the other credentials", async () => {
    stubFetch();
    await renderTab("api-keys");
    expect(screen.getByTestId("input-postforme-api-key")).toBeInTheDocument();
  });

  it("renders the stored postforme key as a mask, never a usable key", async () => {
    stubFetch({ ...MOCK_SETTINGS, postforme_api_key: "••••••••7ac1" });
    await renderTab("api-keys");
    expect(screen.getByTestId("input-postforme-api-key")).toHaveValue("••••••••7ac1");
  });

  it("turning publishing on asks first, and Cancel saves nothing", async () => {
    stubFetch();
    const fetchMock = vi.mocked(fetch);
    await renderTab("publishing");
    await act(async () => {
      fireEvent.click(screen.getByTestId("toggle-publishing"));
    });
    expect(screen.getByTestId("publishing-confirm")).toBeTruthy();
    expect(screen.queryByTestId("publishing-confirm-auto-pilot")).toBeNull();
    await act(async () => { fireEvent.click(screen.getByTestId("publishing-confirm-cancel")); });
    await flushSaves();
    expect(savedBody(fetchMock)).toBeNull();
    expect(screen.getByTestId("toggle-publishing")).toHaveTextContent("OFF");
  });

  it("confirming turns publishing on; the dialog warns when Auto Pilot is on", async () => {
    stubFetch({ ...MOCK_SETTINGS, auto_pilot_enabled: true });
    const fetchMock = vi.mocked(fetch);
    await renderTab("publishing");
    await act(async () => {
      fireEvent.click(screen.getByTestId("toggle-publishing"));
    });
    expect(screen.getByTestId("publishing-confirm-auto-pilot").textContent).toMatch(/without asking/);
    await act(async () => { fireEvent.click(screen.getByTestId("publishing-confirm-ok")); });
    await flushSaves();
    expect(savedBody(fetchMock)).toEqual({ publishing_enabled: true });
  });

  it("turning publishing off saves at once, without asking", async () => {
    stubFetch({ ...MOCK_SETTINGS, publishing_enabled: true });
    const fetchMock = vi.mocked(fetch);
    await renderTab("publishing");
    await act(async () => {
      fireEvent.click(screen.getByTestId("toggle-publishing"));
    });
    expect(screen.queryByTestId("publishing-confirm")).toBeNull();
    await flushSaves();
    expect(savedBody(fetchMock)).toEqual({ publishing_enabled: false });
  });

  it("defaults to off", async () => {
    stubFetch();
    await renderTab("publishing");
    expect(screen.getByTestId("toggle-publishing")).toHaveTextContent("OFF");
  });

  it("keeps the publishing toggle off the API-keys tab", async () => {
    stubFetch();
    await renderTab("api-keys");
    expect(screen.queryByTestId("toggle-publishing")).toBeNull();
  });
});

describe("SettingsPage — Discord notifications (TMDEV-5)", () => {
  beforeEach(() => { stubFetch(); });
  afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

  it("renders the webhook field and every trigger on their own tab", async () => {
    await renderTab("notifications");
    expect(screen.getByTestId("input-discord-webhook-url")).toBeTruthy();
    expect(screen.getByTestId("input-dashboard-base-url")).toBeTruthy();
    expect(screen.getByTestId("toggle-notify-topic-proposed")).toBeTruthy();
    expect(screen.getByTestId("toggle-notify-script-ready")).toBeTruthy();
    expect(screen.getByTestId("toggle-notify-video-ready")).toBeTruthy();
    expect(screen.getByTestId("toggle-notify-partially-published")).toBeTruthy();
    expect(screen.getByTestId("toggle-notify-failed")).toBeTruthy();
  });

  it("shows every trigger off by default", async () => {
    await renderTab("notifications");
    for (const key of ["topic-proposed", "script-ready", "video-ready", "partially-published", "failed"]) {
      expect(screen.getByTestId(`toggle-notify-${key}`)).toHaveTextContent("OFF");
    }
  });

  it("masks the webhook URL, because the URL is the credential", async () => {
    // Anyone holding it can post to that channel, so it is treated exactly
    // like an API key: masked at rest and only revealed while being typed.
    await renderTab("notifications");
    const input = screen.getByTestId("input-discord-webhook-url") as HTMLInputElement;
    expect(input.type).toBe("password");
    await act(async () => { fireEvent.focus(input); });
    expect((screen.getByTestId("input-discord-webhook-url") as HTMLInputElement).type)
      .toBe("text");
  });

  it("saves each trigger independently", async () => {
    const fetchMock = vi.mocked(fetch);
    await renderTab("notifications");
    await act(async () => {
      fireEvent.click(screen.getByTestId("toggle-notify-video-ready"));
    });
    await flushSaves();
    expect(savedBody(fetchMock)).toEqual({ notify_video_ready: true });
  });

  it("saves the webhook URL and the base URL each on blur, saying the webhook is being checked", async () => {
    const fetchMock = vi.mocked(fetch);
    await renderTab("notifications");
    const held = holdPosts();
    const hook = screen.getByTestId("input-discord-webhook-url");
    await act(async () => {
      fireEvent.change(hook, { target: { value: "https://discord.com/api/webhooks/1/t" } });
      fireEvent.blur(hook);
    });
    expect(screen.getByTestId("status-input-discord-webhook-url").textContent).toBe("Checking the webhook…");
    await held.answer(0, okAnswer());
    const base = screen.getByTestId("input-dashboard-base-url");
    // Typing alone sends nothing: a half-typed address is not saved.
    await act(async () => { fireEvent.change(base, { target: { value: "http://box:3000" } }); });
    expect(held.count()).toBe(1);
    await act(async () => { fireEvent.blur(base); });
    await held.answer(1, okAnswer());
    expect(postedBodies(fetchMock)).toEqual([
      { discord_webhook_url: "https://discord.com/api/webhooks/1/t" },
      { dashboard_base_url: "http://box:3000" },
    ]);
  });

  it("sends nothing from this tab when nothing changed", async () => {
    const fetchMock = vi.mocked(fetch);
    await renderTab("notifications");
    await flushSaves();
    expect(savedBody(fetchMock)).toBeNull();
  });

  it("keeps the webhook field off the API-keys tab", async () => {
    // It is a secret, but it belongs with the feature it configures — a reader
    // looking for notification settings should find all of them in one place.
    await renderTab("api-keys");
    expect(screen.queryByTestId("input-discord-webhook-url")).toBeNull();
  });
});

describe("SettingsPage — log retention (TMDEV-86)", () => {
  beforeEach(() => { stubFetch(); });
  afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

  it("shows the stored value on its own Logs tab", async () => {
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("tab-logs"));
    await openTab("logs");
    await waitFor(() => {
      expect((screen.getByTestId("input-log-retention-days") as HTMLInputElement).value)
        .toBe("14");
    });
  });

  it("enforces the 1-365 bound in the markup, matching the API's coercion", async () => {
    // The API rejects out-of-range values with a 400, so an input that let one
    // through would surface as a failed save of the whole tab.
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("tab-logs"));
    await openTab("logs");
    const input = await waitFor(() =>
      screen.getByTestId("input-log-retention-days") as HTMLInputElement);
    expect(input.min).toBe("1");
    expect(input.max).toBe("365");
  });

  it("saves only log_retention_days from this tab", async () => {
    const fetchMock = vi.mocked(fetch);
    render(<SettingsPage />);
    await waitFor(() => screen.getByTestId("tab-logs"));
    await openTab("logs");
    const input = await waitFor(() => screen.getByTestId("input-log-retention-days"));

    fireEvent.change(input, { target: { value: "30" } });
    await act(async () => { fireEvent.blur(input); });
    await flushSaves();

    expect(savedBody(fetchMock)).toEqual({ log_retention_days: 30 });
  });

  // ── Video retention (TMDEV-84) ──

  it("shows retention_days on the Retention tab", async () => {
    await renderTab("retention");
    await waitFor(() => {
      expect((screen.getByTestId("input-retention-days") as HTMLInputElement).value).toBe("7");
    });
  });

  it("allows 0 (the off switch) and caps at 365, matching the API", async () => {
    await renderTab("retention");
    const input = await waitFor(() =>
      screen.getByTestId("input-retention-days") as HTMLInputElement);
    expect(input.min).toBe("0");
    expect(input.max).toBe("365");
  });

  it("saves only retention_days from the Retention tab", async () => {
    const fetchMock = vi.mocked(fetch);
    await renderTab("retention");
    const input = await waitFor(() => screen.getByTestId("input-retention-days"));

    fireEvent.change(input, { target: { value: "0" } });
    await act(async () => { fireEvent.blur(input); });
    await flushSaves();

    expect(savedBody(fetchMock)).toEqual({ retention_days: 0 });
  });

  // ── Failed and rejected videos (TMDEV-134) ──

  it("shows unpublished_retention_days, off by default, bounded like retention_days", async () => {
    await renderTab("retention");
    const input = await waitFor(() =>
      screen.getByTestId("input-unpublished-retention-days") as HTMLInputElement);
    expect(input.value).toBe("0");
    expect(input.min).toBe("0");
    expect(input.max).toBe("365");
  });

  it("saves only unpublished_retention_days when that is the one edited", async () => {
    const fetchMock = vi.mocked(fetch);
    await renderTab("retention");
    const input = await waitFor(() => screen.getByTestId("input-unpublished-retention-days"));

    fireEvent.change(input, { target: { value: "30" } });
    await act(async () => { fireEvent.blur(input); });
    await flushSaves();

    expect(savedBody(fetchMock)).toEqual({ unpublished_retention_days: 30 });
  });

  it("shows how many failed and rejected videos there are and the disk they hold", async () => {
    // The backlog is what makes an off-by-default key discoverable.
    vi.unstubAllGlobals();
    stubFetch(MOCK_SETTINGS, MOCK_STATUS, [], {
      failed: { count: 3, bytes: 1024 ** 3 },
      rejected: { count: 12, bytes: 512 * 1024 ** 2 },
    });
    await renderTab("retention");
    await waitFor(() => {
      expect(screen.getByTestId("retention-backlog"))
        .toHaveTextContent("3 failed and 12 rejected videos are holding 1.5 GB");
    });
  });

  it("says so when nothing is failed or rejected", async () => {
    await renderTab("retention");
    await waitFor(() => {
      expect(screen.getByTestId("retention-backlog"))
        .toHaveTextContent("No failed or rejected videos to sweep");
    });
  });

  it("leaves the backlog line out when the route fails, keeping the field usable", async () => {
    vi.unstubAllGlobals();
    stubFetch(MOCK_SETTINGS, MOCK_STATUS, [], null);
    await renderTab("retention");
    await waitFor(() => screen.getByTestId("input-unpublished-retention-days"));
    expect(screen.queryByTestId("retention-backlog")).toBeNull();
  });
});

describe("SettingsPage — user preferences (TMDEV-117)", () => {
  afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

  it("shows the stored preferences in a textbox on their own tab", async () => {
    stubFetch({ ...MOCK_SETTINGS, user_preferences: "Scripts: calm tone." });
    await renderTab("preferences");
    const box = screen.getByTestId("input-user-preferences") as HTMLTextAreaElement;
    expect(box.tagName).toBe("TEXTAREA");
    expect(box.value).toBe("Scripts: calm tone.");
  });

  it("counts characters against the cap as you type", async () => {
    stubFetch();
    await renderTab("preferences");
    expect(screen.getByTestId("user-preferences-count")).toHaveTextContent("0 / 6000");
    await act(async () => {
      fireEvent.change(screen.getByTestId("input-user-preferences"),
                       { target: { value: "No jokes." } });
    });
    expect(screen.getByTestId("user-preferences-count")).toHaveTextContent("9 / 6000");
  });

  it("stops at the cap the server enforces", async () => {
    stubFetch();
    await renderTab("preferences");
    await act(async () => {
      fireEvent.change(screen.getByTestId("input-user-preferences"),
                       { target: { value: "x".repeat(6001) } });
    });
    expect((screen.getByTestId("input-user-preferences") as HTMLTextAreaElement).value)
      .toHaveLength(6000);
    expect(screen.getByTestId("user-preferences-count")).toHaveTextContent("6000 / 6000");
  });

  it("counts characters the way the server does, so an emoji is one", async () => {
    // Python's len() counts code points; JavaScript's .length (and a textarea's
    // maxLength) count UTF-16 units, i.e. two per emoji. Mixing the two would
    // stop input well short of the limit the API actually allows.
    stubFetch();
    await renderTab("preferences");
    await act(async () => {
      fireEvent.change(screen.getByTestId("input-user-preferences"),
                       { target: { value: "🎬 calm" } });
    });
    expect(screen.getByTestId("user-preferences-count")).toHaveTextContent("6 / 6000");

    await act(async () => {
      fireEvent.change(screen.getByTestId("input-user-preferences"),
                       { target: { value: "🎬".repeat(6001) } });
    });
    expect(Array.from((screen.getByTestId("input-user-preferences") as HTMLTextAreaElement).value))
      .toHaveLength(6000);
  });

  it("saves a second after typing stops, only the preferences, line breaks intact", async () => {
    stubFetch();
    const fetchMock = vi.mocked(fetch);
    await renderTab("preferences");
    await act(async () => {
      fireEvent.change(screen.getByTestId("input-user-preferences"),
                       { target: { value: "Research: Linux.\nScripts: calm." } });
    });
    // Waiting: shown as saving, and nothing sent yet.
    expect(screen.getByTestId("status-input-user-preferences").textContent).toBe("Saving…");
    await flushSaves();
    expect(savedBody(fetchMock)).toBeNull();
    await waitFor(() => expect(savedBody(fetchMock)).toEqual({
      user_preferences: "Research: Linux.\nScripts: calm.",
    }), { timeout: 2500 });
  });

  it("leaving the box sends the text at once", async () => {
    stubFetch();
    const fetchMock = vi.mocked(fetch);
    await renderTab("preferences");
    const box = screen.getByTestId("input-user-preferences");
    await act(async () => { fireEvent.change(box, { target: { value: "UK spelling." } }); });
    await act(async () => { fireEvent.blur(box); });
    await flushSaves();
    expect(postedBodies(fetchMock)).toEqual([{ user_preferences: "UK spelling." }]);
  });

  it("sends nothing from this tab when nothing changed", async () => {
    stubFetch();
    const fetchMock = vi.mocked(fetch);
    await renderTab("preferences");
    await flushSaves();
    expect(savedBody(fetchMock)).toBeNull();
  });
});
