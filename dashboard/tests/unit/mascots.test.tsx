import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import MascotsPage from "@/app/mascots/page";
import type { Mascot } from "@/lib/types";

function mascot(over: Partial<Mascot> = {}): Mascot {
  return {
    id: "moss", name: "Moss", description: "a tardigrade", based_on: "", status: "READY",
    approved_version: 1, agent_id: "", agent_model: "", agent_effort: "", attempt_count: 1,
    error: "", created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
    builtin: false, archived: false, pickable: true, draft_version: null,
    sheets: { approved: null, draft: null }, versions: [], ...over,
  };
}

const AGENTS = [{
  id: "claude", name: "Claude", models: ["opus", "sonnet"], effort: "high", is_default: true, archived_at: null,
}];

/** The list and the by-id read are separate endpoints; the detail carries
 *  versions. Every other URL gets a shape the page must ignore. */
function mockFetch(opts: { list?: Mascot[]; detail?: Mascot; status?: number; body?: Record<string, unknown> } = {}) {
  const list = opts.list ?? [mascot()];
  const detail = opts.detail ?? list[0];
  const status = opts.status ?? 200;
  const body = opts.body ?? {};
  return vi.spyOn(global, "fetch").mockImplementation((url: string | URL | Request, init?: RequestInit) => {
    const u = url.toString();
    const method = (init?.method ?? "GET").toUpperCase();
    const ok = (b: unknown, s = 200) => Promise.resolve({ ok: s < 400, status: s, json: () => Promise.resolve(b) } as Response);
    if (method === "POST" || method === "DELETE") return ok(body, status);
    if (u.endsWith("/agents")) return ok(AGENTS);
    if (u.endsWith("/render/gpu")) return ok({ status: "working" });
    if (/\/mascots\/[^/]+$/.test(u)) return ok(detail);
    if (u.endsWith("/mascots")) return ok(list);
    return ok({});
  });
}

function posts(spy: ReturnType<typeof mockFetch>) {
  return spy.mock.calls
    .filter(([, i]) => (i as RequestInit | undefined)?.method === "POST")
    .map(([u, i]) => [u.toString(), (i as RequestInit).body ? JSON.parse((i as RequestInit).body as string) : null] as const);
}

async function openRow(id: string) {
  await waitFor(() => screen.getByTestId(`mascot-row-${id}`));
  fireEvent.click(screen.getByTestId(`mascot-row-${id}`));
  await waitFor(() => screen.getByTestId("mascot-detail"));
}

