/**
 * Tests for ActionPane button-set selection logic.
 *
 * The ActionPane is the human-checkpoint inbox. The set of buttons it renders
 * depends on the video's status — wrong buttons at a checkpoint could let a
 * video skip a stage or expose the wrong actions. These tests lock that mapping.
 *
 * Critical regressions guarded here:
 *  1. TOPIC_PROPOSED  → Approve + Reject + Revise buttons
 *  2. SCRIPT_READY    → Read + Approve + Revise buttons
 *  3. VIDEO_READY     → Watch + Approve + Revise buttons
 *  4. Empty list      → "INBOX ZERO" message, no buttons
 *  5. Clicking Approve/Reject calls onAction with the correct (videoId, action, video) triple
 *  6. Clicking Revise never calls onAction directly — a revision requires a mandatory
 *     comment, which only the VideoModal's ReviseDialog collects. Every Revise button
 *     opens the modal straight into that dialog (onOpenModal with { revise: true }),
 *     since the Comments tab no longer has a compose box to land on.
 */
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ActionPane } from "@/components/ActionPane";
import type { Agent, Video, VideoStatus } from "@/lib/types";

// Fixed to America/New_York so the date-rendering test below has a
// deterministic, non-UTC expected value.
vi.mock("@/components/TimeZoneProvider", () => ({
  useTimeZone: () => ({ timeZone: "America/New_York", label: "EDT (UTC-04:00)", degraded: false }),
}));

// ── helpers ───────────────────────────────────────────────────────────────────

function makeVideo(status: VideoStatus): Video {
  return {
    id: `vid-${status}`,
    project_id: null,
    title: null,
    topic: `Test topic (${status})`,
    strategy: "curriculum",
    producibility_score: 5,
    status,
    script: null,
    voice_file_path: null,
    timeline_path: null,
    scene_config_path: null,
    video_path: null,
    video_version: 1,
    gemini_feedback: null,
    youtube_url: null,
    voice_id: "",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

// Every existing test below renders with an empty roster — the picker is
// only exercised by the dedicated "voice picker" tests further down.
const NO_VOICES = { voices: [], defaultVoiceId: "" };

// ── tests ─────────────────────────────────────────────────────────────────────

describe("ActionPane", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows Approve, Reject, and Revise for TOPIC_PROPOSED", () => {
    render(
      <ActionPane videos={[makeVideo("TOPIC_PROPOSED")]} onAction={() => {}} onOpenModal={() => {}} {...NO_VOICES} />,
    );
    expect(screen.getByRole("button", { name: "Approve" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Reject" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Revise" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Read" })).toBeNull();
  });

  it("shows Read, Approve, and Revise for SCRIPT_READY", () => {
    render(
      <ActionPane videos={[makeVideo("SCRIPT_READY")]} onAction={() => {}} onOpenModal={() => {}} {...NO_VOICES} />,
    );
    expect(screen.getByRole("button", { name: "Read" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Approve" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Revise" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Reject" })).toBeNull();
  });

  it("shows Watch, Approve, and Revise for VIDEO_READY", () => {
    render(
      <ActionPane videos={[makeVideo("VIDEO_READY")]} onAction={() => {}} onOpenModal={() => {}} {...NO_VOICES} />,
    );
    expect(screen.getByRole("button", { name: "Watch" })).toBeTruthy();
    // Renamed from "Publish" by TMDEV-83: this button never published, it
    // approved, and real publishing now exists at the status it moves to.
    // It shares the "Approve" label with the earlier checkpoints, which is
    // why the old "no Approve button here" assertion below became a Reject
    // one — the two are never on screen together, and Reject is what actually
    // distinguishes the topic checkpoint.
    expect(screen.getByRole("button", { name: "Approve" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Revise" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Reject" })).toBeNull();
  });

  it("renders updated_at in the host timezone, not UTC", () => {
    render(
      <ActionPane videos={[makeVideo("TOPIC_PROPOSED")]} onAction={() => {}} onOpenModal={() => {}} {...NO_VOICES} />,
    );
    // updated_at is 2026-01-01T00:00:00Z — a day earlier in America/New_York.
    expect(screen.getByTestId("action-pane").textContent).toContain("Dec 31");
  });

  it("shows INBOX ZERO message when there are no actionable videos", () => {
    render(<ActionPane videos={[]} onAction={() => {}} onOpenModal={() => {}} {...NO_VOICES} />);
    expect(screen.getByTestId("action-pane").textContent).toContain("INBOX ZERO");
  });

  it("calls onAction with (id, action, video, {script_profile_id}) when Approve is clicked", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout"] });
    const onAction = vi.fn();
    const video = makeVideo("TOPIC_PROPOSED");

    render(<ActionPane videos={[video]} onAction={onAction} onOpenModal={() => {}} {...NO_VOICES} />);
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));

    // "" is a real value for both, not an absence: no profile means the
    // generic style, and no model means the install default.
    expect(onAction).toHaveBeenCalledWith(video.id, "approve-topic", video,
      { script_profile_id: "", agent_model: "", agent_effort: "", visual_style: "auto" });

    await act(async () => { vi.advanceTimersByTime(600); });
    vi.useRealTimers();
  });

  it("calls onAction with 'reject-topic' when Reject is clicked", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout"] });
    const onAction = vi.fn();
    const video = makeVideo("TOPIC_PROPOSED");

    render(<ActionPane videos={[video]} onAction={onAction} onOpenModal={() => {}} {...NO_VOICES} />);
    fireEvent.click(screen.getByRole("button", { name: "Reject" }));

    expect(onAction).toHaveBeenCalledWith(video.id, "reject-topic", video);

    await act(async () => { vi.advanceTimersByTime(600); });
    vi.useRealTimers();
  });

  // Every checkpoint opens the modal straight into Request Revision. The tab
  // behind the dialog is what the human sees if they cancel, so it must be the
  // thing under review: the modal's default already gives Topic and Script, but
  // a rendered video also has a script and the default prefers Script, so
  // VIDEO_READY names the Video tab explicitly.
  it.each([
    ["TOPIC_PROPOSED", undefined],
    ["SCRIPT_READY", undefined],
    ["VIDEO_READY", "video"],
  ] as const)(
    "Revise on %s opens the modal straight into Request Revision (tab: %s), never onAction",
    (status, tab) => {
      const onAction = vi.fn();
      const onOpenModal = vi.fn();
      const video = makeVideo(status);

      render(<ActionPane videos={[video]} onAction={onAction} onOpenModal={onOpenModal} {...NO_VOICES} />);
      fireEvent.click(screen.getByRole("button", { name: "Revise" }));

      expect(onOpenModal).toHaveBeenCalledWith(video, tab, { revise: true });
      expect(onAction).not.toHaveBeenCalled();
    },
  );

  // ── Voice picker (TMDEV-51) ──────────────────────────────────────────────

  const VOICES = [
    { name: "Narrator", voice_id: "abc123", model_id: "eleven_multilingual_v2" },
    { name: "Energetic", voice_id: "def456", model_id: "eleven_multilingual_v2" },
  ];

  it("shows no voice select when the roster is empty", () => {
    const video = makeVideo("SCRIPT_READY");
    render(<ActionPane videos={[video]} onAction={() => {}} onOpenModal={() => {}} {...NO_VOICES} />);
    expect(screen.queryByTestId(`voice-select-${video.id}`)).toBeNull();
  });

  it("shows a voice select pre-selected to the install default when the video has no voice_id", () => {
    const video = makeVideo("SCRIPT_READY");
    render(
      <ActionPane videos={[video]} onAction={() => {}} onOpenModal={() => {}}
        voices={VOICES} defaultVoiceId="def456" />,
    );
    const select = screen.getByTestId(`voice-select-${video.id}`) as HTMLSelectElement;
    expect(select.value).toBe("def456");
  });

  it("pre-selects the video's own voice_id over the install default", () => {
    const video = { ...makeVideo("SCRIPT_READY"), voice_id: "abc123" };
    render(
      <ActionPane videos={[video]} onAction={() => {}} onOpenModal={() => {}}
        voices={VOICES} defaultVoiceId="def456" />,
    );
    const select = screen.getByTestId(`voice-select-${video.id}`) as HTMLSelectElement;
    expect(select.value).toBe("abc123");
  });

  it("Approve on SCRIPT_READY sends the selected voice_id as the fourth onAction argument", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout"] });
    const onAction = vi.fn();
    const video = makeVideo("SCRIPT_READY");

    render(
      <ActionPane videos={[video]} onAction={onAction} onOpenModal={() => {}}
        voices={VOICES} defaultVoiceId="abc123" />,
    );
    fireEvent.change(screen.getByTestId(`voice-select-${video.id}`), { target: { value: "def456" } });
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));

    expect(onAction).toHaveBeenCalledWith(video.id, "approve-script", video, { voice_id: "def456" });

    await act(async () => { vi.advanceTimersByTime(600); });
    vi.useRealTimers();
  });

  it("shows no preview button when the roster is empty", () => {
    const video = makeVideo("SCRIPT_READY");
    render(<ActionPane videos={[video]} onAction={() => {}} onOpenModal={() => {}} {...NO_VOICES} />);
    expect(screen.queryByTestId(/^voice-preview-/)).toBeNull();
  });

  it("renders a preview button for the pre-selected default voice", () => {
    const video = makeVideo("SCRIPT_READY");
    render(
      <ActionPane videos={[video]} onAction={() => {}} onOpenModal={() => {}}
        voices={VOICES} defaultVoiceId="abc123" />,
    );
    expect(screen.getByTestId("voice-preview-abc123")).toBeTruthy();
  });

  // TMDEV-121: a voice whose model cannot speak the script is shown, not pickable.
  it("disables a voice the API says cannot speak this script, with the reason", () => {
    const video = { ...makeVideo("SCRIPT_READY"), voice_id: "abc123",
      voice_conflicts: { def456: "voice text uses <ipa> tags" } };
    render(
      <ActionPane videos={[video]} onAction={() => {}} onOpenModal={() => {}}
        voices={VOICES} defaultVoiceId="abc123" />,
    );
    const options = [...(screen.getByTestId(`voice-select-${video.id}`) as HTMLSelectElement).options];
    const blocked = options.find((o) => o.value === "def456")!;
    expect(blocked.disabled).toBe(true);
    expect(blocked.title).toContain("<ipa>");
    expect(options.find((o) => o.value === "abc123")!.disabled).toBe(false);
    expect(screen.queryByTestId(`voice-conflict-${video.id}`)).toBeNull();
  });

  it("labels each voice with its model", () => {
    const video = makeVideo("SCRIPT_READY");
    render(
      <ActionPane videos={[video]} onAction={() => {}} onOpenModal={() => {}}
        voices={VOICES} defaultVoiceId="abc123" />,
    );
    expect(screen.getByRole("option", { name: "Narrator · eleven_multilingual_v2" })).toBeTruthy();
  });

  it("warns when the video's own voice can no longer speak its script", () => {
    // Its model was changed in Settings after the script was written.
    const video = { ...makeVideo("SCRIPT_READY"), voice_id: "abc123",
      voice_conflicts: { abc123: "voice text uses <ipa> tags" } };
    render(
      <ActionPane videos={[video]} onAction={() => {}} onOpenModal={() => {}}
        voices={VOICES} defaultVoiceId="abc123" />,
    );
    expect(screen.getByTestId(`voice-conflict-${video.id}`)).toBeTruthy();
  });
});

