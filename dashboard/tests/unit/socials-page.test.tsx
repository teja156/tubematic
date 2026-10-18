/**
 * Socials page (TMDEV-83) — the account allowlist.
 *
 * The load-bearing behaviour here is that this is an ALLOWLIST, not a mirror of
 * what is connected to postforme: the same postforme project may hold personal
 * accounts that must never receive pipeline output. Everything below exists to
 * keep that true, plus the reconciliation case (allowlisted upstream, gone now)
 * that otherwise only surfaces as a failed publish.
 */
import { render, screen, act, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import SocialsPage from "@/app/socials/page";
import type { SocialAccount } from "@/lib/types";

vi.mock("@/components/SectionLabel", () => ({
  SectionLabel: ({ label, count }: { label: string; count?: string }) => (
    <div data-testid="section-label">{label} {count}</div>
  ),
}));

const YT: SocialAccount = {
  id: "spc_yt", platform: "youtube", username: "Chan",
  profile_photo_url: "", status: "connected", allowed: true, available: true,
};
const IG: SocialAccount = {
  id: "spc_ig", platform: "instagram", username: "chan_",
  profile_photo_url: "", status: "connected", allowed: false, available: true,
};
const GONE: SocialAccount = {
  id: "spc_gone", platform: "", username: "",
  profile_photo_url: "", status: "disconnected", allowed: true, available: false,
};

function stubFetch(accounts: SocialAccount[] | { error: string }, ok = true) {
  const fn = vi.fn().mockImplementation((_url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      return Promise.resolve({ ok: true, json: async () => ({ account_ids: [] }) });
    }
    return Promise.resolve({ ok, json: async () => accounts });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

describe("SocialsPage", () => {
  beforeEach(() => stubFetch([YT, IG]));
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("groups accounts by platform", async () => {
    render(<SocialsPage />);
    await screen.findByTestId("platform-group-youtube");
    expect(screen.getByTestId("platform-group-instagram")).toBeInTheDocument();
  });

  it("reflects which accounts are allowlisted", async () => {
    render(<SocialsPage />);
    await screen.findByTestId("account-toggle-spc_yt");
    expect(screen.getByTestId("account-toggle-spc_yt")).toBeChecked();
    expect(screen.getByTestId("account-toggle-spc_ig")).not.toBeChecked();
  });

  it("counts only the enabled accounts, not everything connected", async () => {
    render(<SocialsPage />);
    await waitFor(() =>
      expect(screen.getByTestId("section-label")).toHaveTextContent("1 Enabled"));
  });

  it("saves ids only — display data is hydrated live on every load", async () => {
    const fetchMock = stubFetch([YT, IG]);
    render(<SocialsPage />);
    await screen.findByTestId("account-toggle-spc_ig");
    await act(async () => {
      fireEvent.click(screen.getByTestId("account-toggle-spc_ig"));
    });
    const post = fetchMock.mock.calls.find(
      ([, init]) => (init as RequestInit | undefined)?.method === "POST",
    );
    expect(JSON.parse((post![1] as RequestInit).body as string))
      .toEqual({ account_ids: ["spc_yt", "spc_ig"] });
  });

  it("removes an account from the allowlist when unticked", async () => {
    const fetchMock = stubFetch([YT, IG]);
    render(<SocialsPage />);
    await screen.findByTestId("account-toggle-spc_yt");
    await act(async () => {
      fireEvent.click(screen.getByTestId("account-toggle-spc_yt"));
    });
    const post = fetchMock.mock.calls.find(
      ([, init]) => (init as RequestInit | undefined)?.method === "POST",
    );
    expect(JSON.parse((post![1] as RequestInit).body as string)).toEqual({ account_ids: [] });
  });

  it("flags an allowlisted account that is gone upstream", async () => {
    stubFetch([YT, GONE]);
    render(<SocialsPage />);
    await screen.findByTestId("account-unavailable-spc_gone");
  });

  it("still lets a vanished account be unticked, so the list can be cleaned up", async () => {
    stubFetch([GONE]);
    render(<SocialsPage />);
    const toggle = await screen.findByTestId("account-toggle-spc_gone");
    expect(toggle).not.toBeDisabled();
  });

  it("surfaces the API's own message when publishing is not configured", async () => {
    stubFetch({ error: "Publishing is disabled — turn it on in Settings first." }, false);
    render(<SocialsPage />);
    const err = await screen.findByTestId("socials-error");
    expect(err).toHaveTextContent("Publishing is disabled");
  });

  it("does not render a phantom account list when the call failed", async () => {
    stubFetch({ error: "nope" }, false);
    render(<SocialsPage />);
    await screen.findByTestId("socials-error");
    expect(screen.queryByTestId("account-row-spc_yt")).toBeNull();
  });

  it("says so when nothing is connected", async () => {
    stubFetch([]);
    render(<SocialsPage />);
    await screen.findByTestId("socials-empty");
  });

  it("flags an account that can publish but will never yield metrics", async () => {
    // `feeds` is granted separately from posting, at connect time. Without this
    // the account looks entirely healthy and simply never produces analytics.
    stubFetch([{ ...YT, analytics: false }]);
    render(<SocialsPage />);
    expect(await screen.findByTestId("account-no-analytics-spc_yt"))
      .toHaveTextContent("NO ANALYTICS");
  });

  it("says nothing when the feed check passed or was not run", async () => {
    stubFetch([{ ...YT, analytics: true }, { ...IG, analytics: null }]);
    render(<SocialsPage />);
    await screen.findByTestId("account-row-spc_yt");
    expect(screen.queryByTestId("account-no-analytics-spc_yt")).toBeNull();
    expect(screen.queryByTestId("account-no-analytics-spc_ig")).toBeNull();
  });

  it("re-reads the account list on demand", async () => {
    // The list is fetched once on mount and never polled: it changes only when
    // someone connects or disconnects an account at postforme, outside this app.
    const fetchMock = stubFetch([YT]);
    render(<SocialsPage />);
    await screen.findByTestId("account-row-spc_yt");
    const before = fetchMock.mock.calls.length;

    await act(async () => {
      fireEvent.click(screen.getByTestId("refresh-accounts"));
    });
    expect(fetchMock.mock.calls.length).toBeGreaterThan(before);
  });

  it("picks up an account connected elsewhere since the page loaded", async () => {
    let current: SocialAccount[] = [YT];
    vi.stubGlobal("fetch", vi.fn().mockImplementation((_url: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        return Promise.resolve({ ok: true, json: async () => ({ account_ids: [] }) });
      }
      return Promise.resolve({ ok: true, json: async () => current });
    }));

    render(<SocialsPage />);
    await screen.findByTestId("account-row-spc_yt");
    expect(screen.queryByTestId("account-row-spc_ig")).toBeNull();

    current = [YT, IG];   // connected at postforme in another tab
    await act(async () => {
      fireEvent.click(screen.getByTestId("refresh-accounts"));
    });
    expect(await screen.findByTestId("account-row-spc_ig")).toBeInTheDocument();
  });

  it("clears a stale error once the refresh succeeds", async () => {
    let failing = true;
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() =>
      failing
        ? Promise.resolve({ ok: false, json: async () => ({ error: "Publishing is disabled" }) })
        : Promise.resolve({ ok: true, json: async () => [YT] })));

    render(<SocialsPage />);
    await screen.findByTestId("socials-error");

    failing = false;
    await act(async () => {
      fireEvent.click(screen.getByTestId("refresh-accounts"));
    });
    expect(screen.queryByTestId("socials-error")).toBeNull();
    expect(screen.getByTestId("account-row-spc_yt")).toBeInTheDocument();
  });
});

