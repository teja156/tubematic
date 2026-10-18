/**
 * Tests for the Next.js proxy route handler.
 *
 * Critical regressions guarded here:
 *  1. export const dynamic = "force-dynamic"  — prevents Next.js from caching the route
 *  2. Internal fetch uses cache: "no-store"   — bypasses the Next.js Data Cache
 *  3. Every response carries Cache-Control: no-store
 *  4. Network errors from upstream return 502 (not 500 / uncaught throw)
 *  5. Non-JSON upstream responses return 502 (not a parse crash)
 *  6. No valid session → 401 and Flask is never called (TMDEV-152)
 *  7. Every upstream call carries the API token
 *  8. A 401 from Flask means it refused the dashboard's token → 502, never a
 *     401 that would bounce the browser to /login forever
 *  9. A non-GET from another origin (Sec-Fetch-Site other than same-origin) is
 *     403, and one whose body is not JSON is 415 — Flask is never called. A
 *     same-site page (another port, a sibling subdomain) gets the
 *     SameSite=Strict cookie, so this is what stops it (TMDEV-156)
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// vi.hoisted runs before the vi.mock factory (both are hoisted, but hoisted runs first).
const jsonSpy = vi.hoisted(() => vi.fn().mockReturnValue({ _mock: true }));

// ── mock next/server before the route module is imported ────────────────────
vi.mock("next/server", () => ({
  NextResponse: { json: jsonSpy },
}));

const session = vi.hoisted(() => ({ ok: true }));
vi.mock("@/lib/session", () => ({
  isAuthenticated: vi.fn(async () => session.ok),
  apiToken: vi.fn(() => "test-api-token"),
}));

// Static import runs after the vi.mock hoisting completes.
import { DELETE, dynamic, GET, PATCH, POST } from "@/app/api/proxy/[...path]/route";

// ── helpers ─────────────────────────────────────────────────────────────────

function makeUpstream(body: unknown, status = 200) {
  return {
    status,
    json: () => Promise.resolve(body),
  } as unknown as Response;
}

function makeReq(method = "GET", headers: Record<string, string> = {}, body = "{}") {
  const json: Record<string, string> = method === "GET" ? {} : { "Content-Type": "application/json" };
  return {
    method,
    nextUrl: { search: "" },
    headers: new Headers({ ...json, ...headers }),
    text: vi.fn().mockResolvedValue(body),
  };
}

function makeCtx(path: string[]) {
  return { params: Promise.resolve({ path }) };
}

// ── tests ────────────────────────────────────────────────────────────────────

describe("proxy/[...path]/route", () => {
  beforeEach(() => {
    jsonSpy.mockClear();
    session.ok = true;
  });

  // ── authentication (TMDEV-152) ─────────────────────────────────────────────

  it("answers 401 without a session and never calls Flask", async () => {
    session.ok = false;
    const fetchSpy = vi.spyOn(global, "fetch");
    await GET(makeReq() as never, makeCtx(["settings"]));
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(jsonSpy).toHaveBeenCalledWith(
      { error: "unauthorized" },
      expect.objectContaining({ status: 401 }),
    );
  });

  it("sends the API token on every upstream call, PATCH included", async () => {
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(makeUpstream({}));
    await GET(makeReq() as never, makeCtx(["videos"]));
    await PATCH(makeReq("PATCH") as never, makeCtx(["videos", "v1"]));
    for (const [, init] of fetchSpy.mock.calls) {
      expect((init as RequestInit).headers).toMatchObject({ Authorization: "Bearer test-api-token" });
    }
    expect((fetchSpy.mock.calls[1][1] as RequestInit).headers)
      .toMatchObject({ "Content-Type": "application/json" });
  });

  it("turns a 401 from Flask into a 502 naming the fix", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(makeUpstream({ error: "unauthorized" }, 401));
    await GET(makeReq() as never, makeCtx(["settings"]));
    const [body, init] = jsonSpy.mock.calls[0];
    expect(init.status).toBe(502);
    expect(body.error).toContain("docker compose restart");
  });

  afterEach(() => vi.restoreAllMocks());

  // ── static export ──────────────────────────────────────────────────────────

  it('exports dynamic = "force-dynamic" to prevent Next.js route caching', () => {
    expect(dynamic).toBe("force-dynamic");
  });

  // ── upstream fetch options ─────────────────────────────────────────────────

  it('passes cache: "no-store" to the upstream fetch call', async () => {
    const fetchSpy = vi
      .spyOn(global, "fetch")
      .mockResolvedValue(makeUpstream([]));

    await GET(makeReq() as never, makeCtx(["videos"]));

    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining("/videos"),
      expect.objectContaining({ cache: "no-store" }),
    );
  });

  it("forwards query string to upstream", async () => {
    const fetchSpy = vi
      .spyOn(global, "fetch")
      .mockResolvedValue(makeUpstream([]));

    const req = { ...makeReq(), nextUrl: { search: "?status=PUBLISHED" } };
    await GET(req as never, makeCtx(["videos"]));

    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining("?status=PUBLISHED"),
      expect.anything(),
    );
  });

  // ── response headers ───────────────────────────────────────────────────────

  it("sets Cache-Control: no-store on every successful response", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(makeUpstream({ ok: true }));

    await GET(makeReq() as never, makeCtx(["stats"]));

    expect(jsonSpy).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({
        headers: expect.objectContaining({ "Cache-Control": "no-store" }),
      }),
    );
  });

  // ── error handling ─────────────────────────────────────────────────────────

  it("returns 502 with Cache-Control: no-store when upstream is unreachable", async () => {
    vi.spyOn(global, "fetch").mockRejectedValue(new Error("ECONNREFUSED"));

    await GET(makeReq() as never, makeCtx(["stats"]));

    expect(jsonSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        error: expect.stringContaining("Upstream unreachable"),
      }),
      expect.objectContaining({
        status: 502,
        headers: expect.objectContaining({ "Cache-Control": "no-store" }),
      }),
    );
  });

  it("returns 502 with Cache-Control: no-store when upstream returns non-JSON", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue({
      status: 500,
      json: () => Promise.reject(new SyntaxError("Unexpected token")),
    } as unknown as Response);

    await GET(makeReq() as never, makeCtx(["stats"]));

    expect(jsonSpy).toHaveBeenCalledWith(
      expect.objectContaining({ error: expect.stringContaining("non-JSON") }),
      expect.objectContaining({
        status: 502,
        headers: expect.objectContaining({ "Cache-Control": "no-store" }),
      }),
    );
  });

  // ── PATCH body forwarding ──────────────────────────────────────────────────

  it("forwards request body for PATCH requests", async () => {
    const fetchSpy = vi
      .spyOn(global, "fetch")
      .mockResolvedValue(makeUpstream({ id: "v1", status: "VOICING" }));

    const req = makeReq("PATCH", {}, '{"status":"VOICING"}');

    await PATCH(req as never, makeCtx(["videos", "v1"]));

    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining("/videos/v1"),
      expect.objectContaining({
        method: "PATCH",
        body: '{"status":"VOICING"}',
      }),
    );
  });

  // ── cross-site requests (TMDEV-156) ────────────────────────────────────────

  for (const site of ["same-site", "cross-site", "none"]) {
    it(`refuses a POST with Sec-Fetch-Site: ${site} as 403 and never calls Flask`, async () => {
      const fetchSpy = vi.spyOn(global, "fetch");
      await POST(makeReq("POST", { "Sec-Fetch-Site": site }) as never, makeCtx(["settings"]));
      expect(fetchSpy).not.toHaveBeenCalled();
      expect(jsonSpy).toHaveBeenCalledWith(
        expect.objectContaining({ error: expect.any(String) }),
        expect.objectContaining({ status: 403 }),
      );
    });
  }

  it("refuses a cross-site DELETE too", async () => {
    const fetchSpy = vi.spyOn(global, "fetch");
    await DELETE(makeReq("DELETE", { "Sec-Fetch-Site": "same-site" }, "") as never,
      makeCtx(["videos", "v1"]));
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(jsonSpy.mock.calls[0][1].status).toBe(403);
  });

  it("passes a same-origin POST", async () => {
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(makeUpstream({}));
    await POST(makeReq("POST", { "Sec-Fetch-Site": "same-origin" }) as never, makeCtx(["settings"]));
    expect(fetchSpy).toHaveBeenCalledOnce();
  });

  it("passes a POST with no Sec-Fetch-Site header", async () => {
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(makeUpstream({}));
    await POST(makeReq("POST") as never, makeCtx(["settings"]));
    expect(fetchSpy).toHaveBeenCalledOnce();
  });

  it("never guards a GET, whatever its Sec-Fetch-Site", async () => {
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(makeUpstream([]));
    await GET(makeReq("GET", { "Sec-Fetch-Site": "cross-site" }) as never, makeCtx(["videos"]));
    expect(fetchSpy).toHaveBeenCalledOnce();
  });

  // ── JSON only (TMDEV-156) ──────────────────────────────────────────────────

  for (const type of ["text/plain", "application/x-www-form-urlencoded", "multipart/form-data"]) {
    it(`refuses a ${type} POST as 415 and never calls Flask`, async () => {
      const fetchSpy = vi.spyOn(global, "fetch");
      await POST(makeReq("POST", { "Content-Type": type }, '{"paused":true}') as never,
        makeCtx(["pipeline", "pause"]));
      expect(fetchSpy).not.toHaveBeenCalled();
      expect(jsonSpy.mock.calls[0][1].status).toBe(415);
    });
  }

  it("refuses an EMPTY form POST as 415: a form always sends a Content-Type", async () => {
    const fetchSpy = vi.spyOn(global, "fetch");
    await POST(makeReq("POST", { "Content-Type": "text/plain" }, "") as never,
      makeCtx(["analytics", "refresh"]));
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(jsonSpy.mock.calls[0][1].status).toBe(415);
  });

  it("refuses a body with no Content-Type as 415", async () => {
    const fetchSpy = vi.spyOn(global, "fetch");
    const req = { ...makeReq("POST", {}, '{"x":1}'), headers: new Headers() };
    await POST(req as never, makeCtx(["settings"]));
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(jsonSpy.mock.calls[0][1].status).toBe(415);
  });

  it("forwards the browser's own JSON Content-Type, parameters and all", async () => {
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(makeUpstream({}));
    await POST(makeReq("POST", { "Content-Type": "application/json; charset=utf-8" }) as never,
      makeCtx(["settings"]));
    expect((fetchSpy.mock.calls[0][1] as RequestInit).headers)
      .toMatchObject({ "Content-Type": "application/json; charset=utf-8" });
  });

  it("passes a bodiless POST with no Content-Type, and forwards no body", async () => {
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(makeUpstream({}));
    const req = { ...makeReq("POST", {}, ""), headers: new Headers() };
    await POST(req as never, makeCtx(["videos", "v1", "agent-retry"]));
    expect(fetchSpy).toHaveBeenCalledOnce();
    const init = fetchSpy.mock.calls[0][1] as RequestInit;
    expect(init.body).toBeUndefined();
    expect(init.headers).not.toHaveProperty("Content-Type");
  });
});
