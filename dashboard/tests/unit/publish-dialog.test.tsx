/**
 * PublishDialog (TMDEV-83).
 *
 * Publishing is irreversible — there is no un-publish on any of these
 * platforms — so the dialog's job is to make every target an explicit choice
 * and to never open in a state where one wrong click posts to a real account.
 * That is what most of these tests are actually guarding.
 */
import { render, screen, act, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, afterEach } from "vitest";
import { PublishDialog } from "@/components/PublishDialog";
import type { SocialAccount } from "@/lib/types";
import { addDays, wallClock } from "@/lib/datetime";

const YT: SocialAccount = {
  id: "spc_yt", platform: "youtube", username: "Chan",
  profile_photo_url: "", status: "connected", allowed: true, available: true,
};
const IG: SocialAccount = {
  id: "spc_ig", platform: "instagram", username: "chan_",
  profile_photo_url: "", status: "connected", allowed: true, available: true,
};
const NOT_ALLOWED: SocialAccount = { ...IG, id: "spc_no", allowed: false };
const GONE: SocialAccount = { ...IG, id: "spc_gone", available: false };

function stubFetch({
  accounts = [YT, IG] as SocialAccount[] | { error: string },
  accountsOk = true,
  prefill = { title: "Agent Title", description: "Agent body" } as unknown,
  publishOk = true,
  publishBody = {} as unknown,
} = {}) {
  // Order matters: "/publishing/accounts" contains "/publish", so the accounts
  // route has to be matched before the publish one or every account list comes
  // back as the publish response.
  const fn = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    if (String(url).includes("/publishing/accounts")) {
      return Promise.resolve({ ok: accountsOk, json: async () => accounts });
    }
    if (String(url).includes("publish-prefill")) {
      return Promise.resolve({ ok: true, json: async () => prefill });
    }
    return Promise.resolve({ ok: publishOk, json: async () => publishBody });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

function open(props: Partial<React.ComponentProps<typeof PublishDialog>> = {}) {
  return render(
    <PublishDialog
      open
      videoId="vid_1"
      videoTitle="Fallback Title"
      onClose={() => {}}
      onPublished={() => {}}
      {...props}
    />,
  );
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("PublishDialog", () => {
  it("offers only allowlisted, still-connected accounts", async () => {
    stubFetch({ accounts: [YT, NOT_ALLOWED, GONE] });
    open();
    await screen.findByTestId("publish-target-spc_yt");
    expect(screen.queryByTestId("publish-target-spc_no")).toBeNull();
    expect(screen.queryByTestId("publish-target-spc_gone")).toBeNull();
  });

  it("pre-ticks nothing — every target is an explicit choice", async () => {
    stubFetch();
    open();
    const yt = await screen.findByTestId("publish-target-spc_yt");
    expect(yt).not.toBeChecked();
    expect(screen.getByTestId("publish-target-spc_ig")).not.toBeChecked();
  });

  it("cannot publish until at least one target is picked", async () => {
    stubFetch();
    open();
    await screen.findByTestId("publish-target-spc_yt");
    expect(screen.getByTestId("publish-confirm")).toBeDisabled();
    await act(async () => {
      fireEvent.click(screen.getByTestId("publish-target-spc_yt"));
    });
    expect(screen.getByTestId("publish-confirm")).not.toBeDisabled();
  });

  it("cannot publish with an empty title", async () => {
    stubFetch();
    open();
    await screen.findByTestId("publish-target-spc_yt");
    await act(async () => {
      fireEvent.click(screen.getByTestId("publish-target-spc_yt"));
      fireEvent.change(screen.getByTestId("publish-title"), { target: { value: "  " } });
    });
    expect(screen.getByTestId("publish-confirm")).toBeDisabled();
  });

  it("prefills the title and description the agent wrote with the script", async () => {
    stubFetch();
    open();
    await waitFor(() =>
      expect(screen.getByTestId("publish-title")).toHaveValue("Agent Title"));
    expect(screen.getByTestId("publish-description")).toHaveValue("Agent body");
  });

  it("still opens, on the video's own title, when the prefill call fails", async () => {
    stubFetch({ prefill: null });
    open();
    await waitFor(() =>
      expect(screen.getByTestId("publish-title")).toHaveValue("Fallback Title"));
  });

  it("sends the edited metadata and the picked targets", async () => {
    const fetchMock = stubFetch();
    open();
    await screen.findByTestId("publish-target-spc_yt");
    await act(async () => {
      fireEvent.click(screen.getByTestId("publish-target-spc_yt"));
      fireEvent.click(screen.getByTestId("publish-target-spc_ig"));
      fireEvent.change(screen.getByTestId("publish-title"), { target: { value: "Edited" } });
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId("publish-confirm"));
    });
    const post = fetchMock.mock.calls.find(([url, init]) =>
      String(url).endsWith("/publish") && (init as RequestInit | undefined)?.method === "POST");
    expect(JSON.parse((post![1] as RequestInit).body as string)).toEqual({
      account_ids: ["spc_yt", "spc_ig"],
      title: "Edited",
      description: "Agent body",
      // Empty because nothing was changed — the server applies each platform's
      // own default rather than the dialog echoing one back.
      privacy: {},
    });
  });

  it("unticking a target removes it from the publish", async () => {
    const fetchMock = stubFetch();
    open();
    await screen.findByTestId("publish-target-spc_yt");
    await act(async () => {
      fireEvent.click(screen.getByTestId("publish-target-spc_yt"));
      fireEvent.click(screen.getByTestId("publish-target-spc_ig"));
      fireEvent.click(screen.getByTestId("publish-target-spc_ig"));
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId("publish-confirm"));
    });
    const post = fetchMock.mock.calls.find(([url, init]) =>
      String(url).endsWith("/publish") && (init as RequestInit | undefined)?.method === "POST");
    expect(JSON.parse((post![1] as RequestInit).body as string).account_ids).toEqual(["spc_yt"]);
  });

  it("surfaces a publish failure and stays open", async () => {
    const onClose = vi.fn();
    stubFetch({ publishOk: false, publishBody: { error: "postforme returned HTTP 502" } });
    open({ onClose });
    await screen.findByTestId("publish-target-spc_yt");
    await act(async () => {
      fireEvent.click(screen.getByTestId("publish-target-spc_yt"));
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId("publish-confirm"));
    });
    expect(await screen.findByTestId("publish-error")).toHaveTextContent("HTTP 502");
    expect(onClose).not.toHaveBeenCalled();
  });

  it("closes and refreshes on success", async () => {
    const onClose = vi.fn();
    const onPublished = vi.fn();
    stubFetch();
    open({ onClose, onPublished });
    await screen.findByTestId("publish-target-spc_yt");
    await act(async () => {
      fireEvent.click(screen.getByTestId("publish-target-spc_yt"));
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId("publish-confirm"));
    });
    expect(onPublished).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  it("sizes itself with an inline width, not a class", async () => {
    // Regression guard, not styling pedantry. DialogContent's base classes end
    // with `sm:max-w-sm` (384px); twMerge cannot collapse that against an
    // unprefixed max-w-*, so a class-based width is silently clamped on any
    // desktop screen and the title/description fields overflow the dialog.
    // Inline styles beat the media-query rule — VideoModal does the same.
    stubFetch();
    open();
    const dialog = await screen.findByTestId("publish-dialog");
    // The clamp is right there in the rendered classes and cannot be removed —
    // it comes from DialogContent itself. That is exactly why the width has to
    // be inline: only an inline style outranks that media-query rule.
    expect(dialog.className).toContain("sm:max-w-sm");
    expect(dialog.style.maxWidth).not.toBe("");
    expect(dialog.style.width).not.toBe("");
  });

  it("stays narrower than the VideoModal it opens on top of", async () => {
    // VideoModal is 95vw / maxWidth 1280. A child dialog filling its parent
    // reads as a page change rather than a step within one.
    stubFetch();
    open();
    const dialog = await screen.findByTestId("publish-dialog");
    expect(parseInt(dialog.style.maxWidth, 10)).toBeLessThan(1280);
  });

  it("offers each platform only the privacy states it actually has", async () => {
    stubFetch();
    open();
    await screen.findByTestId("publish-privacy-youtube");
    const yt = screen.getByTestId("publish-privacy-youtube") as HTMLSelectElement;
    expect([...yt.options].map((o) => o.value)).toEqual(["public", "unlisted", "private"]);
    // Instagram has no privacy field at all — a control here would imply
    // something that cannot happen.
    expect(screen.queryByTestId("publish-privacy-instagram")).toBeNull();
    expect(screen.getByTestId("publish-no-privacy-instagram")).toHaveTextContent("always public");
  });

  it("defaults to public, matching what the platforms do", async () => {
    stubFetch();
    open();
    const yt = await screen.findByTestId("publish-privacy-youtube");
    expect(yt).toHaveValue("public");
  });

  it("sends a per-platform privacy choice", async () => {
    const fetchMock = stubFetch();
    open();
    await screen.findByTestId("publish-target-spc_yt");
    await act(async () => {
      fireEvent.click(screen.getByTestId("publish-target-spc_yt"));
      fireEvent.change(screen.getByTestId("publish-privacy-youtube"),
                       { target: { value: "unlisted" } });
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId("publish-confirm"));
    });
    const post = fetchMock.mock.calls.find(([url, init]) =>
      String(url).endsWith("/publish") && (init as RequestInit | undefined)?.method === "POST");
    expect(JSON.parse((post![1] as RequestInit).body as string).privacy)
      .toEqual({ youtube: "unlisted" });
  });

  it("forgets a privacy choice when reopened on another video", async () => {
    stubFetch();
    const { rerender } = render(
      <PublishDialog open videoId="vid_1" videoTitle="First"
                     onClose={() => {}} onPublished={() => {}} />);
    await screen.findByTestId("publish-privacy-youtube");
    await act(async () => {
      fireEvent.change(screen.getByTestId("publish-privacy-youtube"),
                       { target: { value: "private" } });
    });
    await act(async () => {
      rerender(<PublishDialog open videoId="vid_2" videoTitle="Second"
                              onClose={() => {}} onPublished={() => {}} />);
    });
    await waitFor(() =>
      expect(screen.getByTestId("publish-privacy-youtube")).toHaveValue("public"));
  });

  it("warns that a long video will not post as a Short", async () => {
    // YouTube infers Shorts from the file and there is no flag to send, so the
    // only signal available is the duration — and nothing enforces the script
    // budget that keeps videos under three minutes.
    stubFetch({ prefill: { title: "T", description: "D",
                           youtube_short: false, duration_secs: 250 } });
    open();
    const warning = await screen.findByTestId("publish-not-a-short");
    expect(warning).toHaveTextContent("4:10");
    expect(warning).toHaveTextContent("not a Short");
  });

  it("stays quiet when the video is short enough", async () => {
    stubFetch({ prefill: { title: "T", description: "D",
                           youtube_short: true, duration_secs: 92 } });
    open();
    await screen.findByTestId("publish-target-spc_yt");
    expect(screen.queryByTestId("publish-not-a-short")).toBeNull();
  });

  it("stays quiet when the duration is unknown rather than guessing", async () => {
    stubFetch({ prefill: { title: "T", description: "D",
                           youtube_short: null, duration_secs: null } });
    open();
    await screen.findByTestId("publish-target-spc_yt");
    expect(screen.queryByTestId("publish-not-a-short")).toBeNull();
  });

  it("says what to do when no account is enabled yet", async () => {
    stubFetch({ accounts: [] });
    open();
    await screen.findByTestId("publish-no-accounts");
    expect(screen.getByTestId("publish-confirm")).toBeDisabled();
  });
});