// ── Voice at the topic checkpoint (TMDEV-127) ────────────────────────────────
// A script is written for its voice's model, so a voice on another model has
// to be chosen before the script exists. The picker holds null until touched:
// an untouched Approve sends no voice_id, so it can never pin the install
// default over the voice the video was seeded with from its project.

describe("ActionPane — voice at TOPIC_PROPOSED", () => {
  afterEach(() => vi.restoreAllMocks());

  const VOICES = [
    { name: "Narrator", voice_id: "abc123", model_id: "eleven_multilingual_v2" },
    { name: "Expressive", voice_id: "v3voice", model_id: "eleven_v3" },
  ];

  async function approve(onAction: ReturnType<typeof vi.fn>) {
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    await act(async () => { vi.advanceTimersByTime(600); });
    return onAction.mock.calls[0][3] as Record<string, unknown>;
  }

  it("shows a voice picker labelled with each voice's model", () => {
    const video = makeVideo("TOPIC_PROPOSED");
    render(<ActionPane videos={[video]} onAction={() => {}} onOpenModal={() => {}}
      voices={VOICES} defaultVoiceId="abc123" />);
    expect(screen.getByTestId(`voice-select-${video.id}`)).toBeTruthy();
    expect(screen.getByRole("option", { name: "Expressive · eleven_v3" })).toBeTruthy();
    expect(screen.getByTestId("voice-preview-abc123")).toBeTruthy();
  });

  it("starts on the video's own voice — the one its project seeded — over the install default", () => {
    const video = { ...makeVideo("TOPIC_PROPOSED"), voice_id: "v3voice" };
    render(<ActionPane videos={[video]} onAction={() => {}} onOpenModal={() => {}}
      voices={VOICES} defaultVoiceId="abc123" />);
    expect((screen.getByTestId(`voice-select-${video.id}`) as HTMLSelectElement).value).toBe("v3voice");
  });

  it("an untouched picker sends no voice_id, never overwriting the seeded voice", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout"] });
    const onAction = vi.fn();
    const video = { ...makeVideo("TOPIC_PROPOSED"), voice_id: "v3voice" };
    render(<ActionPane videos={[video]} onAction={onAction} onOpenModal={() => {}}
      voices={VOICES} defaultVoiceId="abc123" />);
    const extra = await approve(onAction);
    expect(extra).not.toHaveProperty("voice_id");
    vi.useRealTimers();
  });

  it("a picked voice travels with the approval", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout"] });
    const onAction = vi.fn();
    const video = makeVideo("TOPIC_PROPOSED");
    render(<ActionPane videos={[video]} onAction={onAction} onOpenModal={() => {}}
      voices={VOICES} defaultVoiceId="abc123" />);
    fireEvent.change(screen.getByTestId(`voice-select-${video.id}`), { target: { value: "v3voice" } });
    const extra = await approve(onAction);
    expect(extra.voice_id).toBe("v3voice");
    vi.useRealTimers();
  });
});

