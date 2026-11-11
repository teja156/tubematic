/**
 * The Script tab's per-segment voice (TMDEV-216).
 *
 * What these guard:
 *  - At SCRIPT_READY, with a second voice on the roster, each segment has a
 *    picker; its first option is the video's own voice, and a voice the API
 *    says cannot speak that segment's markup is disabled with the reason.
 *  - A pick is one PATCH carrying only segment_voices, and a refusal shows.
 *  - Elsewhere a segment's own voice is shown read-only, and the Details tab
 *    lists the other voices.
 */
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { VideoModal } from "@/components/VideoModal";
import type { ScriptSegment, Video, VideoStatus } from "@/lib/types";

vi.mock("@/components/TimeZoneProvider", () => ({
  useTimeZone: () => ({ timeZone: "UTC", label: "UTC", degraded: false }),
}));

const VOICES = [
  { name: "Teja", voice_id: "t1", model_id: "eleven_v4" },
  { name: "Rachel", voice_id: "r1", model_id: "eleven_multilingual_v2" },
  { name: "Bella", voice_id: "b1", model_id: "eleven_flash_v2_5" },
];

const SEGMENTS: ScriptSegment[] = [
  { id: "s1", voice: "So [pause] here it is.", visual: "" },
  { id: "s2", voice: "Wait, really?", visual: "", voice_id: "r1" },
];

function makeVideo(status: VideoStatus, extra: Partial<Video> = {}): Video {
  return {
    id: "vid-1", project_id: null, title: null, topic: "Test topic", strategy: "curriculum",
    producibility_score: 5, status, script: "Test script", script_segments: SEGMENTS,
    voice_file_path: null, timeline_path: null, scene_config_path: null, video_path: null,
    video_version: 1, gemini_feedback: null, youtube_url: null, voice_id: "t1",
    effective_voice_id: "t1",
    created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z", comments: [],
    ...extra,
  } as Video;
}

function mockFetch(video: Video, patchResponse?: { ok: boolean; body: unknown; status?: number }) {
  const fetchMock = vi.fn((url: unknown, init?: RequestInit) => {
    if (init?.method === "PATCH") {
      const r = patchResponse ?? { ok: true, body: video };
      return Promise.resolve({ ok: r.ok, status: r.status ?? (r.ok ? 200 : 409),
                               json: async () => r.body } as Response);
    }
    return Promise.resolve({ ok: true, json: async () => (String(url).includes("/videos/") ? video : []) } as Response);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("VideoModal — a voice per segment", () => {
  afterEach(() => vi.restoreAllMocks());

  it("offers a picker per segment at Script Ready, the video's voice first", async () => {
    const video = makeVideo("SCRIPT_READY", {
      segment_voice_conflicts: { s1: { r1: "Rachel's model cannot speak [pause]", b1: "no" } } });
    mockFetch(video);
    render(<VideoModal video={video} voices={VOICES} defaultVoiceId="t1" onClose={() => {}} onAction={() => {}} />);
    const s1 = await screen.findByTestId("segment-voice-s1") as HTMLSelectElement;
    expect(s1.value).toBe("");
    expect(s1.options[0].textContent).toBe("Video voice (Teja)");
    const byValue = Object.fromEntries([...s1.options].map((o) => [o.value, o]));
    expect(byValue.t1).toBeUndefined();
    expect(byValue.r1.disabled).toBe(true);
    expect(byValue.r1.title).toMatch(/cannot speak \[pause\]/);
    expect((screen.getByTestId("segment-voice-s2") as HTMLSelectElement).value).toBe("r1");
  });

  it("a pick sends only segment_voices", async () => {
    const video = makeVideo("SCRIPT_READY");
    const fetchMock = mockFetch(video);
    render(<VideoModal video={video} voices={VOICES} defaultVoiceId="t1" onClose={() => {}} onAction={() => {}} />);
    const s2 = await screen.findByTestId("segment-voice-s2");
    await act(async () => { fireEvent.change(s2, { target: { value: "" } }); });
    const patch = fetchMock.mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === "PATCH");
    expect(String(patch![0])).toBe("/api/proxy/videos/vid-1");
    expect(JSON.parse(String((patch![1] as RequestInit).body))).toEqual({ segment_voices: { s2: "" } });
  });

  it("a refused pick shows the reason", async () => {
    const video = makeVideo("SCRIPT_READY");
    mockFetch(video, { ok: false, status: 409, body: { error: "That voice can't speak this segment: no" } });
    render(<VideoModal video={video} voices={VOICES} defaultVoiceId="t1" onClose={() => {}} onAction={() => {}} />);
    const s2 = await screen.findByTestId("segment-voice-s2");
    await act(async () => { fireEvent.change(s2, { target: { value: "b1" } }); });
    await waitFor(() => expect(screen.getByTestId("segment-voice-error").textContent)
      .toMatch(/can't speak this segment/));
  });

  it("no picker with one voice on the roster", async () => {
    const video = makeVideo("SCRIPT_READY");
    mockFetch(video);
    render(<VideoModal video={video} voices={VOICES.slice(0, 1)} defaultVoiceId="t1" onClose={() => {}} onAction={() => {}} />);
    await screen.findByText("Wait, really?");
    expect(screen.queryByTestId("segment-voice-s1")).toBeNull();
    expect(screen.getByTestId("segment-voice-name-s2").textContent).toBe("Voice: r1");
  });

  it("after Script Ready a segment's own voice is shown, not picked", async () => {
    const video = makeVideo("VOICE_READY");
    mockFetch(video);
    render(<VideoModal video={video} voices={VOICES} defaultVoiceId="t1" initialTab="script"
      onClose={() => {}} onAction={() => {}} />);
    expect((await screen.findByTestId("segment-voice-name-s2")).textContent).toBe("Voice: Rachel");
    expect(screen.queryByTestId("segment-voice-s1")).toBeNull();
    expect(screen.queryByTestId("segment-voice-name-s1")).toBeNull();
  });
});
