/**
 * Settings → Auto Pilot (TMDEV-139). Auto Pilot spends money and posts in
 * public with nobody watching, so these guard the things that keep that a
 * deliberate act: the disclaimer is always on screen, turning it on (or
 * widening it) is confirmed with the number of videos it approves at once,
 * and a response that is not a real configuration is never read as "off and
 * empty" and saved back. Every other change saves itself (TMDEV-218).
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, afterEach } from "vitest";
import { AutoPilotPanel } from "@/components/AutoPilotPanel";
import {
  AUTO_PILOT_DISCLAIMER, AUTO_PILOT_POLL_MS, MAX_AUTO_PILOT_IN_FLIGHT, ceilingStatus, gapMins,
  needsConfirmation, newlyApproved, splitGap,
} from "@/lib/autoPilot";
import type { AutoPilotState } from "@/lib/autoPilot";

vi.mock("@/components/SectionLabel", () => ({
  SectionLabel: ({ label }: { label: string }) => <div>{label}</div>,
}));

const STATE: AutoPilotState = {
  enabled: false,
  gap_mins: 240,
  max_in_flight: 0,
  projects: {},
  account_limits: {},
  default_daily_limit: 1,
  in_flight: 0,
  waiting: { linux: { TOPIC_PROPOSED: 2, SCRIPT_READY: 1, VIDEO_APPROVED: 4 } },
};

const PROJECTS = [
  { id: "linux", name: "Linux internals" },
  { id: "net", name: "Networking" },
];

const ACCOUNTS = [
  { id: "spc_yt", platform: "youtube", username: "chan", allowed: true, available: true },
  { id: "spc_ig", platform: "instagram", username: "gram", allowed: true, available: true },
  { id: "spc_off", platform: "tiktok", username: "off", allowed: false, available: true },
];

function stub(state: unknown = STATE, opts: { accountsOk?: boolean; saveOk?: boolean } = {}) {
  const fn = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    if (url.endsWith("/autopilot") && init?.method === "POST") {
      if (opts.saveOk === false)
        return Promise.resolve({ ok: false, status: 400,
                                 json: async () => ({ error: "Unknown project(s): linux" }) });
      const body = JSON.parse(String(init.body));
      return Promise.resolve({ ok: true, json: async () => ({ ...STATE, ...body }) });
    }
    if (url.endsWith("/autopilot"))
      return Promise.resolve({ ok: true, status: 200, json: async () => state });
    if (url.endsWith("/projects"))
      return Promise.resolve({ ok: true, json: async () => PROJECTS });
    if (url.includes("/publishing/accounts"))
      return Promise.resolve(opts.accountsOk === false
        ? { ok: false, status: 503, json: async () => ({ error: "Publishing is disabled" }) }
        : { ok: true, json: async () => ACCOUNTS });
    return Promise.resolve({ ok: true, json: async () => ({}) });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

function posts(fn: ReturnType<typeof vi.fn>) {
  return fn.mock.calls
    .filter(([url, init]) => String(url).endsWith("/autopilot") && init?.method === "POST")
    .map(([, init]) => JSON.parse(String(init.body)));
}

/** The last document sent, or null when nothing was. */
function posted(fn: ReturnType<typeof vi.fn>) {
  const all = posts(fn);
  return all.length ? all[all.length - 1] : null;
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("AutoPilotPanel", () => {
  it("always shows the whole disclaimer", async () => {
    stub();
    render(<AutoPilotPanel inputStyle={{}} />);
    const box = await screen.findByTestId("auto-pilot-disclaimer");
    for (const line of AUTO_PILOT_DISCLAIMER) expect(box).toHaveTextContent(line);
  });

  it("starts off, with no Save button: every change saves itself", async () => {
    stub();
    render(<AutoPilotPanel inputStyle={{}} />);
    expect(await screen.findByTestId("toggle-auto-pilot")).toHaveTextContent("OFF");
    expect(screen.queryByTestId("save-auto-pilot")).toBeNull();
  });

  it("shows the gap in hours when it is whole hours", async () => {
    stub();
    render(<AutoPilotPanel inputStyle={{}} />);
    expect(await screen.findByTestId("input-auto-pilot-gap")).toHaveValue(4);
    expect(screen.getByTestId("select-auto-pilot-gap-unit")).toHaveValue("hours");
  });

  it("offers only accounts that are allowed and connected", async () => {
    const fn = stub();
    render(<AutoPilotPanel inputStyle={{}} />);
    fireEvent.click(await screen.findByTestId("auto-pilot-project-toggle-linux"));
    expect(screen.getByTestId("auto-pilot-account-linux-spc_yt")).toBeTruthy();
    expect(screen.queryByTestId("auto-pilot-account-linux-spc_off")).toBeNull();
    expect(screen.queryByTestId("auto-pilot-limit-spc_off")).toBeNull();
    await waitFor(() => expect(posts(fn)).toHaveLength(1));
  });

  it("says a selected project with no account stops at Video Approved", async () => {
    const fn = stub();
    render(<AutoPilotPanel inputStyle={{}} />);
    fireEvent.click(await screen.findByTestId("auto-pilot-project-toggle-linux"));
    expect(screen.getByTestId("auto-pilot-no-accounts-linux")).toHaveTextContent("Video Approved");
    fireEvent.click(screen.getByTestId("auto-pilot-account-linux-spc_yt"));
    expect(screen.queryByTestId("auto-pilot-no-accounts-linux")).toBeNull();
    await waitFor(() => expect(posts(fn)).toHaveLength(2));
  });

  it("says so when publishing is off, and still lets projects be selected", async () => {
    const fn = stub(STATE, { accountsOk: false });
    render(<AutoPilotPanel inputStyle={{}} />);
    expect(await screen.findByTestId("auto-pilot-no-publishing")).toHaveTextContent("Video Approved");
    fireEvent.click(screen.getByTestId("auto-pilot-project-toggle-linux"));
    await waitFor(() => expect(posted(fn)).toEqual(expect.objectContaining({ projects: { linux: [] } })));
  });

  it("asks before turning on, naming how many videos are approved at once", async () => {
    const fn = stub();
    render(<AutoPilotPanel inputStyle={{}} />);
    // Selecting a project while the switch is off approves nothing: saved at once.
    fireEvent.click(await screen.findByTestId("auto-pilot-project-toggle-linux"));
    await waitFor(() => expect(posts(fn)).toHaveLength(1));
    fireEvent.click(screen.getByTestId("toggle-auto-pilot"));

    // 2 proposed + 1 script ready. The 4 at VIDEO_APPROVED are not approvals.
    expect(await screen.findByTestId("auto-pilot-confirm-count")).toHaveTextContent("3 videos are");
    expect(screen.getByTestId("auto-pilot-confirm-disclaimer")).toHaveTextContent(AUTO_PILOT_DISCLAIMER[0]);
    expect(posts(fn)).toHaveLength(1);

    fireEvent.click(screen.getByTestId("auto-pilot-confirm-ok"));
    await waitFor(() => expect(posts(fn)).toHaveLength(2));
    expect(posted(fn)).toEqual({
      enabled: true, gap_mins: 240, max_in_flight: 0, projects: { linux: [] }, account_limits: {} });
  });

  it("saves nothing when the confirmation is cancelled, and the switch goes back", async () => {
    const fn = stub();
    render(<AutoPilotPanel inputStyle={{}} />);
    fireEvent.click(await screen.findByTestId("toggle-auto-pilot"));
    fireEvent.click(await screen.findByTestId("auto-pilot-confirm-cancel"));
    await waitFor(() => expect(screen.queryByTestId("auto-pilot-confirm")).toBeNull());
    expect(posted(fn)).toBeNull();
    expect(screen.getByTestId("toggle-auto-pilot")).toHaveTextContent("OFF");
  });

  it("saves without asking when nothing is widened, and says it saved", async () => {
    // Selecting a project while the switch stays off acts on nothing.
    const fn = stub();
    render(<AutoPilotPanel inputStyle={{}} />);
    fireEvent.click(await screen.findByTestId("auto-pilot-project-toggle-linux"));
    await waitFor(() => expect(posted(fn)).not.toBeNull());
    expect(screen.queryByTestId("auto-pilot-confirm")).toBeNull();
    await waitFor(() => expect(screen.getByTestId("auto-pilot-status-project-linux")).toHaveTextContent("✓ Saved"));
  });

  it("sends the chosen accounts, the daily number and the gap in minutes", async () => {
    const fn = stub({ ...STATE, projects: { linux: [] } });
    render(<AutoPilotPanel inputStyle={{}} />);
    fireEvent.click(await screen.findByTestId("auto-pilot-account-linux-spc_yt"));
    const limit = screen.getByTestId("auto-pilot-limit-spc_yt");
    fireEvent.change(limit, { target: { value: "3" } });
    fireEvent.blur(limit);
    // Switching the unit shows 240 minutes and saves nothing.
    fireEvent.change(screen.getByTestId("select-auto-pilot-gap-unit"), { target: { value: "minutes" } });
    expect(screen.getByTestId("input-auto-pilot-gap")).toHaveValue(240);
    const gap = screen.getByTestId("input-auto-pilot-gap");
    fireEvent.change(gap, { target: { value: "90" } });
    fireEvent.blur(gap);
    // Each change sent the whole document; the last one carries all three.
    await waitFor(() => expect(posts(fn)).toHaveLength(3));
    expect(posted(fn)).toEqual({
      enabled: false, gap_mins: 90, max_in_flight: 0, projects: { linux: ["spc_yt"] },
      account_limits: { spc_yt: 3 } });
  });

  it("sends the in-progress limit, ignoring a value out of range", async () => {
    const fn = stub();
    render(<AutoPilotPanel inputStyle={{}} />);
    const input = await screen.findByTestId("input-auto-pilot-max-in-flight");
    fireEvent.change(input, { target: { value: String(MAX_AUTO_PILOT_IN_FLIGHT + 1) } });
    fireEvent.blur(input);
    fireEvent.change(input, { target: { value: "-1" } });
    fireEvent.blur(input);
    expect(posted(fn)).toBeNull();
    expect(screen.getByTestId("auto-pilot-status-max-in-flight")).toHaveTextContent("Not saved:");
    fireEvent.change(input, { target: { value: "12" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => expect(posted(fn)).not.toBeNull());
    expect(posted(fn).max_in_flight).toBe(12);
  });

  it("Enter then blur on the gap sends one save and keeps its outcome", async () => {
    const fn = stub();
    render(<AutoPilotPanel inputStyle={{}} />);
    const gap = await screen.findByTestId("input-auto-pilot-gap");
    fireEvent.change(gap, { target: { value: "2" } });
    fireEvent.keyDown(gap, { key: "Enter" });
    fireEvent.blur(gap);
    await waitFor(() => expect(screen.getByTestId("auto-pilot-status-gap")).toHaveTextContent("✓ Saved"));
    expect(posts(fn)).toHaveLength(1);
    expect(posted(fn).gap_mins).toBe(120);
  });

  it("switching the gap's unit only changes how it reads", async () => {
    const fn = stub();
    render(<AutoPilotPanel inputStyle={{}} />);
    const unit = await screen.findByTestId("select-auto-pilot-gap-unit");
    fireEvent.change(unit, { target: { value: "minutes" } });
    expect(screen.getByTestId("input-auto-pilot-gap")).toHaveValue(240);
    fireEvent.change(unit, { target: { value: "hours" } });
    expect(screen.getByTestId("input-auto-pilot-gap")).toHaveValue(4);
    expect(posts(fn)).toHaveLength(0);
    // A fraction of an hour is fine.
    const gap = screen.getByTestId("input-auto-pilot-gap");
    fireEvent.change(gap, { target: { value: "1.5" } });
    fireEvent.blur(gap);
    await waitFor(() => expect(posted(fn)?.gap_mins).toBe(90));
  });

  it("a gap being typed is not replaced when another save answers", async () => {
    const answers: Array<() => void> = [];
    const fn = stub({ ...STATE, projects: { linux: [] } });
    const base = fn.getMockImplementation()!;
    fn.mockImplementation((url: string, init?: RequestInit) => {
      if (String(url).endsWith("/autopilot") && init?.method === "POST") {
        return new Promise((resolve) => answers.push(() => resolve(base(url, init))));
      }
      return base(url, init);
    });
    render(<AutoPilotPanel inputStyle={{}} />);
    const limit = await screen.findByTestId("auto-pilot-limit-spc_yt");
    fireEvent.change(limit, { target: { value: "3" } });
    fireEvent.blur(limit);
    await waitFor(() => expect(answers).toHaveLength(1));
    fireEvent.change(screen.getByTestId("input-auto-pilot-gap"), { target: { value: "6" } });
    answers[0]();
    await waitFor(() => expect(screen.getByTestId("auto-pilot-status-limit-spc_yt")).toHaveTextContent("✓ Saved"));
    expect(screen.getByTestId("input-auto-pilot-gap")).toHaveValue(6);
  });

  it("Cancel during a save on its way keeps that change on screen", async () => {
    const answers: Array<() => void> = [];
    const fn = stub({ ...STATE, enabled: true, projects: { linux: [] } });
    const base = fn.getMockImplementation()!;
    fn.mockImplementation((url: string, init?: RequestInit) => {
      if (String(url).endsWith("/autopilot") && init?.method === "POST") {
        return new Promise((resolve) => answers.push(() => resolve(base(url, init))));
      }
      return base(url, init);
    });
    render(<AutoPilotPanel inputStyle={{}} />);
    const gap = await screen.findByTestId("input-auto-pilot-gap");
    fireEvent.change(gap, { target: { value: "2" } });
    fireEvent.blur(gap);
    await waitFor(() => expect(answers).toHaveLength(1));
    fireEvent.click(screen.getByTestId("auto-pilot-project-toggle-net"));
    expect(await screen.findByTestId("auto-pilot-confirm")).toHaveTextContent("Add these projects");
    fireEvent.click(screen.getByTestId("auto-pilot-confirm-cancel"));
    await waitFor(() => expect(screen.queryByTestId("auto-pilot-confirm")).toBeNull());
    expect(screen.getByTestId("input-auto-pilot-gap")).toHaveValue(2);
    expect(screen.getByTestId("auto-pilot-project-toggle-net")).not.toBeChecked();
    answers[0]();
    await waitFor(() => expect(screen.getByTestId("auto-pilot-status-gap")).toHaveTextContent("✓ Saved"));
  });

  it("a number typed back to its value clears its refusal", async () => {
    stub();
    render(<AutoPilotPanel inputStyle={{}} />);
    const input = await screen.findByTestId("input-auto-pilot-max-in-flight");
    fireEvent.change(input, { target: { value: "-4" } });
    fireEvent.blur(input);
    expect(screen.getByTestId("auto-pilot-status-max-in-flight")).toHaveTextContent("Not saved:");
    fireEvent.change(input, { target: { value: "0" } });
    fireEvent.blur(input);
    expect(screen.getByTestId("auto-pilot-status-max-in-flight")).toHaveTextContent("");
  });

  it("an edit made while a save is on its way survives that save's answer", async () => {
    const answers: Array<() => void> = [];
    const fn = stub({ ...STATE, projects: { linux: [] } });
    const base = fn.getMockImplementation()!;
    fn.mockImplementation((url: string, init?: RequestInit) => {
      if (String(url).endsWith("/autopilot") && init?.method === "POST") {
        return new Promise((resolve) => answers.push(() => resolve(base(url, init))));
      }
      return base(url, init);
    });
    render(<AutoPilotPanel inputStyle={{}} />);
    fireEvent.click(await screen.findByTestId("auto-pilot-account-linux-spc_yt"));
    fireEvent.click(screen.getByTestId("auto-pilot-account-linux-spc_ig"));
    await waitFor(() => expect(answers).toHaveLength(1));
    // The first answer knows only spc_yt; the second tick must stay on screen.
    answers[0]();
    await waitFor(() => expect(answers).toHaveLength(2));
    expect(screen.getByTestId("auto-pilot-account-linux-spc_ig")).toBeChecked();
    answers[1]();
    await waitFor(() => expect(screen.getByTestId("auto-pilot-status-project-linux")).toHaveTextContent("✓ Saved"));
    expect(posted(fn).projects).toEqual({ linux: ["spc_ig", "spc_yt"] });
    expect(screen.getByTestId("auto-pilot-account-linux-spc_ig")).toBeChecked();
  });

  it("says why it starts nothing new when the limit is full", async () => {
    // Without the reason, a full limit is indistinguishable from a broken Auto Pilot.
    stub({ ...STATE, enabled: true, projects: { linux: [] }, max_in_flight: 10, in_flight: 10 });
    render(<AutoPilotPanel inputStyle={{}} />);
    expect(await screen.findByTestId("auto-pilot-ceiling"))
      .toHaveTextContent("Paused — 10 of 10 videos in progress");
  });

  it("keeps the count current while the tab is open, without touching what is being typed", async () => {
    // Videos publish while the panel sits open; a count read once on mount
    // would keep saying "Paused" after one went out.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const full = { ...STATE, enabled: true, max_in_flight: 10, in_flight: 10 };
    const fn = stub(full);
    render(<AutoPilotPanel inputStyle={{}} />);
    expect(await screen.findByTestId("auto-pilot-ceiling")).toHaveTextContent("Paused — 10 of 10");

    fireEvent.change(screen.getByTestId("input-auto-pilot-max-in-flight"), { target: { value: "7" } });
    stub({ ...full, in_flight: 9, max_in_flight: 10 });
    await vi.advanceTimersByTimeAsync(AUTO_PILOT_POLL_MS);

    await waitFor(() => expect(screen.getByTestId("auto-pilot-ceiling"))
      .toHaveTextContent("9 of 10 videos in progress."));
    expect(screen.getByTestId("auto-pilot-ceiling")).not.toHaveTextContent("Paused");
    expect(screen.getByTestId("input-auto-pilot-max-in-flight")).toHaveValue(7);
    expect(fn).toHaveBeenCalled();
    vi.useRealTimers();
  });

  it("counts videos in progress against the limit, and shows nothing with no limit", async () => {
    stub({ ...STATE, enabled: true, max_in_flight: 10, in_flight: 3 });
    const { unmount } = render(<AutoPilotPanel inputStyle={{}} />);
    const line = await screen.findByTestId("auto-pilot-ceiling");
    expect(line).toHaveTextContent("3 of 10 videos in progress");
    expect(line).not.toHaveTextContent("Paused");
    // The number is sized in days of posting, not posts: the help text says so.
    expect(screen.getByText("Most videos in progress")).toBeInTheDocument();
    expect(screen.getByText(/Size it in days of posting/)).toBeInTheDocument();
    unmount();

    stub({ ...STATE, enabled: true, in_flight: 3 });
    render(<AutoPilotPanel inputStyle={{}} />);
    await screen.findByTestId("input-auto-pilot-max-in-flight");
    expect(screen.queryByTestId("auto-pilot-ceiling")).toBeNull();
  });

  it("shows an account that is no longer offered, so it can be removed", async () => {
    // spc_off is connected but switched off on the Socials page; spc_gone is
    // not connected at all. Hidden, either would be resent on every save.
    const fn = stub({ ...STATE, projects: { linux: ["spc_gone", "spc_off", "spc_yt"] } });
    render(<AutoPilotPanel inputStyle={{}} />);
    const stale = await screen.findByTestId("auto-pilot-stale-linux-spc_off");
    expect(stale).toBeChecked();
    expect(screen.getByTestId("auto-pilot-account-linux-spc_yt")).toBeChecked();

    fireEvent.click(stale);
    expect(screen.queryByTestId("auto-pilot-stale-linux-spc_off")).toBeNull();
    fireEvent.click(screen.getByTestId("auto-pilot-stale-linux-spc_gone"));
    await waitFor(() => expect(posts(fn)).toHaveLength(2));
    expect(posted(fn).projects).toEqual({ linux: ["spc_yt"] });
  });

  it("says nothing usable is chosen when only unavailable accounts are", async () => {
    stub({ ...STATE, projects: { linux: ["spc_off"] } });
    render(<AutoPilotPanel inputStyle={{}} />);
    expect(await screen.findByTestId("auto-pilot-no-accounts-linux")).toHaveTextContent("Video Approved");
  });

  it("keeps chosen accounts removable while publishing is off", async () => {
    stub({ ...STATE, projects: { linux: ["spc_yt"] } }, { accountsOk: false });
    render(<AutoPilotPanel inputStyle={{}} />);
    expect(await screen.findByTestId("auto-pilot-stale-linux-spc_yt")).toBeChecked();
  });

  it("shows a refused save beside the change and goes back to what is stored", async () => {
    stub(STATE, { saveOk: false });
    render(<AutoPilotPanel inputStyle={{}} />);
    fireEvent.click(await screen.findByTestId("auto-pilot-project-toggle-linux"));
    expect(await screen.findByText("Not saved: Unknown project(s): linux")).toBeTruthy();
    expect(screen.getByTestId("auto-pilot-project-toggle-linux")).not.toBeChecked();
  });

  it("never treats a response that is not a configuration as one", async () => {
    // Other suites' fetch mocks answer every URL with a settings object; a
    // proxy error does the same in production. Rendering that as "off, no
    // projects" would let the next change wipe the real configuration.
    stub({ pipeline_paused: false });
    render(<AutoPilotPanel inputStyle={{}} />);
    expect(await screen.findByTestId("auto-pilot-error")).toBeTruthy();
    expect(screen.queryByTestId("toggle-auto-pilot")).toBeNull();
  });
});

describe("autoPilot helpers", () => {
  it("round-trips the gap between minutes and hours", () => {
    expect(splitGap(240)).toEqual({ value: 4, unit: "hours" });
    expect(splitGap(90)).toEqual({ value: 90, unit: "minutes" });
    expect(splitGap(0)).toEqual({ value: 0, unit: "minutes" });
    expect(gapMins(4, "hours")).toBe(240);
    expect(gapMins(90, "minutes")).toBe(90);
  });

  it("confirms turning on and adding a project, not narrowing", () => {
    const on: AutoPilotState = { ...STATE, enabled: true, projects: { linux: [] } };
    const cfg = (enabled: boolean, projects: Record<string, string[]>) =>
      ({ enabled, gap_mins: 240, max_in_flight: 0, projects, account_limits: {} });
    expect(needsConfirmation(STATE, cfg(true, {}))).toBe(true);
    expect(needsConfirmation(on, cfg(true, { linux: [], net: [] }))).toBe(true);
    expect(needsConfirmation(on, cfg(true, { linux: ["spc_yt"] }))).toBe(false);
    expect(needsConfirmation(on, cfg(true, {}))).toBe(false);
    expect(needsConfirmation(on, cfg(false, { linux: [], net: [] }))).toBe(false);
  });

  it("counts only checkpoints in projects that are newly acted on", () => {
    const on: AutoPilotState = { ...STATE, enabled: true, projects: { linux: [] },
                                 waiting: { linux: { SCRIPT_READY: 5 }, net: { VIDEO_READY: 2 } } };
    const next = { enabled: true, gap_mins: 0, max_in_flight: 0, projects: { linux: [], net: [] },
                   account_limits: {} };
    expect(newlyApproved(on, next)).toBe(2);
    expect(newlyApproved({ ...on, enabled: false }, next)).toBe(7);
  });

  it("calls a full limit a pause only while Auto Pilot is on", () => {
    const full = { ...STATE, enabled: true, max_in_flight: 5, in_flight: 5 };
    expect(ceilingStatus(full)).toEqual({
      paused: true,
      text: "Paused — 5 of 5 videos in progress. Auto Pilot starts new videos again as these " +
            "publish; finished videos are still approved and scheduled." });
    expect(ceilingStatus({ ...full, in_flight: 7 })?.paused).toBe(true);
    expect(ceilingStatus({ ...full, enabled: false }))
      .toEqual({ paused: false, text: "5 of 5 videos in progress." });
    expect(ceilingStatus({ ...full, in_flight: 1 }))
      .toEqual({ paused: false, text: "1 of 5 videos in progress." });
    expect(ceilingStatus({ ...full, max_in_flight: 0 })).toBeNull();
  });
});