// ── The shown voice follows /settings (TMDEV-127) ────────────────────────────
// The videos and /settings answer independently. Seeding the picker from the
// default at mount froze "" when the videos came first: the row then showed
// the roster's first voice while approving sent "".

describe("ActionPane — voice picker when /settings answers late", () => {
  afterEach(() => vi.restoreAllMocks());

  const VOICES = [
    { name: "Narrator", voice_id: "abc123", model_id: "eleven_multilingual_v2" },
    { name: "Energetic", voice_id: "def456", model_id: "eleven_multilingual_v2" },
  ];

  it("SCRIPT_READY shows, and approves with, the default that arrived after mount", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout"] });
    const onAction = vi.fn();
    const video = makeVideo("SCRIPT_READY");
    const { rerender } = render(<ActionPane videos={[video]} onAction={onAction}
      onOpenModal={() => {}} {...NO_VOICES} />);
    rerender(<ActionPane videos={[video]} onAction={onAction} onOpenModal={() => {}}
      voices={VOICES} defaultVoiceId="def456" />);
    expect((screen.getByTestId(`voice-select-${video.id}`) as HTMLSelectElement).value).toBe("def456");
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(onAction).toHaveBeenCalledWith(video.id, "approve-script", video, { voice_id: "def456" });
    await act(async () => { vi.advanceTimersByTime(600); });
    vi.useRealTimers();
  });

  it("TOPIC_PROPOSED shows the late default too", () => {
    const video = makeVideo("TOPIC_PROPOSED");
    const { rerender } = render(<ActionPane videos={[video]} onAction={() => {}}
      onOpenModal={() => {}} {...NO_VOICES} />);
    rerender(<ActionPane videos={[video]} onAction={() => {}} onOpenModal={() => {}}
      voices={VOICES} defaultVoiceId="def456" />);
    expect((screen.getByTestId(`voice-select-${video.id}`) as HTMLSelectElement).value).toBe("def456");
  });

  it("a voice that left the roster is shown as itself, disabled, not as the first voice", () => {
    const video = { ...makeVideo("SCRIPT_READY"), voice_id: "ghost" };
    render(<ActionPane videos={[video]} onAction={() => {}} onOpenModal={() => {}}
      voices={VOICES} defaultVoiceId="abc123" />);
    const select = screen.getByTestId(`voice-select-${video.id}`) as HTMLSelectElement;
    expect(select.value).toBe("ghost");
    expect(select.options[0].text).toBe("ghost (not in roster)");
    expect(select.options[0].disabled).toBe(true);
    expect((screen.getByTestId("voice-preview-ghost") as HTMLButtonElement).disabled).toBe(true);
  });

  it("with no voice and no install default it says so", () => {
    const video = makeVideo("TOPIC_PROPOSED");
    render(<ActionPane videos={[video]} onAction={() => {}} onOpenModal={() => {}}
      voices={VOICES} defaultVoiceId="" />);
    const select = screen.getByTestId(`voice-select-${video.id}`) as HTMLSelectElement;
    expect(select.options[select.selectedIndex].text).toBe("No voice set");
  });
});

// ── Script profile picker (TMDEV-81) ─────────────────────────────────────────

describe("ActionPane — script profile picker", () => {
  afterEach(() => vi.restoreAllMocks());

  const PROFILES = [
    { id: "p1", name: "Corpus A", status: "READY" as const, source_urls: [], error: "",
      attempt_count: 1, archived: false,
      created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z" },
  ];

  it("shows no picker when there are no profiles", () => {
    const video = makeVideo("TOPIC_PROPOSED");
    render(<ActionPane videos={[video]} onAction={() => {}} onOpenModal={() => {}} {...NO_VOICES} />);
    expect(screen.queryByTestId(`profile-select-${video.id}`)).toBeNull();
  });

  it("offers a 'none' option alongside one profile", () => {
    const video = makeVideo("TOPIC_PROPOSED");
    render(<ActionPane videos={[video]} scriptProfiles={PROFILES} onAction={() => {}} onOpenModal={() => {}} {...NO_VOICES} />);
    const select = screen.getByTestId(`profile-select-${video.id}`) as HTMLSelectElement;
    // Shown at one profile, not two: "no profile" is a real choice (the
    // script-writing skill's generic style), so there are always two options.
    expect([...select.options].map((o) => o.value)).toEqual(["", "p1"]);
    expect(select.value).toBe("");
  });

  it("sends the picked profile with approve-topic", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout"] });
    const onAction = vi.fn();
    const video = makeVideo("TOPIC_PROPOSED");
    render(<ActionPane videos={[video]} scriptProfiles={PROFILES} onAction={onAction} onOpenModal={() => {}} {...NO_VOICES} />);

    fireEvent.change(screen.getByTestId(`profile-select-${video.id}`), { target: { value: "p1" } });
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));

    expect(onAction).toHaveBeenCalledWith(video.id, "approve-topic", video,
      { script_profile_id: "p1", agent_model: "", agent_effort: "", visual_style: "auto" });
    await act(async () => { vi.advanceTimersByTime(600); });
    vi.useRealTimers();
  });

  // Profile names are user-supplied with no length limit, and a <select> is as
  // wide as its longest option, so one long name would widen every row.
  it("caps the picker's width", () => {
    const video = makeVideo("TOPIC_PROPOSED");
    render(<ActionPane videos={[video]} scriptProfiles={PROFILES} onAction={() => {}} onOpenModal={() => {}} {...NO_VOICES} />);
    expect((screen.getByTestId(`profile-select-${video.id}`) as HTMLSelectElement).style.maxWidth).toBe("220px");
  });

  // TMDEV-145: a curriculum video can arrive holding its domain's default
  // profile, which may have been deleted since. Before, the picker showed
  // "No profile" while sending the deleted id (refused by the API), and with no
  // READY profile left it was hidden, so the human could not clear it.
  it("shows a held profile that is no longer offered, even with none left, and lets it be cleared", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout"] });
    const onAction = vi.fn();
    const video = { ...makeVideo("TOPIC_PROPOSED"), script_profile_id: "gone" };
    render(<ActionPane videos={[video]} scriptProfiles={[]} onAction={onAction} onOpenModal={() => {}} {...NO_VOICES} />);

    const select = screen.getByTestId(`profile-select-${video.id}`) as HTMLSelectElement;
    expect(select.value).toBe("gone");
    expect(select.selectedOptions[0].textContent).toBe("Unavailable profile");

    fireEvent.change(select, { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(onAction).toHaveBeenCalledWith(video.id, "approve-topic", video,
      { script_profile_id: "", agent_model: "", agent_effort: "", visual_style: "auto" });
    await act(async () => { vi.advanceTimersByTime(600); });
    vi.useRealTimers();
  });
});

