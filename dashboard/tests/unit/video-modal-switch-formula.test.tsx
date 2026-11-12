/**
 * VideoModal's script formula: the choice at the topic, the pick shown after
 * it, and the switch to its runner-up (TMDEV-213).
 *
 *  1. At Topic Proposed a Formula picker offers Auto, every formula and marks
 *     the experimental ones. The choice goes with the approval only when the
 *     person changed it.
 *  2. After the topic the formula shows beside the script profile: "Auto — X"
 *     when Auto picked it, X alone when a person chose it.
 *  3. A picked formula shows its reason and runner-up. At Script Ready, with
 *     a runner-up, a Switch button posts to /switch-formula after a confirm
 *     and refetches the video. Nowhere else: after Script Ready the voice is
 *     paid for, and before it there is no script to throw away.
 *  4. A refusal shows the server's reason.
 */
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { VideoModal } from "@/components/VideoModal";
import { formulaOptions, videoFormulaLabel } from "@/lib/scriptFormulas";
import type { Video, VideoStatus } from "@/lib/types";

vi.mock("@/components/TimeZoneProvider", () => ({
  useTimeZone: () => ({ timeZone: "UTC", label: "UTC", degraded: false }),
}));

const NAMES = {
  formulas: [
    { id: "follow-the-flow", label: "Follow the Flow", experimental: false },
    { id: "scene-story", label: "Scene Story", experimental: false },
    { id: "news-take", label: "News Take", experimental: true },
  ],
  hook_types: [{ id: "problem", label: "The viewer's problem" }],
};

function makeVideo(status: VideoStatus, extra: Partial<Video> = {}): Video {
  return {
    id: "vid-1", project_id: null, title: null, topic: "Test topic", strategy: "curriculum",
    producibility_score: 5, status, script: null, voice_file_path: null, timeline_path: null,
    scene_config_path: null, video_path: null, archived_at: null, video_version: 1,
    gemini_feedback: null, youtube_url: null, voice_id: "", created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z", comments: [], visual_style: "system_flow",
    formula_choice: "", formula_pick: "follow-the-flow", formula_runner_up: "scene-story",
    formula_reason: "A request moves through fixed stages.",
    ...extra,
  };
}

function renderModal(video: Video, sw = { ok: true, body: {} as object }, onAction = vi.fn()) {
  const fetchMock = vi.fn(async (url: unknown, init?: RequestInit) => {
    const u = String(url);
    if (u.endsWith("/switch-formula") && init?.method === "POST") {
      return { ok: sw.ok, json: async () => sw.body } as Response;
    }
    if (u.endsWith("/script-formulas")) return { ok: true, json: async () => NAMES } as Response;
    if (u.endsWith(`/videos/${video.id}`)) return { ok: true, json: async () => video } as Response;
    return { ok: true, json: async () => [] } as Response;
  });
  vi.stubGlobal("fetch", fetchMock);
  const { rerender } = render(<VideoModal video={video} onClose={vi.fn()} onAction={onAction} />);
  // Same mounted modal, another video: as the pages use it.
  rerenderModal = (v: Video) => rerender(<VideoModal video={v} onClose={vi.fn()} onAction={onAction} />);
  return fetchMock;
}

let rerenderModal: ((v: Video) => void) | null = null;

function cleanupAndRender(video: Video) {
  rerenderModal!(video);
}

async function settle() {
  await screen.findByTestId("video-modal");
  await act(async () => {});
}

const TOPIC = { formula_pick: "", formula_runner_up: "", formula_reason: "" };