/**
 * Connect buttons (TMDEV-144). The API mints a postforme consent URL that
 * always asks for `feeds` as well as `posts`; postforme's own default is posts
 * alone, which publishes fine and silently never reports a metric.
 *
 * The tab is opened INSIDE the click, before the URL exists, because a popup
 * blocker only allows window.open during the user gesture — and the URL is
 * minted per click (its `state` is single-use), so it cannot be fetched ahead.
 */
describe("SocialsPage connect", () => {
  type FakeTab = { opener: unknown; location: { href: string }; close: ReturnType<typeof vi.fn> };
  let tab: FakeTab;
  let openSpy: ReturnType<typeof vi.fn>;

  function stubConnect(reply: { ok: boolean; body: unknown }, pending?: Promise<void>) {
    const fn = vi.fn().mockImplementation(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/publishing/accounts/connect")) {
        if (pending) await pending;
        return { ok: reply.ok, json: async () => reply.body };
      }
      if (init?.method === "POST") return { ok: true, json: async () => ({ account_ids: [] }) };
      return { ok: true, json: async () => [YT] };
    });
    vi.stubGlobal("fetch", fn);
    return fn;
  }

  beforeEach(() => {
    tab = { opener: "parent", location: { href: "" }, close: vi.fn() };
    openSpy = vi.fn(() => tab);
    vi.stubGlobal("open", openSpy);
  });
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("offers one connect button per platform", async () => {
    stubConnect({ ok: true, body: {} });
    render(<SocialsPage />);
    await screen.findByTestId("account-row-spc_yt");
    for (const p of ["youtube", "instagram", "tiktok", "facebook"]) {
      expect(screen.getByTestId(`connect-${p}`)).toBeInTheDocument();
    }
  });

  it("opens a tab during the click, then sends it to the minted URL", async () => {
    const url = "https://www.instagram.com/oauth/authorize?state=s1";
    const fetchMock = stubConnect({ ok: true, body: { platform: "instagram", url } });
    render(<SocialsPage />);
    await screen.findByTestId("account-row-spc_yt");

    await act(async () => {
      fireEvent.click(screen.getByTestId("connect-instagram"));
    });

    expect(openSpy).toHaveBeenCalledWith("", "_blank");
    expect(tab.opener).toBeNull();
    const call = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/publishing/accounts/connect"));
    expect(call?.[1]?.method).toBe("POST");
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ platform: "instagram" });
    await waitFor(() => expect(tab.location.href).toBe(url));
    expect(tab.close).not.toHaveBeenCalled();
    // The flow ends on postforme's own page; the user comes back by hand.
    expect(screen.getByTestId("connect-pending")).toHaveTextContent(/refresh/i);
  });

  it("closes the tab and shows postforme's message when the platform is not enabled", async () => {
    const msg = "postforme returned HTTP 404: Social provider app credentials not found for "
      + "facebook. Please set up or enable this platform in Project Setup.";
    stubConnect({ ok: false, body: { error: msg } });
    render(<SocialsPage />);
    await screen.findByTestId("account-row-spc_yt");

    await act(async () => {
      fireEvent.click(screen.getByTestId("connect-facebook"));
    });

    await waitFor(() => expect(tab.close).toHaveBeenCalled());
    expect(screen.getByTestId("connect-error")).toHaveTextContent("enable this platform in Project Setup");
    expect(screen.queryByTestId("connect-pending")).toBeNull();
  });

  it("closes the tab when the API cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation((url: string) =>
      String(url).endsWith("/connect")
        ? Promise.reject(new Error("down"))
        : Promise.resolve({ ok: true, json: async () => [YT] })));
    render(<SocialsPage />);
    await screen.findByTestId("account-row-spc_yt");

    await act(async () => {
      fireEvent.click(screen.getByTestId("connect-youtube"));
    });

    await waitFor(() => expect(tab.close).toHaveBeenCalled());
    expect(screen.getByTestId("connect-error")).toBeInTheDocument();
  });

  it("allows one connect at a time", async () => {
    let release!: () => void;
    const pending = new Promise<void>((r) => { release = r; });
    stubConnect({ ok: true, body: { platform: "youtube", url: "https://accounts.google.com/x" } }, pending);
    render(<SocialsPage />);
    await screen.findByTestId("account-row-spc_yt");

    await act(async () => {
      fireEvent.click(screen.getByTestId("connect-youtube"));
    });
    expect(screen.getByTestId("connect-tiktok")).toBeDisabled();
    expect(screen.getByTestId("connect-youtube")).toBeDisabled();

    await act(async () => { release(); });
    await waitFor(() => expect(screen.getByTestId("connect-tiktok")).not.toBeDisabled());
  });

  it("does not repeat the page's own error under the buttons", async () => {
    // Publishing off: the list and the connect both answer the same 503, and
    // the page already shows it above.
    const msg = "Publishing is disabled — turn it on in Settings first.";
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() =>
      Promise.resolve({ ok: false, json: async () => ({ error: msg }) })));
    render(<SocialsPage />);
    await screen.findByTestId("socials-error");

    await act(async () => {
      fireEvent.click(screen.getByTestId("connect-youtube"));
    });

    await waitFor(() => expect(tab.close).toHaveBeenCalled());
    expect(screen.getAllByText(msg)).toHaveLength(1);
    expect(screen.queryByTestId("connect-error")).toBeNull();
  });

  it("still shows a connect error that differs from the page's", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation((url: string) =>
      Promise.resolve(String(url).endsWith("/connect")
        ? { ok: false, json: async () => ({ error: "postforme returned HTTP 404: enable it" }) }
        : { ok: false, json: async () => ({ error: "postforme returned HTTP 502: list down" }) })));
    render(<SocialsPage />);
    await screen.findByTestId("socials-error");

    await act(async () => {
      fireEvent.click(screen.getByTestId("connect-facebook"));
    });

    expect(await screen.findByTestId("connect-error")).toHaveTextContent("enable it");
  });

  it("falls back to a link when the browser blocked the tab", async () => {
    openSpy.mockReturnValue(null);
    const url = "https://accounts.google.com/o/oauth2/v2/auth?state=s2";
    stubConnect({ ok: true, body: { platform: "youtube", url } });
    render(<SocialsPage />);
    await screen.findByTestId("account-row-spc_yt");

    await act(async () => {
      fireEvent.click(screen.getByTestId("connect-youtube"));
    });

    const link = await screen.findByTestId("connect-link");
    expect(link).toHaveAttribute("href", url);
    expect(link).toHaveAttribute("target", "_blank");
    expect(link.getAttribute("rel")).toContain("noopener");
  });
});
