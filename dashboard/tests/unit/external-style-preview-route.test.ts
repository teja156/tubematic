// @vitest-environment node
/**
 * The authenticated proxy for an installed external style's preview (TMDEV-252).
 * Built-in previews are static files of the dashboard image; an external one
 * lives in its package, behind the API. The route carries the same lock as
 * /api/proxy and serves nothing but `<ext id>/preview.mp4|webp`.
 */
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";

const session = vi.hoisted(() => ({ ok: true }));
vi.mock("@/lib/session", () => ({
  isAuthenticated: vi.fn(async () => session.ok),
  apiToken: vi.fn(() => "test-api-token"),
}));

import { GET } from "@/app/external-style-previews/[...path]/route";

const ctx = (path: string[]) => ({ params: Promise.resolve({ path }) });
const req = () => ({ headers: new Headers() }) as never;

function upstream(status: number, type: string, body: string | null = "DATA") {
  return new Response(body, { status, headers: { "content-type": type } });
}

describe("GET /external-style-previews", () => {
  let fetchSpy: MockInstance<typeof fetch>;
  beforeEach(() => {
    session.ok = true;
    fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(upstream(200, "video/mp4"));
  });
  afterEach(() => vi.restoreAllMocks());

  it("401 without a session and never calls Flask", async () => {
    session.ok = false;
    expect((await GET(req(), ctx(["ext_dom", "preview.mp4"]))).status).toBe(401);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("forwards to the API's preview route with the token and passes the file through", async () => {
    const res = await GET(req(), ctx(["ext_dom", "preview.mp4"]));
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toBe("video/mp4");
    expect(await res.text()).toBe("DATA");
    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toMatch(/\/visual-styles\/ext_dom\/preview\.mp4$/);
    expect((init?.headers as Record<string, string>).Authorization).toBe("Bearer test-api-token");
  });

  it.each([
    [["night_signal", "preview.mp4"]], [["ext_dom", "style.json"]], [["ext_dom", "preview.gif"]],
    [["..", "preview.mp4"]], [["ext_dom", "preview.mp4", "x"]], [["ext_dom"]],
  ])("404 for %j before Flask is asked", async (path) => {
    expect((await GET(req(), ctx(path))).status).toBe(404);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("passes a 404 through and refuses an unexpected type", async () => {
    fetchSpy.mockResolvedValueOnce(upstream(404, "application/json", "{}"));
    expect((await GET(req(), ctx(["ext_dom", "preview.mp4"]))).status).toBe(404);
    fetchSpy.mockResolvedValueOnce(upstream(200, "text/html"));
    expect((await GET(req(), ctx(["ext_dom", "preview.mp4"]))).status).toBe(502);
  });
});