describe("VideoModal — the formula at the topic", () => {
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it("offers Auto and every formula, the experimental ones marked", async () => {
    renderModal(makeVideo("TOPIC_PROPOSED", TOPIC));
    const select = await screen.findByTestId("video-modal-formula-select") as HTMLSelectElement;
    await waitFor(() => expect(select.options).toHaveLength(4));
    expect([...select.options].map((o) => o.textContent)).toEqual(
      ["Auto", "Follow the Flow", "Scene Story", "News Take (experimental)"]);
    expect(select.value).toBe("");
  });

  it("starts on the formula the video holds", async () => {
    renderModal(makeVideo("TOPIC_PROPOSED", { ...TOPIC, formula_choice: "scene-story" }));
    const select = await screen.findByTestId("video-modal-formula-select") as HTMLSelectElement;
    await waitFor(() => expect(select.value).toBe("scene-story"));
  });

  it("sends a changed choice with the approval", async () => {
    const onAction = vi.fn();
    renderModal(makeVideo("TOPIC_PROPOSED", TOPIC), undefined, onAction);
    const select = await screen.findByTestId("video-modal-formula-select") as HTMLSelectElement;
    await waitFor(() => expect(select.options).toHaveLength(4));
    fireEvent.change(select, { target: { value: "news-take" } });
    fireEvent.click(screen.getByText("Approve Topic"));
    expect(onAction.mock.calls[0][3]).toMatchObject({ formula_choice: "news-take" });
  });

  it("sends nothing about the formula when the person left it alone", async () => {
    const onAction = vi.fn();
    renderModal(makeVideo("TOPIC_PROPOSED", { ...TOPIC, formula_choice: "scene-story" }), undefined, onAction);
    await screen.findByTestId("video-modal-formula-select");
    fireEvent.click(screen.getByText("Approve Topic"));
    expect(onAction.mock.calls[0][3]).not.toHaveProperty("formula_choice");
  });

  it("can put a video back on Auto", async () => {
    const onAction = vi.fn();
    renderModal(makeVideo("TOPIC_PROPOSED", { ...TOPIC, formula_choice: "scene-story" }), undefined, onAction);
    const select = await screen.findByTestId("video-modal-formula-select") as HTMLSelectElement;
    await waitFor(() => expect(select.options).toHaveLength(4));
    fireEvent.change(select, { target: { value: "" } });
    fireEvent.click(screen.getByText("Approve Topic"));
    expect(onAction.mock.calls[0][3]).toMatchObject({ formula_choice: "" });
  });

  it("has no formula picker after the topic", async () => {
    renderModal(makeVideo("SCRIPT_READY"));
    await settle();
    expect(screen.queryByTestId("video-modal-formula-select")).not.toBeInTheDocument();
  });
});

