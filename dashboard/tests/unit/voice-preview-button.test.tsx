import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { VoicePreviewButton } from "@/components/VoicePreviewButton";

function stubFetch(ok = true, body: object = { path: "/output_videos/voice-previews/abc123.mp3", cached: false, credits: 117 }) {
  vi.stubGlobal("fetch", vi.fn().mockImplementation(() => Promise.resolve({
    ok,
    json: async () => body,
  })));
}

/** Routes by the voice_id embedded in the request URL, so a prop change to a
 * different voiceId gets its own distinct preview path back. */
function stubFetchPerVoice() {
  vi.stubGlobal("fetch", vi.fn().mockImplementation((url: string) => {
    const voiceId = url.match(/\/voices\/([^/]+)\/preview/)?.[1];
    return Promise.resolve({
      ok: true,
      json: async () => ({ path: `/output_videos/voice-previews/${voiceId}.mp3`, cached: false, credits: 117 }),
    });
  }));
}

describe("VoicePreviewButton", () => {
  beforeEach(() => {
    // happy-dom's HTMLMediaElement.play() rejects with "not implemented" —
    // stub it so the component's play() call doesn't produce an unhandled
    // rejection unrelated to what these tests assert.
    HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue(undefined);
    HTMLMediaElement.prototype.pause = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("is disabled when voiceId is empty", () => {
    render(<VoicePreviewButton voiceId="" />);
    const btn = screen.getByTestId("voice-preview-") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it("POSTs /voices/<id>/preview on first click and plays the returned url", async () => {
    stubFetch();
    render(<VoicePreviewButton voiceId="abc123" />);
    const btn = screen.getByTestId("voice-preview-abc123");

    await act(async () => {
      fireEvent.click(btn);
    });

    expect(fetch).toHaveBeenCalledWith("/api/proxy/voices/abc123/preview", { method: "POST" });
    await waitFor(() => {
      expect(HTMLMediaElement.prototype.play).toHaveBeenCalled();
    });
  });

  it("a second click replays the cached audio without a second fetch", async () => {
    stubFetch();
    render(<VoicePreviewButton voiceId="abc123" />);
    const btn = screen.getByTestId("voice-preview-abc123");

    await act(async () => {
      fireEvent.click(btn);
    });
    await waitFor(() => expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(1));

    const fetchMock = vi.mocked(fetch);
    fetchMock.mockClear();

    await act(async () => {
      fireEvent.click(btn);
    });

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("fetches again for the newly selected voice after voiceId changes, not the old one", async () => {
    stubFetchPerVoice();
    const { rerender } = render(<VoicePreviewButton voiceId="abc123" />);

    await act(async () => {
      fireEvent.click(screen.getByTestId("voice-preview-abc123"));
    });
    await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/proxy/voices/abc123/preview", { method: "POST" }));

    rerender(<VoicePreviewButton voiceId="def456" />);
    await act(async () => {
      fireEvent.click(screen.getByTestId("voice-preview-def456"));
    });

    expect(fetch).toHaveBeenCalledTimes(2);
    expect(fetch).toHaveBeenNthCalledWith(2, "/api/proxy/voices/def456/preview", { method: "POST" });
  });

  it("shows an error state when the preview request fails", async () => {
    stubFetch(false, { error: "voice_id 'abc123' is not in elevenlabs_voices" });
    render(<VoicePreviewButton voiceId="abc123" />);
    const btn = screen.getByTestId("voice-preview-abc123");

    await act(async () => {
      fireEvent.click(btn);
    });

    await waitFor(() => {
      expect(btn.title).toBe("voice_id 'abc123' is not in elevenlabs_voices");
    });
  });

  // TMDEV-121: play and pause are one button whose label follows the audio.
  it("shows pause while the preview plays and play once it pauses or ends", async () => {
    stubFetch();
    const { container } = render(<VoicePreviewButton voiceId="abc123" />);
    const btn = screen.getByTestId("voice-preview-abc123");
    expect(btn.textContent).toBe("▶");

    await act(async () => { fireEvent.click(btn); });
    const audio = container.querySelector("audio")!;
    await act(async () => { fireEvent.play(audio); });
    expect(btn.textContent).toBe("❚❚");
    expect(btn.getAttribute("aria-label")).toBe("Pause the preview");

    await act(async () => { fireEvent.click(btn); });
    await act(async () => { fireEvent.pause(audio); });
    expect(btn.textContent).toBe("▶");

    await act(async () => { fireEvent.play(audio); });
    await act(async () => { fireEvent.ended(audio); });
    expect(btn.textContent).toBe("▶");
  });

  it("a click while playing pauses the audio rather than refetching", async () => {
    stubFetch();
    const { container } = render(<VoicePreviewButton voiceId="abc123" />);
    const btn = screen.getByTestId("voice-preview-abc123");
    await act(async () => { fireEvent.click(btn); });
    const audio = container.querySelector("audio")!;
    Object.defineProperty(audio, "paused", { configurable: true, get: () => false });
    vi.mocked(fetch).mockClear();
    await act(async () => { fireEvent.click(btn); });
    expect(HTMLMediaElement.prototype.pause).toHaveBeenCalled();
    expect(fetch).not.toHaveBeenCalled();
  });

  // The proxy refuses a body that does not say it is JSON (TMDEV-156).
  it("sends the model it was given, and fetches a new sample when the model changes", async () => {
    stubFetch();
    const { rerender } = render(<VoicePreviewButton voiceId="abc123" modelId="eleven_multilingual_v2" />);
    await act(async () => { fireEvent.click(screen.getByTestId("voice-preview-abc123")); });
    expect(fetch).toHaveBeenLastCalledWith("/api/proxy/voices/abc123/preview", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model_id: "eleven_multilingual_v2" }) });

    rerender(<VoicePreviewButton voiceId="abc123" modelId="eleven_v3" />);
    expect(screen.getByTestId("voice-preview-abc123").textContent).toBe("▶");
    await act(async () => { fireEvent.click(screen.getByTestId("voice-preview-abc123")); });
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(fetch).toHaveBeenLastCalledWith("/api/proxy/voices/abc123/preview", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model_id: "eleven_v3" }) });
  });

  it("drops a slow response for a model that is no longer selected", async () => {
    let resolveFirst: (v: unknown) => void = () => {};
    vi.stubGlobal("fetch", vi.fn()
      .mockImplementationOnce(() => new Promise((r) => { resolveFirst = r; }))
      .mockImplementation(() => Promise.resolve({ ok: true, json: async () => ({ path: "/output_videos/voice-previews/new.mp3" }) })));
    const { rerender, container } = render(<VoicePreviewButton voiceId="abc123" modelId="eleven_multilingual_v2" />);
    await act(async () => { fireEvent.click(screen.getByTestId("voice-preview-abc123")); });
    rerender(<VoicePreviewButton voiceId="abc123" modelId="eleven_v3" />);
    await act(async () => {
      resolveFirst({ ok: true, json: async () => ({ path: "/output_videos/voice-previews/old.mp3" }) });
    });
    expect(container.querySelector("audio")).toBeNull();
    expect(screen.getByTestId("voice-preview-abc123").textContent).toBe("▶");
  });

  it("stays on play when the browser blocks autoplay", async () => {
    HTMLMediaElement.prototype.play = vi.fn().mockRejectedValue(new Error("NotAllowedError"));
    stubFetch();
    render(<VoicePreviewButton voiceId="abc123" />);
    await act(async () => { fireEvent.click(screen.getByTestId("voice-preview-abc123")); });
    await waitFor(() => expect(screen.getByTestId("voice-preview-abc123").textContent).toBe("▶"));
  });
});