// ── Agent model picker (TMDEV-81 follow-up) ─────────────────────────────────

function makeAgent(over: Partial<Agent> = {}): Agent {
  return {
    id: "claude", name: "Claude Code", binary: "claude", run_path: "~/.tubematic-agent",
    install_scope: "user", models: ["sonnet", "opus", "haiku"], effort: "high",
    is_default: true, weight: 100,
    verified_at: "2026-09-01T00:00:00Z", archived_at: null,
    created_at: "2026-09-01T00:00:00Z", updated_at: "2026-09-01T00:00:00Z",
    ...over,
  };
}

describe("ActionPane — agent model picker", () => {
  afterEach(() => vi.restoreAllMocks());

  it("is a select of the effective agent's models, starting on its default", () => {
    const video = makeVideo("TOPIC_PROPOSED");
    render(<ActionPane videos={[video]} agents={[makeAgent()]} onAction={() => {}} onOpenModal={() => {}} {...NO_VOICES} />);
    const select = screen.getByTestId(`model-input-${video.id}`) as HTMLSelectElement;
    expect(select.tagName).toBe("SELECT");
    expect([...select.options].map((o) => o.value)).toEqual(["sonnet", "opus", "haiku"]);
    expect(select.value).toBe("sonnet");
    expect(select.disabled).toBe(false);
    expect((screen.getByTestId(`agent-select-${video.id}`) as HTMLSelectElement).value).toBe("claude");
  });

  it("uses the video's pinned agent over the default", () => {
    const video = { ...makeVideo("TOPIC_PROPOSED"), agent_id: "codex" };
    const agents = [makeAgent(), makeAgent({ id: "codex", name: "Codex", models: ["gpt-5"], is_default: false })];
    render(<ActionPane videos={[video]} agents={agents} onAction={() => {}} onOpenModal={() => {}} {...NO_VOICES} />);
    const select = screen.getByTestId(`model-input-${video.id}`) as HTMLSelectElement;
    expect([...select.options].map((o) => o.value)).toEqual(["gpt-5"]);
    expect((screen.getByTestId(`agent-select-${video.id}`) as HTMLSelectElement).value).toBe("codex");
  });

  it("pre-selects a stored model the agent still offers, and the default otherwise", () => {
    const kept = { ...makeVideo("TOPIC_PROPOSED"), id: "kept", agent_model: "opus" };
    const gone = { ...makeVideo("TOPIC_PROPOSED"), id: "gone", agent_model: "retired-model" };
    render(<ActionPane videos={[kept, gone]} agents={[makeAgent()]} onAction={() => {}} onOpenModal={() => {}} {...NO_VOICES} />);
    expect((screen.getByTestId("model-input-kept") as HTMLSelectElement).value).toBe("opus");
    expect((screen.getByTestId("model-input-gone") as HTMLSelectElement).value).toBe("sonnet");
  });

  it("sends the selected model with approve-topic", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout"] });
    const onAction = vi.fn();
    const video = makeVideo("TOPIC_PROPOSED");
    render(<ActionPane videos={[video]} agents={[makeAgent()]} onAction={onAction} onOpenModal={() => {}} {...NO_VOICES} />);

    fireEvent.change(screen.getByTestId(`model-input-${video.id}`), { target: { value: "haiku" } });
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));

    expect(onAction).toHaveBeenCalledWith(video.id, "approve-topic", video,
      { script_profile_id: "", agent_model: "haiku", agent_effort: "", visual_style: "auto" });
    await act(async () => { vi.advanceTimersByTime(600); });
    vi.useRealTimers();
  });

  it("sends the agent's default when the picker is left alone", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout"] });
    const onAction = vi.fn();
    const video = makeVideo("TOPIC_PROPOSED");
    render(<ActionPane videos={[video]} agents={[makeAgent()]} onAction={onAction} onOpenModal={() => {}} {...NO_VOICES} />);
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(onAction).toHaveBeenCalledWith(video.id, "approve-topic", video,
      { script_profile_id: "", agent_model: "sonnet", agent_effort: "", visual_style: "auto" });
    await act(async () => { vi.advanceTimersByTime(600); });
    vi.useRealTimers();
  });

  it("disables the picker and sends no model when the video's agent is uninstalled", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout"] });
    const onAction = vi.fn();
    const video = { ...makeVideo("TOPIC_PROPOSED"), agent_id: "claude", agent_model: "opus" };
    render(<ActionPane videos={[video]} agents={[makeAgent({ archived_at: "2026-09-05T00:00:00Z" })]}
      onAction={onAction} onOpenModal={() => {}} {...NO_VOICES} />);
    expect((screen.getByTestId(`model-input-${video.id}`) as HTMLSelectElement).disabled).toBe(true);
    expect(screen.getByTestId(`model-input-${video.id}`).title).toBe("Agent uninstalled");
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(onAction).toHaveBeenCalledWith(video.id, "approve-topic", video,
      { script_profile_id: "", agent_model: "", agent_effort: "", visual_style: "auto" });
    await act(async () => { vi.advanceTimersByTime(600); });
    vi.useRealTimers();
  });

  it("greys out agent, model and effort when no agent is installed, with the reason on hover", () => {
    const video = makeVideo("TOPIC_PROPOSED");
    render(<ActionPane videos={[video]} agents={[]} onAction={() => {}} onOpenModal={() => {}} {...NO_VOICES} />);
    expect((screen.getByTestId(`model-input-${video.id}`) as HTMLSelectElement).disabled).toBe(true);
    expect((screen.getByTestId(`effort-input-${video.id}`) as HTMLSelectElement).disabled).toBe(true);
    for (const id of ["agent-name", "model-input", "effort-input"]) {
      expect(screen.getByTestId(`${id}-${video.id}`).title).toBe("Agent not installed");
    }
    // The reason is a tooltip, never a line of text on the row: that text
    // took so much width that the buttons wrapped onto a second line.
    expect(screen.queryByTestId(`model-hint-${video.id}`)).toBeNull();
    expect(screen.getByTestId(`action-card-${video.id}`).textContent).not.toMatch(/not installed/i);
  });

  it("says the list is not loaded, not that no agent is installed, before agents arrive", () => {
    const video = makeVideo("TOPIC_PROPOSED");
    render(<ActionPane videos={[video]} onAction={() => {}} onOpenModal={() => {}} {...NO_VOICES} />);
    expect((screen.getByTestId(`model-input-${video.id}`) as HTMLSelectElement).disabled).toBe(true);
    expect(screen.getByTestId(`model-input-${video.id}`).title).toBe("Agent list not loaded");
  });

  it("does not fall back to the default agent for an unknown pinned agent", () => {
    // The API checks the model against the video's own agent, so offering the
    // default agent's list here would only produce a rejected approve.
    const video = { ...makeVideo("TOPIC_PROPOSED"), agent_id: "gone" };
    render(<ActionPane videos={[video]} agents={[makeAgent()]} onAction={() => {}} onOpenModal={() => {}} {...NO_VOICES} />);
    expect((screen.getByTestId(`model-input-${video.id}`) as HTMLSelectElement).disabled).toBe(true);
  });

  it("keeps the model at the script checkpoint but never the profile (TMDEV-110)", () => {
    const video = makeVideo("SCRIPT_READY");
    render(<ActionPane videos={[video]} agents={[makeAgent()]} onAction={() => {}} onOpenModal={() => {}} {...NO_VOICES} />);
    expect(screen.getByTestId(`model-input-${video.id}`)).toBeTruthy();
    expect(screen.queryByTestId(`profile-select-${video.id}`)).toBeNull();
  });

  it("shows neither control at the video checkpoint, where Approve hands no work to an agent", () => {
    const video = makeVideo("VIDEO_READY");
    render(<ActionPane videos={[video]} agents={[makeAgent()]} onAction={() => {}} onOpenModal={() => {}} {...NO_VOICES} />);
    expect(screen.queryByTestId(`model-input-${video.id}`)).toBeNull();
    expect(screen.queryByTestId(`agent-select-${video.id}`)).toBeNull();
  });
});

