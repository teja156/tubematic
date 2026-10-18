/**
 * Tests for VideoModal's reject-vs-revise split (TMDEV-1).
 *
 * Critical regressions guarded here:
 *  1. TOPIC_PROPOSED "Reject Topic" fires onAction immediately — no dialog, comment optional
 *  2. TOPIC_PROPOSED "Request Revision" is a distinct button that opens ReviseDialog
 *     (mandatory comment) and fires "revise-topic" on submit
 *  3. SCRIPT_READY "Request Revision" posts the comment then fires "revise-script" —
 *     previously this action was swallowed by PipelineClient's special-case intercept
 *     and never changed status; this locks the fix
 *  4. VIDEO_READY "Request Revision" posts the comment then fires "revise-video"
 *  5. Every Request Revision submit also closes the modal (onClose), matching
 *     Approve/Reject — a regression that previously left the modal open showing a
 *     stale status after a revision was sent
 *  6. Request Revision is the ONLY way a human comment enters: the Comments tab
 *     is a read-only thread at every status, and `openRevise` lands directly in
 *     the dialog (the Pipeline page's Revise buttons)
 */
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { VideoModal } from "@/components/VideoModal";
import type { Agent, ScriptSegment, Video, VideoStatus } from "@/lib/types";

// Fixed to America/New_York so the Created/Updated date-rendering test below
// has a deterministic, non-UTC expected value.
vi.mock("@/components/TimeZoneProvider", () => ({
  useTimeZone: () => ({ timeZone: "America/New_York", label: "EDT (UTC-04:00)", degraded: false }),
}));

function makeVideo(status: VideoStatus, scriptSegments?: ScriptSegment[] | null): Video {
  return {
    id: "vid-1",
    project_id: null,
    title: null,
    topic: "Test topic",
    strategy: "curriculum",
    producibility_score: 5,
    status,
    script: status === "SCRIPT_READY" ? "Test script" : null,
    script_segments: status === "SCRIPT_READY" ? scriptSegments ?? null : null,
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
    comments: [],
  };
}

async function requestRevision(comment: string) {
  fireEvent.click(await screen.findByText("Request Revision"));
  const textarea = await screen.findByPlaceholderText("Describe what needs to change...");
  fireEvent.change(textarea, { target: { value: comment } });
  fireEvent.click(screen.getByText("Send Revision Request"));
}

/** Stub fetch so the GET refresh on mount echoes back the same video (same status)
 * that was passed to render — not a hardcoded status — since the component
 * overwrites its `video` state with whatever the refresh call returns. */
function mockFetchFor(video: Video) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: unknown, init?: RequestInit) => {
      if (init?.method === "POST") {
        return Promise.resolve({ ok: true, json: async () => ({ ok: true }) } as Response);
      }
      return Promise.resolve({ ok: true, json: async () => video } as Response);
    }),
  );
}

describe("VideoModal — Created/Updated render in the host timezone", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows both dates converted to America/New_York with the zone label, not UTC", async () => {
    const video = makeVideo("TOPIC_PROPOSED");
    mockFetchFor(video);
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);

    // created_at/updated_at are both 2026-01-01T00:00:00Z (same value in this
    // fixture) — a day earlier in America/New_York — and the zone label must
    // be shown alongside the value. Both Created and Updated rows match.
    await waitFor(() => {
      const matches = screen.getAllByText(/Dec 31, 2025.*EDT \(UTC-04:00\)/);
      expect(matches.length).toBe(2);
    });
  });
});

describe("VideoModal — reject vs. revise", () => {
  afterEach(() => vi.restoreAllMocks());

  it("TOPIC_PROPOSED: Reject Topic fires onAction immediately, no dialog", async () => {
    const onAction = vi.fn();
    const video = makeVideo("TOPIC_PROPOSED");
    mockFetchFor(video);
    render(<VideoModal video={video} onClose={() => {}} onAction={onAction} />);

    fireEvent.click(await screen.findByText("Reject Topic"));

    expect(onAction).toHaveBeenCalledWith(video.id, "reject-topic", video);
    expect(screen.queryByPlaceholderText("Describe what needs to change...")).toBeNull();
  });

  it("TOPIC_PROPOSED: Request Revision opens dialog; submit posts a comment, fires revise-topic, and closes the modal", async () => {
    const onAction = vi.fn();
    const onClose = vi.fn();
    const video = makeVideo("TOPIC_PROPOSED");
    mockFetchFor(video);
    render(<VideoModal video={video} onClose={onClose} onAction={onAction} />);

    await requestRevision("Please tweak the angle");

    await waitFor(() => expect(onAction).toHaveBeenCalledWith(video.id, "revise-topic", video));
    expect(onClose).toHaveBeenCalled();
    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      `/api/proxy/videos/${video.id}/comments`,
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("SCRIPT_READY: Request Revision posts a comment, fires revise-script (previously a no-op), and closes the modal", async () => {
    const onAction = vi.fn();
    const onClose = vi.fn();
    const video = makeVideo("SCRIPT_READY");
    mockFetchFor(video);
    render(<VideoModal video={video} onClose={onClose} onAction={onAction} />);

    await requestRevision("Fix the intro line");

    await waitFor(() => expect(onAction).toHaveBeenCalledWith(video.id, "revise-script", video));
    expect(onClose).toHaveBeenCalled();
  });

  it("SCRIPT_READY: no voice select when the roster is empty (default prop)", async () => {
    const video = makeVideo("SCRIPT_READY");
    mockFetchFor(video);
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);

    await screen.findByText("Approve Script");
    expect(screen.queryByTestId("video-modal-voice-select")).toBeNull();
  });

  it("SCRIPT_READY: voice select pre-selects the video's own voice_id over the install default", async () => {
    const video = { ...makeVideo("SCRIPT_READY"), voice_id: "abc123" };
    mockFetchFor(video);
    const voices = [
      { name: "Narrator", voice_id: "abc123", model_id: "eleven_multilingual_v2" },
      { name: "Energetic", voice_id: "def456", model_id: "eleven_multilingual_v2" },
    ];
    render(
      <VideoModal video={video} onClose={() => {}} onAction={() => {}}
        voices={voices} defaultVoiceId="def456" />,
    );

    const select = await screen.findByTestId("video-modal-voice-select") as HTMLSelectElement;
    expect(select.value).toBe("abc123");
  });

  it("SCRIPT_READY: Approve Script sends the selected voice_id as the fourth onAction argument", async () => {
    const onAction = vi.fn();
    const video = makeVideo("SCRIPT_READY");
    mockFetchFor(video);
    const voices = [
      { name: "Narrator", voice_id: "abc123", model_id: "eleven_multilingual_v2" },
      { name: "Energetic", voice_id: "def456", model_id: "eleven_multilingual_v2" },
    ];
    render(
      <VideoModal video={video} onClose={() => {}} onAction={onAction}
        voices={voices} defaultVoiceId="abc123" />,
    );

    const select = await screen.findByTestId("video-modal-voice-select");
    fireEvent.change(select, { target: { value: "def456" } });
    fireEvent.click(screen.getByText("Approve Script"));

    expect(onAction).toHaveBeenCalledWith(video.id, "approve-script", video, { voice_id: "def456" });
  });

  it("SCRIPT_READY: renders a preview button alongside the voice select", async () => {
    const video = { ...makeVideo("SCRIPT_READY"), voice_id: "abc123" };
    mockFetchFor(video);
    const voices = [{ name: "Narrator", voice_id: "abc123", model_id: "eleven_multilingual_v2" }];
    render(
      <VideoModal video={video} onClose={() => {}} onAction={() => {}}
        voices={voices} defaultVoiceId="abc123" />,
    );

    await screen.findByTestId("video-modal-voice-select");
    expect(screen.getByTestId("voice-preview-abc123")).toBeTruthy();
  });

  // TMDEV-121: the API names the voices whose model cannot speak the script.
  it("SCRIPT_READY: disables a voice that cannot speak the script, and explains a conflicting current voice", async () => {
    const video = { ...makeVideo("SCRIPT_READY"), voice_id: "abc123",
      voice_conflicts: { abc123: "voice text uses <ipa> tags, which only eleven_v3 understands",
                         def456: "voice text uses <ipa> tags" } };
    mockFetchFor(video);
    const voices = [
      { name: "Narrator", voice_id: "abc123", model_id: "eleven_multilingual_v2" },
      { name: "Energetic", voice_id: "def456", model_id: "eleven_multilingual_v2" },
      { name: "Adam", voice_id: "a1", model_id: "eleven_v3" },
    ];
    render(
      <VideoModal video={video} onClose={() => {}} onAction={() => {}}
        voices={voices} defaultVoiceId="abc123" />,
    );
    const select = await screen.findByTestId("video-modal-voice-select") as HTMLSelectElement;
    const byValue = Object.fromEntries([...select.options].map((o) => [o.value, o]));
    expect(byValue.def456.disabled).toBe(true);
    expect(byValue.a1.disabled).toBe(false);
    expect(byValue.a1.textContent).toBe("Adam · eleven_v3");
    expect(screen.getByTestId("video-modal-voice-conflict").textContent).toMatch(/only eleven_v3/);
  });

  it("VIDEO_READY: Request Revision posts a comment, fires revise-video, and closes the modal", async () => {
    const onAction = vi.fn();
    const onClose = vi.fn();
    const video = makeVideo("VIDEO_READY");
    mockFetchFor(video);
    render(<VideoModal video={video} onClose={onClose} onAction={onAction} />);

    await requestRevision("Audio is too quiet");

    await waitFor(() => expect(onAction).toHaveBeenCalledWith(video.id, "revise-video", video));
    expect(onClose).toHaveBeenCalled();
  });

  it("VIDEO_READY: gemini_feedback populated renders the AI Review Feedback panel (TMDEV-46)", async () => {
    const video = { ...makeVideo("VIDEO_READY"), gemini_feedback: "Looks great, no issues found." };
    mockFetchFor(video);
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);

    expect(await screen.findByText("AI Review Feedback")).toBeInTheDocument();
    expect(screen.getByText("Looks great, no issues found.")).toBeInTheDocument();
  });

  it("VIDEO_READY: three-part gemini_feedback (TMDEV-58) renders Overall/Must fix/Suggestions", async () => {
    const feedback = [
      "**Overall:** Solid video, a couple of polish items.",
      "",
      "**Must fix (0):**",
      "No blocking errors found.",
      "",
      "**Suggestions (1):**",
      "- **video** @ 0:30 — scene `StepFlow.tsx`",
      "  hook title could hold a beat longer",
      "  Suggested fix: extend by 12 frames",
    ].join("\n");
    const video = { ...makeVideo("VIDEO_READY"), gemini_feedback: feedback };
    mockFetchFor(video);
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);

    expect(await screen.findByText("AI Review Feedback")).toBeInTheDocument();
    expect(screen.getByText(/Solid video, a couple of polish items\./)).toBeInTheDocument();
    expect(screen.getByText(/No blocking errors found\./)).toBeInTheDocument();
    expect(screen.getByText(/hook title could hold a beat longer/)).toBeInTheDocument();
    expect(screen.getByText(/extend by 12 frames/)).toBeInTheDocument();
  });

  // ── Long-review clipping + read more (VQA-7 follow-up) ──────────────────
  // The review is now stored and served uncapped -- the prompt no longer limits
  // must-fix entries -- so the modal clips it for display rather than dumping a
  // wall of markdown over the rest of the panel.

  const LONG_REVIEW = [
    "**Overall:** many problems.",
    "",
    "**Must fix (30):**",
    ...Array.from({ length: 30 }, (_, i) => `- **animation_defect** @ 0:${i} — defect number ${i} here`),
    "TAIL_MARKER_ONLY_AT_THE_END",
  ].join("\n");

  it("VIDEO_READY: a long review is clipped and offers Read more", async () => {
    const video = { ...makeVideo("VIDEO_READY"), gemini_feedback: LONG_REVIEW };
    mockFetchFor(video);
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);

    expect(await screen.findByText("AI Review Feedback")).toBeInTheDocument();
    expect(screen.getByTestId("review-read-more")).toBeInTheDocument();
    // The tail is genuinely absent, not merely visually hidden.
    expect(screen.queryByText(/TAIL_MARKER_ONLY_AT_THE_END/)).toBeNull();
    // ...while the start of the review is shown.
    expect(screen.getByText(/many problems/)).toBeInTheDocument();
  });

  it("VIDEO_READY: Read more reveals the whole review, Show less collapses it again", async () => {
    const video = { ...makeVideo("VIDEO_READY"), gemini_feedback: LONG_REVIEW };
    mockFetchFor(video);
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);

    fireEvent.click(await screen.findByTestId("review-read-more"));
    expect(screen.getByText(/TAIL_MARKER_ONLY_AT_THE_END/)).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("review-read-less"));
    expect(screen.queryByText(/TAIL_MARKER_ONLY_AT_THE_END/)).toBeNull();
  });

  it("VIDEO_READY: a short review shows no Read more control", async () => {
    const video = { ...makeVideo("VIDEO_READY"), gemini_feedback: "**Overall:** all good." };
    mockFetchFor(video);
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);

    expect(await screen.findByText("AI Review Feedback")).toBeInTheDocument();
    expect(screen.queryByTestId("review-read-more")).toBeNull();
  });

  it("VIDEO_READY: no gemini_feedback hides the AI Review Feedback panel", async () => {
    const video = makeVideo("VIDEO_READY");
    mockFetchFor(video);
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);

    await screen.findByText("Approve Video"); // wait for the async refresh to settle
    expect(screen.queryByText("AI Review Feedback")).toBeNull();
  });
});

