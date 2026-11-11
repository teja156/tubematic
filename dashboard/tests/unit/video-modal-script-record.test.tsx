/**
 * VideoModal's Script tab: what the agent recorded with the script (TMDEV-211).
 *
 *  1. A script with a record shows its formula, the type of the opening in
 *     use, the three openings drafted and the script checks' findings.
 *  2. A script with no record (every script written before scripts recorded
 *     one) shows the segments and nothing else, and asks the API for nothing.
 *  3. The labels come from GET /script-formulas; until it answers, or for an
 *     id it does not know, the id itself is shown.
 *  4. It is read-only: no control in it.
 */
import { act, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { VideoModal } from "@/components/VideoModal";
import { formulaLabel, hasScriptRecord, hookTypeLabel } from "@/lib/scriptFormulas";
import type { Video } from "@/lib/types";

vi.mock("@/components/TimeZoneProvider", () => ({
  useTimeZone: () => ({ timeZone: "UTC", label: "UTC", degraded: false }),
}));

const NAMES = {
  formulas: [{ id: "broken-expectation", label: "Broken Expectation" }],
  hook_types: [
    { id: "problem", label: "The viewer's problem" },
    { id: "question", label: "Question" },
    { id: "myth", label: "Belief, then break" },
  ],
};

const RECORD: Partial<Video> = {
  formula_id: "broken-expectation",
  hook_type: "problem",
  hook_alternatives: [
    { type: "problem", text: "You renamed one file.", kept: true, note: "" },
    { type: "question", text: "Why does the log stop at today?", kept: false, note: "" },
    { type: "myth", text: "A rename is recorded, obviously.", kept: false, note: "claims a test the script never runs" },
  ],
  script_warnings: [
    { id: "closing_ask", message: "The last sentence asks the viewer to follow." },
    { id: "no_turn", message: "No turn word in the middle of the script." },
  ],
};

function makeVideo(extra: Partial<Video> = {}): Video {
  return {
    id: "vid-1", project_id: null, title: null, topic: "Test topic", strategy: "curriculum",
    producibility_score: 5, status: "SCRIPT_READY", script: "You renamed one file. It stops.",
    script_segments: [
      { id: "seg-1", beat: "The symptom", voice: "You renamed one file.", visual: "a terminal" },
      { id: "seg-2", voice: "It stops.", visual: "" },
    ],
    voice_file_path: null, timeline_path: null, scene_config_path: null, video_path: null,
    archived_at: null, video_version: 1, gemini_feedback: null, youtube_url: null, voice_id: "",
    created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z", comments: [],
    visual_style: "system_flow",
    ...extra,
  };
}

function renderModal(video: Video, names: object | null = NAMES) {
  const fetchMock = vi.fn(async (url: unknown) => {
    const u = String(url);
    if (u.endsWith("/script-formulas")) {
      return { ok: names !== null, json: async () => names ?? {} } as Response;
    }
    if (u.endsWith(`/videos/${video.id}`)) return { ok: true, json: async () => video } as Response;
    return { ok: true, json: async () => [] } as Response;
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<VideoModal video={video} onClose={vi.fn()} onAction={vi.fn()} />);
  return fetchMock;
}

async function settle() {
  await screen.findByTestId("video-modal");
  await act(async () => {});
}

const asked = (fetchMock: ReturnType<typeof vi.fn>) =>
  fetchMock.mock.calls.some(([url]) => String(url).endsWith("/script-formulas"));

describe("VideoModal — the script's record", () => {
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it("shows the formula and the opening's type by their labels", async () => {
    renderModal(makeVideo(RECORD));
    await waitFor(() => expect(screen.getByTestId("script-formula")).toHaveTextContent("Broken Expectation"));
    expect(screen.getByTestId("script-hook-type")).toHaveTextContent("The viewer's problem");
  });

  it("lists the three openings and marks the one in use", async () => {
    renderModal(makeVideo(RECORD));
    await settle();
    const used = await screen.findByTestId("script-hook-0");
    expect(used).toHaveAttribute("data-kept", "true");
    expect(used).toHaveTextContent("You renamed one file.");
    await waitFor(() => expect(used).toHaveTextContent("used"));
    const dropped = screen.getByTestId("script-hook-2");
    expect(dropped).toHaveAttribute("data-kept", "false");
    expect(dropped).toHaveTextContent("Not used: claims a test the script never runs");
    expect(screen.getByTestId("script-hook-1")).not.toHaveTextContent("Not used");
  });

  it("lists every warning and says they do not block approval", async () => {
    renderModal(makeVideo(RECORD));
    await settle();
    const box = await screen.findByTestId("script-warnings");
    expect(within(box).getByTestId("script-warning-closing_ask"))
      .toHaveTextContent("The last sentence asks the viewer to follow.");
    expect(within(box).getByTestId("script-warning-no_turn")).toBeInTheDocument();
    expect(box).toHaveTextContent("do not block approval");
    expect(screen.queryByTestId("script-no-warnings")).toBeNull();
  });

  it("says so when the checks raised nothing", async () => {
    renderModal(makeVideo({ ...RECORD, script_warnings: [] }));
    await settle();
    expect(await screen.findByTestId("script-no-warnings")).toBeInTheDocument();
    expect(screen.queryByTestId("script-warnings")).toBeNull();
  });

  it("shows warnings alone for a script written with no formula", async () => {
    renderModal(makeVideo({ script_warnings: [{ id: "no_formula", message: "No formula was recorded." }] }));
    await settle();
    expect(await screen.findByTestId("script-warning-no_formula")).toBeInTheDocument();
    expect(screen.queryByTestId("script-formula")).toBeNull();
    expect(screen.queryByTestId("script-hook-0")).toBeNull();
  });

  it("shows nothing extra, and asks for nothing, for a script with no record", async () => {
    const fetchMock = renderModal(makeVideo({ formula_id: "", hook_alternatives: [], script_warnings: [] }));
    await settle();
    expect(screen.getByTestId("script-segment-seg-1")).toBeInTheDocument();
    expect(screen.queryByTestId("script-record")).toBeNull();
    expect(asked(fetchMock)).toBe(false);
  });

  it("treats a video from before the columns existed the same way", async () => {
    const fetchMock = renderModal(makeVideo());
    await settle();
    expect(screen.queryByTestId("script-record")).toBeNull();
    expect(asked(fetchMock)).toBe(false);
  });

  it("falls back to the ids when the names cannot be loaded", async () => {
    renderModal(makeVideo(RECORD), null);
    await settle();
    expect(await screen.findByTestId("script-formula")).toHaveTextContent("broken-expectation");
    expect(screen.getByTestId("script-hook-type")).toHaveTextContent("problem");
  });

  it("shows a segment's beat label only where it has one", async () => {
    renderModal(makeVideo(RECORD));
    await settle();
    expect(await screen.findByTestId("script-beat-seg-1")).toHaveTextContent("The symptom");
    expect(screen.queryByTestId("script-beat-seg-2")).toBeNull();
  });

  it("has no control in it", async () => {
    renderModal(makeVideo(RECORD));
    await settle();
    const record = await screen.findByTestId("script-record");
    expect(within(record).queryAllByRole("button")).toHaveLength(0);
    expect(record.querySelectorAll("input, select, textarea")).toHaveLength(0);
  });
});

describe("script formula names", () => {
  it("labels a known id and passes an unknown one through", () => {
    expect(formulaLabel("broken-expectation", NAMES)).toBe("Broken Expectation");
    expect(formulaLabel("retired-formula", NAMES)).toBe("retired-formula");
    expect(formulaLabel("broken-expectation", null)).toBe("broken-expectation");
    expect(hookTypeLabel("myth", NAMES)).toBe("Belief, then break");
    expect(hookTypeLabel("shout", NAMES)).toBe("shout");
  });

  it("counts a formula, openings or warnings as a record, and nothing else", () => {
    expect(hasScriptRecord({})).toBe(false);
    expect(hasScriptRecord({ formula_id: "", hook_alternatives: [], script_warnings: null })).toBe(false);
    expect(hasScriptRecord({ formula_id: "scene-story" })).toBe(true);
    expect(hasScriptRecord({ script_warnings: [{ id: "no_formula", message: "m" }] })).toBe(true);
    expect(hasScriptRecord({ hook_alternatives: [{ type: "scene", text: "t", kept: true }] })).toBe(true);
  });
});
