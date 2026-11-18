/**
 * External styles on the dashboard (TMDEV-253): the Styles page and the
 * install screen. The install screen is where a person says yes, with their
 * dashboard password; nothing else on the page installs a package.
 */
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const nav = vi.hoisted(() => ({ push: vi.fn(), id: "0123456789abcdef" }));
vi.mock("next/navigation", () => ({
  usePathname: () => "/styles",
  useRouter: () => ({ push: nav.push }),
  useParams: () => ({ id: nav.id }),
}));
vi.mock("@/components/SectionLabel", () => ({
  SectionLabel: ({ label }: { label: string }) => <div data-testid="section-label">{label}</div>,
}));

import StylesPage from "@/app/styles/page";
import InstallScreen from "@/app/styles/install/[id]/page";
import { installBlocked, installWarning, sourceLabel, type PendingInstall } from "@/lib/externalStyles";

const PENDING: PendingInstall = {
  id: "0123456789abcdef", style_id: "ext_test", label: "Test Style", version: "1.0.0", author: "someone",
  licence: "MIT", homepage: "", renderer: "dom", needs_gpu: false,
  source: { kind: "zip", filename: "test.zip" }, reviewed: false,
  created_at: "2026-11-18T00:00:00Z", expires_at: "2026-11-19T00:00:00Z", fingerprint: "abc",
  check: { ok: true, reason: "" },
  scan: { refusals: [], flags: [{ file: "components/Main.tsx", line: 3, what: "reaches the network (fetch)" }],
          files: [{ path: "components/Main.tsx", bytes: 120, lines: 5 }, { path: "preview.mp4", bytes: 900 }],
          imports: { remotion: 1 }, guide: "# Guide\nDraw it.", fonts: [] },
  replaces: null, audit: { verdict: "concerns", notes: "Main.tsx line 3 calls fetch", at: "x" },
  in_use: { videos: [], domains: [] },
};

type Call = { url: string; init?: RequestInit };

function mockFetch(routes: Record<string, { status?: number; body: unknown }>) {
  const calls: Call[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: unknown, init?: RequestInit) => {
    const u = String(url);
    calls.push({ url: u, init });
    const key = Object.keys(routes).sort((a, b) => b.length - a.length).find((k) => u.includes(k));
    const hit = key ? routes[key] : { body: {} };
    return { ok: (hit.status ?? 200) < 400, status: hit.status ?? 200, json: async () => hit.body } as Response;
  }));
  return calls;
}

afterEach(() => { vi.unstubAllGlobals(); nav.push.mockReset(); });

describe("the helpers", () => {
  it("words the warning by where the package came from", () => {
    expect(installWarning({ reviewed: true }).level).toBe("reviewed");
    expect(installWarning({ reviewed: false }).text).toMatch(/Nobody has reviewed this package/);
    expect(sourceLabel({ kind: "git", url: "https://x/y", commit: "0123456789abcdef0123" })).toBe(
      "Git repository https://x/y at 0123456789ab");
    expect(sourceLabel(null)).toMatch(/by hand/);
  });

  it("blocks the install of a package that fails its check or the scan", () => {
    expect(installBlocked(PENDING)).toBe("");
    expect(installBlocked({ ...PENDING, check: { ok: false, reason: "schema.json is missing" } })).toMatch(/schema.json/);
    expect(installBlocked({ ...PENDING, scan: { ...PENDING.scan, refusals: ["x"] } })).toMatch(/refused/);
  });
});