describe("VideoModal — comments come only through Request Revision", () => {
  afterEach(() => vi.restoreAllMocks());

  const ALL_STATUSES: VideoStatus[] = [
    "TOPIC_PROPOSED", "TOPIC_APPROVED", "TOPIC_REJECTED", "SCRIPT_READY", "VOICING",
    "VOICE_READY", "RENDER_QUEUED", "RENDERING", "VIDEO_READY", "REVISION_REQUESTED",
    "VIDEO_APPROVED", "PUBLISHING", "PUBLISHED", "FAILED",
  ];

  it.each(ALL_STATUSES)("%s: the Comments tab is a read-only thread", async (status) => {
    const video = {
      ...makeVideo(status),
      comments: [{ id: 1, video_id: "vid-1", author: "agent" as const,
                   content: "Wrote the script.", created_at: "2026-01-01T00:00:00Z" }],
    };
    mockFetchFor(video);
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);

    fireEvent.click(await screen.findByRole("tab", { name: /Comments/ }));
    // waitFor, not findBy: the panel re-mounts once the modal's refresh lands,
    // which can detach the first match between finding and asserting it.
    await waitFor(() => expect(screen.getByText("Wrote the script.")).toBeInTheDocument());
    expect(screen.getByTestId("comments-readonly-note")).toHaveTextContent("Request Revision");
    expect(screen.queryByPlaceholderText(/Leave a comment/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Send" })).toBeNull();
    // No textarea anywhere until Request Revision is clicked.
    expect(document.querySelector("textarea")).toBeNull();
  });

  it("openRevise opens the Request Revision dialog on mount", async () => {
    const onAction = vi.fn();
    const video = makeVideo("VIDEO_READY");
    mockFetchFor(video);
    render(<VideoModal video={video} openRevise onClose={() => {}} onAction={onAction} />);

    // By role, not text: getByRole skips aria-hidden subtrees, and that is the
    // regression. Opened at the same moment as the modal, a sibling dialog was
    // hidden by the modal (and vice versa), so assistive tech saw neither.
    const textarea = await screen.findByRole("textbox");
    fireEvent.change(textarea, { target: { value: "Captions overlap the title" } });
    fireEvent.click(screen.getByRole("button", { name: "Send Revision Request" }));

    await waitFor(() => expect(onAction).toHaveBeenCalledWith(video.id, "revise-video", video));
  });

  it("openRevise on a rendered video: cancelling leaves the Video tab showing, not the Script", async () => {
    // A rendered video has both, and the default tab prefers Script — so the
    // Quick Actions Revise button names the Video tab, and the modal must honour
    // it alongside openRevise.
    const video = { ...makeVideo("VIDEO_READY"), script: "Test script", video_path: "/output_videos/v.mp4" };
    mockFetchFor(video);
    render(<VideoModal video={video} initialTab="video" openRevise onClose={() => {}} onAction={() => {}} />);

    fireEvent.click(await screen.findByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("textbox")).toBeNull());
    expect(screen.getByRole("tab", { name: "Video" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Script" })).toHaveAttribute("aria-selected", "false");
  });

  it("plays the video's own render, whatever its stored video_path names", async () => {
    // The column is only a "rendered" marker: a tampered or legacy row naming
    // another video's file must not play that file, and a legacy host path
    // must still play this one.
    for (const stored of ["/output_videos/proj_b/vid_b.mp4", "/home/someone/tubematic/mounted/output_videos/proj_a/vid-1.mp4"]) {
      const video = { ...makeVideo("VIDEO_READY"), project_id: "proj_a", video_path: stored };
      mockFetchFor(video);
      const { container, unmount } = render(
        <VideoModal video={video} initialTab="video" onClose={() => {}} onAction={() => {}} />,
      );
      await waitFor(() => expect(container.ownerDocument.querySelector("video")).not.toBeNull());
      expect(container.ownerDocument.querySelector("video")!.getAttribute("src")).toBe("/stream/proj_a/vid-1.mp4");
      unmount();
    }
  });

  it("without openRevise, the dialog stays closed", async () => {
    const video = makeVideo("VIDEO_READY");
    mockFetchFor(video);
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);
    await screen.findByText("Approve Video");
    expect(screen.queryByPlaceholderText("Describe what needs to change...")).toBeNull();
  });
});

describe("VideoModal — Script tab: segmented vs. legacy flat rendering (TMDEV-2)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("legacy video (no script_segments): renders the flat script text unchanged", async () => {
    const video = makeVideo("SCRIPT_READY");
    mockFetchFor(video);
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);

    expect(await screen.findByText("Test script")).toBeInTheDocument();
    expect(screen.queryByText("Visual")).toBeNull();
  });

  it("video with script_segments: renders each segment's voice and visual text", async () => {
    const segments: ScriptSegment[] = [
      { id: "s1", voice: "Hello there.", visual: "[Show intro card]" },
      { id: "s2", voice: "This is segment two.", visual: "[Cut to diagram]" },
    ];
    const video = makeVideo("SCRIPT_READY", segments);
    mockFetchFor(video);
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);

    expect(await screen.findByText("Hello there.")).toBeInTheDocument();
    expect(screen.getByText("This is segment two.")).toBeInTheDocument();
    expect(screen.getByText("[Show intro card]")).toBeInTheDocument();
    expect(screen.getByText("[Cut to diagram]")).toBeInTheDocument();
    expect(screen.getAllByText("Visual")).toHaveLength(2);
    // The flat `script` string must not also be rendered verbatim when segments are present.
    expect(screen.queryByText("Test script")).toBeNull();
  });

  it("video with empty script_segments array falls back to flat script rendering", async () => {
    const video = makeVideo("SCRIPT_READY", []);
    mockFetchFor(video);
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);

    expect(await screen.findByText("Test script")).toBeInTheDocument();
    expect(screen.queryByText("Visual")).toBeNull();
  });

  it("segment with an empty visual note renders an em-dash placeholder", async () => {
    const segments: ScriptSegment[] = [{ id: "s1", voice: "Just narration.", visual: "" }];
    const video = makeVideo("SCRIPT_READY", segments);
    mockFetchFor(video);
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);

    expect(await screen.findByText("Just narration.")).toBeInTheDocument();
    // Not the disabled model picker's "—" option, which SCRIPT_READY also
    // renders now that the agent group is live there (TMDEV-110).
    expect(screen.getAllByText("—").some((el) => el.tagName !== "OPTION")).toBe(true);
  });

  it("segment voice with an inline <phoneme> tag (TMDEV-26 phoneme mode) displays clean text, no markup", async () => {
    const segments: ScriptSegment[] = [
      {
        id: "s1",
        voice: 'The word <phoneme alphabet="cmu-arpabet" ph="M AE1 D IH0 S AH0 N">Madison</phoneme> is here.',
        visual: "",
      },
    ];
    const video = makeVideo("SCRIPT_READY", segments);
    mockFetchFor(video);
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);

    expect(await screen.findByText("The word Madison is here.")).toBeInTheDocument();
    expect(screen.queryByText(/phoneme/)).toBeNull();
  });

  it("segment voice with a <respell> tag (TMDEV-26 follow-up) displays the authored word, not the respelling", async () => {
    const segments: ScriptSegment[] = [
      {
        id: "s1",
        voice: 'Only <respell as="Vah-gar">Vhagar</respell> could match it.',
        visual: "",
      },
    ];
    const video = makeVideo("SCRIPT_READY", segments);
    mockFetchFor(video);
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);

    expect(await screen.findByText("Only Vhagar could match it.")).toBeInTheDocument();
    expect(screen.queryByText(/respell/)).toBeNull();
    expect(screen.queryByText(/Vah-gar/)).toBeNull();
  });

  it("segment voice with an <ipa> tag displays the authored word, never the IPA", async () => {
    const segments: ScriptSegment[] = [
      {
        id: "s1",
        voice: 'Only <ipa ph="vɑːˈɡɑːr">Vhagar</ipa> could match it.',
        visual: "",
      },
    ];
    const video = makeVideo("SCRIPT_READY", segments);
    mockFetchFor(video);
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);

    expect(await screen.findByText("Only Vhagar could match it.")).toBeInTheDocument();
    expect(screen.queryByText(/ipa/)).toBeNull();
    expect(screen.queryByText(/vɑːˈɡɑːr/)).toBeNull();
  });

  it("segment voice with a <break/> tag (TMDEV-26 pause markup) displays clean text, no markup", async () => {
    const segments: ScriptSegment[] = [
      {
        id: "s1",
        voice: 'Here is the catch. <break time="0.6s" /> It never verifies.',
        visual: "",
      },
    ];
    const video = makeVideo("SCRIPT_READY", segments);
    mockFetchFor(video);
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);

    // Single space where the tag was — not the double space a naive strip leaves.
    expect(await screen.findByText("Here is the catch. It never verifies.")).toBeInTheDocument();
    expect(screen.queryByText(/break/)).toBeNull();
  });

  it("segment voice with an eleven_v3 [pause] audio tag displays clean text, no markup", async () => {
    const segments: ScriptSegment[] = [
      { id: "s1", voice: "Here is the catch. [long pause] It never verifies.", visual: "" },
    ];
    const video = makeVideo("SCRIPT_READY", segments);
    mockFetchFor(video);
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);

    expect(await screen.findByText("Here is the catch. It never verifies.")).toBeInTheDocument();
    expect(screen.queryByText(/pause/)).toBeNull();
  });
});

