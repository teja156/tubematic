/**
 * VideoModal's Topic tab: the topic's angle (TMDEV-214).
 *
 *  1. A topic with an angle shows the sentence, its kind by label and the
 *     agent's score; an unscored angle shows a dash.
 *  2. At Topic Proposed the angle can be edited or added. Save sends the
 *     sentence and the kind together and re-reads the video. A sentence with
 *     no kind, or one over the limit, cannot be saved. An emptied sentence
 *     saves as "no angle".
 *  3. Past Topic Proposed it is read-only, and a video with no angle shows no
 *     block at all (every video made before topics carried one).
 *  4. A refused save shows the API's reason and keeps the draft.
 */
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { VideoModal } from "@/components/VideoModal";
import { angleKindLabel, angleScoreLabel, hasAngle } from "@/lib/angles";
import type { Video } from "@/lib/types";

vi.mock("@/components/TimeZoneProvider", () => ({
  useTimeZone: () => ({ timeZone: "UTC", label: "UTC", degraded: false }),
}));

const KINDS = [
  { id: "paradox", label: "Paradox", means: "Something works in a way that seems impossible." },
  { id: "myth", label: "Myth", means: "A belief most people hold is wrong." },
  { id: "design_question", label: "Design question", means: "A design that looks stupid from outside." },
];

const ANGLE: Partial<Video> = {
  angle: "Deleting the file frees no space until the last program holding it lets go.",
  angle_kind: "paradox",
  angle_score: 7,
};

function makeVideo(extra: Partial<Video> = {}): Video {
  return {
    id: "vid-1", project_id: null, title: "Deleting a file", topic: "How deleting a file works",
    strategy: "curriculum", producibility_score: 6, status: "TOPIC_PROPOSED", script: null,
    voice_file_path: null, timeline_path: null, scene_config_path: null, video_path: null,
    archived_at: null, video_version: 1, gemini_feedback: null, youtube_url: null, voice_id: "",
    created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z", comments: [],
    visual_style: "auto",
    ...extra,
  };
}

/** Renders the modal on a fake API. `patch` answers the PATCH; the video the
 *  API returns afterwards is `after` (what a re-read shows). */
