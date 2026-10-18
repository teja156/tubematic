/**
 * The video modal's cost breakdown (TMDEV-107).
 *
 * What this guards: an agent session shared by a batch is shown as this
 * video's even share with the whole session beside it, and the total adds the
 * share — never the whole session, which would count it once per video;
 * ElevenLabs is credits and never dollars; unpriced calls are counted, never
 * shown as $0; a video from before cost tracking says so instead of "$0.00";
 * and the API-list-price disclaimer is always present.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, afterEach } from "vitest";
import { CostBreakdown } from "@/components/CostBreakdown";
import type { VideoCosts } from "@/lib/types";

vi.mock("@/components/TimeZoneProvider", () => ({
  useTimeZone: () => ({ timeZone: "UTC", label: "UTC" }),
}));

const COSTS: VideoCosts = {
  has_usage: true,
  lines: [
    { service: "elevenlabs", model: "eleven_multilingual_v2", operation: "voice", calls: 1,
      cost_usd: null, credits: 1240, unpriced_calls: 0, estimated: false },
    { service: "gemini", model: "gemini-2.5-flash", operation: "ai_review", calls: 2,
      cost_usd: 0.04, credits: 0, unpriced_calls: 0, estimated: false },
    { service: "gemini", model: "gemini-9-flash", operation: "image", calls: 1,
      cost_usd: null, credits: 0, unpriced_calls: 1, estimated: false },
  ],
  agent: {
    models: ["claude-sonnet-5"], share_usd: 0.13, session_total_usd: 0.23, shared: true,
    estimated: false,
    sessions: [
      { session_id: "s1", created_at: "2026-09-23T14:02:00Z", stage: "TOPIC_APPROVED",
        operation: "agent_pipeline", batch_size: 3, models: ["claude-sonnet-5"],
        total_usd: 0.15, share_usd: 0.05, unpriced: false, estimated: false },
      { session_id: "s2", created_at: "2026-09-23T14:42:00Z", stage: "VOICE_READY",
        operation: "agent_pipeline", batch_size: 1, models: ["claude-sonnet-5"],
        total_usd: 0.08, share_usd: 0.08, unpriced: false, estimated: false },
    ],
  },
  total_usd: 0.17,
  credits: 1240,
  unpriced_calls: 1,
};

function stubCosts(body: unknown, ok = true) {
  const fn = vi.fn().mockImplementation(() => Promise.resolve({ ok, status: ok ? 200 : 500,
                                                                  json: async () => body }));
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("CostBreakdown", () => {
  it("fetches this video's costs", async () => {
    const fn = stubCosts(COSTS);
    render(<CostBreakdown videoId="vid-1" />);
    await screen.findByTestId("cost-total");
    expect(fn).toHaveBeenCalledWith("/api/proxy/videos/vid-1/costs");
  });

  it("shows ElevenLabs as credits, never dollars", async () => {
    stubCosts(COSTS);
    render(<CostBreakdown videoId="vid-1" />);
    const line = await screen.findByTestId("cost-line-elevenlabs-voice");
    expect(line).toHaveTextContent("– · 1,240 credits");
    expect(line).not.toHaveTextContent("$");
  });

  it("shows a shared session as this video's share of the whole", async () => {
    stubCosts(COSTS);
    render(<CostBreakdown videoId="vid-1" />);
    const agent = await screen.findByTestId("cost-agent-value");
    expect(agent).toHaveTextContent("≈ $0.13");
    expect(agent).toHaveTextContent("of $0.23 · 2 sessions");
  });

  it("shows each agent model whole, on its own line", async () => {
    // Joined into one string, the sidebar wrapped it after a hyphen, and the
    // dangling "claude-" read as part of the value column beside it.
    const models = ["claude-opus-5-5", "gpt-5.6-sol"];
    stubCosts({ ...COSTS, agent: { ...COSTS.agent!, models } });
    render(<CostBreakdown videoId="vid-1" />);
    await screen.findByTestId("cost-agent");
    const lines = screen.getAllByTestId("cost-agent-model");
    expect(lines.map((l) => l.textContent)).toEqual(models);
    for (const line of lines) expect(line).toHaveStyle({ whiteSpace: "nowrap" });
    expect(screen.getByTestId("cost-agent")).not.toHaveTextContent("claude-opus-5-5, gpt");
  });

  it("expands into one row per session, labelled by stage, with the split", async () => {
    stubCosts(COSTS);
    render(<CostBreakdown videoId="vid-1" />);
    fireEvent.click(await screen.findByTestId("cost-agent-toggle"));
    const sessions = screen.getByTestId("cost-agent-sessions");
    expect(sessions).toHaveTextContent("Script writing");
    expect(sessions).toHaveTextContent("$0.15 ÷ 3 → $0.05");
    expect(sessions).toHaveTextContent("Scene writing");
    expect(sessions).toHaveTextContent("even split");
  });

  it("labels a session that started at VOICING as voicing only", async () => {
    // The poller runs one stage per session, so a session that starts at
    // VOICING stops at VOICE_READY and scene writing is a session of its own.
    const voicing = { ...COSTS.agent!.sessions[1], stage: "VOICING" };
    stubCosts({ ...COSTS, agent: { ...COSTS.agent!, sessions: [voicing] } });
    render(<CostBreakdown videoId="vid-1" />);
    fireEvent.click(await screen.findByTestId("cost-agent-toggle"));
    const sessions = screen.getByTestId("cost-agent-sessions");
    expect(sessions).toHaveTextContent("Voicing");
    expect(sessions).not.toHaveTextContent("scene writing");
  });

  it("labels a pre-upgrade voicing session as voicing and scene writing", async () => {
    // The old poller carried a voicing session straight on into scene writing;
    // migration 0007 relabels those rows so their spend is not shown as voicing only.
    const legacy = { ...COSTS.agent!.sessions[1], stage: "VOICING_WITH_SCENES" };
    stubCosts({ ...COSTS, agent: { ...COSTS.agent!, sessions: [legacy] } });
    render(<CostBreakdown videoId="vid-1" />);
    fireEvent.click(await screen.findByTestId("cost-agent-toggle"));
    expect(screen.getByTestId("cost-agent-sessions")).toHaveTextContent("Voicing & scene writing");
  });

  it("counts unpriced calls instead of showing them as $0", async () => {
    stubCosts(COSTS);
    render(<CostBreakdown videoId="vid-1" />);
    expect(await screen.findByTestId("cost-line-gemini-image")).toHaveTextContent("unpriced");
    expect(screen.getByTestId("cost-total-extras")).toHaveTextContent("+ 1 unpriced call");
    expect(screen.getByTestId("cost-total")).toHaveTextContent("≈ $0.17");
  });

  it("says a video from before cost tracking has no usage, not $0.00", async () => {
    stubCosts({ has_usage: false, lines: [], agent: null, total_usd: 0, credits: 0,
                unpriced_calls: 0 });
    render(<CostBreakdown videoId="vid-1" />);
    expect(await screen.findByTestId("cost-none")).toHaveTextContent("No usage recorded");
    expect(screen.queryByTestId("cost-total")).toBeNull();
  });

  it("always carries the API list price disclaimer", async () => {
    stubCosts(COSTS);
    render(<CostBreakdown videoId="vid-1" />);
    expect(screen.getByTestId("cost-disclaimer")).toHaveTextContent("API list prices");
    expect(screen.getByTestId("cost-disclaimer")).toHaveTextContent("subscriptions");
  });

  it("reports a failed or malformed response rather than rendering nonsense", async () => {
    stubCosts([], true);
    render(<CostBreakdown videoId="vid-1" />);
    await waitFor(() => expect(screen.getByTestId("cost-error")).toBeInTheDocument());
  });
});