// ── Script profile picker (TMDEV-81) ─────────────────────────────────────────

describe("VideoModal — script profile picker", () => {
  afterEach(() => vi.unstubAllGlobals());

  const PROFILES = [
    { id: "p1", name: "Corpus A", status: "READY" as const, source_urls: [], error: "",
      attempt_count: 1, archived: false,
      created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z" },
  ];

  it("shows no picker when there are no profiles", async () => {
    const video = makeVideo("TOPIC_PROPOSED");
    mockFetchFor(video);
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);
    await screen.findByText("Approve Topic");
    expect(screen.queryByTestId("video-modal-profile-select")).toBeNull();
  });

  it("sends the picked profile with approve-topic, and 'none' when nothing is picked", async () => {
    const video = makeVideo("TOPIC_PROPOSED");
    mockFetchFor(video);
    const onAction = vi.fn();
    render(<VideoModal video={video} scriptProfiles={PROFILES} onClose={() => {}} onAction={onAction} />);

    const select = (await screen.findByTestId("video-modal-profile-select")) as HTMLSelectElement;
    expect(select.value).toBe("");
    fireEvent.click(screen.getByText("Approve Topic"));
    expect(onAction).toHaveBeenCalledWith(video.id, "approve-topic", video,
      { script_profile_id: "", agent_model: "", agent_effort: "", visual_style: "auto" });

    onAction.mockClear();
    render(<VideoModal video={video} scriptProfiles={PROFILES} onClose={() => {}} onAction={onAction} />);
    const selects = (await screen.findAllByTestId("video-modal-profile-select")) as HTMLSelectElement[];
    fireEvent.change(selects[selects.length - 1], { target: { value: "p1" } });
    fireEvent.click(screen.getAllByText("Approve Topic").slice(-1)[0]);
    expect(onAction).toHaveBeenCalledWith(video.id, "approve-topic", video,
      { script_profile_id: "p1", agent_model: "", agent_effort: "", visual_style: "auto" });
  });

  it("sends the selected agent model alongside the profile", async () => {
    const video = makeVideo("TOPIC_PROPOSED");
    mockFetchFor(video);
    const onAction = vi.fn();
    render(<VideoModal video={video} scriptProfiles={PROFILES} agents={[makeAgent()]}
      onClose={() => {}} onAction={onAction} />);

    const select = (await screen.findByTestId("video-modal-model-input")) as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "opus" } });
    fireEvent.click(screen.getByText("Approve Topic"));

    expect(onAction).toHaveBeenCalledWith(video.id, "approve-topic", video,
      { script_profile_id: "", agent_model: "opus", agent_effort: "", visual_style: "auto" });
  });

  it("pre-selects the profile the video already carries", async () => {
    const video = { ...makeVideo("TOPIC_PROPOSED"), script_profile_id: "p1" };
    mockFetchFor(video);
    render(<VideoModal video={video} scriptProfiles={PROFILES} onClose={() => {}} onAction={() => {}} />);
    const select = (await screen.findByTestId("video-modal-profile-select")) as HTMLSelectElement;
    expect(select.value).toBe("p1");
  });

  // TMDEV-145: a seeded domain default may have been deleted since. It must
  // show as what it is and stay clearable, even with no READY profile left.
  it("shows a held profile that is no longer offered, even with none left, and lets it be cleared", async () => {
    const video = { ...makeVideo("TOPIC_PROPOSED"), script_profile_id: "gone" };
    vi.stubGlobal("fetch", vi.fn((url: unknown) => Promise.resolve({ ok: true, json: async () =>
      String(url).includes("/script-profiles/gone")
        ? { id: "gone", name: "Old style", status: "READY", archived: true }
        : video } as Response)));
    const onAction = vi.fn();
    render(<VideoModal video={video} scriptProfiles={[]} onClose={() => {}} onAction={onAction} />);

    const select = (await screen.findByTestId("video-modal-profile-select")) as HTMLSelectElement;
    expect(select.value).toBe("gone");
    await waitFor(() => expect(select.selectedOptions[0].textContent).toBe("Old style (deleted)"));

    fireEvent.change(select, { target: { value: "" } });
    fireEvent.click(screen.getByText("Approve Topic"));
    expect(onAction).toHaveBeenCalledWith(video.id, "approve-topic", video,
      { script_profile_id: "", agent_model: "", agent_effort: "", visual_style: "auto" });
  });
});

// ── Agent model picker (agents table) ─────────────────────────────────────────

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