// ── Read-only choices in the inbox meta line (TMDEV-81 follow-up) ────────────

describe("ActionPane — frozen choices stay visible", () => {
  afterEach(() => vi.restoreAllMocks());

  const PROFILES = [
    { id: "p1", name: "Corpus A", status: "READY" as const, source_urls: [], error: "",
      attempt_count: 1, archived: false,
      created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z" },
  ];

  it("names the profile and model on a later checkpoint", () => {
    const video = { ...makeVideo("VIDEO_READY"), script_profile_id: "p1", agent_model: "opus" };
    render(<ActionPane videos={[video]} scriptProfiles={PROFILES} onAction={() => {}} onOpenModal={() => {}} {...NO_VOICES} />);
    const meta = screen.getByTestId(`choices-${video.id}`).textContent ?? "";
    expect(meta).toContain("Corpus A");
    expect(meta).toContain("opus");
  });

  it("says which defaults are in play when neither was chosen", () => {
    const video = makeVideo("VIDEO_READY");
    render(<ActionPane videos={[video]} agents={[makeAgent()]} onAction={() => {}} onOpenModal={() => {}} {...NO_VOICES} />);
    const meta = screen.getByTestId(`choices-${video.id}`).textContent ?? "";
    expect(meta).toContain("generic style");
    expect(meta).toContain("Claude Code");
    // A blank stored model is the agent's own models[0], spelled out.
    expect(meta).toContain("sonnet (default)");
  });

  it("stays out of the way at TOPIC_PROPOSED, where the pickers are live", () => {
    const video = makeVideo("TOPIC_PROPOSED");
    render(<ActionPane videos={[video]} scriptProfiles={PROFILES} onAction={() => {}} onOpenModal={() => {}} {...NO_VOICES} />);
    expect(screen.queryByTestId(`choices-${video.id}`)).toBeNull();
  });
});

describe("ActionPane — visual style picker", () => {
  const NO_VOICES = { voices: [], defaultVoiceId: "" };

  function makeVideo(status: VideoStatus): Video {
    return {
      id: `vid-style-${status}`,
      project_id: null,
      title: "",
      topic: "A topic",
      strategy: "curriculum",
      producibility_score: 8,
      status,
      script: "",
      voice_file_path: null,
      timeline_path: null,
      scene_config_path: null,
      video_path: null,
      video_version: 1,
      gemini_feedback: "",
      youtube_url: null,
      voice_id: "",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
      comments: [],
    };
  }

  it("offers exactly the styles the API accepts, and defaults to Auto", () => {
    // These values are hand-duplicated from mcp/server.py's VISUAL_STYLES.
    // Offering one the API rejects produces a 400 on approval, which surfaces
    // to the human as a failed click with no explanation.
    const video = makeVideo("TOPIC_PROPOSED");
    render(<ActionPane videos={[video]} onAction={() => {}} onOpenModal={() => {}} {...NO_VOICES} />);
    const select = screen.getByTestId(`style-select-${video.id}`) as HTMLSelectElement;
    expect([...select.options].map((o) => o.value)).toEqual([
      "auto", "motion_graphics", "stick", "illustrated",
    ]);
    expect(select.value).toBe("auto");
  });

  it("disables Illustrated, saying why, when no OpenAI key is stored", () => {
    // Its characters can only be drawn by OpenAI; without a key the API
    // refuses the style, and before this the failure surfaced only after the
    // video had been voiced.
    const video = makeVideo("TOPIC_PROPOSED");
    render(<ActionPane videos={[video]} illustratedAvailable={false} onAction={() => {}}
      onOpenModal={() => {}} {...NO_VOICES} />);
    const select = screen.getByTestId(`style-select-${video.id}`) as HTMLSelectElement;
    const illustrated = [...select.options].find((o) => o.value === "illustrated")!;
    expect(illustrated.disabled).toBe(true);
    expect(illustrated.textContent).toMatch(/needs an OpenAI key/);
    expect([...select.options].filter((o) => o.disabled).map((o) => o.value))
      .toEqual(["illustrated"]);
  });

  it("leaves Illustrated enabled when key state is not given", () => {
    // The API is the authority: a page that never loads settings must not
    // grey out an option that may be valid.
    const video = makeVideo("TOPIC_PROPOSED");
    render(<ActionPane videos={[video]} onAction={() => {}} onOpenModal={() => {}} {...NO_VOICES} />);
    const select = screen.getByTestId(`style-select-${video.id}`) as HTMLSelectElement;
    expect([...select.options].some((o) => o.disabled)).toBe(false);
  });

  it("sends the picked register with approve-topic", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout"] });
    const onAction = vi.fn();
    const video = makeVideo("TOPIC_PROPOSED");
    render(<ActionPane videos={[video]} onAction={onAction} onOpenModal={() => {}} {...NO_VOICES} />);
    fireEvent.change(screen.getByTestId(`style-select-${video.id}`), {
      target: { value: "stick" },
    });
    fireEvent.click(screen.getByText("Approve"));
    await act(async () => { vi.advanceTimersByTime(600); });
    expect(onAction).toHaveBeenCalledWith(video.id, "approve-topic", video,
      { script_profile_id: "", agent_model: "", agent_effort: "", visual_style: "stick" });
    vi.useRealTimers();
  });

  it("pre-selects the register the video already carries", () => {
    const video = { ...makeVideo("TOPIC_PROPOSED"), visual_style: "stick" as const };
    render(<ActionPane videos={[video]} onAction={() => {}} onOpenModal={() => {}} {...NO_VOICES} />);
    expect((screen.getByTestId(`style-select-${video.id}`) as HTMLSelectElement).value)
      .toBe("stick");
  });

  it("goes read-only once the choice is frozen", () => {
    const video = { ...makeVideo("SCRIPT_READY"), visual_style: "stick" as const };
    render(<ActionPane videos={[video]} onAction={() => {}} onOpenModal={() => {}} {...NO_VOICES} />);
    expect(screen.queryByTestId(`style-select-${video.id}`)).toBeNull();
    expect(screen.getByTestId(`choices-${video.id}`).textContent ?? "")
      .toContain("Stick Explainer");
  });

  it("says which canvas auto actually chose, and marks it automatic", () => {
    // Without this the dashboard cannot explain why two videos look different,
    // which is the entire reason the resolution is recorded. It names the
    // CANVAS rather than a register, because an auto video on a dark canvas
    // may still contain figures — "Motion Graphics" would be a lie.
    const video = {
      ...makeVideo("VIDEO_READY"),
      visual_style: "auto" as const,
      resolved_visual_style: "light",
    };
    render(<ActionPane videos={[video]} onAction={() => {}} onOpenModal={() => {}} {...NO_VOICES} />);
    const meta = screen.getByTestId(`choices-${video.id}`).textContent ?? "";
    expect(meta.toLowerCase()).toContain("light canvas");
  });

  it("does not imply a register before auto has chosen one", () => {
    const video = { ...makeVideo("VOICE_READY"), visual_style: "auto" as const };
    render(<ActionPane videos={[video]} onAction={() => {}} onOpenModal={() => {}} {...NO_VOICES} />);
    expect(screen.getByTestId(`choices-${video.id}`).textContent ?? "")
      .toContain("not yet chosen");
  });
});

