/**
 * The New Video page (TMDEV-118): a human submits a video without an agent
 * harness. What matters is the POST body — an untouched picker must send the
 * value that means "the default", never a guess:
 *
 *  - agent: no agent_id at all, so the API deals one by weight, exactly as it
 *    does for every other new video;
 *  - model: "" under Automatic (the agent is not known until it is dealt), the
 *    picked agent's default otherwise — pinned, as approving a topic pins it;
 *  - effort: "", which follows the agent's own level.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/VoicePreviewButton", () => ({ VoicePreviewButton: () => null }));

import NewVideoPage from "@/app/new-video/page";
import type { Agent, ScriptProfile } from "@/lib/types";

function agent(over: Partial<Agent>): Agent {
  return {
    id: "claude", name: "Claude Code", binary: "/usr/local/bin/claude", run_path: "/home/u/.a",
    install_scope: "user", models: ["sonnet", "opus"], effort: "high", is_default: true,
    weight: 1, verified_at: "2026-01-01T00:00:00Z", archived_at: null,
    created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
    ...over,
  } as Agent;
}

const AGENTS: Agent[] = [
  agent({}),
  agent({ id: "codex", name: "Codex", models: ["gpt-5"], effort: "medium", is_default: false }),
  agent({ id: "old", name: "Old", archived_at: "2026-02-01T00:00:00Z", is_default: false }),
];

function profile(over: Partial<ScriptProfile>): ScriptProfile {
  return {
    id: "p1", name: "My voice", status: "READY", source_urls: [], error: "", attempt_count: 1,
    archived: false, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
    ...over,
  };
}

function ok(body: unknown, status = 200) {
  return Promise.resolve({
    ok: status < 400, status, json: () => Promise.resolve(body),
  } as Response);
}

function mockApi({
  agents = AGENTS as Agent[] | "fail",
  openaiKey = "",
  projects = [] as unknown[],
  post = { status: 201, body: { id: "v1", title: "T", status: "TOPIC_APPROVED" } as unknown },
} = {}) {
  return vi.spyOn(global, "fetch").mockImplementation((url, init) => {
    const u = url.toString();
    if ((init?.method ?? "GET").toUpperCase() === "POST") return ok(post.body, post.status);
    if (u.endsWith("/agents")) return agents === "fail" ? Promise.reject(new Error("x")) : ok(agents);
    if (u.endsWith("/settings")) {
      return ok({
        elevenlabs_voices: [{ name: "Narrator", voice_id: "n1", model_id: "eleven_multilingual_v2" }, { name: "Other", voice_id: "o2", model_id: "eleven_multilingual_v2" }],
        elevenlabs_voice_id: "n1",
        openai_api_key: openaiKey,
      });
    }
    if (u.endsWith("/projects")) return ok(projects);
    if (u.endsWith("/script-profiles")) {
      return ok([profile({}), profile({ id: "p2", name: "Building", status: "GENERATING" })]);
    }
    return ok({});
  });
}

function posted(spy: ReturnType<typeof mockApi>) {
  const call = spy.mock.calls.find(([, init]) => init?.method === "POST");
  if (!call) throw new Error("no POST was made");
  expect(call[0].toString()).toBe("/api/proxy/videos/manual");
  return JSON.parse(call[1]!.body as string);
}

function fill(title = "How DNS resolves a name", topic = "Walk a DNS lookup end to end") {
  fireEvent.change(screen.getByLabelText("Title"), { target: { value: title } });
  fireEvent.change(screen.getByLabelText("Topic"), { target: { value: topic } });
}

async function ready() {
  render(<NewVideoPage />);
  await waitFor(() => expect(screen.getByRole("option", { name: "Codex" })).toBeTruthy());
}

describe("NewVideoPage", () => {
  afterEach(() => vi.restoreAllMocks());

  // TMDEV-121: "Default" is what the API will actually seed — the manual
  // domain's own voice when it has one still in the roster, else the install's.
  it("names the install default voice when the manual domain has none", async () => {
    mockApi();
    await ready();
    await waitFor(() => expect(screen.getByRole("option", { name: "Default (Narrator)" })).toBeTruthy());
  });

  it("names the manual domain's default voice when it has one", async () => {
    mockApi({ projects: [{ id: "manual", name: "Manual Videos", default_voice_id: "o2" }] });
    await ready();
    await waitFor(() => expect(screen.getByRole("option", { name: "Default (Other)" })).toBeTruthy());
  });

  it("ignores a manual-domain voice that has left the roster, as the API does", async () => {
    mockApi({ projects: [{ id: "manual", name: "Manual Videos", default_voice_id: "gone" }] });
    await ready();
    await waitFor(() => expect(screen.getByRole("option", { name: "Default (Narrator)" })).toBeTruthy());
  });

  it("sends the defaults for untouched pickers, approved", async () => {
    const spy = mockApi();
    await ready();
    fill();
    fireEvent.click(screen.getByRole("button", { name: /submit/i }));
    await waitFor(() => expect(posted(spy)).toEqual({
      title: "How DNS resolves a name",
      topic: "Walk a DNS lookup end to end",
      approve: true,
      agent_model: "",
      agent_effort: "",
      script_profile_id: "",
      visual_style: "auto",
      voice_id: "",
    }));
  });

  it("sends the picked agent, and pins its default model when the model is untouched", async () => {
    const spy = mockApi();
    await ready();
    fill();
    fireEvent.change(screen.getByLabelText("Agent"), { target: { value: "codex" } });
    fireEvent.click(screen.getByRole("button", { name: /submit/i }));
    await waitFor(() => {
      const body = posted(spy);
      expect(body.agent_id).toBe("codex");
      expect(body.agent_model).toBe("gpt-5");
    });
  });

  it("sends every explicit pick", async () => {
    const spy = mockApi({ openaiKey: "••••" });
    await ready();
    fill();
    fireEvent.change(screen.getByLabelText("Agent"), { target: { value: "claude" } });
    fireEvent.change(screen.getByLabelText("Model"), { target: { value: "opus" } });
    fireEvent.change(screen.getByLabelText("Effort"), { target: { value: "max" } });
    fireEvent.change(screen.getByLabelText("Script profile"), { target: { value: "p1" } });
    fireEvent.change(screen.getByLabelText("Visual style"), { target: { value: "illustrated" } });
    fireEvent.change(screen.getByLabelText("Voice"), { target: { value: "o2" } });
    fireEvent.click(screen.getByLabelText(/automatically approve topic/i));
    fireEvent.click(screen.getByRole("button", { name: /submit/i }));
    await waitFor(() => expect(posted(spy)).toEqual({
      title: "How DNS resolves a name",
      topic: "Walk a DNS lookup end to end",
      approve: false,
      agent_id: "claude",
      agent_model: "opus",
      agent_effort: "max",
      script_profile_id: "p1",
      visual_style: "illustrated",
      voice_id: "o2",
    }));
  });

  it("disables the model picker under Automatic", async () => {
    mockApi();
    await ready();
    expect((screen.getByLabelText("Model") as HTMLSelectElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Agent"), { target: { value: "claude" } });
    expect((screen.getByLabelText("Model") as HTMLSelectElement).disabled).toBe(false);
  });

  it("offers only live agents and READY profiles", async () => {
    mockApi();
    await ready();
    expect(screen.queryByRole("option", { name: "Old" })).toBeNull();
    expect(screen.getByRole("option", { name: "My voice" })).toBeTruthy();
    expect(screen.queryByRole("option", { name: "Building" })).toBeNull();
  });

  it("disables Illustrated when no OpenAI key is stored", async () => {
    mockApi({ openaiKey: "" });
    await ready();
    const option = screen.getByRole("option", { name: /illustrated/i }) as HTMLOptionElement;
    expect(option.disabled).toBe(true);
  });

  it("disables the agent picker when the agent list cannot be loaded", async () => {
    mockApi({ agents: "fail" });
    render(<NewVideoPage />);
    await waitFor(() => expect(screen.getByText(/agent list not loaded/i)).toBeTruthy());
    expect((screen.getByLabelText("Agent") as HTMLSelectElement).disabled).toBe(true);
  });

  it("will not submit without a title and a topic, or with a title over 70", async () => {
    mockApi();
    await ready();
    const submit = screen.getByRole("button", { name: /submit/i }) as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
    fill("x".repeat(70));
    expect(submit.disabled).toBe(false);
    expect(screen.getByText(/^70\/70/)).toBeTruthy();
    fill("x".repeat(71));
    expect(submit.disabled).toBe(true);
    fill("A title", "   ");
    expect(submit.disabled).toBe(true);
  });

  it("counts the title in code points, as the API does", async () => {
    mockApi();
    await ready();
    // 69 letters + one emoji: 70 code points (the API's len()), 71 UTF-16 units.
    fill("x".repeat(69) + "🚀");
    expect(screen.getByText(/^70\/70/)).toBeTruthy();
    expect((screen.getByRole("button", { name: /submit/i }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("shows the API's refusal and keeps what was typed", async () => {
    mockApi({ post: { status: 400, body: { error: "agent_id 'ghost' is not an installed agent" } } });
    await ready();
    fill();
    fireEvent.click(screen.getByRole("button", { name: /submit/i }));
    await waitFor(() =>
      expect(screen.getByTestId("new-video-error").textContent).toContain("not an installed agent"));
    expect((screen.getByLabelText("Title") as HTMLInputElement).value).toBe("How DNS resolves a name");
  });

  it("confirms the submission and clears the form", async () => {
    mockApi({ post: { status: 201, body: { id: "v1", title: "How DNS resolves a name", status: "TOPIC_APPROVED" } } });
    await ready();
    fill();
    fireEvent.click(screen.getByRole("button", { name: /submit/i }));
    await waitFor(() =>
      expect(screen.getByTestId("new-video-success").textContent).toContain("TOPIC_APPROVED"));
    expect((screen.getByLabelText("Title") as HTMLInputElement).value).toBe("");
    expect((screen.getByLabelText("Topic") as HTMLTextAreaElement).value).toBe("");
  });
});