describe("VideoModal — agent model picker", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("offers the effective agent's models, names the agent, and starts on models[0]", async () => {
    const video = makeVideo("TOPIC_PROPOSED");
    mockFetchFor(video);
    render(<VideoModal video={video} agents={[makeAgent()]} onClose={() => {}} onAction={() => {}} />);
    const select = (await screen.findByTestId("video-modal-model-input")) as HTMLSelectElement;
    expect(select.tagName).toBe("SELECT");
    expect([...select.options].map((o) => o.value)).toEqual(["sonnet", "opus", "haiku"]);
    expect(select.value).toBe("sonnet");
    expect(select.disabled).toBe(false);
    expect((screen.getByTestId("video-modal-agent-select") as HTMLSelectElement).value).toBe("claude");
  });

  it("pre-selects the model the video already carries when the agent offers it", async () => {
    const video = { ...makeVideo("TOPIC_PROPOSED"), agent_model: "haiku" };
    mockFetchFor(video);
    render(<VideoModal video={video} agents={[makeAgent()]} onClose={() => {}} onAction={() => {}} />);
    const select = (await screen.findByTestId("video-modal-model-input")) as HTMLSelectElement;
    expect(select.value).toBe("haiku");
  });

  it("falls back to models[0] when the stored model is no longer offered", async () => {
    const video = { ...makeVideo("TOPIC_PROPOSED"), agent_model: "retired-model" };
    mockFetchFor(video);
    const onAction = vi.fn();
    render(<VideoModal video={video} agents={[makeAgent()]} onClose={() => {}} onAction={onAction} />);
    const select = (await screen.findByTestId("video-modal-model-input")) as HTMLSelectElement;
    expect(select.value).toBe("sonnet");
    fireEvent.click(screen.getByText("Approve Topic"));
    expect(onAction).toHaveBeenCalledWith(video.id, "approve-topic", video,
      { script_profile_id: "", agent_model: "sonnet", agent_effort: "", visual_style: "auto" });
  });

  it("resolves a pinned agent_id over the live default", async () => {
    const video = { ...makeVideo("TOPIC_PROPOSED"), agent_id: "codex" };
    mockFetchFor(video);
    const agents = [makeAgent(), makeAgent({ id: "codex", name: "Codex", models: ["gpt-5", "gpt-5-mini"], is_default: false })];
    render(<VideoModal video={video} agents={agents} onClose={() => {}} onAction={() => {}} />);
    const select = (await screen.findByTestId("video-modal-model-input")) as HTMLSelectElement;
    expect([...select.options].map((o) => o.value)).toEqual(["gpt-5", "gpt-5-mini"]);
    expect((screen.getByTestId("video-modal-agent-select") as HTMLSelectElement).value).toBe("codex");
  });

  it("is disabled, hinted, and sends no model when the agent is uninstalled", async () => {
    const video = { ...makeVideo("TOPIC_PROPOSED"), agent_id: "claude", agent_model: "opus" };
    mockFetchFor(video);
    const onAction = vi.fn();
    render(<VideoModal video={video} agents={[makeAgent({ archived_at: "2026-09-05T00:00:00Z" })]}
      onClose={() => {}} onAction={onAction} />);
    const select = (await screen.findByTestId("video-modal-model-input")) as HTMLSelectElement;
    expect(select.disabled).toBe(true);
    expect(screen.getByTestId("video-modal-model-hint").textContent).toContain("uninstalled");
    const agentSelect = screen.getByTestId("video-modal-agent-select") as HTMLSelectElement;
    expect(agentSelect.selectedOptions[0].text).toBe("Claude Code (uninstalled)");
    expect(agentSelect.selectedOptions[0].disabled).toBe(true);
    fireEvent.click(screen.getByText("Approve Topic"));
    expect(onAction).toHaveBeenCalledWith(video.id, "approve-topic", video,
      { script_profile_id: "", agent_model: "", agent_effort: "", visual_style: "auto" });
  });

  it("is disabled and hinted when no agent is installed", async () => {
    const video = makeVideo("TOPIC_PROPOSED");
    mockFetchFor(video);
    render(<VideoModal video={video} agents={[]} onClose={() => {}} onAction={() => {}} />);
    const select = (await screen.findByTestId("video-modal-model-input")) as HTMLSelectElement;
    expect(select.disabled).toBe(true);
    expect(screen.getByTestId("video-modal-model-hint").textContent).toContain("not installed");
  });

  it("does not claim no agent is installed when the page never loaded the list", async () => {
    // Library, Projects and Archive render this modal without fetching agents.
    const video = makeVideo("TOPIC_PROPOSED");
    mockFetchFor(video);
    const onAction = vi.fn();
    render(<VideoModal video={video} onClose={() => {}} onAction={onAction} />);
    const select = (await screen.findByTestId("video-modal-model-input")) as HTMLSelectElement;
    expect(select.disabled).toBe(true);
    const hint = screen.getByTestId("video-modal-model-hint").textContent ?? "";
    expect(hint).toContain("not loaded");
    expect(hint).not.toContain("not installed");
    fireEvent.click(screen.getByText("Approve Topic"));
    expect(onAction).toHaveBeenCalledWith(video.id, "approve-topic", video,
      { script_profile_id: "", agent_model: "", agent_effort: "", visual_style: "auto" });
  });
});

// ── Frozen choices are shown read-only afterwards (TMDEV-81 follow-up) ───────

describe("VideoModal — read-only profile and model after the topic checkpoint", () => {
  afterEach(() => vi.unstubAllGlobals());

  /** The modal resolves the profile by id rather than from the scriptProfiles
   *  prop, so this stubs both the video refresh and the profile fetch. */
  function mockFetchWithProfile(video: Video, profile: Record<string, unknown> | null) {
    vi.stubGlobal("fetch", vi.fn((url: unknown) => {
      const u = String(url);
      if (u.includes("/script-profiles/")) {
        return Promise.resolve({ ok: true, json: async () => profile ?? {} } as Response);
      }
      return Promise.resolve({ ok: true, json: async () => video } as Response);
    }));
  }

  it("shows the profile name and model while work is in flight", async () => {
    const video = { ...makeVideo("VOICE_READY"), script_profile_id: "p1", agent_model: "opus" };
    mockFetchWithProfile(video, { id: "p1", name: "Corpus A", archived: false });
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);

    expect(await screen.findByText("Corpus A")).toBeInTheDocument();
    expect(screen.getByText("opus")).toBeInTheDocument();
    // ...and no editable control at this status.
    expect(screen.queryByTestId("video-modal-model-input")).toBeNull();
    expect(screen.queryByTestId("video-modal-profile-select")).toBeNull();
  });

  it("spells out the two defaults rather than leaving them blank", async () => {
    const video = makeVideo("VOICE_READY");
    mockFetchWithProfile(video, null);
    render(<VideoModal video={video} agents={[makeAgent()]} onClose={() => {}} onAction={() => {}} />);

    expect(await screen.findByText("None — generic style")).toBeInTheDocument();
    expect(screen.getByText("Claude Code")).toBeInTheDocument();
    // A blank stored model is the agent's own models[0], spelled out.
    expect(screen.getByText("sonnet (default)")).toBeInTheDocument();
  });

  it("marks a profile that has since been deleted", async () => {
    const video = { ...makeVideo("VIDEO_READY"), script_profile_id: "p1" };
    mockFetchWithProfile(video, { id: "p1", name: "Corpus A", archived: true });
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);
    expect(await screen.findByText("Corpus A (deleted)")).toBeInTheDocument();
  });

  it("falls back to the raw id when the profile cannot be resolved", async () => {
    const video = { ...makeVideo("VOICE_READY"), script_profile_id: "gone-forever" };
    vi.stubGlobal("fetch", vi.fn((url: unknown) =>
      String(url).includes("/script-profiles/")
        ? Promise.reject(new Error("404"))
        : Promise.resolve({ ok: true, json: async () => video } as Response)));
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);
    expect(await screen.findByText("gone-forever")).toBeInTheDocument();
  });

  it("does not show the read-only rows while the pickers are still live", async () => {
    const video = makeVideo("TOPIC_PROPOSED");
    mockFetchWithProfile(video, null);
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);
    await screen.findByText("Approve Topic");
    expect(screen.queryByText("None — generic style")).toBeNull();
  });
});

// ── read-only voice and voice model (TMDEV-147) ──────────────────────────────
// The API decides the model (the last voicing call's, else the current
// setting); the modal only presents it, and only where no voice picker is up.

describe("VideoModal — read-only voice and voice model", () => {
  afterEach(() => vi.unstubAllGlobals());

  const VOICES = [{ name: "Adam", voice_id: "a1", model_id: "eleven_v3" }];
  const VOICED = { voice_id: "a1", name: "Adam", model_id: "eleven_v3", model_voiced: true };

  it("shows the voice and the model it was voiced with", async () => {
    const video = { ...makeVideo("VIDEO_READY"), voice_info: VOICED };
    mockFetchFor(video);
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);
    expect(await screen.findByText("Voice model")).toBeInTheDocument();
    expect(screen.getByText("Adam")).toBeInTheDocument();
    expect(screen.getByText("eleven_v3")).toBeInTheDocument();
    expect(screen.queryByText("(current setting)")).toBeNull();
  });

  it("marks a model that is only the voice's current setting", async () => {
    const video = { ...makeVideo("VOICING"), voice_info: { ...VOICED, model_voiced: false } };
    mockFetchFor(video);
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);
    expect(await screen.findByText("(current setting)")).toBeInTheDocument();
  });

  it("shows a voice that left the roster by its id", async () => {
    const video = { ...makeVideo("PUBLISHED"),
      voice_info: { voice_id: "gone", name: "", model_id: "", model_voiced: false } };
    mockFetchFor(video);
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);
    expect(await screen.findByText("(not in roster)")).toBeInTheDocument();
    expect(screen.getByText(/^gone/)).toBeInTheDocument();
  });

  it("is hidden while the voice picker is up", async () => {
    const video = { ...makeVideo("SCRIPT_READY"), voice_info: { ...VOICED, model_voiced: false } };
    mockFetchFor(video);
    render(<VideoModal video={video} voices={VOICES} defaultVoiceId="a1"
      onClose={() => {}} onAction={() => {}} />);
    await screen.findByTestId("video-modal-voice-select");
    expect(screen.queryByText("Voice model")).toBeNull();
  });

  it("shows at a checkpoint when no roster was handed in, so no picker shows", async () => {
    const video = { ...makeVideo("SCRIPT_READY"), voice_info: { ...VOICED, model_voiced: false } };
    mockFetchFor(video);
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);
    expect(await screen.findByText("Voice model")).toBeInTheDocument();
  });

  it("shows on an archived video even with the roster, since nothing is editable", async () => {
    const video = { ...makeVideo("SCRIPT_READY"), archived_at: "2026-02-01T00:00:00Z",
      voice_info: { ...VOICED, model_voiced: false } };
    mockFetchFor(video);
    render(<VideoModal video={video} voices={VOICES} defaultVoiceId="a1"
      onClose={() => {}} onAction={() => {}} />);
    expect(await screen.findByText("Voice model")).toBeInTheDocument();
    expect(screen.queryByTestId("video-modal-voice-select")).toBeNull();
  });
});