// ── Agent effort picker (TMDEV-106) ─────────────────────────────────────────

describe("ActionPane — agent effort picker", () => {
  afterEach(() => vi.restoreAllMocks());

  it("offers the five CLI levels plus a blank that names the agent's own", () => {
    const video = makeVideo("TOPIC_PROPOSED");
    render(<ActionPane videos={[video]} agents={[makeAgent({ effort: "low" })]} onAction={() => {}} onOpenModal={() => {}} {...NO_VOICES} />);
    const select = screen.getByTestId(`effort-input-${video.id}`) as HTMLSelectElement;
    expect([...select.options].map((o) => o.value))
      .toEqual(["", "low", "medium", "high", "xhigh", "max"]);
    expect(select.value).toBe("");
    expect([...select.options][0].textContent).toBe("low (agent default)");
  });

  it("pre-selects a stored effort, and blank otherwise", () => {
    const kept = { ...makeVideo("TOPIC_PROPOSED"), id: "kept", agent_effort: "max" };
    const none = { ...makeVideo("TOPIC_PROPOSED"), id: "none", agent_effort: "" };
    render(<ActionPane videos={[kept, none]} agents={[makeAgent()]} onAction={() => {}} onOpenModal={() => {}} {...NO_VOICES} />);
    expect((screen.getByTestId("effort-input-kept") as HTMLSelectElement).value).toBe("max");
    expect((screen.getByTestId("effort-input-none") as HTMLSelectElement).value).toBe("");
  });

  it("never submits a guessed level when the agent list is unavailable", async () => {
    /* The regression this guards. Projects and Library never fetch /agents at
       all, and Pipeline has not fetched it before first paint. Resolving the
       picker to a literal default and submitting it would silently override an
       agent configured for anything else — and agent_effort is frozen at
       approval, so it could never be corrected afterwards. */
    vi.useFakeTimers({ toFake: ["setTimeout"] });
    const onAction = vi.fn();
    const video = makeVideo("TOPIC_PROPOSED");
    render(<ActionPane videos={[video]} onAction={onAction} onOpenModal={() => {}} {...NO_VOICES} />);
    const select = screen.getByTestId(`effort-input-${video.id}`) as HTMLSelectElement;
    expect(select.value).toBe("");
    expect([...select.options][0].textContent).toBe("Agent default");
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(onAction).toHaveBeenCalledWith(video.id, "approve-topic", video,
      expect.objectContaining({ agent_effort: "" }));
    await act(async () => { vi.advanceTimersByTime(600); });
    vi.useRealTimers();
  });

  it("can be set back to blank after a pick", () => {
    const video = makeVideo("TOPIC_PROPOSED");
    render(<ActionPane videos={[video]} agents={[makeAgent()]} onAction={() => {}} onOpenModal={() => {}} {...NO_VOICES} />);
    const select = screen.getByTestId(`effort-input-${video.id}`) as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "max" } });
    expect(select.value).toBe("max");
    fireEvent.change(select, { target: { value: "" } });
    expect(select.value).toBe("");
  });

  it("is greyed out with the model picker while the agent is unusable, and comes back with an installed one", () => {
    /* Reversed in TMDEV-135 (user decision): with no agent able to run the
       video, an effort level for it records nothing useful, and the live
       picker read as if it would. The agent picker stays live, because
       switching to an installed agent is the way out — and it re-enables both. */
    const video = { ...makeVideo("TOPIC_PROPOSED"), agent_id: "claude" };
    render(<ActionPane videos={[video]}
      agents={[makeAgent({ archived_at: "2026-09-05T00:00:00Z" }), makeAgent({ id: "codex", name: "Codex", is_default: false, models: ["gpt-5"] })]}
      onAction={() => {}} onOpenModal={() => {}} {...NO_VOICES} />);
    const effortSel = () => screen.getByTestId(`effort-input-${video.id}`) as HTMLSelectElement;
    expect((screen.getByTestId(`model-input-${video.id}`) as HTMLSelectElement).disabled).toBe(true);
    expect(effortSel().disabled).toBe(true);
    const agentSel = screen.getByTestId(`agent-select-${video.id}`) as HTMLSelectElement;
    expect(agentSel.disabled).toBe(false);

    fireEvent.change(agentSel, { target: { value: "codex" } });
    expect((screen.getByTestId(`model-input-${video.id}`) as HTMLSelectElement).disabled).toBe(false);
    expect(effortSel().disabled).toBe(false);
    expect(effortSel().title).not.toMatch(/install/i);
  });

  it("sends the picked effort with approve-topic", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout"] });
    const onAction = vi.fn();
    const video = makeVideo("TOPIC_PROPOSED");
    render(<ActionPane videos={[video]} agents={[makeAgent()]} onAction={onAction} onOpenModal={() => {}} {...NO_VOICES} />);
    fireEvent.change(screen.getByTestId(`effort-input-${video.id}`), { target: { value: "max" } });
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(onAction).toHaveBeenCalledWith(video.id, "approve-topic", video,
      { script_profile_id: "", agent_model: "sonnet", agent_effort: "max", visual_style: "auto" });
    await act(async () => { vi.advanceTimersByTime(600); });
    vi.useRealTimers();
  });

  it("is gone where no picker is offered, and the choice is shown read-only", () => {
    /* VIDEO_READY has no inline pickers (its Revise is in the modal), so
       without the read-only row the choice would vanish from view. */
    const video = { ...makeVideo("VIDEO_READY"), agent_effort: "max" };
    render(<ActionPane videos={[video]} agents={[makeAgent()]} onAction={() => {}} onOpenModal={() => {}} {...NO_VOICES} />);
    expect(screen.queryByTestId(`effort-input-${video.id}`)).toBeNull();
    expect(screen.getByTestId(`choices-${video.id}`).textContent).toContain("max");
  });

  it("spells out the agent's level when the video stored none", () => {
    const video = { ...makeVideo("VIDEO_READY"), agent_effort: "" };
    render(<ActionPane videos={[video]} agents={[makeAgent({ effort: "xhigh" })]} onAction={() => {}} onOpenModal={() => {}} {...NO_VOICES} />);
    expect(screen.getByTestId(`choices-${video.id}`).textContent).toContain("xhigh (default)");
  });
});