// ── Reopening on a different video (review fix) ─────────────────────────────

describe("PublishDialog — reopening", () => {
  it("cannot be confirmed while the dialog is still loading", async () => {
    // Publishing is irreversible; an enabled button over a half-built form is
    // how the wrong metadata reaches the wrong accounts.
    let release: (v: unknown) => void = () => {};
    const pending = new Promise((r) => { release = r; });
    vi.stubGlobal("fetch", vi.fn().mockImplementation((url: string) => {
      if (String(url).includes("/publishing/accounts")) {
        return pending.then(() => ({ ok: true, json: async () => [YT] }));
      }
      return Promise.resolve({ ok: true, json: async () => ({ title: "T", description: "D" }) });
    }));

    open();
    expect(screen.getByTestId("publish-confirm")).toBeDisabled();
    await act(async () => { release(null); });
    expect(await screen.findByTestId("publish-target-spc_yt")).toBeInTheDocument();
  });

  it("drops the previous video's selection and metadata as soon as it reopens", async () => {
    stubFetch();
    const { rerender } = render(
      <PublishDialog open videoId="vid_1" videoTitle="First"
                     onClose={() => {}} onPublished={() => {}} />);
    await screen.findByTestId("publish-target-spc_yt");
    await act(async () => {
      fireEvent.click(screen.getByTestId("publish-target-spc_yt"));
      fireEvent.change(screen.getByTestId("publish-title"), { target: { value: "Edited" } });
    });
    expect(screen.getByTestId("publish-confirm")).not.toBeDisabled();

    // Same dialog, different video — the stale ticks and title must not carry.
    stubFetch({ prefill: { title: "Second AI", description: "Second body" } });
    await act(async () => {
      rerender(<PublishDialog open videoId="vid_2" videoTitle="Second"
                              onClose={() => {}} onPublished={() => {}} />);
    });
    await waitFor(() =>
      expect(screen.getByTestId("publish-title")).toHaveValue("Second AI"));
    expect(screen.getByTestId("publish-target-spc_yt")).not.toBeChecked();
  });

  // ── scheduling (TMDEV-133) ──

  async function pickTargetAndSchedule() {
    await screen.findByTestId("publish-target-spc_yt");
    await act(async () => {
      fireEvent.click(screen.getByTestId("publish-target-spc_yt"));
      fireEvent.click(screen.getByTestId("publish-when-schedule"));
    });
  }

  it("publishes now by default, with no schedule controls on screen", async () => {
    stubFetch();
    open();
    await screen.findByTestId("publish-target-spc_yt");
    expect(screen.getByTestId("publish-when-now")).toBeChecked();
    expect(screen.queryByTestId("publish-timezone")).toBeNull();
  });

  it("defaults the timezone to the browser's own", async () => {
    stubFetch();
    open();
    await pickTargetAndSchedule();
    expect(screen.getByTestId("publish-timezone"))
      .toHaveValue(Intl.DateTimeFormat().resolvedOptions().timeZone);
  });

  it("will not schedule until both a date and a time are picked", async () => {
    stubFetch();
    open();
    await pickTargetAndSchedule();
    expect(screen.getByTestId("publish-confirm")).toBeDisabled();
    expect(screen.getByTestId("publish-confirm")).toHaveTextContent("Schedule for 1");
    await act(async () => {
      fireEvent.change(screen.getByTestId("publish-date"), { target: { value: "2030-01-02" } });
    });
    expect(screen.getByTestId("publish-confirm")).toBeDisabled();
    await act(async () => {
      fireEvent.change(screen.getByTestId("publish-time"), { target: { value: "09:30" } });
    });
    expect(screen.getByTestId("publish-confirm")).not.toBeDisabled();
  });

  it("sends the wall time and the picked zone, never a UTC instant", async () => {
    // The API converts: it owns DST, and a browser-computed instant is exactly
    // the class of bug the Spend presets had (TMDEV-130).
    const fetchMock = stubFetch();
    open();
    await pickTargetAndSchedule();
    await act(async () => {
      // Not Asia/Kolkata: the browser list is CLDR's, which names it
      // Asia/Calcutta — the API accepts either spelling.
      fireEvent.change(screen.getByTestId("publish-timezone"), { target: { value: "Europe/Berlin" } });
      fireEvent.change(screen.getByTestId("publish-date"), { target: { value: "2030-01-02" } });
      fireEvent.change(screen.getByTestId("publish-time"), { target: { value: "09:30" } });
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId("publish-confirm"));
    });
    const post = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/videos/vid_1/publish"));
    expect(JSON.parse((post![1] as RequestInit).body as string).schedule).toEqual({
      local: "2030-01-02T09:30", timezone: "Europe/Berlin",
    });
  });

  it("fills the date and time from a preset, in the picked zone", async () => {
    stubFetch();
    open();
    await pickTargetAndSchedule();
    await act(async () => {
      fireEvent.change(screen.getByTestId("publish-timezone"), { target: { value: "Pacific/Auckland" } });
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId("publish-preset-1"));   // Tomorrow 9:00
    });
    expect(screen.getByTestId("publish-date"))
      .toHaveValue(addDays(wallClock("Pacific/Auckland", new Date()).date, 1));
    expect(screen.getByTestId("publish-time")).toHaveValue("09:00");
  });

  it("shows the API's refusal of a schedule inline", async () => {
    stubFetch({ publishOk: false, publishBody: { error: "A scheduled time must be at least 5 minutes from now." } });
    open();
    await pickTargetAndSchedule();
    await act(async () => {
      fireEvent.click(screen.getByTestId("publish-preset-0"));
    });
    await act(async () => {
      fireEvent.click(screen.getByTestId("publish-confirm"));
    });
    expect(screen.getByTestId("publish-error")).toHaveTextContent("at least 5 minutes");
  });

  it("goes back to publish now when it reopens", async () => {
    stubFetch();
    const { rerender } = render(
      <PublishDialog open videoId="vid_1" videoTitle="First"
                     onClose={() => {}} onPublished={() => {}} />);
    await pickTargetAndSchedule();
    await act(async () => {
      rerender(<PublishDialog open videoId="vid_2" videoTitle="Second"
                              onClose={() => {}} onPublished={() => {}} />);
    });
    expect(screen.getByTestId("publish-when-now")).toBeChecked();
  });
});