// ── the title/topic split ────────────────────────────────────────────────────
// The header shows the short display name; the full descriptive brief moved to
// its own Topic tab, since it is far too long for either the header or the
// 300px sidebar.

const LONG_TOPIC =
  "Why a web app can convert a 2 GB video without ever uploading it, and the two "
  + "HTTP headers it must send to be allowed to. Walk the mechanism in order, then "
  + "close on how to check any tool's claim yourself in one line.";

describe("VideoModal — title and topic", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the short title in the header when the video has one", async () => {
    const video = { ...makeVideo("TOPIC_PROPOSED"), title: "Converting video in the browser", topic: LONG_TOPIC };
    mockFetchFor(video);
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);
    expect(await screen.findByText("Converting video in the browser")).toBeInTheDocument();
  });

  it("falls back to the topic in the header when title is the empty string", async () => {
    // Every pre-split row holds '' here, not null — a `??` fallback would leave
    // the header blank for every video written before the split.
    const video = { ...makeVideo("TOPIC_PROPOSED"), title: "", topic: LONG_TOPIC };
    mockFetchFor(video);
    // The dialog renders through a portal, so it is under baseElement, not container.
    const { baseElement } = render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);
    await screen.findByTestId("video-modal");
    expect(baseElement.querySelector("h2")).toHaveTextContent(LONG_TOPIC);
  });

  it("renders the full brief in the Topic tab", async () => {
    const video = { ...makeVideo("TOPIC_PROPOSED"), title: "A short name", topic: LONG_TOPIC };
    mockFetchFor(video);
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);
    expect(await screen.findByTestId("video-topic-body")).toHaveTextContent(LONG_TOPIC);
  });

  it("opens on the Topic tab for a video with no script and no render yet", async () => {
    // A TOPIC_PROPOSED video is exactly when a human is reading the brief to
    // decide approve or reject, so the brief is the tab that should be showing.
    const video = { ...makeVideo("TOPIC_PROPOSED"), title: "A short name", topic: LONG_TOPIC };
    mockFetchFor(video);
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);
    const tab = await screen.findByRole("tab", { name: "Topic" });
    expect(tab).toHaveAttribute("aria-selected", "true");
  });

  it("keeps the Topic tab available once a script exists, without stealing the default", async () => {
    // Topic leads the strip but must not displace Script — that is what a human
    // opens a scripted video for.
    const video = { ...makeVideo("SCRIPT_READY"), title: "A short name", topic: LONG_TOPIC };
    mockFetchFor(video);
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);
    expect(await screen.findByRole("tab", { name: "Topic" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Script" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Topic" })).toHaveAttribute("aria-selected", "false");
  });
});

// ── Publishing (TMDEV-83) ───────────────────────────────────────────────────
//
// Two things worth pinning beyond "the button renders". First, the publish
// affordance is gated on settings.publishing_enabled, and the default is off —
// a page that does not fetch settings (Library, Projects) must not offer
// publishing at all. Second, PUBLISHING/PUBLISHED stay in VideoStatus and keep
// rendering; hiding is a UI filter and never a state-machine change.

function mockFetchWithPublications(video: Video, publications: unknown[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: unknown, init?: RequestInit) => {
      if (init?.method === "POST") {
        return Promise.resolve({ ok: true, json: async () => ({ ok: true }) } as Response);
      }
      if (String(url).includes("/publications")) {
        return Promise.resolve({ ok: true, json: async () => publications } as Response);
      }
      return Promise.resolve({ ok: true, json: async () => video } as Response);
    }),
  );
}

const LIVE_POST = {
  id: "pub1", video_id: "vid-1", platform: "youtube", social_account_id: "spc_yt",
  status: "PUBLISHED", post_url: "https://yt/1", error: "", published_at: "2026-01-02T00:00:00Z",
  created_at: "2026-01-02T00:00:00Z", updated_at: "2026-01-02T00:00:00Z",
};

describe("VideoModal — publishing", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("offers Publish at VIDEO_APPROVED when publishing is enabled", async () => {
    const video = makeVideo("VIDEO_APPROVED");
    mockFetchFor(video);
    render(<VideoModal video={video} publishingEnabled onClose={() => {}} onAction={() => {}} />);
    expect(await screen.findByText("Publish…")).toBeInTheDocument();
  });

  it("hides Publish when publishing is disabled", async () => {
    const video = makeVideo("VIDEO_APPROVED");
    mockFetchFor(video);
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);
    await screen.findByTestId("video-modal");
    expect(screen.queryByText("Publish…")).toBeNull();
  });

  it("defaults to hidden, so a page that never fetches settings cannot publish", async () => {
    const video = makeVideo("VIDEO_APPROVED");
    mockFetchFor(video);
    // No publishingEnabled prop at all — Library and Projects render it this way.
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);
    await screen.findByTestId("video-modal");
    expect(screen.queryByText("Publish…")).toBeNull();
  });

  it("VIDEO_READY approves rather than publishes — the old button never published", async () => {
    const onAction = vi.fn();
    const video = makeVideo("VIDEO_READY");
    mockFetchFor(video);
    render(<VideoModal video={video} onClose={() => {}} onAction={onAction} />);
    fireEvent.click(await screen.findByText("Approve Video"));
    expect(onAction).toHaveBeenCalledWith("vid-1", "approve-video", expect.anything());
  });

  it("shows a Publishing Results tab once the video has been published somewhere", async () => {
    const video = makeVideo("PUBLISHED");
    mockFetchWithPublications(video, [LIVE_POST]);
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);
    expect(await screen.findByText("Publishing Results")).toBeInTheDocument();
  });

  it("hides the tab on a video that was never published", async () => {
    const video = makeVideo("VIDEO_READY");
    mockFetchWithPublications(video, []);
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);
    await screen.findByTestId("video-modal");
    expect(screen.queryByText("Publishing Results")).toBeNull();
  });

  it("links to each live post instead of a single YouTube URL", async () => {
    const video = makeVideo("PUBLISHED");
    mockFetchWithPublications(video, [
      LIVE_POST,
      { ...LIVE_POST, id: "pub2", platform: "instagram", post_url: "https://ig/2" },
    ]);
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);
    const section = await screen.findByTestId("video-modal-published-to");
    // Brand spellings, not CSS capitalisation of the stored lower-case name.
    expect(within(section).getByText("YouTube →")).toBeInTheDocument();
    expect(within(section).getByText("Instagram →")).toBeInTheDocument();
  });

  it("keeps live-post links out of the Actions block", async () => {
    // Opening a post is navigation, not an action on the video.
    const video = makeVideo("PUBLISHED");
    mockFetchWithPublications(video, [LIVE_POST]);
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);
    await screen.findByTestId("video-modal-published-to");
    expect(within(screen.getByTestId("video-modal-actions")).queryByText("YouTube →")).toBeNull();
  });

  it("shows no Actions block at all when the only thing left is a live post", async () => {
    // An archived published video: nothing can be done to it, but it still
    // links to where it went. The heading used to hold just "Youtube →".
    const video = { ...makeVideo("PUBLISHED"), archived_at: "2026-09-01T00:00:00Z" };
    mockFetchWithPublications(video, [LIVE_POST]);
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);
    expect(await screen.findByTestId("video-modal-published-to")).toBeInTheDocument();
    expect(screen.queryByTestId("video-modal-actions")).toBeNull();
  });

  it("labels the Publishing Results rows with the brand spelling", async () => {
    const video = makeVideo("PUBLISHED");
    mockFetchWithPublications(video, [{ ...LIVE_POST, platform: "tiktok" }]);
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);
    fireEvent.click(await screen.findByText("Publishing Results"));
    expect(await screen.findByTestId("publication-pub1")).toHaveTextContent("TikTok");
  });

  it("surfaces a per-account failure rather than hiding it behind the video status", async () => {
    // A video is PUBLISHED if ANY target succeeded, so the one that failed is
    // only ever visible on its own row.
    const video = makeVideo("PUBLISHED");
    mockFetchWithPublications(video, [
      LIVE_POST,
      { ...LIVE_POST, id: "pub2", platform: "instagram", status: "FAILED",
        post_url: "", error: "account disconnected" },
    ]);
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);
    // The tab content only mounts once selected — a PUBLISHED video with a
    // render defaults to the Video tab.
    fireEvent.click(await screen.findByText("Publishing Results"));
    expect(await screen.findByTestId("publication-error-pub2"))
      .toHaveTextContent("account disconnected");
  });

  it("shows the live URL itself, not a generic link label", async () => {
    // It is the thing you copy, paste and check — and seeing it confirms which
    // account the video actually landed on.
    const video = makeVideo("PUBLISHED");
    mockFetchWithPublications(video, [LIVE_POST]);
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);
    fireEvent.click(await screen.findByText("Publishing Results"));
    const link = await screen.findByTestId("publication-url-pub1");
    expect(link).toHaveTextContent("https://yt/1");
    expect(link).toHaveAttribute("href", "https://yt/1");
  });

  it("gives a failed target no link, only the reason", async () => {
    const video = makeVideo("PUBLISHED");
    mockFetchWithPublications(video, [
      { ...LIVE_POST, id: "pubX", platform: "tiktok", status: "FAILED",
        post_url: "", error: "account disconnected" },
    ]);
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);
    fireEvent.click(await screen.findByText("Publishing Results"));
    expect(await screen.findByTestId("publication-error-pubX")).toBeInTheDocument();
    expect(screen.queryByTestId("publication-url-pubX")).toBeNull();
  });
});

