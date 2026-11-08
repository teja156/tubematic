// @vitest-environment node
/**
 * The authenticated image proxy for mascot sheets. /api/proxy is JSON-only and
 * /stream serves only mp4/mp3, so sheets need their own route. It must carry
 * the same lock as /api/proxy and serve nothing but the sheet path shape.
 */
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";

const session = vi.hoisted(() => ({ ok: true }));
vi.mock("@/lib/session", () => ({
  isAuthenticated: vi.fn(async () => session.ok),
  apiToken: vi.fn(() => "test-api-token"),
}));

import { GET } from "@/app/mascot-sheets/[...path]/route";

const ctx = (path: string[]) => ({ params: Promise.resolve({ path }) });
const req = () => ({ headers: new Headers() }) as never;
const GOOD = ["tubi", "versions", "1", "sheets", "turn"];

function upstream(status: number, type: string, body: string | null = "PNGDATA") {
  return new Response(body, { status, headers: { "content-type": type } });
}

describe("GET /mascot-sheets", () => {
  let fetchSpy: MockInstance<typeof fetch>;
  beforeEach(() => {
    session.ok = true;
    fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue(upstream(200, "image/png"));
  });
  afterEach(() => vi.restoreAllMocks());

  it("401 without a session and never calls Flask", async () => {
    session.ok = false;
    const res = await GET(req(), ctx(GOOD));
    expect(res.status).toBe(401);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("forwards to the sheet route with the API token and passes the image through", async () => {
    const res = await GET(req(), ctx(GOOD));
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toBe("image/png");
    expect(await res.text()).toBe("PNGDATA");
    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toMatch(/\/mascots\/tubi\/versions\/1\/sheets\/turn$/);
    expect((init as RequestInit).headers).toEqual({ Authorization: "Bearer test-api-token" });
  });

  it("serves jpeg (builtin sheets)", async () => {
    fetchSpy.mockResolvedValue(upstream(200, "image/jpeg"));
    expect((await GET(req(), ctx(GOOD))).headers.get("content-type")).toBe("image/jpeg");
  });

  it.each([
    [["tubi", "versions", "1", "sheets", "evil"]],
    [["tubi", "versions", "x", "sheets", "turn"]],
    [["..", "versions", "1", "sheets", "turn"]],
    [["Tubi", "versions", "1", "sheets", "turn"]],
    [["tubi", "versions", "1", "sheets"]],
    [["tubi", "versions", "1", "sheets", "turn", "extra"]],
    [["tubi", "approve"]],
  ])("404 for %j before Flask is asked", async (path) => {
    const res = await GET(req(), ctx(path));
    expect(res.status).toBe(404);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("accepts an underscore in the id, like MASCOT_ID_RE", async () => {
    const res = await GET(req(), ctx(["my_tubi", "versions", "1", "sheets", "turn"]));
    expect(res.status).toBe(200);
    expect(String(fetchSpy.mock.calls[0][0])).toMatch(/\/mascots\/my_tubi\//);
    fetchSpy.mockClear();
    expect((await GET(req(), ctx(["_tubi", "versions", "1", "sheets", "turn"]))).status).toBe(404);
  });

  it("will not relay a non-image answer", async () => {
    fetchSpy.mockResolvedValue(upstream(200, "text/html", "<script>"));
    expect((await GET(req(), ctx(GOOD))).status).toBe(502);
  });

  it("passes a 404 on and turns a Flask 401 into a 502", async () => {
    fetchSpy.mockResolvedValue(upstream(404, "application/json", "{}"));
    expect((await GET(req(), ctx(GOOD))).status).toBe(404);
    fetchSpy.mockResolvedValue(upstream(401, "application/json", "{}"));
    expect((await GET(req(), ctx(GOOD))).status).toBe(502);
  });

  it("502 when Flask is unreachable", async () => {
    fetchSpy.mockRejectedValue(new Error("down"));
    expect((await GET(req(), ctx(GOOD))).status).toBe(502);
  });
});