// ── Picker labels ────────────────────────────────────────────────────────────

describe("ActionPane — picker labels", () => {
  /* The pickers sit side by side with near-identical option text (a model name
     and an effort level look alike), so without a caption a human can only tell
     them apart by position. Resolving each by its label also proves the caption
     is the control's accessible name, not just nearby text. */
  const PROFILE = {
    id: "p1", name: "Corpus A", status: "READY" as const, source_urls: [], error: "",
    attempt_count: 1, archived: false,
    created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
  };

  it("labels every topic-checkpoint picker, and names the agent", () => {
    const video = makeVideo("TOPIC_PROPOSED");
    render(<ActionPane videos={[video]} scriptProfiles={[PROFILE]} agents={[makeAgent()]}
      onAction={() => {}} onOpenModal={() => {}} {...NO_VOICES} />);
    expect(screen.getByLabelText("Script profile")).toBe(screen.getByTestId(`profile-select-${video.id}`));
    expect(screen.getByLabelText("Visual style")).toBe(screen.getByTestId(`style-select-${video.id}`));
    expect(screen.getByLabelText("Model")).toBe(screen.getByTestId(`model-input-${video.id}`));
    expect(screen.getByLabelText("Effort")).toBe(screen.getByTestId(`effort-input-${video.id}`));
    expect(screen.getByLabelText("Agent")).toBe(screen.getByTestId(`agent-select-${video.id}`));
  });

  it("still names the agent read-only when there is no list to pick from", () => {
    const video = makeVideo("TOPIC_PROPOSED");
    render(<ActionPane videos={[video]} onAction={() => {}} onOpenModal={() => {}} {...NO_VOICES} />);
    expect(screen.queryByTestId(`agent-select-${video.id}`)).toBeNull();
    expect(screen.getByTestId(`agent-name-${video.id}`).textContent).toBe("Default agent");
  });

  it("labels the voice picker at the script checkpoint", () => {
    const video = makeVideo("SCRIPT_READY");
    render(<ActionPane videos={[video]} onAction={() => {}} onOpenModal={() => {}}
      voices={[{ name: "Narrator", voice_id: "abc123", model_id: "eleven_multilingual_v2" }]} defaultVoiceId="abc123" />);
    expect(screen.getByLabelText("Voice")).toBe(screen.getByTestId(`voice-select-${video.id}`));
  });
});

// ── Changing the agent at a checkpoint (TMDEV-110) ───────────────────────────

describe("ActionPane — agent picker", () => {
  afterEach(() => vi.restoreAllMocks());

  const CLAUDE = makeAgent();
  const CODEX = makeAgent({ id: "codex", name: "Codex", models: ["gpt-5", "gpt-5-mini"], is_default: false });
  const OLD = makeAgent({ id: "old", name: "Old", is_default: false, archived_at: "2026-09-05T00:00:00Z" });
  const AGENTS = [CLAUDE, CODEX, OLD];

  function options(id: string) {
    const select = screen.getByTestId(`agent-select-${id}`) as HTMLSelectElement;
    return [...select.options].map((o) => [o.value, o.text, o.disabled]);
  }

  it("offers only live agents, starting on the video's own", () => {
    const video = { ...makeVideo("TOPIC_PROPOSED"), agent_id: "claude" };
    render(<ActionPane videos={[video]} agents={AGENTS} onAction={() => {}} onOpenModal={() => {}} {...NO_VOICES} />);
    expect(options(video.id)).toEqual([["claude", "Claude Code", false], ["codex", "Codex", false]]);
    expect((screen.getByTestId(`agent-select-${video.id}`) as HTMLSelectElement).value).toBe("claude");
  });

  it("shows an uninstalled agent the video is on, but not as a choice", () => {
    const video = { ...makeVideo("SCRIPT_READY"), agent_id: "old" };
    render(<ActionPane videos={[video]} agents={AGENTS} onAction={() => {}} onOpenModal={() => {}} {...NO_VOICES} />);
    expect(options(video.id)[0]).toEqual(["old", "Old (uninstalled)", true]);
    expect((screen.getByTestId(`agent-select-${video.id}`) as HTMLSelectElement).value).toBe("old");
  });

  it("switching agent swaps in its models, starts on its default, and says so", () => {
    const video = { ...makeVideo("TOPIC_PROPOSED"), agent_id: "claude", agent_model: "opus" };
    render(<ActionPane videos={[video]} agents={AGENTS} onAction={() => {}} onOpenModal={() => {}} {...NO_VOICES} />);
    expect(screen.queryByTestId(`agent-reset-note-${video.id}`)).toBeNull();
    fireEvent.change(screen.getByTestId(`agent-select-${video.id}`), { target: { value: "codex" } });
    const model = screen.getByTestId(`model-input-${video.id}`) as HTMLSelectElement;
    expect([...model.options].map((o) => o.value)).toEqual(["gpt-5", "gpt-5-mini"]);
    expect(model.value).toBe("gpt-5");
    expect(screen.getByTestId(`agent-reset-note-${video.id}`).textContent).toBe("Model reset to Codex's default");
  });

  it("approve-topic carries the new agent and its model", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout"] });
    const onAction = vi.fn();
    const video = { ...makeVideo("TOPIC_PROPOSED"), agent_id: "claude" };
    render(<ActionPane videos={[video]} agents={AGENTS} onAction={onAction} onOpenModal={() => {}} {...NO_VOICES} />);
    fireEvent.change(screen.getByTestId(`agent-select-${video.id}`), { target: { value: "codex" } });
    fireEvent.change(screen.getByTestId(`model-input-${video.id}`), { target: { value: "gpt-5-mini" } });
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(onAction).toHaveBeenCalledWith(video.id, "approve-topic", video, {
      script_profile_id: "", agent_id: "codex", agent_model: "gpt-5-mini", agent_effort: "",
      visual_style: "auto",
    });
    await act(async () => { vi.advanceTimersByTime(600); });
    vi.useRealTimers();
  });

  it("approve-script left alone sends only the voice — never a guessed agent value", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout"] });
    const onAction = vi.fn();
    const video = { ...makeVideo("SCRIPT_READY"), agent_id: "claude", agent_model: "opus" };
    render(<ActionPane videos={[video]} agents={AGENTS} onAction={onAction} onOpenModal={() => {}} {...NO_VOICES} />);
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(onAction).toHaveBeenCalledWith(video.id, "approve-script", video, { voice_id: "" });
    await act(async () => { vi.advanceTimersByTime(600); });
    vi.useRealTimers();
  });

  it("approve-script carries a changed agent, its default model, and a touched effort", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout"] });
    const onAction = vi.fn();
    const video = { ...makeVideo("SCRIPT_READY"), agent_id: "claude", agent_model: "opus" };
    render(<ActionPane videos={[video]} agents={AGENTS} onAction={onAction} onOpenModal={() => {}} {...NO_VOICES} />);
    fireEvent.change(screen.getByTestId(`agent-select-${video.id}`), { target: { value: "codex" } });
    fireEvent.change(screen.getByTestId(`effort-input-${video.id}`), { target: { value: "max" } });
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(onAction).toHaveBeenCalledWith(video.id, "approve-script", video, {
      voice_id: "", agent_id: "codex", agent_model: "gpt-5", agent_effort: "max",
    });
    await act(async () => { vi.advanceTimersByTime(600); });
    vi.useRealTimers();
  });

  it.each(["TOPIC_PROPOSED", "SCRIPT_READY"] as const)(
    "%s: Revise hands the row's picks to the modal instead of dropping them", (status) => {
      const onOpenModal = vi.fn();
      const video = { ...makeVideo(status), agent_id: "claude" };
      render(<ActionPane videos={[video]} agents={AGENTS} onAction={() => {}} onOpenModal={onOpenModal} {...NO_VOICES} />);
      fireEvent.change(screen.getByTestId(`agent-select-${video.id}`), { target: { value: "codex" } });
      fireEvent.click(screen.getByRole("button", { name: "Revise" }));
      expect(onOpenModal).toHaveBeenCalledWith(video, undefined, {
        revise: true, picks: { agentId: "codex", model: null, effort: null },
      });
    });
});