describe("VideoModal — the formula pick", () => {
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it("shows the formula beside the profile, marked as Auto's", async () => {
    renderModal(makeVideo("SCRIPT_READY"));
    await waitFor(() => expect(screen.getByTestId("video-formula")).toHaveTextContent("Auto — Follow the Flow"));
  });

  it("shows a person's choice without the Auto mark", async () => {
    renderModal(makeVideo("SCRIPT_READY", { formula_choice: "follow-the-flow" }));
    await waitFor(() => expect(screen.getByTestId("video-formula")).toHaveTextContent("Follow the Flow"));
    expect(screen.getByTestId("video-formula")).not.toHaveTextContent("Auto");
  });

  it("says the formula is not chosen yet on an approved topic", async () => {
    renderModal(makeVideo("TOPIC_APPROVED", TOPIC));
    await waitFor(() => expect(screen.getByTestId("video-formula")).toHaveTextContent("Auto (not yet chosen)"));
  });

  it("shows no formula row for a video scripted before formulas existed", async () => {
    renderModal(makeVideo("VIDEO_READY", TOPIC));
    await settle();
    expect(screen.queryByTestId("video-formula")).not.toBeInTheDocument();
  });

  it("shows the reason and the runner-up", async () => {
    renderModal(makeVideo("SCRIPT_READY"));
    const reason = await screen.findByTestId("formula-pick-reason");
    expect(reason).toHaveTextContent("A request moves through fixed stages.");
    await waitFor(() => expect(reason).toHaveTextContent("Runner-up: Scene Story"));
  });

  it("offers the switch at Script Ready and posts it after a confirm", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    const fetchMock = renderModal(makeVideo("SCRIPT_READY"));
    const box = await screen.findByTestId("switch-formula");
    await waitFor(() => expect(box).toHaveTextContent("Switch to Scene Story"));
    fireEvent.click(box.querySelector("button")!);
    await waitFor(() => expect(fetchMock.mock.calls.some(
      ([u, i]) => String(u).endsWith("/videos/vid-1/switch-formula") && (i as RequestInit)?.method === "POST",
    )).toBe(true));
    expect(confirm.mock.calls[0][0]).toContain("The script is discarded");
  });

  it("does nothing when the confirm is declined", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const fetchMock = renderModal(makeVideo("SCRIPT_READY"));
    fireEvent.click((await screen.findByTestId("switch-formula")).querySelector("button")!);
    await act(async () => {});
    expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/switch-formula"))).toBe(false);
  });

  it("shows the server's refusal", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderModal(makeVideo("SCRIPT_READY"), { ok: false, body: { error: "The runner-up is no longer a formula" } });
    fireEvent.click((await screen.findByTestId("switch-formula")).querySelector("button")!);
    expect(await screen.findByTestId("switch-formula-error")).toHaveTextContent("no longer a formula");
  });

  it("clears a refusal when the window shows another video", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderModal(makeVideo("SCRIPT_READY"), { ok: false, body: { error: "The runner-up is no longer a formula" } });
    fireEvent.click((await screen.findByTestId("switch-formula")).querySelector("button")!);
    await screen.findByTestId("switch-formula-error");
    const other = makeVideo("SCRIPT_READY", { id: "vid-2" });
    vi.stubGlobal("fetch", vi.fn(async (url: unknown) => {
      const u = String(url);
      if (u.endsWith("/script-formulas")) return { ok: true, json: async () => NAMES } as Response;
      if (u.endsWith("/videos/vid-2")) return { ok: true, json: async () => other } as Response;
      return { ok: true, json: async () => [] } as Response;
    }));
    cleanupAndRender(other);
    await settle();
    expect(screen.queryByTestId("switch-formula-error")).not.toBeInTheDocument();
  });

  it.each<VideoStatus>(["TOPIC_APPROVED", "VOICING", "VOICE_READY", "VIDEO_READY"])(
    "is not offered at %s", async (status) => {
      renderModal(makeVideo(status));
      await settle();
      expect(screen.queryByTestId("switch-formula")).not.toBeInTheDocument();
    });

  it("is not offered without a runner-up", async () => {
    renderModal(makeVideo("SCRIPT_READY", { formula_runner_up: "" }));
    await settle();
    expect(screen.getByTestId("formula-pick-reason")).toBeInTheDocument();
    expect(screen.queryByTestId("switch-formula")).not.toBeInTheDocument();
  });

  it("shows no reason and no switch for a script written before formulas were picked", async () => {
    renderModal(makeVideo("SCRIPT_READY", { ...TOPIC, formula_id: "scene-story" }));
    await waitFor(() => expect(screen.getByTestId("video-formula")).toHaveTextContent("Scene Story"));
    expect(screen.queryByTestId("formula-pick-reason")).not.toBeInTheDocument();
    expect(screen.queryByTestId("switch-formula")).not.toBeInTheDocument();
  });
});

describe("formula labels and options", () => {
  it("names the formula a video is written in", () => {
    expect(videoFormulaLabel({ formula_choice: "", formula_pick: "", formula_id: "" }, NAMES))
      .toBe("Auto (not yet chosen)");
    expect(videoFormulaLabel({ formula_choice: "scene-story", formula_pick: "", formula_id: "" }, NAMES))
      .toBe("Scene Story");
    expect(videoFormulaLabel({ formula_choice: "", formula_pick: "scene-story", formula_id: "" }, NAMES))
      .toBe("Auto — Scene Story");
    // After a switch the pick is ahead of the stored script's formula.
    expect(videoFormulaLabel({ formula_choice: "scene-story", formula_pick: "scene-story", formula_id: "follow-the-flow" }, NAMES))
      .toBe("Scene Story");
    expect(videoFormulaLabel({ formula_id: "follow-the-flow" }, NAMES)).toBe("Follow the Flow");
    expect(videoFormulaLabel({ formula_pick: "retired" }, null)).toBe("Auto — retired");
  });

  it("names a person's choice only while no script exists", () => {
    const chosen = { formula_choice: "scene-story", formula_pick: "", formula_id: "" };
    expect(videoFormulaLabel({ ...chosen, status: "TOPIC_APPROVED" }, NAMES)).toBe("Scene Story");
    // A script written by hand clears the pick and the record: it follows no formula.
    expect(videoFormulaLabel({ ...chosen, status: "SCRIPT_READY" }, NAMES)).toBe("No formula");
  });

  it("keeps a held formula the list does not know selectable", () => {
    expect(formulaOptions(null)).toEqual([{ value: "", label: "Auto" }]);
    expect(formulaOptions(NAMES, "retired").at(-1)).toEqual({ value: "retired", label: "retired" });
    expect(formulaOptions(NAMES, "scene-story")).toHaveLength(4);
  });
});
