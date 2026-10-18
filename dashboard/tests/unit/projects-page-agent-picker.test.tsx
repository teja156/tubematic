/**
 * TMDEV-110: the Projects page with the REAL VideoModal, not a stub.
 *
 * TMDEV-106's live test could not catch its two Projects-page defects — a
 * guessed value submitted as an explicit one, and a value leaking between
 * videos — because it always touched the picker. These tests are the path
 * where nobody does: approving from Projects must leave the dealt agent in
 * place, whether or not GET /agents has answered yet.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/SectionLabel", () => ({
  SectionLabel: ({ label }: { label: string }) => <div>{label}</div>,
}));
vi.mock("@/components/TimeZoneProvider", () => ({
  useTimeZone: () => ({ timeZone: "UTC", label: "UTC", degraded: false }),
}));

import ProjectsPage from "@/app/projects/page";

const PROJECT = {
  id: "proj-1", name: "Domain", description: "d", is_curriculum_seed: 1,
  status: "active", created_at: "2026-01-01T00:00:00Z",
};
const AGENTS = [
  { id: "claude", name: "Claude Code", binary: "claude", run_path: "/w", install_scope: "user",
    models: ["sonnet", "opus"], effort: "high", is_default: true, weight: 1, verified_at: "",
    archived_at: null, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z" },
  { id: "codex", name: "Codex", binary: "codex", run_path: "/w", install_scope: "user",
    models: ["gpt-5"], effort: "high", is_default: false, weight: 1, verified_at: "",
    archived_at: null, created_at: "2026-01-02T00:00:00Z", updated_at: "2026-01-02T00:00:00Z" },
];

function video(status: string, over: Record<string, unknown> = {}) {
  return {
    id: "vid-1", project_id: "proj-1", title: null, topic: "A topic", strategy: "curriculum",
    status, producibility_score: 7, script: status === "SCRIPT_READY" ? "A script" : null,
    voice_id: "", agent_id: "claude", agent_model: "opus", agent_effort: "",
    visual_style: "auto", comments: [], video_version: 1,
    created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z", ...over,
  };
}

/** agents: the list /agents answers with, or "pending" for a request that has
 *  not answered yet. */
function mockApi(v: Record<string, unknown>, agents: unknown[] | "pending") {
  return vi.spyOn(global, "fetch").mockImplementation((url: string | URL | Request) => {
    const u = url.toString();
    const ok = (body: unknown) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) } as Response);
    if (u.endsWith("/agents")) return agents === "pending" ? new Promise(() => {}) : ok(agents);
    if (u.endsWith("/projects")) return ok([PROJECT]);
    if (u.endsWith("/videos")) return ok([v]);
    if (u.includes("/publications")) return ok([]);
    if (u.includes("/logs")) return ok({ records: [] });
    if (u.endsWith("/videos/vid-1")) return ok(v);
    return ok({});
  });
}

async function openVideo() {
  fireEvent.click(await screen.findByText("Domain"));
  fireEvent.click(await screen.findByText("A topic"));
}

function patchBody(fetchSpy: ReturnType<typeof mockApi>) {
  const patch = fetchSpy.mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === "PATCH");
  return patch ? JSON.parse((patch[1] as RequestInit).body as string) : undefined;
}

afterEach(() => vi.restoreAllMocks());

describe("Projects page — approving without touching the agent picker", () => {
  it("fetches /agents, so the modal can offer the live ones", async () => {
    const fetchSpy = mockApi(video("TOPIC_PROPOSED"), AGENTS);
    render(<ProjectsPage />);
    await openVideo();
    const select = (await screen.findByTestId("video-modal-agent-select")) as HTMLSelectElement;
    expect([...select.options].map((o) => o.value)).toEqual(["claude", "codex"]);
    expect(fetchSpy.mock.calls.some(([u]) => String(u).endsWith("/api/proxy/agents"))).toBe(true);
  });

  it.each([["answered", AGENTS], ["pending", "pending"]] as const)(
    "approve-topic leaves the dealt agent in place (/agents %s)", async (_, agents) => {
      const fetchSpy = mockApi(video("TOPIC_PROPOSED"), agents as unknown[] | "pending");
      render(<ProjectsPage />);
      await openVideo();
      if (agents !== "pending") await screen.findByTestId("video-modal-agent-select");
      fireEvent.click(await screen.findByText("Approve Topic"));
      await waitFor(() => expect(patchBody(fetchSpy)).toBeTruthy());
      const body = patchBody(fetchSpy);
      expect(body.status).toBe("TOPIC_APPROVED");
      expect(body).not.toHaveProperty("agent_id");
    });

  it.each([["answered", AGENTS], ["pending", "pending"]] as const)(
    "approve-script sends no agent field at all (/agents %s)", async (_, agents) => {
      const fetchSpy = mockApi(video("SCRIPT_READY"), agents as unknown[] | "pending");
      render(<ProjectsPage />);
      await openVideo();
      if (agents !== "pending") await screen.findByTestId("video-modal-agent-select");
      fireEvent.click(await screen.findByText("Approve Script"));
      await waitFor(() => expect(patchBody(fetchSpy)).toBeTruthy());
      expect(patchBody(fetchSpy)).toEqual(
        { status: "VOICING", onlyIfCurrentStatus: "SCRIPT_READY", voice_id: "" });
    });

  it("a picked agent does reach the PATCH", async () => {
    const fetchSpy = mockApi(video("SCRIPT_READY"), AGENTS);
    render(<ProjectsPage />);
    await openVideo();
    fireEvent.change(await screen.findByTestId("video-modal-agent-select"), { target: { value: "codex" } });
    fireEvent.click(screen.getByText("Approve Script"));
    await waitFor(() => expect(patchBody(fetchSpy)).toBeTruthy());
    expect(patchBody(fetchSpy)).toEqual({
      status: "VOICING", onlyIfCurrentStatus: "SCRIPT_READY", voice_id: "",
      agent_id: "codex", agent_model: "gpt-5",
    });
  });
});
