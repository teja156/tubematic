import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ScriptProfilesPage from "@/app/script-profiles/page";
import type { ScriptProfile } from "@/lib/types";

function profile(over: Partial<ScriptProfile> = {}): ScriptProfile {
  return {
    id: "prof-1",
    name: "Corpus A",
    status: "READY",
    source_urls: ["https://youtu.be/aaaaaaaaaaa"],
    error: "",
    attempt_count: 1,
    archived: false,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...over,
  };
}

/** list + detail are separate endpoints: the list omits markdown on purpose. */
function mockFetch({ list = [profile()], detail = profile({ markdown: "# Voice", corpus_summary: "2 transcripts" }), createStatus = 201, createBody = {} as Record<string, unknown> } = {}) {
  return vi.spyOn(global, "fetch").mockImplementation((url: string | URL | Request, init?: RequestInit) => {
    const urlStr = url.toString();
    const method = (init?.method ?? "GET").toUpperCase();
    if (method === "POST") {
      return Promise.resolve({
        ok: createStatus < 400, status: createStatus,
        json: () => Promise.resolve(createBody),
      } as Response);
    }
    if (method === "DELETE") {
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ ok: true }) } as Response);
    }
    if (/\/script-profiles\/[^/]+$/.test(urlStr)) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(detail) } as Response);
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve(list) } as Response);
  });
}

describe("ScriptProfilesPage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists profiles with their status", async () => {
    mockFetch({ list: [profile({ id: "p1", name: "Corpus A", status: "READY" }),
                       profile({ id: "p2", name: "Corpus B", status: "GENERATING" })] });
    render(<ScriptProfilesPage />);
    await waitFor(() => expect(screen.getByText("Corpus A")).toBeTruthy());
    expect(screen.getByText("Corpus B")).toBeTruthy();
    expect(screen.getByText("GENERATING")).toBeTruthy();
  });

  it("fetches the full row on select, since the list omits the markdown", async () => {
    const spy = mockFetch();
    render(<ScriptProfilesPage />);
    await waitFor(() => screen.getByTestId("profile-row-prof-1"));
    fireEvent.click(screen.getByTestId("profile-row-prof-1"));

    await waitFor(() => expect(screen.getByTestId("profile-markdown").textContent).toBe("# Voice"));
    expect(screen.getByTestId("profile-summary").textContent).toBe("2 transcripts");
    expect(spy.mock.calls.some(([u]) => u.toString().endsWith("/script-profiles/prof-1"))).toBe(true);
  });

  it("posts the name and one URL per line", async () => {
    const spy = mockFetch({ list: [] });
    render(<ScriptProfilesPage />);
    fireEvent.change(screen.getByTestId("profile-name"), { target: { value: "  Corpus A  " } });
    fireEvent.change(screen.getByTestId("profile-urls"), {
      target: { value: "https://youtu.be/aaaaaaaaaaa\n\n  https://youtu.be/bbbbbbbbbbb  \n" },
    });
    fireEvent.click(screen.getByTestId("profile-create"));

    await waitFor(() => {
      const post = spy.mock.calls.find(([, init]) => (init as RequestInit)?.method === "POST");
      expect(post).toBeTruthy();
      expect(JSON.parse((post![1] as RequestInit).body as string)).toEqual({
        name: "Corpus A",
        urls: ["https://youtu.be/aaaaaaaaaaa", "https://youtu.be/bbbbbbbbbbb"],
      });
    });
  });

  it("refuses to post without a name or a URL", async () => {
    const spy = mockFetch({ list: [] });
    render(<ScriptProfilesPage />);
    fireEvent.click(screen.getByTestId("profile-create"));
    await waitFor(() => expect(screen.getByTestId("profile-error")).toBeTruthy());
    expect(spy.mock.calls.some(([, init]) => (init as RequestInit)?.method === "POST")).toBe(false);
  });

  it("surfaces the server's message when creation fails", async () => {
    mockFetch({
      list: [], createStatus: 503,
      createBody: { error: "youtube-transcript.io API key not configured" },
    });
    render(<ScriptProfilesPage />);
    fireEvent.change(screen.getByTestId("profile-name"), { target: { value: "A" } });
    fireEvent.change(screen.getByTestId("profile-urls"), { target: { value: "https://youtu.be/aaaaaaaaaaa" } });
    fireEvent.click(screen.getByTestId("profile-create"));

    await waitFor(() => {
      expect(screen.getByTestId("profile-error").textContent).toContain("youtube-transcript.io");
    });
  });

  it("shows a FAILED profile's stored error", async () => {
    mockFetch({
      list: [profile({ status: "FAILED", error: "did not complete after 2 agent session(s)" })],
      detail: profile({ status: "FAILED", error: "did not complete after 2 agent session(s)" }),
    });
    render(<ScriptProfilesPage />);
    await waitFor(() => screen.getByTestId("profile-row-prof-1"));
    fireEvent.click(screen.getByTestId("profile-row-prof-1"));
    await waitFor(() => {
      expect(screen.getByTestId("profile-detail-error").textContent).toContain("2 agent session");
    });
  });

  it("deletes only after confirmation", async () => {
    const spy = mockFetch();
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<ScriptProfilesPage />);
    await waitFor(() => screen.getByTestId("profile-row-prof-1"));
    fireEvent.click(screen.getByTestId("profile-row-prof-1"));
    await waitFor(() => screen.getByTestId("profile-delete"));

    fireEvent.click(screen.getByTestId("profile-delete"));
    expect(spy.mock.calls.some(([, init]) => (init as RequestInit)?.method === "DELETE")).toBe(false);

    confirmSpy.mockReturnValue(true);
    fireEvent.click(screen.getByTestId("profile-delete"));
    await waitFor(() => {
      expect(spy.mock.calls.some(([, init]) => (init as RequestInit)?.method === "DELETE")).toBe(true);
    });
  });
});