/**
 * Per-video Logs tab (TMDEV-86).
 *
 * The regression worth guarding is the tab-order one: adding a tab at the front
 * of `leftTabs` previously hijacked `defaultLeftTab` and broke eight tests, so
 * Logs goes last and the script -> video -> topic precedence must be unmoved.
 */
describe("VideoModal — Logs tab", () => {
  function mockFetchWithLogs(video: Video, records: unknown[]) {
    const fn = vi.fn((url: unknown, init?: RequestInit) => {
      if (init?.method === "POST") {
        return Promise.resolve({ ok: true, json: async () => ({ ok: true }) } as Response);
      }
      if (String(url).includes("/logs")) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ records, count: records.length, limit: 200,
                               services: [], levels: [] }),
        } as Response);
      }
      return Promise.resolve({ ok: true, json: async () => video } as Response);
    });
    vi.stubGlobal("fetch", fn);
    return fn;
  }

  const LOG = {
    ts: "2026-09-06T12:00:00Z", service: "renderer", level: "error",
    message: "render failed", video_id: "vid-1",
  };

  afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

  it("requests logs scoped to this video, with no service filter", async () => {
    // Deliberately unscoped by service: one video's trail spans the renderer,
    // the MCP tools and the API.
    const video = makeVideo("VIDEO_READY");
    const fn = mockFetchWithLogs(video, [LOG]);
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);

    await waitFor(() => {
      const call = fn.mock.calls.find((c) => String(c[0]).includes("/logs"));
      expect(call).toBeTruthy();
      expect(String(call![0])).toContain("video_id=vid-1");
      expect(String(call![0])).not.toContain("service=");
    });
  });

  it("shows the tab and its records", async () => {
    const video = makeVideo("VIDEO_READY");
    mockFetchWithLogs(video, [LOG]);
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);

    fireEvent.click(await screen.findByRole("tab", { name: /logs/i }));
    expect(await screen.findByTestId("video-log-list")).toHaveTextContent("render failed");
  });

  it("is present even when the video has no publications", async () => {
    // It is most useful exactly when nothing about the video worked, so it must
    // not be gated on success the way Publishing Results is.
    const video = makeVideo("TOPIC_PROPOSED");
    mockFetchWithLogs(video, []);
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);

    expect(await screen.findByRole("tab", { name: /logs/i })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /publishing results/i })).toBeNull();
  });

  it("does not steal the default tab from script, video or topic", async () => {
    const scripted = makeVideo("SCRIPT_READY");
    mockFetchWithLogs(scripted, [LOG]);
    const { unmount } = render(
      <VideoModal video={scripted} onClose={() => {}} onAction={() => {}} />);
    await waitFor(() => {
      expect(screen.getByRole("tab", { name: "Script" })).toHaveAttribute("aria-selected", "true");
      expect(screen.getByRole("tab", { name: "Logs" })).toHaveAttribute("aria-selected", "false");
    });
    unmount();

    const proposed = makeVideo("TOPIC_PROPOSED");
    mockFetchWithLogs(proposed, [LOG]);
    render(<VideoModal video={proposed} onClose={() => {}} onAction={() => {}} />);
    await waitFor(() => {
      expect(screen.getByRole("tab", { name: "Topic" })).toHaveAttribute("aria-selected", "true");
      expect(screen.getByRole("tab", { name: "Logs" })).toHaveAttribute("aria-selected", "false");
    });
  });

  it("explains an empty result rather than showing a bare blank", async () => {
    const video = makeVideo("VIDEO_READY");
    mockFetchWithLogs(video, []);
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);

    fireEvent.click(await screen.findByRole("tab", { name: /logs/i }));
    expect(await screen.findByTestId("video-log-list-empty")).toHaveTextContent("older video");
  });

  it("survives a failed logs fetch without breaking the rest of the modal", async () => {
    const video = makeVideo("VIDEO_READY");
    vi.stubGlobal("fetch", vi.fn((url: unknown) =>
      String(url).includes("/logs")
        ? Promise.reject(new Error("boom"))
        : Promise.resolve({ ok: true, json: async () => video } as Response)));
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);

    fireEvent.click(await screen.findByRole("tab", { name: /logs/i }));
    expect(await screen.findByTestId("video-log-list-empty")).toBeInTheDocument();
  });
});

// ── Agent effort picker (TMDEV-106) ─────────────────────────────────────────

describe("VideoModal — agent effort picker", () => {
  afterEach(() => vi.restoreAllMocks());

  it("offers the five CLI levels plus a blank that names the agent's own", async () => {
    const video = makeVideo("TOPIC_PROPOSED");
    mockFetchFor(video);
    render(<VideoModal video={video} agents={[makeAgent({ effort: "low" })]} onClose={() => {}} onAction={() => {}} />);
    const select = (await screen.findByTestId("video-modal-effort-input")) as HTMLSelectElement;
    expect([...select.options].map((o) => o.value))
      .toEqual(["", "low", "medium", "high", "xhigh", "max"]);
    expect(select.value).toBe("");
    expect([...select.options][0].textContent).toBe("low (agent default)");
  });

  it("never submits a guessed level when the page passes no agents", async () => {
    /* Projects and Library render this modal without the agents prop at all,
       so there is nothing to resolve a default from. Submitting a literal
       would silently override the assigned agent's level — and agent_effort
       is frozen at approval, so it could never be corrected afterwards. */
    const video = makeVideo("TOPIC_PROPOSED");
    mockFetchFor(video);
    const onAction = vi.fn();
    render(<VideoModal video={video} onClose={() => {}} onAction={onAction} />);
    const select = (await screen.findByTestId("video-modal-effort-input")) as HTMLSelectElement;
    expect(select.value).toBe("");
    expect([...select.options][0].textContent).toBe("Agent default");
    fireEvent.click(screen.getByText("Approve Topic"));
    expect(onAction).toHaveBeenCalledWith(video.id, "approve-topic", video,
      expect.objectContaining({ agent_effort: "" }));
  });

  it("forgets a pick when a different video is opened", async () => {
    /* This modal stays mounted between videos — the seed-change effect is the
       only thing that clears per-video picker state. Without resetting this
       one, an effort picked for the first video is inherited by the second and
       written on approval even though its picker was never touched. */
    const first = { ...makeVideo("TOPIC_PROPOSED"), id: "vid-first" };
    const second = { ...makeVideo("TOPIC_PROPOSED"), id: "vid-second" };
    mockFetchFor(first);
    const onAction = vi.fn();
    const { rerender } = render(
      <VideoModal video={first} agents={[makeAgent()]} onClose={() => {}} onAction={onAction} />);
    const select = (await screen.findByTestId("video-modal-effort-input")) as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "max" } });
    expect(select.value).toBe("max");

    mockFetchFor(second);
    rerender(<VideoModal video={second} agents={[makeAgent()]} onClose={() => {}} onAction={onAction} />);
    await waitFor(() => {
      expect((screen.getByTestId("video-modal-effort-input") as HTMLSelectElement).value)
        .toBe("");
    });
    fireEvent.click(screen.getByText("Approve Topic"));
    expect(onAction).toHaveBeenCalledWith(second.id, "approve-topic", expect.anything(),
      expect.objectContaining({ agent_effort: "" }));
  });

  it("stays usable when the model picker is disabled", async () => {
    /* The levels come from the CLI, not from the agent's probed model list. */
    const video = { ...makeVideo("TOPIC_PROPOSED"), agent_id: "claude" };
    mockFetchFor(video);
    render(<VideoModal video={video} agents={[makeAgent({ archived_at: "2026-09-05T00:00:00Z" })]}
      onClose={() => {}} onAction={() => {}} />);
    const effort = (await screen.findByTestId("video-modal-effort-input")) as HTMLSelectElement;
    const model = screen.getByTestId("video-modal-model-input") as HTMLSelectElement;
    expect(model.disabled).toBe(true);
    expect(effort.disabled).toBe(false);
  });

  it("sends the picked effort with approve-topic", async () => {
    const video = makeVideo("TOPIC_PROPOSED");
    mockFetchFor(video);
    const onAction = vi.fn();
    render(<VideoModal video={video} agents={[makeAgent()]} onClose={() => {}} onAction={onAction} />);
    const select = await screen.findByTestId("video-modal-effort-input");
    fireEvent.change(select, { target: { value: "xhigh" } });
    fireEvent.click(screen.getByText("Approve Topic"));
    expect(onAction).toHaveBeenCalledWith(video.id, "approve-topic", video,
      { script_profile_id: "", agent_model: "sonnet", agent_effort: "xhigh",
        visual_style: "auto" });
  });

  it("shows the frozen choice read-only while work is in flight", async () => {
    const video = { ...makeVideo("VOICE_READY"), agent_effort: "max" };
    mockFetchFor(video);
    render(<VideoModal video={video} agents={[makeAgent()]} onClose={() => {}} onAction={() => {}} />);
    expect(await screen.findByText("Agent effort")).toBeTruthy();
    expect(screen.queryByTestId("video-modal-effort-input")).toBeNull();
  });
});

