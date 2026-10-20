/**
 * GET /api/update-check (TMDEV-114): the dashboard server asks the API which
 * version is installed and which repo it comes from, then compares that with
 * GitHub's releases.
 *
 * Guarded here:
 *  1. No session → 401, and neither the API nor GitHub is called
 *  2. The API call carries the token and bypasses the Next.js Data Cache
 *  3. The development branch, an API with no `github_repo` (older than this
 *     feature) and an unreachable API all answer "no update" and never call GitHub
 *  4. The installed version is read on every request, so the banner goes away
 *     right after an upgrade even though GitHub's list is cached
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

const jsonSpy = vi.hoisted(() => vi.fn().mockReturnValue({ _mock: true }));
vi.mock("next/server", () => ({ NextResponse: { json: jsonSpy } }));

const session = vi.hoisted(() => ({ ok: true }));
vi.mock("@/lib/session", () => ({
  isAuthenticated: vi.fn(async () => session.ok),
  apiToken: vi.fn(() => "test-api-token"),
}));

import { dynamic, GET } from "@/app/api/update-check/route";
import { _resetReleaseCache } from "@/lib/updateCheck";

const req = {} as never;
const GITHUB = "https://api.github.com/";

function reply(body: unknown, ok = true) {
  return { ok, status: ok ? 200 : 500, json: async () => body } as Response;
}

/** Answers the API's /pipeline/status with `status`, and GitHub with `releases`. */
function stubFetch(status: unknown, releases: unknown = [{ tag_name: "v2.0.1", draft: false, prerelease: false }]) {
  const fetchMock = vi.fn(async (url: string) =>
    url.startsWith(GITHUB) ? reply(releases) : reply(status),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const githubCalls = (m: ReturnType<typeof vi.fn>) =>
  m.mock.calls.filter(([url]) => String(url).startsWith(GITHUB)).length;

const lastBody = () => jsonSpy.mock.calls.at(-1)?.[0];

describe("update-check route", () => {
  beforeEach(() => {
    jsonSpy.mockClear();
    session.ok = true;
    _resetReleaseCache();
    vi.unstubAllGlobals();
  });

  it("is never cached by Next.js", () => {
    expect(dynamic).toBe("force-dynamic");
  });

  it("answers 401 without a session and calls nothing", async () => {
    session.ok = false;
    const fetchMock = stubFetch({});
    await GET(req);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(jsonSpy).toHaveBeenCalledWith({ error: "unauthorized" }, expect.objectContaining({ status: 401 }));
  });

  it("reads the version and repo from the API with the token, then offers a newer release", async () => {
    const fetchMock = stubFetch({ version: "2.0.0", github_repo: "teja156/tubematic" });
    await GET(req);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toMatch(/\/pipeline\/status$/);
    expect(init.cache).toBe("no-store");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer test-api-token");
    expect(lastBody()).toMatchObject({
      available: true,
      current: "2.0.0",
      latest: "2.0.1",
      release_url: "https://github.com/teja156/tubematic/releases/tag/v2.0.1",
    });
  });

  it("never calls GitHub on the development branch", async () => {
    const fetchMock = stubFetch({ version: "develop", github_repo: "teja156/tubematic" });
    await GET(req);
    expect(githubCalls(fetchMock)).toBe(0);
    expect(lastBody()).toEqual({ available: false });
  });

  it("never calls GitHub when the API sends no repo (an API older than this feature)", async () => {
    const fetchMock = stubFetch({ version: "2.0.0" });
    await GET(req);
    expect(githubCalls(fetchMock)).toBe(0);
    expect(lastBody()).toEqual({ available: false });
  });

  it("never calls GitHub for a malformed repo", async () => {
    const fetchMock = stubFetch({ version: "2.0.0", github_repo: "../../evil" });
    await GET(req);
    expect(githubCalls(fetchMock)).toBe(0);
  });

  it("answers no update when the API is down or refuses", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("connection refused")));
    await GET(req);
    expect(lastBody()).toEqual({ available: false });

    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(reply({}, false)));
    await GET(req);
    expect(lastBody()).toEqual({ available: false });
  });

  it("answers no update when GitHub cannot be reached", async () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url.startsWith(GITHUB)) throw new Error("offline");
      return reply({ version: "2.0.0", github_repo: "teja156/tubematic" });
    }));
    await GET(req);
    expect(lastBody()).toEqual({ available: false });
  });

  it("re-reads the installed version on every request, so an upgrade clears the banner at once", async () => {
    const fetchMock = stubFetch({ version: "2.0.0", github_repo: "teja156/tubematic" });
    await GET(req);
    expect(lastBody()).toMatchObject({ available: true });

    fetchMock.mockImplementation(async (url: string) =>
      url.startsWith(GITHUB)
        ? reply([{ tag_name: "v2.0.1", draft: false, prerelease: false }])
        : reply({ version: "2.0.1", github_repo: "teja156/tubematic" }),
    );
    await GET(req);
    expect(lastBody()).toEqual({ available: false });
    expect(githubCalls(fetchMock)).toBe(1); // GitHub's list stayed cached
  });
});
