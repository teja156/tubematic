/**
 * The Analytics page's Watch time tab (TMDEV-212): seconds watched, share
 * watched and stayed to watch for one account, grouped by visual style, script
 * profile, domain or script length.
 *
 * What these guard: figures are read one account at a time and the API picks
 * the first one; a group too small to read is marked instead of hidden; a
 * figure only some of a group's videos report says how many; and a figure
 * nobody reports is a dash, never 0.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, afterEach } from "vitest";
import { WatchTimePanel } from "@/components/WatchTimePanel";

function group(key: string, label: string, videos: number, over: Record<string, unknown> = {}) {
  return {
    key, label, videos,
    avg_watch_secs: { median: 31, n: videos },
    watched_pct: { median: 41.5, n: videos },
    stayed_pct: { median: 60, n: videos },
    ...over,
  };
}

const YOUTUBE = {
  accounts: [{ id: "spc_yt", platform: "youtube", videos: 56 },
             { id: "spc_ig", platform: "instagram", videos: 40 }],
  social_account_id: "spc_yt", platform: "youtube", videos: 56, min_group: 20,
  dimensions: [
    { id: "visual_style", label: "Visual style", groups: [
      group("system_flow", "System Flow", 34),
      group("whiteboard", "Whiteboard", 6, { avg_watch_secs: { median: 24.5, n: 6 } }),
    ] },
    { id: "script_profile", label: "Script profile", groups: [group("", "No profile", 56)] },
    { id: "domain", label: "Domain", groups: [group("git", "Git", 56)] },
    { id: "script_length", label: "Script length", groups: [group("200", "200 to 249 words", 56)] },
  ],
};

const INSTAGRAM = {
  ...YOUTUBE, social_account_id: "spc_ig", platform: "instagram", videos: 40,
  dimensions: [
    { id: "visual_style", label: "Visual style", groups: [
      group("system_flow", "System Flow", 40, {
        avg_watch_secs: { median: 23.5, n: 38 },
        // Only the videos whose length was stored have a share.
        watched_pct: { median: 25, n: 9 },
        stayed_pct: { median: null, n: 0 },
      }),
    ] },
    { id: "script_profile", label: "Script profile", groups: [] },
    { id: "domain", label: "Domain", groups: [] },
    { id: "script_length", label: "Script length", groups: [] },
  ],
};

const NAMES = { spc_yt: { username: "demo_channel", platform: "youtube" } };

function stub(byAccount: Record<string, unknown> = { "": YOUTUBE, spc_ig: INSTAGRAM }, ok = true) {
  const fn = vi.fn().mockImplementation((url: string) => {
    const account = new URL(String(url), "http://x").searchParams.get("social_account_id") ?? "";
    return Promise.resolve({ ok, json: async () => byAccount[account] });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("WatchTimePanel", () => {
  it("asks for no account first and shows the one the API chose", async () => {
    const fetchMock = stub();
    render(<WatchTimePanel names={NAMES} />);
    await screen.findByTestId("watch-group-system_flow");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/proxy/analytics/watch-time");
    const select = screen.getByTestId("watch-account") as HTMLSelectElement;
    expect(select.value).toBe("spc_yt");
    // A name when the lookup has one, the id when it does not.
    expect(Array.from(select.options).map((o) => o.textContent)).toEqual([
      "demo_channel (YouTube), 56 videos", "spc_ig (Instagram), 40 videos"]);
  });

  it("shows each group's size and its three figures", async () => {
    stub();
    render(<WatchTimePanel names={{}} />);
    const row = await screen.findByTestId("watch-group-system_flow");
    expect(row).toHaveTextContent("System Flow");
    expect(row).toHaveTextContent("34");
    expect(screen.getByTestId("watch-avg_watch_secs-system_flow")).toHaveTextContent("31 s");
    expect(screen.getByTestId("watch-watched_pct-system_flow")).toHaveTextContent("41.5%");
    expect(screen.getByTestId("watch-stayed_pct-system_flow")).toHaveTextContent("60%");
  });

  it("marks a group under the threshold as too few, and still shows it", async () => {
    stub();
    render(<WatchTimePanel names={{}} />);
    await screen.findByTestId("watch-group-whiteboard");
    expect(screen.getByTestId("watch-small-whiteboard")).toHaveTextContent("TOO FEW");
    expect(screen.getByTestId("watch-avg_watch_secs-whiteboard")).toHaveTextContent("24.5 s");
    expect(screen.queryByTestId("watch-small-system_flow")).toBeNull();
  });

  it("takes the threshold from the API", async () => {
    stub({ "": { ...YOUTUBE, min_group: 40 } });
    render(<WatchTimePanel names={{}} />);
    await screen.findByTestId("watch-group-system_flow");
    expect(screen.getByTestId("watch-small-system_flow")).toBeInTheDocument();
  });

  it("re-reads for the account picked, since accounts are never combined", async () => {
    const fetchMock = stub();
    render(<WatchTimePanel names={{}} />);
    await screen.findByTestId("watch-group-system_flow");
    fireEvent.change(screen.getByTestId("watch-account"), { target: { value: "spc_ig" } });
    await waitFor(() =>
      expect(screen.getByTestId("watch-avg_watch_secs-system_flow")).toHaveTextContent("23.5 s"));
    expect(String(fetchMock.mock.calls[1][0]))
      .toBe("/api/proxy/analytics/watch-time?social_account_id=spc_ig");
  });

  it("says how many videos a figure speaks for when not all report it, and dashes one nobody reports", async () => {
    stub({ "": INSTAGRAM });
    render(<WatchTimePanel names={{}} />);
    await screen.findByTestId("watch-group-system_flow");
    expect(screen.getByTestId("watch-avg_watch_secs-system_flow")).toHaveTextContent("23.5 s (38 of 40)");
    // Nine videos are as hard to read as a nine-video group, and it says so.
    expect(screen.getByTestId("watch-watched_pct-system_flow"))
      .toHaveTextContent("25% (9 of 40, too few)");
    const stayed = screen.getByTestId("watch-stayed_pct-system_flow");
    expect(stayed).toHaveTextContent("—");
    expect(stayed).not.toHaveTextContent("0");
    // The group itself is big enough; only the share rests on few videos.
    expect(screen.queryByTestId("watch-small-system_flow")).toBeNull();
  });

  it("changes the grouping without asking the API again", async () => {
    const fetchMock = stub();
    render(<WatchTimePanel names={{}} />);
    await screen.findByTestId("watch-group-system_flow");
    fireEvent.change(screen.getByTestId("watch-group-by"), { target: { value: "script_length" } });
    expect(screen.getByTestId("watch-group-200")).toHaveTextContent("200 to 249 words");
    expect(screen.queryByTestId("watch-group-system_flow")).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("says so when the platform reports no watch figure at all", async () => {
    const none = { median: null, n: 0 };
    stub({ "": {
      ...YOUTUBE, platform: "tiktok",
      dimensions: [{ id: "visual_style", label: "Visual style", groups: [
        group("system_flow", "System Flow", 30,
              { avg_watch_secs: none, watched_pct: none, stayed_pct: none })] }],
    } });
    render(<WatchTimePanel names={{}} />);
    expect(await screen.findByTestId("watch-time-unreported"))
      .toHaveTextContent("TikTok has reported no watch figures");
  });

  it("says so when nothing has been published", async () => {
    stub({ "": { ...YOUTUBE, accounts: [], social_account_id: "", videos: 0,
                 dimensions: YOUTUBE.dimensions.map((d) => ({ ...d, groups: [] })) } });
    render(<WatchTimePanel names={{}} />);
    expect(await screen.findByTestId("watch-time-empty")).toHaveTextContent("Nothing published yet");
  });

  it("never shows one account's figures under another account's name", async () => {
    // The pick fails. The last answer is YouTube's, and the select now names
    // Instagram, so the table must go and not stay up under the wrong name.
    const fetchMock = vi.fn().mockImplementation((url: string) =>
      String(url).includes("spc_ig")
        ? Promise.resolve({ ok: false, json: async () => ({ error: "API restarting" }) })
        : Promise.resolve({ ok: true, json: async () => YOUTUBE }));
    vi.stubGlobal("fetch", fetchMock);
    render(<WatchTimePanel names={{}} />);
    await screen.findByTestId("watch-group-system_flow");
    fireEvent.change(screen.getByTestId("watch-account"), { target: { value: "spc_ig" } });
    // Gone at once, while the request is still out.
    expect(screen.queryByTestId("watch-group-system_flow")).toBeNull();
    expect(await screen.findByTestId("watch-time-error")).toHaveTextContent("API restarting");
    expect((screen.getByTestId("watch-account") as HTMLSelectElement).value).toBe("spc_ig");
    expect(screen.queryByTestId("watch-group-system_flow")).toBeNull();
    // Picking the first account again brings its figures back.
    fireEvent.change(screen.getByTestId("watch-account"), { target: { value: "spc_yt" } });
    expect(await screen.findByTestId("watch-group-system_flow")).toBeInTheDocument();
    expect(screen.queryByTestId("watch-time-error")).toBeNull();
  });

  it("surfaces an API error", async () => {
    stub({ "": { error: "boom" } }, false);
    render(<WatchTimePanel names={{}} />);
    expect(await screen.findByTestId("watch-time-error")).toHaveTextContent("boom");
  });

  it("does not render another suite's settings object as figures", async () => {
    // Other suites' fetch mocks answer every URL with whatever they hold.
    stub({ "": { publishing_enabled: true } });
    render(<WatchTimePanel names={{}} />);
    expect(await screen.findByTestId("watch-time-error"))
      .toHaveTextContent("Could not load watch figures");
  });
});