describe("the install screen", () => {
  it("shows the warning, the scan, the audit and the guide, and installs with the password", async () => {
    const calls = mockFetch({
      "/external-styles/pending/0123456789abcdef/confirm": { body: { style_id: "ext_test" } },
      "/external-styles/pending/0123456789abcdef/file": { body: { text: "export default 1;" } },
      "/external-styles/pending/0123456789abcdef": { body: PENDING },
    });
    render(<InstallScreen />);
    await act(async () => {});
    expect(screen.getByTestId("install-warning").getAttribute("data-level")).toBe("unreviewed");
    expect(screen.getByTestId("install-flags").textContent).toContain("components/Main.tsx:3");
    expect(screen.getByTestId("install-audit").textContent).toContain("Concerns");
    expect(screen.getByTestId("install-guide").textContent).toContain("Draw it.");
    expect(screen.queryByTestId("install-reviewed")).toBeNull();
    fireEvent.click(screen.getByText("components/Main.tsx"));
    await act(async () => {});
    expect(screen.getByTestId("install-file-view").textContent).toContain("export default 1;");

    const button = screen.getByTestId("install-confirm") as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    fireEvent.change(screen.getByTestId("install-password"), { target: { value: "secret pw" } });
    await act(async () => { fireEvent.click(button); });
    const confirm = calls.find((c) => c.url.endsWith("/confirm"));
    expect(JSON.parse(String(confirm?.init?.body))).toEqual({ password: "secret pw" });
    expect(nav.push).toHaveBeenCalledWith("/styles");
  });

  it("shows a wrong password and keeps the person on the screen", async () => {
    mockFetch({
      "/external-styles/pending/0123456789abcdef/confirm": { status: 401, body: { error: "wrong password" } },
      "/external-styles/pending/0123456789abcdef": { body: PENDING },
    });
    render(<InstallScreen />);
    await act(async () => {});
    fireEvent.change(screen.getByTestId("install-password"), { target: { value: "nope" } });
    await act(async () => { fireEvent.click(screen.getByTestId("install-confirm")); });
    expect(screen.getByTestId("install-error").textContent).toBe("wrong password");
    expect(nav.push).not.toHaveBeenCalled();
    expect((screen.getByTestId("install-password") as HTMLInputElement).value).toBe("");
  });

  it("offers no install for a refused package, and marks a gallery package reviewed", async () => {
    mockFetch({ "/external-styles/pending/0123456789abcdef": { body: {
      ...PENDING, reviewed: true, source: { kind: "gallery", gallery_id: "ext_test" },
      scan: { ...PENDING.scan, refusals: ["components/Main.tsx: imports 'fs'"] } } } });
    render(<InstallScreen />);
    await act(async () => {});
    expect(screen.queryByTestId("install-password")).toBeNull();
    expect(screen.getByTestId("install-blocked").textContent).toMatch(/refused/);
    expect(screen.getByTestId("install-reviewed")).toBeTruthy();
    expect(screen.getByTestId("install-warning").getAttribute("data-level")).toBe("reviewed");
  });

  it("says when the install no longer waits", async () => {
    mockFetch({ "/external-styles/pending/": { status: 404, body: { error: "no such pending install (it may have expired)" } } });
    render(<InstallScreen />);
    await act(async () => {});
    expect(screen.getByTestId("install-load-error").textContent).toMatch(/expired/);
  });
});

const INSTALLED = [
  { id: "ext_good", label: "Good", ok: true, reason: "", needs_review: false, version: "1.0.0", author: "a",
    licence: "MIT", homepage: "", renderer: "dom", needs_gpu: false, source: { kind: "gallery", gallery_id: "ext_good" },
    reviewed: true, installed_at: "x", in_auto: false, unfinished_videos: 0, domains: [] },
  { id: "ext_copied", label: "Copied", ok: false, reason: "it has not been approved", needs_review: true, version: "1",
    author: "b", licence: "MIT", homepage: "", renderer: "dom", needs_gpu: false, source: null, reviewed: false,
    installed_at: "", in_auto: false, unfinished_videos: 2, domains: [] },
];