function renderModal(video: Video, { kinds = KINDS as object | null, patch = { status: 200, body: {} as object },
                                     after = video, tab = undefined as string | undefined } = {}) {
  let saved = false;
  const fetchMock = vi.fn(async (url: unknown, init?: RequestInit) => {
    const u = String(url);
    if (u.endsWith("/angle-kinds")) return { ok: kinds !== null, json: async () => kinds ?? {} } as Response;
    if (u.endsWith(`/videos/${video.id}`) && init?.method === "PATCH") {
      saved = patch.status < 400;
      return { ok: patch.status < 400, status: patch.status, json: async () => patch.body } as Response;
    }
    if (u.endsWith(`/videos/${video.id}`)) return { ok: true, json: async () => (saved ? after : video) } as Response;
    return { ok: true, json: async () => [] } as Response;
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<VideoModal video={video} initialTab={tab} onClose={vi.fn()} onAction={vi.fn()} />);
  return fetchMock;
}

async function settle() {
  await screen.findByTestId("video-modal");
  await act(async () => {});
}

function patches(fetchMock: ReturnType<typeof vi.fn>) {
  return fetchMock.mock.calls
    .filter(([, init]) => (init as RequestInit | undefined)?.method === "PATCH")
    .map(([, init]) => JSON.parse(String((init as RequestInit).body)));
}

describe("lib/angles", () => {
  it("labels a kind from the list, and from its id without one", () => {
    expect(angleKindLabel("design_question", KINDS)).toBe("Design question");
    expect(angleKindLabel("design_question", null)).toBe("design question");
    expect(angleKindLabel("retired_kind", KINDS)).toBe("retired kind");
  });

  it("shows a dash for an angle nobody scored", () => {
    expect(angleScoreLabel(7)).toBe("7/10");
    expect(angleScoreLabel(0)).toBe("—");
    expect(angleScoreLabel(undefined)).toBe("—");
  });

  it("knows a video with no angle", () => {
    expect(hasAngle({ angle: "A sentence." })).toBe(true);
    expect(hasAngle({ angle: "" })).toBe(false);
    expect(hasAngle({})).toBe(false);
  });
});

describe("VideoModal — the topic's angle", () => {
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it("shows the sentence, the kind's label and the score", async () => {
    renderModal(makeVideo(ANGLE));
    await settle();
    expect(screen.getByTestId("topic-angle-text")).toHaveTextContent(ANGLE.angle!);
    await waitFor(() => expect(screen.getByTestId("topic-angle-kind")).toHaveTextContent("Paradox"));
    expect(screen.getByTestId("topic-angle-score")).toHaveTextContent("7/10");
    expect(screen.getByTestId("angle-score-row")).toHaveTextContent("7 / 10");
  });

  it("shows a dash for a person's own angle, which has no score", async () => {
    renderModal(makeVideo({ ...ANGLE, angle_score: 0 }));
    await settle();
    expect(screen.getByTestId("topic-angle-score")).toHaveTextContent("—");
    expect(screen.getByTestId("angle-score-row")).toHaveTextContent("—");
    expect(screen.getByTestId("angle-score-row")).not.toHaveTextContent("/ 10");
  });

  it("says a proposed topic has no angle and offers to add one", async () => {
    renderModal(makeVideo());
    await settle();
    expect(screen.getByTestId("topic-angle-none")).toHaveTextContent("The agent adds one");
    expect(screen.getByTestId("topic-angle-edit")).toHaveTextContent("Add angle");
  });

  it("saves an edited sentence and kind together and re-reads the video", async () => {
    const video = makeVideo(ANGLE);
    const after = makeVideo({ angle: "Most people think delete means gone.", angle_kind: "myth", angle_score: 0 });
    const fetchMock = renderModal(video, { after });
    await settle();
    fireEvent.click(screen.getByTestId("topic-angle-edit"));
    expect(screen.getByTestId("topic-angle-input")).toHaveValue(ANGLE.angle);
    await waitFor(() => expect(screen.getByTestId("topic-angle-kind-select")).toHaveValue("paradox"));
    fireEvent.change(screen.getByTestId("topic-angle-input"), { target: { value: "  Most people think delete means gone.  " } });
    fireEvent.change(screen.getByTestId("topic-angle-kind-select"), { target: { value: "myth" } });
    expect(screen.getByTestId("topic-angle-means")).toHaveTextContent("A belief most people hold is wrong.");
    fireEvent.click(screen.getByTestId("topic-angle-save"));
    await waitFor(() => expect(screen.getByTestId("topic-angle-text")).toHaveTextContent("Most people think delete means gone."));
    expect(patches(fetchMock)).toEqual([{ angle: "Most people think delete means gone.", angle_kind: "myth" }]);
    expect(screen.getByTestId("topic-angle-kind")).toHaveTextContent("Myth");
    // The old score described the old words.
    expect(screen.getByTestId("topic-angle-score")).toHaveTextContent("—");
    expect(screen.queryByTestId("topic-angle-input")).toBeNull();
  });

  it("will not save a sentence without a kind", async () => {
    const fetchMock = renderModal(makeVideo());
    await settle();
    fireEvent.click(screen.getByTestId("topic-angle-edit"));
    fireEvent.change(screen.getByTestId("topic-angle-input"), { target: { value: "A sentence." } });
    expect(screen.getByTestId("topic-angle-save")).toBeDisabled();
    fireEvent.click(screen.getByTestId("topic-angle-save"));
    expect(patches(fetchMock)).toEqual([]);
    fireEvent.change(screen.getByTestId("topic-angle-kind-select"), { target: { value: "paradox" } });
    expect(screen.getByTestId("topic-angle-save")).not.toBeDisabled();
  });

  it("counts the sentence and will not save one over the limit", async () => {
    renderModal(makeVideo(ANGLE));
    await settle();
    fireEvent.click(screen.getByTestId("topic-angle-edit"));
    fireEvent.change(screen.getByTestId("topic-angle-input"), { target: { value: "x".repeat(301) } });
    expect(screen.getByTestId("topic-angle-count")).toHaveTextContent("301/300");
    expect(screen.getByTestId("topic-angle-save")).toBeDisabled();
    fireEvent.change(screen.getByTestId("topic-angle-input"), { target: { value: "x".repeat(300) } });
    expect(screen.getByTestId("topic-angle-save")).not.toBeDisabled();
  });

  it("saves an emptied sentence as no angle", async () => {
    const fetchMock = renderModal(makeVideo(ANGLE), { after: makeVideo() });
    await settle();
    fireEvent.click(screen.getByTestId("topic-angle-edit"));
    fireEvent.change(screen.getByTestId("topic-angle-input"), { target: { value: "   " } });
    fireEvent.click(screen.getByTestId("topic-angle-save"));
    await waitFor(() => expect(screen.getByTestId("topic-angle-none")).toBeInTheDocument());
    expect(patches(fetchMock)).toEqual([{ angle: "", angle_kind: "" }]);
  });

  it("shows why a save was refused and keeps the draft", async () => {
    renderModal(makeVideo(ANGLE), {
      patch: { status: 409, body: { error: "angle can only be changed while the video is at TOPIC_PROPOSED (this one is TOPIC_APPROVED)" } },
    });
    await settle();
    fireEvent.click(screen.getByTestId("topic-angle-edit"));
    fireEvent.change(screen.getByTestId("topic-angle-input"), { target: { value: "A new sentence." } });
    fireEvent.click(screen.getByTestId("topic-angle-save"));
    await waitFor(() => expect(screen.getByTestId("topic-angle-error")).toHaveTextContent("TOPIC_PROPOSED"));
    expect(screen.getByTestId("topic-angle-input")).toHaveValue("A new sentence.");
  });

  it("cancel drops the draft", async () => {
    const fetchMock = renderModal(makeVideo(ANGLE));
    await settle();
    fireEvent.click(screen.getByTestId("topic-angle-edit"));
    fireEvent.change(screen.getByTestId("topic-angle-input"), { target: { value: "Thrown away." } });
    fireEvent.click(screen.getByTestId("topic-angle-cancel"));
    expect(screen.getByTestId("topic-angle-text")).toHaveTextContent(ANGLE.angle!);
    expect(patches(fetchMock)).toEqual([]);
  });

  it.each(["TOPIC_APPROVED", "SCRIPT_READY", "VIDEO_READY"] as const)(
    "is read-only at %s", async (status) => {
      // A scripted video opens on its Script tab; the angle is on Topic.
      renderModal(makeVideo({ ...ANGLE, status, script: status === "TOPIC_APPROVED" ? null : "Words." }),
                  { tab: "topic" });
      await settle();
      expect(await screen.findByTestId("topic-angle-text")).toHaveTextContent(ANGLE.angle!);
      expect(screen.queryByTestId("topic-angle-edit")).toBeNull();
    },
  );

  it("is read-only on an archived video", async () => {
    renderModal(makeVideo({ ...ANGLE, archived_at: "2026-02-01T00:00:00Z" }));
    await settle();
    expect(screen.getByTestId("topic-angle-text")).toBeInTheDocument();
    expect(screen.queryByTestId("topic-angle-edit")).toBeNull();
  });

  it("shows no block, and asks the API for nothing, on an approved video with no angle", async () => {
    const fetchMock = renderModal(makeVideo({ status: "TOPIC_APPROVED" }));
    await settle();
    expect(screen.queryByTestId("topic-angle")).toBeNull();
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/angle-kinds"))).toBe(false);
  });

  it("says why no kind can be chosen when the list cannot be loaded", async () => {
    renderModal(makeVideo(), { kinds: null });
    await settle();
    fireEvent.click(screen.getByTestId("topic-angle-edit"));
    expect(await screen.findByTestId("topic-angle-kinds-failed")).toHaveTextContent("could not be loaded");
    fireEvent.change(screen.getByTestId("topic-angle-input"), { target: { value: "A sentence." } });
    expect(screen.getByTestId("topic-angle-save")).toBeDisabled();
  });

  it("counts and sends the sentence as the API stores it", async () => {
    const fetchMock = renderModal(makeVideo(ANGLE));
    await settle();
    fireEvent.click(screen.getByTestId("topic-angle-edit"));
    // 298 letters, a line break with spaces around it, and an emoji: 300 as stored.
    fireEvent.change(screen.getByTestId("topic-angle-input"), { target: { value: "x".repeat(298) + "  \n  🚀" } });
    expect(screen.getByTestId("topic-angle-count")).toHaveTextContent("300/300");
    fireEvent.click(screen.getByTestId("topic-angle-save"));
    await waitFor(() => expect(patches(fetchMock)).toHaveLength(1));
    expect(patches(fetchMock)[0].angle).toBe("x".repeat(298) + " 🚀");
  });

  it("falls back to the kind's id when the list cannot be loaded", async () => {
    renderModal(makeVideo({ ...ANGLE, angle_kind: "design_question" }), { kinds: null });
    await settle();
    expect(screen.getByTestId("topic-angle-kind")).toHaveTextContent("design question");
  });
});