// ── grouping and status filter (TMDEV-135) ─────────────────────────────────────
//
// The API returns the inbox oldest first with every status interleaved. The
// pane groups it by checkpoint in pipeline order and keeps the API's order
// inside each group, and a multi-select filter hides whole statuses.

describe("ActionPane — grouping and filter", () => {
  afterEach(() => vi.restoreAllMocks());

  function vid(id: string, status: VideoStatus): Video {
    return { ...makeVideo(status), id, topic: `Topic ${id}` };
  }

  // Scrambled the way the oldest-first API order would interleave them.
  const MIXED = [
    vid("v1", "VIDEO_READY"),
    vid("t1", "TOPIC_PROPOSED"),
    vid("s1", "SCRIPT_READY"),
    vid("t2", "TOPIC_PROPOSED"),
  ];

  function cardOrder(): string[] {
    return Array.from(document.querySelectorAll("[data-testid^='action-card-']"))
      .map((el) => el.getAttribute("data-testid")!.replace("action-card-", ""));
  }

  it("groups rows by checkpoint in pipeline order, oldest first within a group", () => {
    render(<ActionPane videos={MIXED} onAction={() => {}} onOpenModal={() => {}} {...NO_VOICES} />);
    expect(cardOrder()).toEqual(["t1", "t2", "s1", "v1"]);
    const groups = Array.from(document.querySelectorAll("[data-testid^='action-group-']"))
      .map((el) => el.getAttribute("data-testid"));
    expect(groups).toEqual([
      "action-group-TOPIC_PROPOSED", "action-group-SCRIPT_READY", "action-group-VIDEO_READY",
    ]);
    expect(screen.getByTestId("action-group-TOPIC_PROPOSED").textContent).toContain("2");
  });

  it("renders no group header for a status with no rows", () => {
    render(<ActionPane videos={[vid("t1", "TOPIC_PROPOSED")]} onAction={() => {}} onOpenModal={() => {}} {...NO_VOICES} />);
    expect(screen.queryByTestId("action-group-SCRIPT_READY")).toBeNull();
    expect(screen.queryByTestId("action-group-VIDEO_READY")).toBeNull();
  });

  it("shows a pill per status with its count, all on by default", () => {
    render(<ActionPane videos={MIXED} onAction={() => {}} onOpenModal={() => {}} {...NO_VOICES} />);
    const topic = screen.getByTestId("action-filter-TOPIC_PROPOSED");
    expect(topic.textContent).toContain("Topic Proposed");
    expect(topic.textContent).toContain("2");
    expect(screen.getByTestId("action-filter-SCRIPT_READY").textContent).toContain("1");
    expect(screen.getByTestId("action-filter-VIDEO_READY").textContent).toContain("1");
    for (const s of ["TOPIC_PROPOSED", "SCRIPT_READY", "VIDEO_READY"]) {
      expect(screen.getByTestId(`action-filter-${s}`).getAttribute("aria-pressed")).toBe("true");
    }
  });

  it("toggling a pill off hides that status, and toggling it on restores it", () => {
    render(<ActionPane videos={MIXED} onAction={() => {}} onOpenModal={() => {}} {...NO_VOICES} />);
    const pill = screen.getByTestId("action-filter-SCRIPT_READY");
    fireEvent.click(pill);
    expect(pill.getAttribute("aria-pressed")).toBe("false");
    expect(cardOrder()).toEqual(["t1", "t2", "v1"]);
    expect(screen.queryByTestId("action-group-SCRIPT_READY")).toBeNull();
    // A hidden status still shows its count, so the pill says what it hides.
    expect(pill.textContent).toContain("1");

    fireEvent.click(pill);
    expect(pill.getAttribute("aria-pressed")).toBe("true");
    expect(cardOrder()).toEqual(["t1", "t2", "s1", "v1"]);
  });

  it("says nothing matches, not INBOX ZERO, when every status is filtered out", () => {
    render(<ActionPane videos={MIXED} onAction={() => {}} onOpenModal={() => {}} {...NO_VOICES} />);
    for (const s of ["TOPIC_PROPOSED", "SCRIPT_READY", "VIDEO_READY"]) {
      fireEvent.click(screen.getByTestId(`action-filter-${s}`));
    }
    const pane = screen.getByTestId("action-pane");
    expect(cardOrder()).toEqual([]);
    expect(pane.textContent).toContain("NO ACTIONS MATCH THE FILTER");
    expect(pane.textContent).not.toContain("INBOX ZERO");
    // The pills stay, so the filter can be undone.
    expect(screen.getByTestId("action-filter-TOPIC_PROPOSED")).toBeTruthy();
  });

  it("shows no filter on an empty inbox", () => {
    render(<ActionPane videos={[]} onAction={() => {}} onOpenModal={() => {}} {...NO_VOICES} />);
    expect(screen.queryByTestId("action-filter-TOPIC_PROPOSED")).toBeNull();
  });

  it("drops an actioned row from its pill count once it flashes away", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout"] });
    render(<ActionPane videos={MIXED} onAction={() => {}} onOpenModal={() => {}} {...NO_VOICES} />);
    const card = screen.getByTestId("action-card-v1");
    fireEvent.click(Array.from(card.querySelectorAll("button")).find((b) => b.textContent === "Approve")!);
    await act(async () => { vi.advanceTimersByTime(600); });
    vi.useRealTimers();
    expect(screen.getByTestId("action-filter-VIDEO_READY").textContent).toContain("0");
    expect(screen.queryByTestId("action-group-VIDEO_READY")).toBeNull();
  });
});