describe("VideoModal — picker labels", () => {
  /* The actions block stacks the pickers one under another with near-identical
     option text (a model name and an effort level look alike), so without a
     caption a human can only tell them apart by position. Resolving each by its
     label also proves the caption is the control's accessible name. */
  afterEach(() => vi.unstubAllGlobals());

  const PROFILE = {
    id: "p1", name: "Corpus A", status: "READY" as const, source_urls: [], error: "",
    attempt_count: 1, archived: false,
    created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
  };

  it("labels every topic-checkpoint picker, and names the agent", async () => {
    const video = makeVideo("TOPIC_PROPOSED");
    mockFetchFor(video);
    render(<VideoModal video={video} scriptProfiles={[PROFILE]} agents={[makeAgent()]}
      onClose={() => {}} onAction={() => {}} />);
    await screen.findByText("Approve Topic");
    const actions = screen.getByTestId("video-modal-actions");
    expect(within(actions).getByLabelText("Visual style")).toBe(screen.getByTestId("video-modal-style-select"));
    expect(within(actions).getByLabelText("Script profile")).toBe(screen.getByTestId("video-modal-profile-select"));
    expect(within(actions).getByLabelText("Model")).toBe(screen.getByTestId("video-modal-model-input"));
    expect(within(actions).getByLabelText("Effort")).toBe(screen.getByTestId("video-modal-effort-input"));
    expect(within(actions).getByLabelText("Agent")).toBe(screen.getByTestId("video-modal-agent-select"));
  });

  it("disables Illustrated in the style picker when no OpenAI key is stored", async () => {
    const video = makeVideo("TOPIC_PROPOSED");
    mockFetchFor(video);
    render(<VideoModal video={video} illustratedAvailable={false}
      onClose={() => {}} onAction={() => {}} />);
    await screen.findByText("Approve Topic");
    const select = screen.getByTestId("video-modal-style-select") as HTMLSelectElement;
    const illustrated = [...select.options].find((o) => o.value === "illustrated")!;
    expect(illustrated.disabled).toBe(true);
    expect(illustrated.textContent).toMatch(/needs an OpenAI key/);
  });

  it("leaves Illustrated enabled by default", async () => {
    const video = makeVideo("TOPIC_PROPOSED");
    mockFetchFor(video);
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}} />);
    await screen.findByText("Approve Topic");
    const select = screen.getByTestId("video-modal-style-select") as HTMLSelectElement;
    expect([...select.options].some((o) => o.disabled)).toBe(false);
  });

  it("labels the voice picker at the script checkpoint", async () => {
    const video = makeVideo("SCRIPT_READY");
    mockFetchFor(video);
    render(<VideoModal video={video} onClose={() => {}} onAction={() => {}}
      voices={[{ name: "Narrator", voice_id: "abc123", model_id: "eleven_multilingual_v2" }]} defaultVoiceId="abc123" />);
    await screen.findByText("Approve Script");
    expect(within(screen.getByTestId("video-modal-actions")).getByLabelText("Voice"))
      .toBe(screen.getByTestId("video-modal-voice-select"));
  });
});

// ── Changing the agent at every checkpoint (TMDEV-110) ───────────────────────

describe("VideoModal — agent picker", () => {
  afterEach(() => vi.unstubAllGlobals());

  const CLAUDE = makeAgent();
  const CODEX = makeAgent({ id: "codex", name: "Codex", models: ["gpt-5", "gpt-5-mini"], is_default: false });
  const OLD = makeAgent({ id: "old", name: "Old", is_default: false, archived_at: "2026-09-05T00:00:00Z" });
  const AGENTS = [CLAUDE, CODEX, OLD];
  const pinned = (status: VideoStatus) => ({ ...makeVideo(status), agent_id: "claude", agent_model: "opus" });

  async function agentSelect() {
    return (await screen.findByTestId("video-modal-agent-select")) as HTMLSelectElement;
  }

  it.each(["TOPIC_PROPOSED", "SCRIPT_READY", "VIDEO_READY"] as const)(
    "%s: offers every live agent and no uninstalled one", async (status) => {
      const video = pinned(status);
      mockFetchFor(video);
      render(<VideoModal video={video} agents={AGENTS} onClose={() => {}} onAction={() => {}} />);
      expect([...(await agentSelect()).options].map((o) => o.value)).toEqual(["claude", "codex"]);
    });

  it("is not offered once an agent holds the video", async () => {
    const video = pinned("VOICE_READY");
    mockFetchFor(video);
    render(<VideoModal video={video} agents={AGENTS} onClose={() => {}} onAction={() => {}} />);
    expect(await screen.findByText("Agent effort")).toBeTruthy();
    expect(screen.queryByTestId("video-modal-agent-select")).toBeNull();
  });

  it("switching agent swaps in its models at its default, and says so", async () => {
    const video = pinned("SCRIPT_READY");
    mockFetchFor(video);
    render(<VideoModal video={video} agents={AGENTS} onClose={() => {}} onAction={() => {}} />);
    fireEvent.change(await agentSelect(), { target: { value: "codex" } });
    const model = screen.getByTestId("video-modal-model-input") as HTMLSelectElement;
    expect([...model.options].map((o) => o.value)).toEqual(["gpt-5", "gpt-5-mini"]);
    expect(model.value).toBe("gpt-5");
    expect(screen.getByTestId("video-modal-agent-reset-note").textContent)
      .toBe("Model reset to Codex's default");
  });

  it("Approve Script left alone sends only the voice", async () => {
    const video = pinned("SCRIPT_READY");
    mockFetchFor(video);
    const onAction = vi.fn();
    render(<VideoModal video={video} agents={AGENTS} onClose={() => {}} onAction={onAction} />);
    fireEvent.click(await screen.findByText("Approve Script"));
    expect(onAction).toHaveBeenCalledWith(video.id, "approve-script", video, { voice_id: "" });
  });

  it("Approve Script carries a changed agent and its default model", async () => {
    const video = pinned("SCRIPT_READY");
    mockFetchFor(video);
    const onAction = vi.fn();
    render(<VideoModal video={video} agents={AGENTS} onClose={() => {}} onAction={onAction} />);
    fireEvent.change(await agentSelect(), { target: { value: "codex" } });
    fireEvent.click(screen.getByText("Approve Script"));
    expect(onAction).toHaveBeenCalledWith(video.id, "approve-script", video,
      { voice_id: "", agent_id: "codex", agent_model: "gpt-5" });
  });

  it("Approve Video carries nothing — it hands no work to an agent", async () => {
    const video = pinned("VIDEO_READY");
    mockFetchFor(video);
    const onAction = vi.fn();
    render(<VideoModal video={video} agents={AGENTS} onClose={() => {}} onAction={onAction} />);
    fireEvent.change(await agentSelect(), { target: { value: "codex" } });
    fireEvent.click(screen.getByText("Approve Video"));
    expect(onAction).toHaveBeenCalledWith(video.id, "approve-video", video);
  });

  it.each([
    ["TOPIC_PROPOSED", "revise-topic"],
    ["SCRIPT_READY", "revise-script"],
    ["VIDEO_READY", "revise-video"],
  ] as const)("%s: Request Revision hands the revision to the picked agent", async (status, action) => {
    const video = pinned(status);
    mockFetchFor(video);
    const onAction = vi.fn();
    render(<VideoModal video={video} agents={AGENTS} onClose={() => {}} onAction={onAction} />);
    fireEvent.change(await agentSelect(), { target: { value: "codex" } });
    fireEvent.change(screen.getByTestId("video-modal-effort-input"), { target: { value: "max" } });
    await requestRevision("Try again");
    await waitFor(() => expect(onAction).toHaveBeenCalledWith(video.id, action, video,
      { agent_id: "codex", agent_model: "gpt-5", agent_effort: "max" }));
  });

  it("opens seeded with the picks the inbox row handed over", async () => {
    const video = pinned("SCRIPT_READY");
    mockFetchFor(video);
    const onAction = vi.fn();
    render(<VideoModal video={video} agents={AGENTS} openRevise
      initialPicks={{ agentId: "codex", model: "gpt-5-mini", effort: null }}
      onClose={() => {}} onAction={onAction} />);
    const textarea = await screen.findByPlaceholderText("Describe what needs to change...");
    expect((screen.getByTestId("video-modal-agent-select") as HTMLSelectElement).value).toBe("codex");
    fireEvent.change(textarea, { target: { value: "Tighter intro" } });
    fireEvent.click(screen.getByText("Send Revision Request"));
    await waitFor(() => expect(onAction).toHaveBeenCalledWith(video.id, "revise-script", video,
      { agent_id: "codex", agent_model: "gpt-5-mini" }));
  });

  it("forgets a picked agent when a different video is opened", async () => {
    const first = { ...pinned("SCRIPT_READY"), id: "vid-first" };
    const second = { ...pinned("SCRIPT_READY"), id: "vid-second" };
    mockFetchFor(first);
    const onAction = vi.fn();
    const { rerender } = render(
      <VideoModal video={first} agents={AGENTS} onClose={() => {}} onAction={onAction} />);
    fireEvent.change(await agentSelect(), { target: { value: "codex" } });
    mockFetchFor(second);
    rerender(<VideoModal video={second} agents={AGENTS} onClose={() => {}} onAction={onAction} />);
    await waitFor(() => expect((screen.getByTestId("video-modal-agent-select") as HTMLSelectElement).value)
      .toBe("claude"));
    fireEvent.click(screen.getByText("Approve Script"));
    expect(onAction).toHaveBeenCalledWith(second.id, "approve-script", expect.anything(), { voice_id: "" });
  });

  it("without an agent list, says the pinned choice stays, and sends nothing for it", async () => {
    const video = pinned("SCRIPT_READY");
    mockFetchFor(video);
    const onAction = vi.fn();
    render(<VideoModal video={video} onClose={() => {}} onAction={onAction} />);
    expect(await screen.findByTestId("video-modal-agent-name")).toBeTruthy();
    expect(screen.getByTestId("video-modal-model-hint").textContent)
      .toBe("Agent list not loaded here — the agent and model stay as they are.");
    fireEvent.click(screen.getByText("Approve Script"));
    expect(onAction).toHaveBeenCalledWith(video.id, "approve-script", video, { voice_id: "" });
  });
});