describe("the Styles page", () => {
  it("lists installed styles with their badges, reasons and use, and pending installs", async () => {
    mockFetch({ "/external-styles": { body: { styles: INSTALLED, pending: [PENDING], gallery_url: "" } } });
    render(<StylesPage />);
    await act(async () => {});
    expect(screen.getAllByTestId("installed-row")).toHaveLength(2);
    expect(screen.getAllByTestId("external-badge")).toHaveLength(2);
    expect(screen.getAllByTestId("reviewed-badge")).toHaveLength(1);
    expect(screen.getByTestId("installed-reason").textContent).toMatch(/not been approved/);
    expect(screen.getByText(/In use by 2 unfinished videos/)).toBeTruthy();
    expect(screen.getAllByTestId("pending-row")).toHaveLength(1);
    expect((screen.getAllByTestId("auto-toggle")[1] as HTMLInputElement).disabled).toBe(true);
  });

  it("re-reviews a hand-copied package through the install screen", async () => {
    const calls = mockFetch({
      "/external-styles/pending": { status: 201, body: { id: "fedcba9876543210" } },
      "/external-styles": { body: { styles: INSTALLED, pending: [], gallery_url: "" } },
    });
    render(<StylesPage />);
    await act(async () => {});
    await act(async () => { fireEvent.click(screen.getByTestId("review-installed")); });
    const stage = calls.find((c) => c.url.endsWith("/external-styles/pending") && c.init?.method === "POST");
    expect(JSON.parse(String(stage?.init?.body))).toEqual({ kind: "installed", id: "ext_copied" });
    expect(nav.push).toHaveBeenCalledWith("/styles/install/fedcba9876543210");
  });

  it("turns Auto on for one style without dropping the others", async () => {
    const calls = mockFetch({ "/external-styles": { body: {
      styles: [{ ...INSTALLED[0], in_auto: true }, { ...INSTALLED[0], id: "ext_two", in_auto: false }],
      pending: [], gallery_url: "" } }, "/settings": { body: {} } });
    render(<StylesPage />);
    await act(async () => {});
    await act(async () => { fireEvent.click(screen.getAllByTestId("auto-toggle")[1]); });
    const post = calls.find((c) => c.url.includes("/settings"));
    expect(JSON.parse(String(post?.init?.body))).toEqual({ external_styles_in_auto: ["ext_good", "ext_two"] });
  });

  it("fetches a repository only with a commit or tag", async () => {
    const calls = mockFetch({
      "/external-styles/pending": { status: 201, body: { id: "0123456789abcdef" } },
      "/external-styles": { body: { styles: [], pending: [], gallery_url: "" } },
    });
    render(<StylesPage />);
    await act(async () => {});
    fireEvent.click(screen.getByTestId("styles-tab-repo"));
    fireEvent.change(screen.getByTestId("repo-url"), { target: { value: "https://github.com/a/b" } });
    expect((screen.getByTestId("repo-stage") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByTestId("repo-ref"), { target: { value: "v1.0.0" } });
    await act(async () => { fireEvent.click(screen.getByTestId("repo-stage")); });
    const stage = calls.find((c) => c.init?.method === "POST");
    expect(JSON.parse(String(stage?.init?.body))).toEqual({ kind: "git", url: "https://github.com/a/b", ref: "v1.0.0" });
  });

  it("shows the gallery's styles and installs one through the install screen", async () => {
    const calls = mockFetch({
      "/external-styles/gallery": { body: { gallery_url: "https://g/i.json", styles: [
        { id: "ext_good", name: "Good", version: "1.1.0", installed_version: "1.0.0", tagline: "t" },
        { id: "ext_new", name: "New", version: "1.0.0", installed_version: null }] } },
      "/external-styles/pending": { status: 201, body: { id: "0123456789abcdef" } },
      "/external-styles": { body: { styles: [], pending: [], gallery_url: "https://g/i.json" } },
    });
    render(<StylesPage />);
    await act(async () => {});
    await act(async () => { fireEvent.click(screen.getByTestId("styles-tab-gallery")); });
    const buttons = screen.getAllByTestId("gallery-install");
    expect(buttons.map((b) => b.textContent)).toEqual(["Update from 1.0.0", "Install"]);
    await act(async () => { fireEvent.click(buttons[1]); });
    const stage = calls.find((c) => c.init?.method === "POST");
    expect(JSON.parse(String(stage?.init?.body))).toEqual({ kind: "gallery", id: "ext_new" });
  });
});