describe("MascotsPage", () => {
  beforeEach(() => vi.spyOn(window, "confirm").mockReturnValue(true));
  afterEach(() => vi.restoreAllMocks());

  it("lists mascots with their status, and says when there are none", async () => {
    mockFetch({ list: [mascot({ id: "tubi", name: "Tubi", builtin: true }),
                       mascot({ id: "wip", name: "Wip", status: "BUILDING", approved_version: 0 })] });
    render(<MascotsPage />);
    await waitFor(() => expect(screen.getByText("Tubi")).toBeTruthy());
    expect(screen.getByText("BUILDING")).toBeTruthy();
    expect(screen.getByText(/Built in/)).toBeTruthy();
  });

  it("shows the empty state", async () => {
    mockFetch({ list: [] });
    render(<MascotsPage />);
    await waitFor(() => expect(screen.getByText(/No mascots yet/)).toBeTruthy());
  });

  it("carries the Script profiles / Mascots sub-nav", async () => {
    mockFetch();
    render(<MascotsPage />);
    expect(screen.getByTestId("profiles-subnav-script-profiles").getAttribute("href")).toBe("/script-profiles");
    expect(screen.getByTestId("profiles-subnav-mascots").getAttribute("href")).toBe("/mascots");
  });

  it("creates a mascot from a name and description", async () => {
    const spy = mockFetch({ list: [], body: { id: "new", name: "New", status: "PENDING" } });
    render(<MascotsPage />);
    fireEvent.change(screen.getByTestId("mascot-name"), { target: { value: "  Pip  " } });
    fireEvent.change(screen.getByTestId("mascot-description"), { target: { value: " a robot " } });
    fireEvent.click(screen.getByTestId("mascot-create"));
    await waitFor(() => expect(posts(spy)).toContainEqual([expect.stringMatching(/\/mascots$/), { name: "Pip", description: "a robot" }]));
  });

  it("refuses a create with no description before any request", async () => {
    const spy = mockFetch({ list: [] });
    render(<MascotsPage />);
    fireEvent.change(screen.getByTestId("mascot-name"), { target: { value: "Pip" } });
    fireEvent.click(screen.getByTestId("mascot-create"));
    expect(screen.getByTestId("mascot-error")).toBeTruthy();
    expect(posts(spy)).toEqual([]);
  });

  it("Surprise me sends surprise:true and no name or description", async () => {
    const spy = mockFetch({ list: [], body: { id: "s", status: "PENDING" } });
    render(<MascotsPage />);
    fireEvent.change(screen.getByTestId("mascot-name"), { target: { value: "ignored" } });
    fireEvent.click(screen.getByTestId("mascot-surprise"));
    await waitFor(() => expect(posts(spy)).toEqual([[expect.stringMatching(/\/mascots$/), { surprise: true }]]));
  });

  it("sends the picked agent, model and effort, and nothing for Automatic", async () => {
    const spy = mockFetch({ list: [], body: { id: "n", status: "PENDING" } });
    render(<MascotsPage />);
    await waitFor(() => expect(screen.getByRole("option", { name: "Claude" })).toBeTruthy());
    fireEvent.change(screen.getByTestId("mascot-agent"), { target: { value: "claude" } });
    fireEvent.change(screen.getByTestId("mascot-model"), { target: { value: "sonnet" } });
    fireEvent.change(screen.getByTestId("mascot-effort"), { target: { value: "max" } });
    fireEvent.click(screen.getByTestId("mascot-surprise"));
    await waitFor(() => expect(posts(spy)[0][1]).toEqual({
      surprise: true, agent_id: "claude", agent_model: "sonnet", agent_effort: "max" }));
  });

  it("shows the API's refusal on create", async () => {
    mockFetch({ list: [], status: 400, body: { error: "name too long" } });
    render(<MascotsPage />);
    fireEvent.click(screen.getByTestId("mascot-surprise"));
    await waitFor(() => expect(screen.getByTestId("mascot-error").textContent).toBe("name too long"));
  });

  describe("IN_REVIEW", () => {
    const inReview = mascot({
      status: "IN_REVIEW", approved_version: 1, draft_version: 2, change_request: "bigger eyes",
      agent_id: "claude", agent_model: "opus", agent_effort: "high",
      sheets: {
        approved: { turn: "/mascots/moss/versions/1/sheets/turn" },
        draft: { turn: "/mascots/moss/versions/2/sheets/turn", feels: "/mascots/moss/versions/2/sheets/feels",
                 act: "/mascots/moss/versions/2/sheets/act" },
      },
      versions: [{ version: 1, change_request: "a tardigrade", created_at: "2026-01-01T00:00:00Z", approved_at: "2026-01-02T00:00:00Z", has_code: true },
                 { version: 2, change_request: "bigger eyes", created_at: "2026-01-03T00:00:00Z", approved_at: "", has_code: true }],
    });

    it("shows draft and approved sheets through the dashboard image route, the history and the agent", async () => {
      mockFetch({ list: [inReview], detail: inReview });
      render(<MascotsPage />);
      await openRow("moss");
      for (const n of ["turn", "feels", "act"]) {
        expect(screen.getByTestId(`mascot-sheet-draft-${n}`).getAttribute("src"))
          .toBe(`/mascot-sheets/moss/versions/2/sheets/${n}`);
      }
      expect(screen.getByTestId("mascot-sheet-approved-turn").getAttribute("src"))
        .toBe("/mascot-sheets/moss/versions/1/sheets/turn");
      expect(screen.getByTestId("mascot-version-2").textContent).toContain("bigger eyes");
      expect(screen.getByTestId("mascot-built-by").textContent).toContain("claude · opus · high");
    });

    it("approves", async () => {
      const spy = mockFetch({ list: [inReview], detail: inReview, body: { ...inReview, status: "READY" } });
      render(<MascotsPage />);
      await openRow("moss");
      fireEvent.click(screen.getByTestId("mascot-approve"));
      await waitFor(() => expect(posts(spy)).toContainEqual([expect.stringMatching(/\/mascots\/moss\/approve$/), null]));
    });

    it("requires a comment to request changes, then sends it", async () => {
      const spy = mockFetch({ list: [inReview], detail: inReview, body: { ...inReview, status: "PENDING" } });
      render(<MascotsPage />);
      await openRow("moss");
      const button = screen.getByTestId("mascot-request-changes") as HTMLButtonElement;
      expect(button.disabled).toBe(true);
      fireEvent.change(screen.getByTestId("mascot-comment"), { target: { value: "  rounder  " } });
      expect(button.disabled).toBe(false);
      fireEvent.click(button);
      await waitFor(() => expect(posts(spy)).toContainEqual([expect.stringMatching(/\/mascots\/moss\/request-changes$/), { comment: "rounder" }]));
    });
  });

  it("FAILED shows the error and offers Request changes, not Approve", async () => {
    const failed = mascot({ status: "FAILED", error: "Version 2 failed after 3 attempts" });
    mockFetch({ list: [failed], detail: failed });
    render(<MascotsPage />);
    await openRow("moss");
    expect(screen.getByTestId("mascot-detail-error").textContent).toContain("failed after 3 attempts");
    expect(screen.getByTestId("mascot-request-changes")).toBeTruthy();
    expect(screen.queryByTestId("mascot-approve")).toBeNull();
  });

  it("READY non-builtin offers Request changes only", async () => {
    mockFetch();
    render(<MascotsPage />);
    await openRow("moss");
    expect(screen.getByTestId("mascot-request-changes")).toBeTruthy();
    expect(screen.queryByTestId("mascot-approve")).toBeNull();
    expect(screen.queryByTestId("mascot-variation")).toBeNull();
  });

  it("PENDING and BUILDING offer no review action", async () => {
    const wip = mascot({ status: "BUILDING", approved_version: 0 });
    mockFetch({ list: [wip], detail: wip });
    render(<MascotsPage />);
    await openRow("moss");
    expect(screen.queryByTestId("mascot-approve")).toBeNull();
    expect(screen.queryByTestId("mascot-request-changes")).toBeNull();
  });

  it("a builtin gets 'Ask for a variation' (based_on), never Request changes", async () => {
    const tubi = mascot({ id: "tubi", name: "Tubi", builtin: true });
    const spy = mockFetch({ list: [tubi], detail: tubi, body: { id: "tubi-2", status: "PENDING" } });
    render(<MascotsPage />);
    await openRow("tubi");
    expect(screen.queryByTestId("mascot-request-changes")).toBeNull();
    const button = screen.getByTestId("mascot-variation") as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    fireEvent.change(screen.getByTestId("mascot-variation-name"), { target: { value: "Tubi Red" } });
    fireEvent.change(screen.getByTestId("mascot-variation-description"), { target: { value: "red screen" } });
    fireEvent.click(button);
    await waitFor(() => expect(posts(spy)).toContainEqual([expect.stringMatching(/\/mascots$/),
      { name: "Tubi Red", description: "red screen", based_on: "tubi" }]));
  });

  it("archives after a confirm, and not when the confirm is declined", async () => {
    const spy = mockFetch();
    render(<MascotsPage />);
    await openRow("moss");
    vi.spyOn(window, "confirm").mockReturnValue(false);
    fireEvent.click(screen.getByTestId("mascot-archive"));
    expect(spy.mock.calls.some(([, i]) => (i as RequestInit | undefined)?.method === "DELETE")).toBe(false);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    fireEvent.click(screen.getByTestId("mascot-archive"));
    await waitFor(() => expect(spy.mock.calls.some(([u, i]) =>
      u.toString().endsWith("/mascots/moss") && (i as RequestInit | undefined)?.method === "DELETE")).toBe(true));
    await waitFor(() => expect(screen.queryByTestId("mascot-detail")).toBeNull());
  });

  it("offers nothing for an archived mascot", async () => {
    const gone = mascot({ archived: true, status: "IN_REVIEW", draft_version: 2 });
    mockFetch({ list: [gone], detail: gone });
    render(<MascotsPage />);
    await openRow("moss");
    for (const id of ["mascot-approve", "mascot-request-changes", "mascot-variation", "mascot-archive"]) {
      expect(screen.queryByTestId(id)).toBeNull();
    }
  });
});