// ── Voice at the topic checkpoint (TMDEV-127) ────────────────────────────────
// Same contract as the Quick Actions row: the picker holds null until touched,
// an untouched Approve Topic sends no voice_id (so it cannot pin the install
// default over a project-seeded voice), and the shown voice is derived, so it
// follows a roster that answers late.

describe("VideoModal — voice at TOPIC_PROPOSED", () => {
  afterEach(() => vi.restoreAllMocks());

  const VOICES = [
    { name: "Narrator", voice_id: "abc123", model_id: "eleven_multilingual_v2" },
    { name: "Expressive", voice_id: "v3voice", model_id: "eleven_v3" },
  ];

  it("offers the voices, starting on the video's own", async () => {
    const video = { ...makeVideo("TOPIC_PROPOSED"), voice_id: "v3voice" };
    mockFetchFor(video);
    render(<VideoModal video={video} voices={VOICES} defaultVoiceId="abc123"
      onClose={() => {}} onAction={() => {}} />);
    const select = await screen.findByTestId("video-modal-voice-select") as HTMLSelectElement;
    expect(select.value).toBe("v3voice");
    expect(screen.getByRole("option", { name: "Expressive · eleven_v3" })).toBeTruthy();
    expect(screen.getByTestId("voice-preview-v3voice")).toBeTruthy();
  });

  it("an untouched picker sends no voice_id with Approve Topic", async () => {
    const onAction = vi.fn();
    const video = { ...makeVideo("TOPIC_PROPOSED"), voice_id: "v3voice" };
    mockFetchFor(video);
    render(<VideoModal video={video} voices={VOICES} defaultVoiceId="abc123"
      onClose={() => {}} onAction={onAction} />);
    await screen.findByTestId("video-modal-voice-select");
    fireEvent.click(screen.getByText("Approve Topic"));
    expect(onAction.mock.calls[0][1]).toBe("approve-topic");
    expect(onAction.mock.calls[0][3]).not.toHaveProperty("voice_id");
  });

  it("a picked voice travels with Approve Topic", async () => {
    const onAction = vi.fn();
    const video = makeVideo("TOPIC_PROPOSED");
    mockFetchFor(video);
    render(<VideoModal video={video} voices={VOICES} defaultVoiceId="abc123"
      onClose={() => {}} onAction={onAction} />);
    fireEvent.change(await screen.findByTestId("video-modal-voice-select"),
      { target: { value: "v3voice" } });
    fireEvent.click(screen.getByText("Approve Topic"));
    expect(onAction).toHaveBeenCalledWith(video.id, "approve-topic", expect.anything(),
      expect.objectContaining({ voice_id: "v3voice" }));
  });

  it("forgets a picked voice when a different video is opened", async () => {
    const first = { ...makeVideo("TOPIC_PROPOSED"), id: "vid-first" };
    const second = { ...makeVideo("TOPIC_PROPOSED"), id: "vid-second" };
    mockFetchFor(first);
    const onAction = vi.fn();
    const { rerender } = render(<VideoModal video={first} voices={VOICES} defaultVoiceId="abc123"
      onClose={() => {}} onAction={onAction} />);
    fireEvent.change(await screen.findByTestId("video-modal-voice-select"),
      { target: { value: "v3voice" } });

    mockFetchFor(second);
    rerender(<VideoModal video={second} voices={VOICES} defaultVoiceId="abc123"
      onClose={() => {}} onAction={onAction} />);
    await waitFor(() => {
      expect((screen.getByTestId("video-modal-voice-select") as HTMLSelectElement).value)
        .toBe("abc123");
    });
    fireEvent.click(screen.getByText("Approve Topic"));
    expect(onAction.mock.calls[0][0]).toBe(second.id);
    expect(onAction.mock.calls[0][3]).not.toHaveProperty("voice_id");
  });

  it("SCRIPT_READY approves with a default that arrived after the modal opened", async () => {
    const onAction = vi.fn();
    const video = makeVideo("SCRIPT_READY");
    mockFetchFor(video);
    const { rerender } = render(<VideoModal video={video} voices={VOICES} defaultVoiceId=""
      onClose={() => {}} onAction={onAction} />);
    await screen.findByTestId("video-modal-voice-select");
    rerender(<VideoModal video={video} voices={VOICES} defaultVoiceId="abc123"
      onClose={() => {}} onAction={onAction} />);
    expect((screen.getByTestId("video-modal-voice-select") as HTMLSelectElement).value).toBe("abc123");
    fireEvent.click(screen.getByText("Approve Script"));
    expect(onAction).toHaveBeenCalledWith(video.id, "approve-script", video, { voice_id: "abc123" });
  });
});

describe("VideoModal — scheduled publishing (TMDEV-133)", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  const SCHEDULED: Video = {
    ...makeVideo("SCHEDULED"),
    scheduled_at: "2026-10-01T03:30:00Z",
    scheduled_timezone: "Asia/Kolkata",
  };
  const WAITING_POST = { ...LIVE_POST, status: "PENDING", post_url: "", published_at: "" };

  it("says when the post goes out, in the zone it was picked in, even without publishing controls", async () => {
    mockFetchWithPublications(SCHEDULED, [WAITING_POST]);
    // No publishingEnabled — the Library renders it this way.
    render(<VideoModal video={SCHEDULED} onClose={() => {}} onAction={() => {}} />);
    const banner = await screen.findByTestId("video-modal-scheduled-for");
    expect(banner).toHaveTextContent("Oct 1, 2026");
    expect(banner).toHaveTextContent("9:00 AM");
    expect(banner).toHaveTextContent("Asia/Kolkata");
    // And the same instant in the host's zone, since it differs.
    expect(banner).toHaveTextContent("Sep 30, 2026, 11:30 PM EDT (UTC-04:00)");
    expect(screen.queryByText("Cancel schedule")).toBeNull();
  });

  it("labels a waiting target SCHEDULED rather than PENDING", async () => {
    mockFetchWithPublications(SCHEDULED, [WAITING_POST]);
    render(<VideoModal video={SCHEDULED} onClose={() => {}} onAction={() => {}} />);
    fireEvent.click(await screen.findByText("Publishing Results"));
    expect(within(await screen.findByTestId("publication-pub1")).getByText("SCHEDULED"))
      .toBeInTheDocument();
  });

  it("cancels through the API after a confirm", async () => {
    mockFetchWithPublications(SCHEDULED, [WAITING_POST]);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<VideoModal video={SCHEDULED} publishingEnabled onClose={() => {}} onAction={() => {}} />);
    await act(async () => {
      fireEvent.click(await screen.findByText("Cancel schedule"));
    });
    const calls = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls;
    expect(calls.some(([u, init]) =>
      String(u).endsWith("/videos/vid-1/schedule/cancel") && init?.method === "POST")).toBe(true);
  });

  it("does nothing when the confirm is declined", async () => {
    mockFetchWithPublications(SCHEDULED, [WAITING_POST]);
    vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<VideoModal video={SCHEDULED} publishingEnabled onClose={() => {}} onAction={() => {}} />);
    await act(async () => {
      fireEvent.click(await screen.findByText("Cancel schedule"));
    });
    const calls = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls;
    expect(calls.some(([u]) => String(u).includes("/schedule/cancel"))).toBe(false);
  });

  it("shows the API's refusal inline", async () => {
    vi.stubGlobal("fetch", vi.fn((url: unknown, init?: RequestInit) => {
      if (String(url).includes("/schedule/cancel")) {
        return Promise.resolve({ ok: false, json: async () => ({
          error: "postforme has already started sending this post, so it can no longer be cancelled.",
        }) } as Response);
      }
      if (String(url).includes("/publications")) {
        return Promise.resolve({ ok: true, json: async () => [WAITING_POST] } as Response);
      }
      return Promise.resolve({ ok: true, json: async () => (init?.method ? { ok: true } : SCHEDULED) } as Response);
    }));
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<VideoModal video={SCHEDULED} publishingEnabled onClose={() => {}} onAction={() => {}} />);
    await act(async () => {
      fireEvent.click(await screen.findByText("Cancel schedule"));
    });
    expect(await screen.findByTestId("cancel-schedule-error"))
      .toHaveTextContent("can no longer be cancelled");
  });

  it("offers no Delete on a scheduled video", async () => {
    mockFetchWithPublications(SCHEDULED, [WAITING_POST]);
    render(<VideoModal video={SCHEDULED} publishingEnabled onClose={() => {}} onAction={() => {}} />);
    await screen.findByText("Cancel schedule");
    expect(screen.queryByText("Delete Video")).toBeNull();
  });
});
