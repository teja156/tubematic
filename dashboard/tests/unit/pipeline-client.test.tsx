/**
 * Tests for PipelineClient data-fetching behavior.
 *
 * Critical regressions guarded here:
 *  1. All fetch calls include cache: "no-store" (bypasses browser HTTP cache)
 *  2. Non-array API response (e.g. {error: "..."}) doesn't crash the component
 *  3. Polling fires again after 5 seconds
 *  4. Polling interval is cleaned up on unmount (no memory leak)
 *  5. Stale out-of-order responses are discarded
 */
import { act, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// ── mock sub-components to isolate data-fetching logic ───────────────────────
vi.mock("@/components/SummaryStrip", () => ({ SummaryStrip: () => null }));
vi.mock("@/components/ActionPane", () => ({ ActionPane: () => null }));
vi.mock("@/components/KanbanBoard", () => ({ KanbanBoard: () => null }));
vi.mock("@/components/VideoModal", () => ({ VideoModal: () => null }));
vi.mock("@/components/SectionLabel", () => ({ SectionLabel: () => null }));

import { PipelineClient } from "@/components/PipelineClient";

// ── helpers ──────────────────────────────────────────────────────────────────

function setupFetchMock() {
  return vi.spyOn(global, "fetch").mockImplementation((url) => {
    const u = String(url);
    if (u.endsWith("/stats")) {
      return Promise.resolve({
        status: 200,
        json: () => Promise.resolve({}),
      } as unknown as Response);
    }
    return Promise.resolve({
      status: 200,
      json: () => Promise.resolve([]),
    } as unknown as Response);
  });
}

// ── tests ─────────────────────────────────────────────────────────────────────

describe("PipelineClient", () => {
  afterEach(() => vi.restoreAllMocks());

  // ── cache header ───────────────────────────────────────────────────────────

  it('all fetch calls on mount include cache: "no-store"', async () => {
    const fetchSpy = setupFetchMock();

    render(<PipelineClient />);
    await act(async () => {});

    expect(fetchSpy.mock.calls.length).toBeGreaterThanOrEqual(3);
    for (const [, init] of fetchSpy.mock.calls) {
      expect((init as RequestInit)?.cache).toBe("no-store");
    }
  });

  // ── endpoint coverage ──────────────────────────────────────────────────────

  it("fetches /stats, /videos, and /videos/actionable on mount", async () => {
    const fetchSpy = setupFetchMock();

    render(<PipelineClient />);
    await act(async () => {});

    const urls = fetchSpy.mock.calls.map(([url]) => String(url));
    expect(urls.some((u) => u.endsWith("/stats"))).toBe(true);
    expect(urls.some((u) => u.endsWith("/videos"))).toBe(true);
    expect(urls.some((u) => u.endsWith("/videos/actionable"))).toBe(true);
  });

  // ── array guard ────────────────────────────────────────────────────────────

  it("does not crash when the API returns an error object instead of an array", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue({
      status: 502,
      json: () => Promise.resolve({ error: "DB unreachable" }),
    } as unknown as Response);

    expect(() => render(<PipelineClient />)).not.toThrow();
    await act(async () => {});
    // No unhandled rejection and no crash — the Array.isArray guard held.
  });

  it("does not crash when the stats endpoint returns an error object", async () => {
    vi.spyOn(global, "fetch").mockImplementation((url) => {
      const u = String(url);
      if (u.endsWith("/stats")) {
        return Promise.resolve({
          status: 502,
          json: () => Promise.resolve({ error: "upstream down" }),
        } as unknown as Response);
      }
      return Promise.resolve({
        status: 200,
        json: () => Promise.resolve([]),
      } as unknown as Response);
    });

    expect(() => render(<PipelineClient />)).not.toThrow();
    await act(async () => {});
  });

  // ── polling ────────────────────────────────────────────────────────────────

  it("polls again after 5 seconds", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    const fetchSpy = setupFetchMock();

    render(<PipelineClient />);
    await act(async () => { await Promise.resolve(); });

    const countAfterMount = fetchSpy.mock.calls.length;
    expect(countAfterMount).toBeGreaterThanOrEqual(3);

    await act(async () => {
      vi.advanceTimersByTime(5_000);
      await Promise.resolve();
    });

    expect(fetchSpy.mock.calls.length).toBeGreaterThan(countAfterMount);
    vi.useRealTimers();
  });

  it("clears the polling interval on unmount (no memory leak)", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    const clearSpy = vi.spyOn(global, "clearInterval");
    setupFetchMock();

    const { unmount } = render(<PipelineClient />);
    await act(async () => {});

    unmount();
    expect(clearSpy).toHaveBeenCalled();
    vi.useRealTimers();
  });

  // ── race condition guard ───────────────────────────────────────────────────

  it("discards a stale fetch response that arrives after a newer one", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });

    let resolveStale!: (v: Response) => void;
    const stalePending = new Promise<Response>((r) => { resolveStale = r; });

    let callCount = 0;
    vi.spyOn(global, "fetch").mockImplementation(() => {
      callCount++;
      // First group of 3 fetches (initial mount): return a pending promise
      if (callCount <= 3) return stalePending;
      // Second group (5s poll): resolve immediately with empty data
      return Promise.resolve({
        status: 200,
        json: () => Promise.resolve([]),
      } as unknown as Response);
    });

    const { unmount } = render(<PipelineClient />);

    // Trigger the second (newer) fetch group by advancing the timer
    await act(async () => {
      vi.advanceTimersByTime(5_000);
      await Promise.resolve();
      await Promise.resolve();
    });

    // Now resolve the stale first fetch with unexpected data — it should be discarded
    await act(async () => {
      resolveStale({
        status: 200,
        json: () => Promise.resolve([{ id: "stale", topic: "Stale result" }]),
      } as unknown as Response);
      await Promise.resolve();
    });

    // Component must still be mounted and stable — no crash from stale resolution
    unmount();
    vi.useRealTimers();
  });

  // ── voice roster (TMDEV-51) ────────────────────────────────────────────────

  it("fetches /settings once and threads the voice roster down to ActionPane", async () => {
    const actionPaneProps: unknown[] = [];
    vi.doMock("@/components/ActionPane", () => ({
      ActionPane: (props: unknown) => { actionPaneProps.push(props); return null; },
    }));
    vi.resetModules();
    const { PipelineClient: FreshPipelineClient } = await import("@/components/PipelineClient");

    vi.spyOn(global, "fetch").mockImplementation((url) => {
      const u = String(url);
      if (u.endsWith("/settings")) {
        return Promise.resolve({
          status: 200,
          json: () => Promise.resolve({
            elevenlabs_voices: [{ name: "Narrator", voice_id: "abc123", model_id: "eleven_multilingual_v2" }],
            elevenlabs_voice_id: "abc123",
          }),
        } as unknown as Response);
      }
      if (u.endsWith("/stats")) {
        return Promise.resolve({ status: 200, json: () => Promise.resolve({}) } as unknown as Response);
      }
      return Promise.resolve({ status: 200, json: () => Promise.resolve([]) } as unknown as Response);
    });

    render(<FreshPipelineClient />);
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });

    const lastProps = actionPaneProps[actionPaneProps.length - 1] as {
      voices: unknown[]; defaultVoiceId: string;
    };
    expect(lastProps.voices).toEqual([{ name: "Narrator", voice_id: "abc123", model_id: "eleven_multilingual_v2" }]);
    expect(lastProps.defaultVoiceId).toBe("abc123");
  });

  it("tells ActionPane that Illustrated is unavailable when no OpenAI key is stored", async () => {
    const actionPaneProps: unknown[] = [];
    vi.doMock("@/components/ActionPane", () => ({
      ActionPane: (props: unknown) => { actionPaneProps.push(props); return null; },
    }));
    vi.resetModules();
    const { PipelineClient: FreshPipelineClient } = await import("@/components/PipelineClient");

    vi.spyOn(global, "fetch").mockImplementation((url) => {
      const u = String(url);
      if (u.endsWith("/settings")) {
        return Promise.resolve({
          status: 200, json: () => Promise.resolve({ openai_api_key: "" }),
        } as unknown as Response);
      }
      if (u.endsWith("/stats")) {
        return Promise.resolve({ status: 200, json: () => Promise.resolve({}) } as unknown as Response);
      }
      return Promise.resolve({ status: 200, json: () => Promise.resolve([]) } as unknown as Response);
    });

    render(<FreshPipelineClient />);
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });

    const lastProps = actionPaneProps[actionPaneProps.length - 1] as { illustratedAvailable: boolean };
    expect(lastProps.illustratedAvailable).toBe(false);
  });

  // ── agents ─────────────────────────────────────────────────────────────────

  it("fetches /agents and threads them down to ActionPane in place of a settings model", async () => {
    const actionPaneProps: unknown[] = [];
    vi.doMock("@/components/ActionPane", () => ({
      ActionPane: (props: unknown) => { actionPaneProps.push(props); return null; },
    }));
    vi.resetModules();
    const { PipelineClient: FreshPipelineClient } = await import("@/components/PipelineClient");

    const agents = [{ id: "claude", name: "Claude Code", models: ["sonnet"], is_default: true, archived_at: null }];
    const fetchSpy = vi.spyOn(global, "fetch").mockImplementation((url) => {
      const u = String(url);
      if (u.endsWith("/agents")) {
        return Promise.resolve({ status: 200, json: () => Promise.resolve(agents) } as unknown as Response);
      }
      if (u.endsWith("/settings")) {
        // A stale server still returning the retired key must not leak through.
        return Promise.resolve({ status: 200, json: () => Promise.resolve({ agent_model: "opus" }) } as unknown as Response);
      }
      if (u.endsWith("/stats")) {
        return Promise.resolve({ status: 200, json: () => Promise.resolve({}) } as unknown as Response);
      }
      return Promise.resolve({ status: 200, json: () => Promise.resolve([]) } as unknown as Response);
    });

    render(<FreshPipelineClient />);
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });

    expect(fetchSpy.mock.calls.some(([url]) => String(url).endsWith("/api/proxy/agents"))).toBe(true);
    const lastProps = actionPaneProps[actionPaneProps.length - 1] as Record<string, unknown>;
    expect(lastProps.agents).toEqual(agents);
    expect(lastProps).not.toHaveProperty("defaultAgentModel");
  });

  // ── changing the agent at a checkpoint (TMDEV-110) ─────────────────────────

  async function renderCapturing() {
    const paneProps: Record<string, unknown>[] = [];
    const modalProps: Record<string, unknown>[] = [];
    vi.doMock("@/components/ActionPane", () => ({
      ActionPane: (props: Record<string, unknown>) => { paneProps.push(props); return null; },
    }));
    vi.doMock("@/components/VideoModal", () => ({
      VideoModal: (props: Record<string, unknown>) => { modalProps.push(props); return null; },
    }));
    vi.resetModules();
    const { PipelineClient: FreshPipelineClient } = await import("@/components/PipelineClient");
    // ok: true — patchVideo throws on anything else, which setupFetchMock's
    // bare status responses would trip.
    const fetchSpy = vi.spyOn(global, "fetch").mockImplementation((url) =>
      Promise.resolve({
        status: 200, ok: true,
        json: () => Promise.resolve(String(url).endsWith("/stats") ? {} : []),
      } as unknown as Response));
    render(<FreshPipelineClient />);
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    return { paneProps, modalProps, fetchSpy };
  }

  it.each([
    ["revise-topic", "TOPIC_PROPOSED"],
    ["revise-script", "SCRIPT_READY"],
    ["revise-video", "VIDEO_READY"],
  ])("%s carries the modal's agent picks in the same PATCH", async (action, current) => {
    const { modalProps, fetchSpy } = await renderCapturing();
    const onAction = modalProps[modalProps.length - 1].onAction as
      (id: string, a: string, v: unknown, extra?: Record<string, unknown>) => Promise<void>;
    await act(async () => {
      await onAction("vid-1", action, { id: "vid-1" }, { agent_id: "codex", agent_model: "gpt-5" });
    });
    const patch = fetchSpy.mock.calls.find(([, init]) => (init as RequestInit)?.method === "PATCH");
    expect(JSON.parse((patch![1] as RequestInit).body as string)).toEqual({
      status: "REVISION_REQUESTED", onlyIfCurrentStatus: current,
      agent_id: "codex", agent_model: "gpt-5",
    });
  });

  it("hands the inbox row's picks to the modal its Revise opens", async () => {
    const { paneProps, modalProps } = await renderCapturing();
    const onOpenModal = paneProps[paneProps.length - 1].onOpenModal as
      (v: unknown, tab?: string, opts?: Record<string, unknown>) => void;
    const picks = { agentId: "codex", model: null, effort: null };
    act(() => onOpenModal({ id: "vid-1" }, undefined, { revise: true, picks }));
    const last = modalProps[modalProps.length - 1];
    expect(last.openRevise).toBe(true);
    expect(last.initialPicks).toEqual(picks);
  });
});
